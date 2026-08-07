"""Typed public catalog records; no cardholder or payment data belongs here."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True)
class ReleaseMetadata:
    schema_version: str
    release_id: str
    generated_at: datetime
    market_scope: tuple[str, ...]


@dataclass(frozen=True)
class Offering:
    id: str
    slug: str
    display_name: str
    issuer_id: str
    product_variant_id: str
    network_id: str
    market: str
    co_brand_id: str | None
    cohort_id: str | None
    aliases: tuple[str, ...]
    effective_from: date | None
    effective_to: date | None


@dataclass(frozen=True)
class ProductRelationship:
    """A reviewed, explicit edge between two public offerings.

    Relationship types: renamed, legacy, cloned, reskinned.
    Relationships are reviewed data with provenance — never inferred from
    product names or slugs alone.
    """

    id: str
    from_offering_id: str
    to_offering_id: str
    relationship_type: str
    effective_from: date | None
    effective_to: date | None
    review_state: str


@dataclass(frozen=True)
class HumanReview:
    """An immutable, attributable human decision about one evidence assertion."""

    id: str
    reviewer_id: str
    reviewed_at: datetime
    decision: str


@dataclass(frozen=True)
class EvidenceAssertion:
    id: str
    source_policy_class: str
    url: str
    content_sha256: str
    retrieved_at: datetime
    effective_from: date | None
    effective_to: date | None
    confidence: str
    review_state: str
    reviews: tuple[HumanReview, ...]


@dataclass(frozen=True)
class BenefitRule:
    id: str
    offering_id: str
    benefit_type: str
    title: str
    status: str
    review_tier: str
    effective_from: date | None
    effective_to: date | None
    eligibility: tuple[dict[str, Any], ...]
    allowance: dict[str, Any] | None
    evidence: tuple[EvidenceAssertion, ...]
    conflicts_with: tuple[str, ...]
    end_date_known: bool | None = None
    rule_version: int = 1
    supersedes: str | None = None

    def __post_init__(self) -> None:
        if self.end_date_known is None:
            object.__setattr__(self, "end_date_known", self.effective_to is not None)
