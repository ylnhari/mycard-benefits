"""Frozen public-data records for candidate review; payloads are canonical JSON."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class CandidateValidationError(ValueError):
    """Public candidate input is invalid or exceeds a fixed safety bound."""


class RecordKind(StrEnum):
    OFFERING = "offering"
    BENEFIT = "benefit"


class CandidateState(StrEnum):
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"
    STALE = "stale"


class ReviewDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    CHANGES_REQUESTED = "changes_requested"


@dataclass(frozen=True)
class Candidate:
    id: str
    base_release_id: str
    record_kind: RecordKind
    target_record_id: str
    author_id: str
    review_tier: str
    base_record_json: str
    payload_json: str
    content_hash: str
    state: CandidateState
    created_at: datetime


@dataclass(frozen=True)
class CandidateReview:
    id: int
    candidate_id: str
    reviewer_kind: str
    reviewer_id: str
    decision: ReviewDecision
    note: str | None
    created_at: datetime


@dataclass(frozen=True)
class CandidateEvent:
    id: int
    candidate_id: str
    event_type: str
    detail: str
    created_at: datetime


@dataclass(frozen=True)
class DiffEntry:
    path: str
    before_json: str | None
    after_json: str | None
