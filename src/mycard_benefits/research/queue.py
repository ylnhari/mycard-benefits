"""A local, no-network queue for admitted public-source research work."""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Protocol, cast
from urllib.parse import urlsplit

from mycard_benefits.sources import SourceAdmission

_MAX_ATTEMPTS = 3
_MIN_CADENCE_SECONDS = 900
_MAX_LIST_LIMIT = 1_000
_MAX_BACKOFF_SECONDS = 86_400


class Clock(Protocol):
    """Injectable source of timezone-aware timestamps."""

    def now(self) -> datetime: ...


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    REVIEW_PENDING = "review_pending"
    BLOCKED = "blocked"
    FAILED = "failed"
    COMPLETED = "completed"


class Outcome(StrEnum):
    OK = "ok"
    BLOCKED = "blocked"
    FETCH_FAILURE = "fetch_failure"
    PARSE_FAILURE = "parse_failure"
    MAX_ATTEMPTS = "max_attempts"


class ClaimError(RuntimeError):
    """A caller no longer holds the supplied job lease."""


class InvalidTransition(ValueError):
    """The requested state change is not permitted."""


class JobNotFound(LookupError):
    """The requested job does not exist."""


@dataclass(frozen=True)
class Job:
    id: int
    admission_id: str
    source_url: str
    cadence_seconds: int
    next_run_at: str
    state: JobState
    attempts: int
    lease_token: str | None
    lease_expires_at: str | None
    outcome: Outcome | None
    created_at: str
    updated_at: str


def _iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _validate_admission_id(admission_id: object) -> None:
    if type(admission_id) is not str:
        raise ValueError("admission id is invalid")
    try:
        if str(uuid.UUID(admission_id)) != admission_id:
            raise ValueError("admission id is invalid")
    except ValueError:
        raise ValueError("admission id is invalid") from None


