"""Canonical, lossless public benefit/evidence graph.

This module is deliberately transport- and provider-neutral.  It stores hashes
and coordinates, never source text, and performs no retrieval or model work.
The graph is the compatibility boundary for catalog, candidate, provider DTO,
API, migration fixtures, and release snapshots.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from types import MappingProxyType
from typing import Any, Final, cast

GRAPH_SCHEMA_VERSION: Final = "1.0.0"
_HASH = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class EvidenceGraphError(ValueError):
    """A graph is malformed, unsupported, or cannot be promoted safely."""


def _freeze(value: Any) -> Any:
    """Freeze only public JSON values; never retain caller-owned mutables."""
    allowed_types = {type(None), bool, int, str, float, dict, list, tuple, set, frozenset}
    if type(value) not in allowed_types and not isinstance(value, (date, datetime)):
        raise EvidenceGraphError("graph values must be JSON-safe public data")
    if type(value) is float:
        raise EvidenceGraphError("graph values must not contain floats")
    if isinstance(value, Mapping):
        if type(value) is not dict:
            raise EvidenceGraphError("graph mappings must be plain objects")
        keys = list(value)
        if any(type(k) is not str or not k.isascii() or not k or k != k.strip() for k in keys):
            raise EvidenceGraphError("graph object keys must be non-empty ASCII strings")
        if len(keys) != len(set(keys)):
            raise EvidenceGraphError("graph object keys must be unique")
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, tuple):
        return tuple(_freeze(v) for v in value)
    if isinstance(value, set | frozenset):
        raise EvidenceGraphError("unordered graph values are not permitted")
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _thaw(v) for k, v in value.items()}
    if isinstance(value, (tuple, list, frozenset)):
        return [_thaw(v) for v in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if dataclasses.is_dataclass(value):
        return {field.name: _thaw(getattr(value, field.name)) for field in dataclasses.fields(value)}
    return value


def canonical_json(value: Any) -> str:
    """Return the stable UTF-8 JSON representation used for graph hashes."""
    return json.dumps(_thaw(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _check_id(value: str, field: str) -> None:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise EvidenceGraphError(f"{field} must be a stable bounded identifier")


def _check_hash(value: str, field: str) -> None:
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        raise EvidenceGraphError(f"{field} must be a lowercase SHA-256 hash")


def _check_version(value: int, field: str = "version") -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise EvidenceGraphError(f"{field} must be a positive integer")


@dataclass(frozen=True)
class OfferingNode:
    id: str
    version: int
    fields: Mapping[str, Any]

    def __post_init__(self) -> None:
        _check_id(self.id, "offering.id")
        _check_version(self.version, "offering.version")
        object.__setattr__(self, "fields", _freeze(self.fields))


@dataclass(frozen=True)
class RuleNode:
    id: str
    version: int
    offering_id: str
    fields: Mapping[str, Any]
    field_citations: Mapping[str, tuple[str, ...]]
    supersedes: str | None = None
    conflicts_with: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _check_id(self.id, "rule.id")
        _check_version(self.version, "rule.version")
        _check_id(self.offering_id, "rule.offering_id")
        object.__setattr__(self, "fields", _freeze(self.fields))
        if type(self.field_citations) is not dict or any(
            type(key) is not str
            or type(value) is not tuple
            or not value
            or any(type(span_id) is not str for span_id in value)
            for key, value in self.field_citations.items()
        ):
            raise EvidenceGraphError("rule.field_citations must be an ordered object of span IDs")
        object.__setattr__(self, "field_citations", _freeze(self.field_citations))
        object.__setattr__(self, "conflicts_with", tuple(self.conflicts_with))


@dataclass(frozen=True)
class SourceDocumentVersion:
    id: str
    version: int
    admission_id: str
    canonical_url: str
    owner_id: str
    tier: int
    scope: str
    content_sha256: str
    normalized_chunk_sha256: str
    retrieved_at: datetime
    effective_from: date | None = None
    effective_to: date | None = None
    validators: Mapping[str, str] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        _check_id(self.id, "source_document.id")
        _check_version(self.version, "source_document.version")
        _check_id(self.admission_id, "source_document.admission_id")
        if type(self.canonical_url) is not str or not re.fullmatch(r"https://[a-z0-9.-]+(?:/[^?#]*)?", self.canonical_url):
            raise EvidenceGraphError("source_document.canonical_url must be canonical anonymous HTTPS")
        if not 1 <= self.tier <= 6:
            raise EvidenceGraphError("source_document.tier must be between 1 and 6")
        _check_hash(self.content_sha256, "source_document.content_sha256")
        _check_hash(self.normalized_chunk_sha256, "source_document.normalized_chunk_sha256")
        if type(self.scope) is not str or not self.scope or not self.scope.isascii():
            raise EvidenceGraphError("source_document.scope must be exact ASCII metadata")
        if type(self.owner_id) is not str or not self.owner_id:
            raise EvidenceGraphError("source_document.owner_id is required")
        if not _is_date(self.effective_from) or not _is_date(self.effective_to):
            raise EvidenceGraphError("source document effective dates are invalid")
        if self.effective_from and self.effective_to and self.effective_from > self.effective_to:
            raise EvidenceGraphError("source document effective range is invalid")
        object.__setattr__(self, "validators", _freeze(self.validators))


@dataclass(frozen=True)
class SourceAdmissionNode:
    id: str
    version: int
    canonical_url: str
    scope: str
    effective_from: date
    effective_to: date | None
    state: str
    terms_sha256: str

    def __post_init__(self) -> None:
        _check_id(self.id, "source_admission.id")
        _check_version(self.version, "source_admission.version")
        _check_hash(self.terms_sha256, "source_admission.terms_sha256")
        if type(self.canonical_url) is not str or not re.fullmatch(r"https://[a-z0-9.-]+(?:/[^?#]*)?", self.canonical_url):
            raise EvidenceGraphError("source_admission.canonical_url is invalid")
        if type(self.scope) is not str or not self.scope.isascii() or not self.scope:
            raise EvidenceGraphError("source_admission.scope is invalid")
        if self.state not in {"candidate", "approved", "revoked", "expired"}:
            raise EvidenceGraphError("source_admission.state is invalid")
        if not _is_date(self.effective_from) or not _is_date(self.effective_to):
            raise EvidenceGraphError("source admission effective dates are invalid")
        if self.effective_to is not None and self.effective_from > self.effective_to:
            raise EvidenceGraphError("source_admission effective range is invalid")


@dataclass(frozen=True)
class ReviewDecisionNode:
    id: str
    version: int
    target_id: str
    decision: str
    reviewer_id: str
    decided_at: datetime

    def __post_init__(self) -> None:
        _check_id(self.id, "review.id")
        _check_version(self.version, "review.version")
        _check_id(self.target_id, "review.target_id")
        if self.decision not in {"approve", "reject", "changes_requested"} or not self.reviewer_id:
            raise EvidenceGraphError("review decision is invalid")


@dataclass(frozen=True)
class EffectiveStateNode:
    id: str
    version: int
    target_id: str
    state: str
    effective_from: date
    effective_to: date | None

    def __post_init__(self) -> None:
        _check_id(self.id, "effective_state.id")
        _check_version(self.version, "effective_state.version")
        _check_id(self.target_id, "effective_state.target_id")
        if self.state not in {"active", "historical", "needs_review", "superseded"}:
            raise EvidenceGraphError("effective state is invalid")
        if self.effective_to is not None and self.effective_from > self.effective_to:
            raise EvidenceGraphError("effective state range is invalid")


@dataclass(frozen=True)
class ObservationNode:
    id: str
    version: int
    source_document_id: str
    source_document_version: int
    result: str
    adapter_name: str
    adapter_version: str
    extraction_version: str
    redaction_version: str
    content_sha256: str
    normalized_chunk_sha256: str

    def __post_init__(self) -> None:
        _check_id(self.id, "observation.id")
        _check_version(self.version, "observation.version")
        _check_id(self.source_document_id, "observation.source_document_id")
        _check_version(self.source_document_version, "observation.source_document_version")
        _check_hash(self.content_sha256, "observation.content_sha256")
        _check_hash(self.normalized_chunk_sha256, "observation.normalized_chunk_sha256")
        if self.result not in {"matched", "not_found", "blocked", "ambiguous"}:
            raise EvidenceGraphError("observation.result is unsupported")
        for field in (self.adapter_name, self.adapter_version, self.extraction_version, self.redaction_version):
            if type(field) is not str or not field or not field.isascii():
                raise EvidenceGraphError("observation processing versions are invalid")


@dataclass(frozen=True)
class ExtractionSpan:
    id: str
    version: int
    observation_id: str
    source_document_id: str
    source_document_version: int
    content_sha256: str
    normalized_chunk_sha256: str
    start_offset: int
    end_offset: int
    anchor_start: str
    anchor_end: str

    def __post_init__(self) -> None:
        _check_id(self.id, "span.id")
        _check_version(self.version, "span.version")
        _check_id(self.observation_id, "span.observation_id")
        _check_id(self.source_document_id, "span.source_document_id")
        _check_version(self.source_document_version, "span.source_document_version")
        _check_hash(self.content_sha256, "span.content_sha256")
        _check_hash(self.normalized_chunk_sha256, "span.normalized_chunk_sha256")
        if (isinstance(self.start_offset, bool) or isinstance(self.end_offset, bool)
                or not isinstance(self.start_offset, int) or not isinstance(self.end_offset, int)
                or self.start_offset < 0 or self.end_offset <= self.start_offset):
            raise EvidenceGraphError("span offsets must be a non-empty ordered range")
        if not self.anchor_start or not self.anchor_end:
            raise EvidenceGraphError("span anchors are required")


@dataclass(frozen=True)
class AssertionNode:
    id: str
    version: int
    rule_id: str
    source_document_id: str
    source_document_version: int
    observation_id: str
    span_ids: tuple[str, ...]
    field_citations: Mapping[str, tuple[str, ...]]
    review_state: str

    def __post_init__(self) -> None:
        _check_id(self.id, "assertion.id")
        _check_version(self.version, "assertion.version")
        for name, value in (("rule_id", self.rule_id), ("source_document_id", self.source_document_id), ("observation_id", self.observation_id)):
            _check_id(value, f"assertion.{name}")
        if not self.span_ids:
            raise EvidenceGraphError("assertion requires exact extraction spans")
        object.__setattr__(self, "span_ids", tuple(self.span_ids))
        if type(self.field_citations) is not dict or any(
            type(key) is not str
            or type(value) is not tuple
            or not value
            or any(type(span_id) is not str for span_id in value)
            for key, value in self.field_citations.items()
        ):
            raise EvidenceGraphError("assertion.field_citations must be an ordered object of span IDs")
        object.__setattr__(self, "field_citations", _freeze(self.field_citations))
        if self.review_state not in {"needs_review", "approved", "rejected", "superseded"}:
            raise EvidenceGraphError("assertion.review_state is unsupported")


@dataclass(frozen=True)
class LineageEdge:
    id: str
    version: int
    kind: str
    from_id: str
    to_id: str

    def __post_init__(self) -> None:
        _check_id(self.id, "lineage.id")
        _check_version(self.version, "lineage.version")
        _check_id(self.from_id, "lineage.from_id")
        _check_id(self.to_id, "lineage.to_id")
        if self.from_id == self.to_id:
            raise EvidenceGraphError("lineage cannot self-reference")


@dataclass(frozen=True)
class CandidateNode:
    id: str
    version: int
    target_rule_id: str
    payload: Mapping[str, Any]
    assertion_ids: tuple[str, ...]
    revalidated_document_id: str | None
    revalidated_document_version: int | None
    revalidated_at: datetime | None

    def __post_init__(self) -> None:
        _check_id(self.id, "candidate.id")
        _check_version(self.version, "candidate.version")
        _check_id(self.target_rule_id, "candidate.target_rule_id")
        if not self.assertion_ids:
            raise EvidenceGraphError("candidate requires evidence assertions")
        object.__setattr__(self, "payload", _freeze(self.payload))
        object.__setattr__(self, "assertion_ids", tuple(self.assertion_ids))
        if (self.revalidated_document_id is None) != (self.revalidated_document_version is None):
            raise EvidenceGraphError("candidate revalidation document ID and version must be paired")
        if self.revalidated_at is not None and self.revalidated_document_id is None:
            raise EvidenceGraphError("candidate revalidation timestamp is not bound")


@dataclass(frozen=True)
class DerivationNode:
    """A deterministic, hash-bound value derived from admitted evidence spans."""

    id: str
    version: int
    rule_id: str
    field: str
    algorithm: str
    input_span_ids: tuple[str, ...]
    value_sha256: str

    def __post_init__(self) -> None:
        _check_id(self.id, "derivation.id")
        _check_version(self.version, "derivation.version")
        _check_id(self.rule_id, "derivation.rule_id")
        if type(self.field) is not str or not self.field:
            raise EvidenceGraphError("derivation.field is invalid")
        if self.algorithm != "canonical-json-sha256-v1":
            raise EvidenceGraphError("derivation algorithm is unsupported")
        if not self.input_span_ids:
            raise EvidenceGraphError("derivation requires exact evidence spans")
        object.__setattr__(self, "input_span_ids", tuple(self.input_span_ids))
        _check_hash(self.value_sha256, "derivation.value_sha256")


@dataclass(frozen=True)
class CanonicalEvidenceGraph:
    schema_version: str
    graph_id: str
    version: int
    offerings: tuple[OfferingNode, ...] = ()
    rules: tuple[RuleNode, ...] = ()
    source_documents: tuple[SourceDocumentVersion, ...] = ()
    observations: tuple[ObservationNode, ...] = ()
    spans: tuple[ExtractionSpan, ...] = ()
    assertions: tuple[AssertionNode, ...] = ()
    candidates: tuple[CandidateNode, ...] = ()
    lineage: tuple[LineageEdge, ...] = ()
    source_admissions: tuple[SourceAdmissionNode, ...] = ()
    review_decisions: tuple[ReviewDecisionNode, ...] = ()
    effective_states: tuple[EffectiveStateNode, ...] = ()
    derivations: tuple[DerivationNode, ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != GRAPH_SCHEMA_VERSION:
            raise EvidenceGraphError(f"unsupported graph schema version: {self.schema_version}")
        _check_id(self.graph_id, "graph_id")
        _check_version(self.version, "graph.version")
        for name in ("offerings", "rules", "source_documents", "observations", "spans", "assertions", "candidates", "derivations", "lineage", "source_admissions", "review_decisions", "effective_states"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        self._validate_references()

    def _validate_references(self) -> None:
        ids: dict[str, set[str]] = {}
        for name in ("offerings", "rules", "source_documents", "observations", "spans", "assertions", "candidates", "derivations", "lineage"):
            nodes = getattr(self, name)
            values = {node.id for node in nodes}
            if len(values) != len(nodes):
                raise EvidenceGraphError(f"duplicate IDs in {name}")
            ids[name] = values
        for name in ("source_admissions", "review_decisions", "effective_states"):
            nodes = getattr(self, name)
            values = {node.id for node in nodes}
            if len(values) != len(nodes):
                raise EvidenceGraphError(f"duplicate IDs in {name}")
            ids[name] = values
        for rule in self.rules:
            if rule.offering_id not in ids["offerings"]:
                raise EvidenceGraphError("rule references unknown offering")
            if any(span not in ids["spans"] for span_ids in rule.field_citations.values() for span in span_ids):
                raise EvidenceGraphError("rule citation references unknown span")
        for span in self.spans:
            if span.observation_id not in ids["observations"] or span.source_document_id not in ids["source_documents"]:
                raise EvidenceGraphError("span references unknown evidence node")
        for observation in self.observations:
            document = next((item for item in self.source_documents if item.id == observation.source_document_id), None)
            if document is None or observation.source_document_version != document.version or (observation.content_sha256, observation.normalized_chunk_sha256) != (document.content_sha256, document.normalized_chunk_sha256):
                raise EvidenceGraphError("observation references unknown source document")
        admissions = {item.id: item for item in self.source_admissions}
        if self.source_documents and not admissions:
            raise EvidenceGraphError("source documents require source admissions")
        for document in self.source_documents:
            if document.admission_id not in admissions:
                raise EvidenceGraphError("document references an unknown source admission")
            admission = admissions.get(document.admission_id)
            if admission is None or (document.canonical_url, document.scope) != (admission.canonical_url, admission.scope):
                raise EvidenceGraphError("document source URL or scope differs from admission")
            if admission.state not in {"candidate", "approved"}:
                raise EvidenceGraphError("document source admission is not usable")
        for assertion in self.assertions:
            if (assertion.rule_id not in ids["rules"] or assertion.observation_id not in ids["observations"]
                    or assertion.source_document_id not in ids["source_documents"] or any(span not in ids["spans"] for span in assertion.span_ids)):
                raise EvidenceGraphError("assertion references unknown graph node")
            document = next(item for item in self.source_documents if item.id == assertion.source_document_id)
            observation = next(item for item in self.observations if item.id == assertion.observation_id)
            if document.version != assertion.source_document_version or document.tier == 6:
                raise EvidenceGraphError("assertion must bind an admitted official source document version")
            if (observation.source_document_id, observation.source_document_version) != (
                assertion.source_document_id,
                assertion.source_document_version,
            ):
                raise EvidenceGraphError("assertion observation is not the exact source document version")
            for span_id in assertion.span_ids:
                span = next(item for item in self.spans if item.id == span_id)
                if (span.source_document_id, span.source_document_version, span.content_sha256, span.normalized_chunk_sha256) != (
                    document.id, document.version, document.content_sha256, document.normalized_chunk_sha256
                ):
                    raise EvidenceGraphError("assertion span is not bound to the exact source document hashes")
                if span.observation_id != assertion.observation_id or (observation.content_sha256, observation.normalized_chunk_sha256) != (span.content_sha256, span.normalized_chunk_sha256):
                    raise EvidenceGraphError("assertion span is not bound to its observation")
            for field, citations in assertion.field_citations.items():
                if type(field) is not str or not isinstance(citations, tuple) or not citations or any(span_id not in assertion.span_ids for span_id in citations):
                    raise EvidenceGraphError("assertion field citation is not assertion-owned")
            rule = next(item for item in self.rules if item.id == assertion.rule_id)
            if set(assertion.field_citations) != set(rule.field_citations):
                raise EvidenceGraphError("assertion citations do not exactly cover the rule fields")
        for candidate in self.candidates:
            if candidate.target_rule_id not in ids["rules"] or any(item not in ids["assertions"] for item in candidate.assertion_ids):
                raise EvidenceGraphError("candidate references unknown graph node")
            assertions = [item for item in self.assertions if item.id in candidate.assertion_ids]
            if any(item.rule_id != candidate.target_rule_id for item in assertions):
                raise EvidenceGraphError("candidate assertion crosses target rule")
            if candidate.revalidated_document_id is not None and any((item.source_document_id, item.source_document_version) != (candidate.revalidated_document_id, candidate.revalidated_document_version) for item in assertions):
                raise EvidenceGraphError("candidate revalidation is not exact")
            rule = next(item for item in self.rules if item.id == candidate.target_rule_id)
            self._validate_payload_bindings(rule, candidate.payload, assertions)
        derivations = {item.id: item for item in self.derivations}
        for derivation in self.derivations:
            derived_rule = next((item for item in self.rules if item.id == derivation.rule_id), None)
            if derived_rule is None or derivation.field not in derived_rule.fields:
                raise EvidenceGraphError("derivation targets an unknown rule field")
            if derivation.field in derived_rule.field_citations:
                raise EvidenceGraphError("derived field cannot also carry direct citations")
            if derivation.value_sha256 != canonical_hash(derived_rule.fields[derivation.field]):
                raise EvidenceGraphError("derivation value hash does not match canonical rule field")
            assertions = [item for item in self.assertions if item.rule_id == derivation.rule_id]
            assertion_spans = {span_id for item in assertions for span_id in item.span_ids}
            if any(span_id not in assertion_spans for span_id in derivation.input_span_ids):
                raise EvidenceGraphError("derivation is not bound to its rule evidence spans")
        if len(derivations) != len(self.derivations):
            raise EvidenceGraphError("duplicate IDs in derivations")
        rule_ids = ids["rules"]
        candidate_ids = ids["candidates"]
        for review in self.review_decisions:
            if review.target_id not in candidate_ids:
                raise EvidenceGraphError("review targets an unknown candidate")
        for state in self.effective_states:
            if state.target_id not in rule_ids:
                raise EvidenceGraphError("effective state targets an unknown rule")

    def eligible_for_human_promotion(self, candidate_id: str, *, as_of: datetime | None = None) -> bool:
        """Derive eligibility from the complete graph; no serialized boolean is trusted."""
        candidate = next((item for item in self.candidates if item.id == candidate_id), None)
        if candidate is None or candidate.revalidated_document_id is None or candidate.revalidated_at is None:
            return False
        if as_of is not None and candidate.revalidated_at > as_of:
            return False
        timestamp = as_of or datetime.now().astimezone()
        docs = [item for item in self.source_documents if item.id == candidate.revalidated_document_id and item.version == candidate.revalidated_document_version and item.tier < 6]
        admissions = {item.id: item for item in self.source_admissions}
        if len(docs) != 1:
            return False
        admission = admissions.get(docs[0].admission_id)
        if admission is None or admission.state != "approved":
            return False
        if not _source_window_active(docs[0], admission, timestamp.date()):
            return False
        assertions = [item for item in self.assertions if item.id in candidate.assertion_ids]
        rule = next(item for item in self.rules if item.id == candidate.target_rule_id)
        try:
            self._validate_payload_bindings(rule, candidate.payload, assertions)
        except EvidenceGraphError:
            return False
        review_ids = {item.target_id for item in self.review_decisions if item.decision == "approve"}
        observations = {item.id: item for item in self.observations}
        return (
            bool(assertions)
            and all(item.review_state == "approved" for item in assertions)
            and all(observations[item.observation_id].result == "matched" for item in assertions)
            and candidate.id in review_ids
            and all(
                item.decided_at <= timestamp
                for item in self.review_decisions
                if item.target_id == candidate.id and item.decision == "approve"
            )
            and _payload_window_active(rule.fields, timestamp.date())
            and self._has_active_state(candidate.target_rule_id, timestamp.date())
        )

    def eligible_for_catalog_export(
        self,
        rule_id: str,
        payload: Mapping[str, Any],
        *,
        rule_version: int,
        as_of: date,
    ) -> bool:
        """Return whether one exact public catalog record has active evidence."""

        rule = next((item for item in self.rules if item.id == rule_id), None)
        if rule is None or rule.version != rule_version or canonical_json(rule.fields) != canonical_json(payload):
            return False
        assertions = [item for item in self.assertions if item.rule_id == rule_id]
        admissions = {item.id: item for item in self.source_admissions}
        try:
            self._validate_payload_bindings(rule, payload, assertions)
        except EvidenceGraphError:
            return False
        return (
            bool(assertions)
            and all(
                item.review_state == "approved"
                and (document := next((doc for doc in self.source_documents if doc.id == item.source_document_id and doc.version == item.source_document_version), None)) is not None
                and document.tier < 6
                and (admission := admissions.get(document.admission_id)) is not None
                and (observation := next((value for value in self.observations if value.id == item.observation_id), None)) is not None
                and admission.state == "approved"
                and observation.result == "matched"
                and _in_date_range(as_of, document.effective_from, document.effective_to)
                and _in_date_range(as_of, admission.effective_from, admission.effective_to)
                for item in assertions
            )
            and _payload_window_active(rule.fields, as_of)
            and self._has_active_state(rule_id, as_of)
        )

    def _validate_payload_bindings(
        self,
        rule: RuleNode,
        payload: Mapping[str, Any],
        assertions: list[AssertionNode],
    ) -> None:
        if canonical_json(rule.fields) != canonical_json(payload):
            raise EvidenceGraphError("candidate payload is not the exact canonical rule content")
        covered = set(rule.field_citations)
        for derivation in self.derivations:
            if derivation.rule_id == rule.id:
                covered.add(derivation.field)
        if set(rule.fields) != covered:
            raise EvidenceGraphError("canonical rule has uncited or unbound payload fields")
        assertion_citations: dict[str, set[str]] = {}
        for assertion in assertions:
            if set(assertion.field_citations) != set(rule.field_citations):
                raise EvidenceGraphError("canonical field citations do not exactly bind candidate evidence")
            for field, spans in assertion.field_citations.items():
                assertion_citations.setdefault(field, set()).update(spans)
        for field, spans in rule.field_citations.items():
            if not spans or set(spans) != assertion_citations.get(field, set()):
                raise EvidenceGraphError("canonical field citations do not exactly bind candidate evidence")

    def _has_active_state(self, target_id: str, as_of: date) -> bool:
        return any(
            state.target_id == target_id
            and state.state == "active"
            and _in_date_range(as_of, state.effective_from, state.effective_to)
            for state in self.effective_states
        )

    def to_dict(self) -> dict[str, Any]:
        return cast(dict[str, Any], _thaw(self))

    def canonical_json(self) -> str:
        return canonical_json(self)

    @property
    def content_hash(self) -> str:
        return canonical_hash(self)


def _strict_object(raw: Any, required: set[str], optional: set[str], name: str) -> dict[str, Any]:
    if type(raw) is not dict or set(raw) != required | (set(raw) & optional):
        raise EvidenceGraphError(f"{name} has missing or unknown fields")
    if not required <= set(raw):
        raise EvidenceGraphError(f"{name} has missing or unknown fields")
    return raw


def migrate_legacy_record(record: Mapping[str, Any], *, graph_id: str = "legacy-migration") -> CanonicalEvidenceGraph:
    """Wrap a current offering/benefit fixture without inventing verification.

    Legacy evidence has no spans or admitted document version.  The migration
    therefore creates explicitly non-promotable ``legacy-migrated`` nodes with
    deterministic IDs and preserves the complete original record in payload.
    """
    raw = dict(record)
    if not isinstance(raw, dict) or "id" not in raw:
        raise EvidenceGraphError("legacy record must contain id")
    record_id = str(raw["id"])
    _check_id(record_id, "legacy.id")
    offering_id = str(raw.get("offering_id", record_id))
    if "offering_id" not in raw:
        offering = OfferingNode(record_id, 1, raw)
        target = record_id
    else:
        offering = OfferingNode(offering_id, 1, {"id": offering_id})
        target = record_id
    rule = RuleNode(target, int(raw.get("rule_version", 1)), offering.id, raw, {}) if "offering_id" in raw else None
    rules = (rule,) if rule else ()
    return CanonicalEvidenceGraph(GRAPH_SCHEMA_VERSION, graph_id, 1, (offering,), rules)


def revalidate_candidate(graph: CanonicalEvidenceGraph, candidate_id: str, document_id: str, document_version: int) -> CanonicalEvidenceGraph:
    """Mark a candidate promotable only when all citations bind exact evidence."""
    _check_id(candidate_id, "candidate_id")
    _check_id(document_id, "document_id")
    _check_version(document_version, "document_version")
    documents = {(item.id, item.version) for item in graph.source_documents}
    if (document_id, document_version) not in documents:
        raise EvidenceGraphError("revalidation evidence version is not admitted in graph")
    selected = next(item for item in graph.source_documents if (item.id, item.version) == (document_id, document_version))
    if selected.tier == 6:
        raise EvidenceGraphError("discovery-only evidence cannot revalidate a candidate")
    candidates = []
    for candidate in graph.candidates:
        if candidate.id != candidate_id:
            candidates.append(candidate)
            continue
        assertions = [item for item in graph.assertions if item.id in candidate.assertion_ids]
        if not assertions or any((item.source_document_id, item.source_document_version) != (document_id, document_version) for item in assertions):
            raise EvidenceGraphError("candidate citations do not revalidate against the exact evidence version")
        candidates.append(dataclasses.replace(candidate, revalidated_document_id=document_id, revalidated_document_version=document_version, revalidated_at=datetime.now().astimezone()))
    if len(candidates) == len(graph.candidates):
        raise EvidenceGraphError("candidate not found")
    return dataclasses.replace(graph, candidates=tuple(candidates))


def _date(value: Any, field: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceGraphError(f"{field} must be an ISO date") from exc


def _is_date(value: Any) -> bool:
    return value is None or (isinstance(value, date) and not isinstance(value, datetime))


def _in_date_range(value: date, start: date | None, end: date | None) -> bool:
    return (start is None or start <= value) and (end is None or value <= end)


def _source_window_active(
    document: SourceDocumentVersion,
    admission: SourceAdmissionNode,
    as_of: date,
) -> bool:
    """Require both the source document and its admission to be effective."""

    return _in_date_range(as_of, document.effective_from, document.effective_to) and _in_date_range(
        as_of, admission.effective_from, admission.effective_to
    )


def _payload_window_active(payload: Mapping[str, Any], as_of: date) -> bool:
    """Apply a rule's optional effective window without trusting raw strings."""

    try:
        start = _date(payload.get("effective_from"), "rule.effective_from")
        end = _date(payload.get("effective_to"), "rule.effective_to")
    except EvidenceGraphError:
        return False
    if start is not None and end is not None and start > end:
        return False
    return _in_date_range(as_of, start, end)


