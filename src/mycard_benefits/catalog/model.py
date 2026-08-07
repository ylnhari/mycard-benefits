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
class HumanReview:
    """An immutable, attributable human decision about one evidence assertion."""

    id: str
    reviewer_id: str
    reviewed_at: datetime
    decision: str


_SOURCE_TIERS = {
    "administering_terms": 1,
    "issuer_document": 2,
    "network_rule": 3,
    "merchant_terms": 4,
    "regulatory_context": 5,
    "discovery_only": 6,
}


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
    source_tier: int = 6

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "source_tier", _SOURCE_TIERS.get(self.source_policy_class, 6)
        )


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
    evidence: tuple[EvidenceAssertion, ...]


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
    rule_version: int = 1
    supersedes: str | None = None

    @property
    def end_date_known(self) -> bool:
        return self.effective_to is not None