class ResearchQueue:
    """SQLite-backed scheduling state for already-admitted public URLs.

    A successful retrieval may move to ``review_pending``.  Only an explicit
    post-review ``schedule_next`` returns it to ``queued`` and resets attempts.
    The queue itself neither performs retrieval nor stores retrieved content.
    """

    def __init__(self, path: str | Path, clock: Clock | None = None) -> None:
        self.path = Path(path)
        self.clock = clock or _SystemClock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._create()

    @classmethod
    def init(cls, path: str | Path, clock: Clock | None = None) -> ResearchQueue:
        return cls(path, clock)

    def enqueue(
        self,
        admission: SourceAdmission,
        source_url: str,
        cadence_seconds: int | None = None,
    ) -> Job:
        _validate_admission_id(admission.id)
        cadence = admission.cadence_seconds if cadence_seconds is None else cadence_seconds
        if isinstance(cadence, bool) or not isinstance(cadence, int) or cadence < _MIN_CADENCE_SECONDS:
            raise ValueError("cadence_seconds must be an integer of at least 900")
        parts = urlsplit(source_url)
        if parts.query or parts.fragment:
            raise ValueError("queue URLs may not contain a query or fragment")
        url = admission.authorize_url(source_url)
        stamp = _iso(self.clock.now())
        with self._transaction() as con:
            # Admissions are reviewed files, not queue rows, so a database FK
            # would invent a second source of truth instead of adding safety.
            con.execute(
                """
                INSERT INTO queue_jobs(
                    admission_id, source_url, cadence_seconds, next_run_at, state, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(admission_id, source_url) DO NOTHING
                """,
                (admission.id, url, cadence, stamp, JobState.QUEUED, stamp, stamp),
            )
            row = self._by_key(con, admission.id, url)
            if row["cadence_seconds"] != cadence:
                raise ValueError("existing job uses a different cadence_seconds")
        return self._job(row)

    def claim_next(self, lease_seconds: int = 300) -> Job | None:
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) or lease_seconds <= 0:
            raise ValueError("lease_seconds must be a positive integer")
        now = self.clock.now()
        stamp = _iso(now)
        token = str(uuid.uuid4())
        expiry = _iso(now + timedelta(seconds=lease_seconds))
        with self._transaction() as con:
            row = con.execute(
                """
                SELECT id FROM queue_jobs
                WHERE state = ? AND attempts < ? AND next_run_at <= ?
                ORDER BY next_run_at, id
                LIMIT 1
                """,
                (JobState.QUEUED, _MAX_ATTEMPTS, stamp),
            ).fetchone()
            if row is None:
                return None
            con.execute(
                """
                UPDATE queue_jobs
                SET state = ?, attempts = attempts + 1, lease_token = ?, lease_expires_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (JobState.RUNNING, token, expiry, stamp, row["id"]),
            )
            result = self._row(con, row["id"])
        return self._job(result)

    def finish(
        self,
        job_id: int,
        lease_token: str,
        outcome: Outcome,
        *,
        review_pending: bool = False,
    ) -> Job:
        if not isinstance(outcome, Outcome):
            raise InvalidTransition("outcome is invalid")
        if review_pending and outcome is not Outcome.OK:
            raise InvalidTransition("only successful work may await review")
        now = self.clock.now()
        stamp = _iso(now)
        with self._transaction() as con:
            row = self._row(con, job_id)
            if (
                row["state"] != JobState.RUNNING
                or row["lease_token"] != lease_token
                or row["lease_expires_at"] <= stamp
            ):
                raise ClaimError("job is not held by this unexpired lease")
            state, final_outcome, next_run_at = self._finished(row, outcome, review_pending, now)
            con.execute(
                """
                UPDATE queue_jobs
                SET state = ?, next_run_at = ?, lease_token = NULL, lease_expires_at = NULL,
                    outcome = ?, updated_at = ?
                WHERE id = ?
                """,
                (state, next_run_at, final_outcome, stamp, job_id),
            )
            result = self._row(con, job_id)
        return self._job(result)

    def recover_stale_leases(self) -> int:
        stamp = _iso(self.clock.now())
        with self._transaction() as con:
            result = con.execute(
                """
                UPDATE queue_jobs
                SET state = CASE WHEN attempts >= ? THEN ? ELSE ? END,
                    outcome = CASE WHEN attempts >= ? THEN ? ELSE outcome END,
                    lease_token = NULL,
                    lease_expires_at = NULL,
                    updated_at = ?
                WHERE state = ? AND lease_expires_at <= ?
                """,
                (
                    _MAX_ATTEMPTS,
                    JobState.FAILED,
                    JobState.QUEUED,
                    _MAX_ATTEMPTS,
                    Outcome.MAX_ATTEMPTS,
                    stamp,
                    JobState.RUNNING,
                    stamp,
                ),
            )
        return result.rowcount

    def unblock(self, job_id: int) -> Job:
        """Explicitly resume a policy-blocked job after human intervention."""
        return self._move(job_id, {JobState.BLOCKED}, JobState.QUEUED, reset=True)

    def retry_failed(self, job_id: int) -> Job:
        """Explicitly retry a failed job after a human or operator decision."""
        stamp = _iso(self.clock.now())
        with self._transaction() as con:
            row = self._row(con, job_id)
            if JobState(row["state"]) is not JobState.FAILED:
                raise InvalidTransition("transition is not allowed")
            con.execute(
                """
                UPDATE queue_jobs
                SET state = ?, next_run_at = ?, attempts = 0, outcome = NULL,
                    lease_token = NULL, lease_expires_at = NULL, updated_at = ?
                WHERE id = ?
                """,
                (JobState.QUEUED, stamp, stamp, job_id),
            )
            result = self._row(con, job_id)
        return self._job(result)

    def mark_review_pending(self, job_id: int) -> Job:
        return self._move(job_id, {JobState.COMPLETED}, JobState.REVIEW_PENDING)

    def schedule_next(self, job_id: int) -> Job:
        """Schedule the next recurrence only after the current result is reviewed."""
        return self._move(job_id, {JobState.REVIEW_PENDING}, JobState.QUEUED, reset=True)

    def list_jobs(
        self,
        state: JobState | None = None,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Job]:
        if state is not None and not isinstance(state, JobState):
            raise ValueError("state is invalid")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= _MAX_LIST_LIMIT
            or isinstance(offset, bool)
            or not isinstance(offset, int)
            or offset < 0
        ):
            raise ValueError("invalid list bounds")
        if state is None:
            sql = "SELECT * FROM queue_jobs ORDER BY id LIMIT ? OFFSET ?"
            args: tuple[object, ...] = (limit, offset)
        else:
            sql = "SELECT * FROM queue_jobs WHERE state = ? ORDER BY id LIMIT ? OFFSET ?"
            args = (state, limit, offset)
        with self._connection() as con:
            rows = con.execute(sql, args).fetchall()
        return [self._job(row) for row in rows]

    def stats(self) -> dict[JobState, int]:
        result = {state: 0 for state in JobState}
        with self._connection() as con:
            rows = con.execute("SELECT state, COUNT(*) AS count FROM queue_jobs GROUP BY state")
            for row in rows:
                result[JobState(row["state"])] = cast(int, row["count"])
        return result

    def _finished(
        self,
        row: sqlite3.Row,
        outcome: Outcome,
        review_pending: bool,
        now: datetime,
    ) -> tuple[JobState, Outcome, str]:
        if outcome is Outcome.OK:
            state = JobState.REVIEW_PENDING if review_pending else JobState.COMPLETED
            return state, outcome, row["next_run_at"]
        if outcome is Outcome.BLOCKED:
            return JobState.BLOCKED, outcome, row["next_run_at"]
        if outcome not in {Outcome.FETCH_FAILURE, Outcome.PARSE_FAILURE}:
            raise InvalidTransition("max_attempts is not a worker outcome")
        if row["attempts"] >= _MAX_ATTEMPTS:
            return JobState.FAILED, Outcome.MAX_ATTEMPTS, row["next_run_at"]
        delay = min(row["cadence_seconds"] * row["attempts"], _MAX_BACKOFF_SECONDS)
        return JobState.QUEUED, outcome, _iso(now + timedelta(seconds=delay))

    def _move(
        self,
        job_id: int,
        allowed: set[JobState],
        target: JobState,
        *,
        reset: bool = False,
    ) -> Job:
        now = self.clock.now()
        stamp = _iso(now)
        with self._transaction() as con:
            row = self._row(con, job_id)
            if JobState(row["state"]) not in allowed:
                raise InvalidTransition("transition is not allowed")
            next_run_at = (
                _iso(now + timedelta(seconds=row["cadence_seconds"])) if reset else row["next_run_at"]
            )
            con.execute(
                """
                UPDATE queue_jobs
                SET state = ?, next_run_at = ?, attempts = ?, outcome = ?, lease_token = NULL,
                    lease_expires_at = NULL, updated_at = ?
                WHERE id = ?
                """,
                (target, next_run_at, 0 if reset else row["attempts"], None if reset else row["outcome"], stamp, job_id),
            )
            result = self._row(con, job_id)
        return self._job(result)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA busy_timeout=5000")
            yield con
        finally:
            con.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._connection() as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                yield con
            except BaseException:
                con.rollback()
                raise
            else:
                con.commit()

    def _create(self) -> None:
        with self._connection() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS queue_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admission_id TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    cadence_seconds INTEGER NOT NULL CHECK(cadence_seconds >= 900),
                    next_run_at TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN (
                        'queued', 'running', 'review_pending', 'blocked', 'failed', 'completed'
                    )),
                    attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 3),
                    lease_token TEXT,
                    lease_expires_at TEXT,
                    outcome TEXT CHECK(outcome IN (
                        'ok', 'blocked', 'fetch_failure', 'parse_failure', 'max_attempts'
                    )),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(admission_id, source_url)
                );
                CREATE INDEX IF NOT EXISTS queue_jobs_claim
                    ON queue_jobs(state, next_run_at, id);
                CREATE INDEX IF NOT EXISTS queue_jobs_lease
                    ON queue_jobs(state, lease_expires_at);
                """
            )

    @staticmethod
    def _row(con: sqlite3.Connection, job_id: int) -> sqlite3.Row:
        row = con.execute("SELECT * FROM queue_jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise JobNotFound(str(job_id))
        return cast(sqlite3.Row, row)

    @staticmethod
    def _by_key(con: sqlite3.Connection, admission_id: str, url: str) -> sqlite3.Row:
        row = con.execute(
            "SELECT * FROM queue_jobs WHERE admission_id = ? AND source_url = ?",
            (admission_id, url),
        ).fetchone()
        if row is None:
            raise JobNotFound("newly enqueued job is missing")
        return cast(sqlite3.Row, row)

    @staticmethod
    def _job(row: sqlite3.Row) -> Job:
        outcome = Outcome(row["outcome"]) if row["outcome"] is not None else None
        return Job(
            id=row["id"],
            admission_id=row["admission_id"],
            source_url=row["source_url"],
            cadence_seconds=row["cadence_seconds"],
            next_run_at=row["next_run_at"],
            state=JobState(row["state"]),
            attempts=row["attempts"],
            lease_token=row["lease_token"],
            lease_expires_at=row["lease_expires_at"],
            outcome=outcome,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class _SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)