def _required_date(value: Any, field: str) -> date:
    parsed = _date(value, field)
    if parsed is None:
        raise EvidenceGraphError(f"{field} is required")
    return parsed


def _datetime(value: Any, field: str) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise EvidenceGraphError(f"{field} must be an ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise EvidenceGraphError(f"{field} must include a timezone")
    return parsed


def _required_datetime(value: Any, field: str) -> datetime:
    parsed = _datetime(value, field)
    if parsed is None:
        raise EvidenceGraphError(f"{field} is required")
    return parsed


def _node(raw: Any, required: set[str], optional: set[str], name: str) -> dict[str, Any]:
    return _strict_object(raw, required, optional, name)


def _citation_map(value: Any, field: str) -> dict[str, tuple[str, ...]]:
    if type(value) is not dict:
        raise EvidenceGraphError(f"{field} must be an object")
    result: dict[str, tuple[str, ...]] = {}
    for key, spans in value.items():
        if type(key) is not str or type(spans) is not list or any(type(span) is not str for span in spans):
            raise EvidenceGraphError(f"{field} contains malformed span citations")
        result[key] = tuple(spans)
    return result


def graph_from_dict(raw: Mapping[str, Any]) -> CanonicalEvidenceGraph:
    """Parse a graph snapshot with exact fields and fail closed on future data."""
    root = _node(raw, {"schema_version", "graph_id", "version"}, {
        "offerings", "rules", "source_documents", "observations", "spans", "assertions", "candidates", "lineage", "source_admissions", "review_decisions", "effective_states", "derivations"
    }, "graph")
    if root["schema_version"] != GRAPH_SCHEMA_VERSION:
        raise EvidenceGraphError(f"unsupported graph schema version: {root['schema_version']}")

    offerings = tuple(
        OfferingNode(item["id"], item["version"], item["fields"])
        for item in (_node(v, {"id", "version", "fields"}, set(), "offering") for v in root.get("offerings", []))
    )
    rules = tuple(
        RuleNode(item["id"], item["version"], item["offering_id"], item["fields"], _citation_map(item["field_citations"], "rule.field_citations"), item.get("supersedes"), tuple(item.get("conflicts_with", [])))
        for item in (_node(v, {"id", "version", "offering_id", "fields", "field_citations"}, {"supersedes", "conflicts_with"}, "rule") for v in root.get("rules", []))
    )
    documents = tuple(
        SourceDocumentVersion(item["id"], item["version"], item["admission_id"], item["canonical_url"], item["owner_id"], item["tier"], item["scope"], item["content_sha256"], item["normalized_chunk_sha256"], _required_datetime(item["retrieved_at"], "source_document.retrieved_at"), _date(item.get("effective_from"), "source_document.effective_from"), _date(item.get("effective_to"), "source_document.effective_to"), item.get("validators", {}))
        for item in (_node(v, {"id", "version", "admission_id", "canonical_url", "owner_id", "tier", "scope", "content_sha256", "normalized_chunk_sha256", "retrieved_at"}, {"effective_from", "effective_to", "validators"}, "source_document") for v in root.get("source_documents", []))
    )
    observations = tuple(
        ObservationNode(**item)
        for item in (_node(v, {"id", "version", "source_document_id", "source_document_version", "result", "adapter_name", "adapter_version", "extraction_version", "redaction_version", "content_sha256", "normalized_chunk_sha256"}, set(), "observation") for v in root.get("observations", []))
    )
    spans = tuple(
        ExtractionSpan(**item)
        for item in (_node(v, {"id", "version", "observation_id", "source_document_id", "source_document_version", "content_sha256", "normalized_chunk_sha256", "start_offset", "end_offset", "anchor_start", "anchor_end"}, set(), "span") for v in root.get("spans", []))
    )
    assertions = tuple(
        AssertionNode(item["id"], item["version"], item["rule_id"], item["source_document_id"], item["source_document_version"], item["observation_id"], tuple(item["span_ids"]), _citation_map(item["field_citations"], "assertion.field_citations"), item["review_state"])
        for item in (_node(v, {"id", "version", "rule_id", "source_document_id", "source_document_version", "observation_id", "span_ids", "field_citations", "review_state"}, set(), "assertion") for v in root.get("assertions", []))
    )
    candidates = tuple(
        CandidateNode(item["id"], item["version"], item["target_rule_id"], item["payload"], tuple(item["assertion_ids"]), item["revalidated_document_id"], item["revalidated_document_version"], _datetime(item.get("revalidated_at"), "candidate.revalidated_at"))
        for item in (_node(v, {"id", "version", "target_rule_id", "payload", "assertion_ids", "revalidated_document_id", "revalidated_document_version"}, {"revalidated_at"}, "candidate") for v in root.get("candidates", []))
    )
    derivations = tuple(
        DerivationNode(item["id"], item["version"], item["rule_id"], item["field"], item["algorithm"], tuple(item["input_span_ids"]), item["value_sha256"])
        for item in (_node(value, {"id", "version", "rule_id", "field", "algorithm", "input_span_ids", "value_sha256"}, set(), "derivation") for value in root.get("derivations", []))
    )
    lineage = tuple(LineageEdge(**item) for item in (_node(v, {"id", "version", "kind", "from_id", "to_id"}, set(), "lineage") for v in root.get("lineage", [])))
    admissions = tuple(SourceAdmissionNode(item["id"], item["version"], item["canonical_url"], item["scope"], _required_date(item["effective_from"], "source_admission.effective_from"), _date(item.get("effective_to"), "source_admission.effective_to"), item["state"], item["terms_sha256"]) for item in (_node(v, {"id", "version", "canonical_url", "scope", "effective_from", "state", "terms_sha256"}, {"effective_to"}, "source_admission") for v in root.get("source_admissions", [])))
    reviews = tuple(ReviewDecisionNode(item["id"], item["version"], item["target_id"], item["decision"], item["reviewer_id"], _required_datetime(item["decided_at"], "review.decided_at")) for item in (_node(v, {"id", "version", "target_id", "decision", "reviewer_id", "decided_at"}, set(), "review") for v in root.get("review_decisions", [])))
    states = tuple(EffectiveStateNode(item["id"], item["version"], item["target_id"], item["state"], _required_date(item["effective_from"], "effective_state.effective_from"), _date(item.get("effective_to"), "effective_state.effective_to")) for item in (_node(v, {"id", "version", "target_id", "state", "effective_from"}, {"effective_to"}, "effective_state") for v in root.get("effective_states", [])))
    return CanonicalEvidenceGraph(root["schema_version"], root["graph_id"], root["version"], offerings, rules, documents, observations, spans, assertions, candidates, lineage, admissions, reviews, states, derivations)


def provider_dto(graph: CanonicalEvidenceGraph) -> dict[str, Any]:
    """Return the provider/API DTO; it is the same lossless canonical contract."""
    return graph.to_dict()


def graph_from_provider_dto(value: Mapping[str, Any]) -> CanonicalEvidenceGraph:
    return graph_from_dict(value)


@dataclass(frozen=True)
class EvidenceGraphRepository:
    """The single versioned graph boundary used by stores and transports."""

    graph: CanonicalEvidenceGraph

    @classmethod
    def from_dto(cls, value: Mapping[str, Any]) -> EvidenceGraphRepository:
        return cls(graph_from_dict(value))

    @classmethod
    def from_json(cls, value: str) -> EvidenceGraphRepository:
        try:
            decoded = json.loads(value)
        except (TypeError, json.JSONDecodeError) as exc:
            raise EvidenceGraphError("graph JSON is invalid") from exc
        if not isinstance(decoded, dict):
            raise EvidenceGraphError("graph JSON must be an object")
        return cls.from_dto(decoded)

    @property
    def schema_version(self) -> str:
        return self.graph.schema_version

    @property
    def content_hash(self) -> str:
        return self.graph.content_hash

    def to_dto(self) -> dict[str, Any]:
        return self.graph.to_dict()

    def to_json(self) -> str:
        return self.graph.canonical_json()

    def require_candidate(self, candidate_id: str) -> CandidateNode:
        candidate = next((item for item in self.graph.candidates if item.id == candidate_id), None)
        if candidate is None:
            raise EvidenceGraphError("graph candidate is not present")
        return candidate


legacy_record_to_graph = migrate_legacy_record
