"""Append-only local SQLite workflow for public catalog candidates only."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

from .diff import MAX_DIFF_DEPTH, deterministic_diff
from .model import (
    Candidate,
    CandidateEvent,
    CandidateReview,
    CandidateState,
    CandidateValidationError,
    DiffEntry,
    RecordKind,
    ReviewDecision,
)

MAX_IDENTIFIER = 128
MAX_NOTE = 1000
MAX_STRING = 512
MAX_RECORD_BYTES = 65536
MAX_LIST = 50
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_CLASSES = {"administering_terms", "issuer_document", "network_rule", "merchant_terms", "regulatory_context", "discovery_only"}
_CONFIDENCE = {"high", "medium", "low"}
_REVIEW_TIERS = {"standard", "enhanced", "high_impact", "ambiguous"}
_BENEFIT_TYPES = {"reward_points", "conversion", "movie", "hotel", "food", "cashback", "voucher", "meet_and_greet", "lounge", "priority_pass", "other"}
_OPERATORS = {"equals", "in", "not_in", "gte", "lte", "between", "exists"}
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")
_DNS_HOST = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


class CandidateIntegrityError(RuntimeError):
    """Persisted candidate no longer matches its immutable release/content binding."""


def canonical_uuid(value: object, field: str) -> str:
    if not isinstance(value, str) or not _UUID.fullmatch(value):
        raise CandidateValidationError(f"{field} must be a canonical lowercase UUID")
    try:
        if str(uuid.UUID(value)) != value:
            raise CandidateValidationError(f"{field} must be a canonical lowercase UUID")
    except ValueError as exc:
        raise CandidateValidationError(f"{field} must be a canonical lowercase UUID") from exc
    return value


def validate_record(record_kind: RecordKind, record: Mapping[str, object]) -> str:
    if not isinstance(record, Mapping):
        raise CandidateValidationError("record must be an object")
    payload = dict(record)
    _validate_json(payload, 0)
    if record_kind is RecordKind.OFFERING:
        _validate_offering(payload)
    else:
        _validate_benefit(payload)
    rendered = _canonical_json(payload)
    if len(rendered.encode("utf-8")) > MAX_RECORD_BYTES:
        raise CandidateValidationError("record exceeds maximum size")
    return rendered


def _validate_offering(value: dict[str, Any]) -> None:
    required = {"id", "slug", "display_name", "issuer_id", "product_variant_id", "network_id", "market", "aliases"}
    optional = {"co_brand_id", "cohort_id", "effective_from", "effective_to"}
    _exact_keys(value, required, optional)
    canonical_uuid(value["id"], "offering.id")
    for key in required - {"id", "aliases"}:
        _string(value[key], key)
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value["slug"]):
        raise CandidateValidationError("offering.slug must be lowercase kebab-case")
    if not re.fullmatch(r"[A-Z]{2}", value["market"]):
        raise CandidateValidationError("offering.market must be an ISO country code")
    _string_list(value["aliases"], "aliases")
    _date_range(value)
    for key in {"co_brand_id", "cohort_id"} & value.keys():
        _string(value[key], key)


def _validate_benefit(value: dict[str, Any]) -> None:
    required = {"id", "offering_id", "benefit_type", "title", "status", "review_tier", "eligibility", "evidence", "conflicts_with"}
    optional = {"effective_from", "effective_to", "allowance"}
    _exact_keys(value, required, optional)
    canonical_uuid(value["id"], "benefit.id")
    canonical_uuid(value["offering_id"], "benefit.offering_id")
    if value["benefit_type"] not in _BENEFIT_TYPES or value["status"] not in {"active", "historical", "needs_review", "superseded"}:
        raise CandidateValidationError("benefit has an unsupported type or status")
    if value["review_tier"] not in _REVIEW_TIERS:
        raise CandidateValidationError("benefit has an unsupported review_tier")
    _string(value["title"], "title")
    _date_range(value)
    _string_list(value["conflicts_with"], "conflicts_with", uuid_items=True)
    eligibility = value["eligibility"]
    if not isinstance(eligibility, list) or len(eligibility) > MAX_LIST:
        raise CandidateValidationError("eligibility must be a bounded list")
    for predicate in eligibility:
        if not isinstance(predicate, dict):
            raise CandidateValidationError("eligibility entries must be objects")
        _exact_keys(predicate, {"field", "operator"}, {"value"})
        _string(predicate["field"], "eligibility.field")
        if predicate["operator"] not in _OPERATORS or (predicate["operator"] != "exists" and "value" not in predicate):
            raise CandidateValidationError("invalid eligibility predicate")
    evidence = value["evidence"]
    if not isinstance(evidence, list) or not evidence or len(evidence) > MAX_LIST:
        raise CandidateValidationError("evidence must be a non-empty bounded list")
    for item in evidence:
        if not isinstance(item, dict):
            raise CandidateValidationError("evidence entries must be objects")
        _validate_evidence(item)
    if "allowance" in value and not isinstance(value["allowance"], dict):
        raise CandidateValidationError("allowance must be an object")


def _validate_evidence(value: dict[str, Any]) -> None:
    required = {"id", "source_policy_class", "url", "content_sha256", "retrieved_at", "confidence"}
    optional = {"effective_from", "effective_to"}
    _exact_keys(value, required, optional)
    canonical_uuid(value["id"], "evidence.id")
    if value["source_policy_class"] not in _SOURCE_CLASSES or value["confidence"] not in _CONFIDENCE:
        raise CandidateValidationError("evidence has an unsupported source class or confidence")
    _anonymous_https(value["url"], "evidence.url")
    if not isinstance(value["content_sha256"], str) or not _SHA256.fullmatch(value["content_sha256"]):
        raise CandidateValidationError("evidence.content_sha256 must be a lowercase SHA-256 digest")
    _timestamp(value["retrieved_at"], "evidence.retrieved_at")
    _date_range(value)


def _validate_json(value: object, depth: int) -> None:
    if depth > MAX_DIFF_DEPTH:
        raise CandidateValidationError("record exceeds maximum nesting depth")
    if value is None or isinstance(value, bool | int):
        return
    if isinstance(value, float):
        raise CandidateValidationError("record floats are not supported")
    if isinstance(value, str):
        if len(value) > MAX_STRING:
            raise CandidateValidationError("record string exceeds maximum length")
        return
    if isinstance(value, list):
        if len(value) > MAX_LIST:
            raise CandidateValidationError("record list exceeds maximum length")
        for item in value:
            _validate_json(item, depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > MAX_LIST:
            raise CandidateValidationError("record object exceeds maximum fields")
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > MAX_IDENTIFIER:
                raise CandidateValidationError("record key is invalid")
            _validate_json(item, depth + 1)
        return
    raise CandidateValidationError("record contains a non-JSON value")


def _exact_keys(value: dict[str, Any], required: set[str], optional: set[str]) -> None:
    missing = required - value.keys()
    unknown = value.keys() - required - optional
    if missing or unknown:
        raise CandidateValidationError("record has missing or unknown fields")


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_STRING:
        raise CandidateValidationError(f"{field} must be a bounded non-empty string")
    return value


def _string_list(value: object, field: str, *, uuid_items: bool = False) -> None:
    if not isinstance(value, list) or len(value) > MAX_LIST:
        raise CandidateValidationError(f"{field} must be a bounded list")
    items = [_string(item, field) for item in value]
    if len(items) != len(set(items)):
        raise CandidateValidationError(f"{field} must not contain duplicates")
    if uuid_items:
        for item in items:
            canonical_uuid(item, field)


def _date_range(value: dict[str, Any]) -> None:
    start = _date(value["effective_from"], "effective_from") if "effective_from" in value else None
    end = _date(value["effective_to"], "effective_to") if "effective_to" in value else None
    if start is not None and end is not None and end < start:
        raise CandidateValidationError("effective_to precedes effective_from")


def _date(value: object, field: str) -> date | None:
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        raise CandidateValidationError(f"{field} must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise CandidateValidationError(f"{field} must be an ISO date") from exc


def _timestamp(value: object, field: str) -> None:
    timestamp = _string(value, field)
    if not _TIMESTAMP.fullmatch(timestamp):
        raise CandidateValidationError(f"{field} must be an RFC3339 timestamp with UTC or offset")
    try:
        parsed = datetime.fromisoformat(timestamp[:-1] + "+00:00" if timestamp.endswith("Z") else timestamp)
    except ValueError as exc:
        raise CandidateValidationError(f"{field} must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CandidateValidationError(f"{field} must include a timezone")


def _anonymous_https(value: object, field: str) -> None:
    """Evidence may retain query/fragment provenance, but must name an anonymous DNS HTTPS origin."""
    url = _string(value, field)
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise CandidateValidationError(f"{field} must be an anonymous HTTPS URL")
    try:
        port = parsed.port
    except ValueError as exc:
        raise CandidateValidationError(f"{field} has an invalid HTTPS port") from exc
    if port is not None and not 1 <= port <= 65535:
        raise CandidateValidationError(f"{field} has an invalid HTTPS port")
    host = parsed.hostname
    if host is None:
        raise CandidateValidationError(f"{field} must have a valid DNS host")
    try:
        canonical_host = host.encode("idna").decode("ascii").casefold()
    except UnicodeError as exc:
        raise CandidateValidationError(f"{field} must have a valid DNS host") from exc
    if not _DNS_HOST.fullmatch(canonical_host):
        raise CandidateValidationError(f"{field} must have a valid DNS host")


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


class CandidateStore:
    """A release-bound store. It creates review records but never activates catalog data."""

    def __init__(self, path: str | Path, base_release_id: str) -> None:
        self._path = Path(path)
        self._base_release_id = canonical_uuid(base_release_id, "base_release_id")
        self._initialize()

    @property
    def base_release_id(self) -> str:
        return self._base_release_id

    def propose(
        self,
        *,
        record_kind: RecordKind,
        target_record_id: str,
        author_id: str,
        review_tier: str,
        base_record: Mapping[str, object],
        payload: Mapping[str, object],
    ) -> Candidate:
        if not isinstance(record_kind, RecordKind):
            raise CandidateValidationError("record_kind is unsupported")
        target = canonical_uuid(target_record_id, "target_record_id")
        author = _bounded_identifier(author_id, "author_id")
        if review_tier not in _REVIEW_TIERS:
            raise CandidateValidationError("unsupported review_tier")
        base_json = validate_record(record_kind, base_record)
        payload_json = validate_record(record_kind, payload)
        if json.loads(base_json)["id"] != target or json.loads(payload_json)["id"] != target:
            raise CandidateValidationError("base and proposed records must match target_record_id")
        deterministic_diff(base_json, payload_json)
        candidate_id = str(uuid.uuid4())
        content_hash = _content_hash(self._base_release_id, record_kind, target, author, review_tier, base_json, payload_json)
        created_at = _now()
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO candidates VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (candidate_id, self._base_release_id, record_kind.value, target, author, review_tier, base_json, payload_json, content_hash, CandidateState.NEEDS_REVIEW.value, created_at),
            )
            _event(connection, candidate_id, "proposed", "candidate proposed", created_at)
        return self.get_candidate(candidate_id)

    def review(
        self,
        candidate_id: str,
        *,
        reviewer_kind: str,
        reviewer_id: str,
        decision: ReviewDecision,
        note: str | None = None,
    ) -> Candidate:
        candidate_id = canonical_uuid(candidate_id, "candidate_id")
        if reviewer_kind != "human":
            raise CandidateValidationError("reviewer_kind must be exactly human")
        if not isinstance(decision, ReviewDecision):
            raise CandidateValidationError("review decision is unsupported")
        reviewer = _bounded_identifier(reviewer_id, "reviewer_id")
        if note is not None and (not isinstance(note, str) or len(note) > MAX_NOTE):
            raise CandidateValidationError("review note exceeds maximum length")
        integrity_error: str | None = None
        with self._transaction() as connection:
            row = _candidate_row(connection, candidate_id)
            integrity_error = _integrity_issue(row, self._base_release_id)
            if integrity_error is not None:
                _mark_stale(connection, candidate_id, integrity_error)
            else:
                candidate = _candidate_from_row(row)
                if candidate.state is not CandidateState.NEEDS_REVIEW:
                    raise CandidateValidationError("candidate is in a terminal state")
                if reviewer == candidate.author_id:
                    raise CandidateValidationError("author cannot review own candidate")
                duplicate = connection.execute("SELECT 1 FROM reviews WHERE candidate_id = ? AND reviewer_id = ?", (candidate_id, reviewer)).fetchone()
                if duplicate is not None:
                    raise CandidateValidationError("reviewer has already reviewed this candidate")
                now = _now()
                connection.execute("INSERT INTO reviews(candidate_id, reviewer_kind, reviewer_id, decision, note, created_at) VALUES (?, ?, ?, ?, ?, ?)", (candidate_id, reviewer_kind, reviewer, decision.value, note, now))
                _event(connection, candidate_id, "reviewed", decision.value, now)
                if decision is ReviewDecision.REJECT:
                    _set_state(connection, candidate_id, CandidateState.REJECTED, now)
                elif decision is ReviewDecision.CHANGES_REQUESTED:
                    _set_state(connection, candidate_id, CandidateState.CHANGES_REQUESTED, now)
                elif _approval_count(connection, candidate_id) >= _required_approvals(candidate.review_tier):
                    _set_state(connection, candidate_id, CandidateState.APPROVED, now)
        if integrity_error is not None:
            raise CandidateIntegrityError(integrity_error)
        return self.get_candidate(candidate_id)

    def get_candidate(self, candidate_id: str) -> Candidate:
        candidate_id = canonical_uuid(candidate_id, "candidate_id")
        integrity_error: str | None = None
        result: Candidate | None = None
        with self._transaction() as connection:
            row = _candidate_row(connection, candidate_id)
            integrity_error = _integrity_issue(row, self._base_release_id)
            if integrity_error is not None:
                _mark_stale(connection, candidate_id, integrity_error)
            else:
                result = _candidate_from_row(row)
        if integrity_error is not None:
            raise CandidateIntegrityError(integrity_error)
        assert result is not None
        return result

    def diff(self, candidate_id: str) -> tuple[DiffEntry, ...]:
        candidate = self.get_candidate(candidate_id)
        return deterministic_diff(candidate.base_record_json, candidate.payload_json)

    def list_candidates(self, state: CandidateState | None = None) -> tuple[Candidate, ...]:
        query = "SELECT id FROM candidates" + (" WHERE state = ?" if state is not None else "") + " ORDER BY created_at, id"
        with self._connection() as connection:
            rows = connection.execute(query, (() if state is None else (state.value,))).fetchall()
        return tuple(self.get_candidate(row["id"]) for row in rows)

    def reviews(self, candidate_id: str) -> tuple[CandidateReview, ...]:
        self.get_candidate(candidate_id)
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM reviews WHERE candidate_id = ? ORDER BY id", (candidate_id,)).fetchall()
        return tuple(_review_from_row(row) for row in rows)

    def events(self, candidate_id: str) -> tuple[CandidateEvent, ...]:
        self.get_candidate(candidate_id)
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM events WHERE candidate_id = ? ORDER BY id", (candidate_id,)).fetchall()
        return tuple(CandidateEvent(row["id"], row["candidate_id"], row["event_type"], row["detail"], _parse_timestamp(row["created_at"], "event created_at")) for row in rows)

    def stats(self) -> dict[CandidateState, int]:
        candidates = self.list_candidates()
        return {state: sum(candidate.state is state for candidate in candidates) for state in CandidateState}

    def _initialize(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # sqlite3.executescript commits implicitly; individual DDL statements keep
        # schema creation and the release binding in this explicit transaction.
        with self._transaction() as connection:
            for statement in _DDL:
                connection.execute(statement)
            row = connection.execute("SELECT value FROM metadata WHERE key = 'base_release_id'").fetchone()
            if row is None:
                connection.execute("INSERT INTO metadata VALUES ('base_release_id', ?)", (self._base_release_id,))
            elif row["value"] != self._base_release_id:
                raise CandidateIntegrityError("candidate store is bound to a different base_release_id")

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except Exception:
                connection.rollback()
                raise
            else:
                connection.commit()


def _candidate_row(connection: sqlite3.Connection, candidate_id: str) -> sqlite3.Row:
    row = connection.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,)).fetchone()
    if row is None:
        raise CandidateValidationError("candidate does not exist")
    return cast(sqlite3.Row, row)


def _candidate_from_row(row: sqlite3.Row) -> Candidate:
    return Candidate(row["id"], row["base_release_id"], _record_kind_from_db(row["record_kind"]), row["target_record_id"], row["author_id"], row["review_tier"], row["base_record_json"], row["payload_json"], row["content_hash"], _candidate_state_from_db(row["state"]), _parse_timestamp(row["created_at"], "candidate created_at"))


def _review_from_row(row: sqlite3.Row) -> CandidateReview:
    return CandidateReview(row["id"], row["candidate_id"], row["reviewer_kind"], row["reviewer_id"], _review_decision_from_db(row["decision"]), row["note"], _parse_timestamp(row["created_at"], "review created_at"))


def _integrity_issue(row: sqlite3.Row, base_release_id: str) -> str | None:
    if row["base_release_id"] != base_release_id:
        return "candidate base_release_id drift detected"
    try:
        record_kind = _record_kind_from_db(row["record_kind"])
        _candidate_state_from_db(row["state"])
        _parse_timestamp(row["created_at"], "candidate created_at")
    except CandidateIntegrityError as exc:
        return str(exc)
    expected = _content_hash(row["base_release_id"], record_kind, row["target_record_id"], row["author_id"], row["review_tier"], row["base_record_json"], row["payload_json"])
    return "candidate content hash mismatch detected" if expected != row["content_hash"] else None


def _content_hash(base_release_id: str, record_kind: RecordKind, target_record_id: str, author_id: str, review_tier: str, base_json: str, payload_json: str) -> str:
    material = _canonical_json({"author_id": author_id, "base_record_json": base_json, "base_release_id": base_release_id, "payload_json": payload_json, "record_kind": record_kind.value, "review_tier": review_tier, "target_record_id": target_record_id})
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _mark_stale(connection: sqlite3.Connection, candidate_id: str, reason: str) -> None:
    state = connection.execute("SELECT state FROM candidates WHERE id = ?", (candidate_id,)).fetchone()[0]
    if state == CandidateState.STALE.value:
        return
    now = _now()
    connection.execute("UPDATE candidates SET state = ? WHERE id = ?", (CandidateState.STALE.value, candidate_id))
    _event(connection, candidate_id, "staled", reason, now)


def _set_state(connection: sqlite3.Connection, candidate_id: str, state: CandidateState, created_at: str) -> None:
    connection.execute("UPDATE candidates SET state = ? WHERE id = ?", (state.value, candidate_id))
    _event(connection, candidate_id, "state_changed", state.value, created_at)


def _event(connection: sqlite3.Connection, candidate_id: str, event_type: str, detail: str, created_at: str) -> None:
    connection.execute("INSERT INTO events(candidate_id, event_type, detail, created_at) VALUES (?, ?, ?, ?)", (candidate_id, event_type, detail, created_at))


def _approval_count(connection: sqlite3.Connection, candidate_id: str) -> int:
    return int(connection.execute("SELECT COUNT(*) FROM reviews WHERE candidate_id = ? AND decision = ?", (candidate_id, ReviewDecision.APPROVE.value)).fetchone()[0])


def _required_approvals(review_tier: str) -> int:
    return 1 if review_tier == "standard" else 2


def _bounded_identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_IDENTIFIER:
        raise CandidateValidationError(f"{field} must be a bounded non-empty identifier")
    return value


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _record_kind_from_db(value: object) -> RecordKind:
    if not isinstance(value, str):
        raise CandidateIntegrityError("candidate record_kind is invalid")
    try:
        return RecordKind(value)
    except (TypeError, ValueError) as exc:
        raise CandidateIntegrityError("candidate record_kind is invalid") from exc


def _candidate_state_from_db(value: object) -> CandidateState:
    if not isinstance(value, str):
        raise CandidateIntegrityError("candidate state is invalid")
    try:
        return CandidateState(value)
    except (TypeError, ValueError) as exc:
        raise CandidateIntegrityError("candidate state is invalid") from exc


def _review_decision_from_db(value: object) -> ReviewDecision:
    if not isinstance(value, str):
        raise CandidateIntegrityError("review decision is invalid")
    try:
        return ReviewDecision(value)
    except (TypeError, ValueError) as exc:
        raise CandidateIntegrityError("review decision is invalid") from exc


def _parse_timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise CandidateIntegrityError(f"{field} is invalid")
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise CandidateIntegrityError(f"{field} is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CandidateIntegrityError(f"{field} is invalid")
    return parsed


_DDL = (
    "CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
    """CREATE TABLE IF NOT EXISTS candidates (
        id TEXT PRIMARY KEY, base_release_id TEXT NOT NULL, record_kind TEXT NOT NULL, target_record_id TEXT NOT NULL,
        author_id TEXT NOT NULL, review_tier TEXT NOT NULL, base_record_json TEXT NOT NULL, payload_json TEXT NOT NULL,
        content_hash TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id TEXT NOT NULL, reviewer_kind TEXT NOT NULL,
        reviewer_id TEXT NOT NULL, decision TEXT NOT NULL, note TEXT, created_at TEXT NOT NULL,
        UNIQUE(candidate_id, reviewer_id),
        FOREIGN KEY(candidate_id) REFERENCES candidates(id) ON DELETE RESTRICT
    )""",
    """CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_id TEXT NOT NULL, event_type TEXT NOT NULL,
        detail TEXT NOT NULL, created_at TEXT NOT NULL,
        FOREIGN KEY(candidate_id) REFERENCES candidates(id) ON DELETE RESTRICT
    )""",
)
