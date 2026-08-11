"""Typed public catalog records; no cardholder or payment data belongs here."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal


class BenefitCategory(StrEnum):
    HOTEL = "hotel"
    FLIGHT = "flight"
    DINING = "dining"
    FUEL = "fuel"
    SHOPPING = "shopping"
    VOUCHER = "voucher"
    COUPON = "coupon"
    LOUNGE = "lounge"
    PRIORITY_PASS = "priority_pass"
    MEET_AND_GREET = "meet_and_greet"
    CONCIERGE = "concierge"
    TRAVEL_ASSISTANCE = "travel_assistance"
    INSURANCE = "insurance"
    GOLF = "golf"
    SUBSCRIPTION = "subscription"
    RAILWAY_LOUNGE = "railway_lounge"
    REWARD_POINTS = "reward_points"
    MILES = "miles"
    CASHBACK = "cashback"
    CONVERSION = "conversion"
    MOVIE = "movie"
    FOOD = "food"
    FOREIGN_EXCHANGE = "foreign_exchange"
    WELLNESS = "wellness"
    EDUCATION = "education"
    JOINING = "joining"
    RENEWAL = "renewal"
    ANNUAL_FEE = "annual_fee"
    FEE_WAIVER = "fee_waiver"
    MILESTONE = "milestone"
    OTHER = "other"


RuleOwnerKind = Literal["issuer", "network", "co_brand", "merchant", "membership", "event"]
ValueClass = Literal["guaranteed", "conditional", "estimated"]


@dataclass(frozen=True)
class ConditionPredicate:
    type: str
    operator: str
    value: Any = None

    def evaluate(self, actual: Any) -> bool:
        if self.operator == "exists":
            return actual is not None
        if self.operator == "equals":
            return bool(actual == self.value)
        if self.operator == "in":
            return bool(actual in self.value) if isinstance(self.value, list) else False
        if self.operator == "not_in":
            return (
                actual is not None and bool(actual not in self.value)
                if isinstance(self.value, list)
                else False
            )
        try:
            if self.operator == "gte":
                return bool(actual >= self.value)
            if self.operator == "lte":
                return bool(actual <= self.value)
            if self.operator == "between":
                return bool(
                    isinstance(self.value, list)
                    and len(self.value) == 2
                    and self.value[0] <= actual <= self.value[1]
                )
        except TypeError:
            return False
        return False


@dataclass(frozen=True)
class RuleOwner:
    kind: RuleOwnerKind
    id: str
    display_name: str


@dataclass(frozen=True)
class EarnRule:
    currency: str
    rate: str
    basis: str
    scope: str
    cap: dict[str, Any] | None = None
    exclusions: tuple[str, ...] = ()
    rounding: str | None = None
    reversal: str | None = None
    expiry: dict[str, Any] | None = None


@dataclass(frozen=True)
class ConversionRule:
    partner_id: str
    ratio: str
    fee: dict[str, Any] | None
    minimum: int | None
    increment: int | None
    expiry: dict[str, Any] | None
    redemption_options: tuple[str, ...]


@dataclass(frozen=True)
class ValuationRange:
    name: str
    redemption_path: str
    currency: str
    minimum: str
    maximum: str


@dataclass(frozen=True)
class InheritanceRule:
    owner: RuleOwner
    source_benefit_id: str
    source_offering_id: str
    target_offering_id: str
    source_network_id: str
    target_network_id: str
    source_co_brand_id: str | None
    target_co_brand_id: str | None
    review_state: str
    opt_in: bool
    effective_from: date
    effective_to: date

    def applies(self, as_of: date) -> bool:
        return (
            self.opt_in
            and self.review_state == "approved"
            and self.effective_from <= as_of <= self.effective_to
        )


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
    personalized: bool = False
    source_observation_id: str | None = None
    hash_kind: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_tier", _SOURCE_TIERS.get(self.source_policy_class, 6))


def is_current_approved_evidence(evidence: EvidenceAssertion, as_of: date) -> bool:
    """Whether evidence is current, approved, and backed by a human review.

    ``review_state`` is authoring metadata rather than proof by itself.  Every
    public consumer must also require a qualifying human approval no later
    than its requested date, so candidate, stale, rejected, and low-confidence
    assertions cannot become public facts through a second code path.
    """
    return (
        evidence.review_state == "approved"
        and evidence.confidence in {"high", "medium"}
        and evidence.retrieved_at.date() <= as_of
        and (evidence.effective_from is None or evidence.effective_from <= as_of)
        and (evidence.effective_to is None or as_of <= evidence.effective_to)
        and any(
            review.decision == "approved" and review.reviewed_at.date() <= as_of
            for review in evidence.reviews
        )
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
    review_tier: str | None
    effective_from: date | None
    effective_to: date | None
    eligibility: tuple[dict[str, Any], ...]
    allowance: dict[str, Any] | None
    evidence: tuple[EvidenceAssertion, ...]
    conflicts_with: tuple[str, ...]
    rule_version: int = 1
    supersedes: str | None = None
    # Movie-specific fulfillment metadata.  These stay optional on the common
    # rule model so existing non-movie records retain their exact shape.
    provider: str | None = None
    official_reference: str | None = None
    redemption_steps: tuple[str, ...] = ()
    exclusions: tuple[str, ...] = ()
    category: BenefitCategory | None = None
    owners: tuple[RuleOwner, ...] = ()
    conditions: tuple[ConditionPredicate, ...] = ()
    earn: EarnRule | None = None
    conversion: ConversionRule | None = None
    valuations: tuple[ValuationRange, ...] = ()
    value_class: ValueClass | None = None
    inheritance: InheritanceRule | None = None
    # Structural classification is separate from the display taxonomy. The
    # coverage validator uses this closed shape to prevent relabelled rules
    # from satisfying rare/event coverage slots.
    benefit_shape: str = "ordinary"
    # Rescued public records carry an explicit source state rather than the
    # legacy publication/review fields. Keep it internal to the model so
    # discovery can preserve the distinction without relabelling the record.
    state: str | None = None
    not_claimed: tuple[str, ...] = ()
    source_divergence: tuple[dict[str, Any], ...] = ()

    @property
    def end_date_known(self) -> bool:
        return self.effective_to is not None
