"""Immutable input and explanation models for purchase-route comparison."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import TypeVar
from urllib.parse import urlparse

# Bound public calculations to values that remain exact and inexpensive in Decimal.
MAX_MONETARY_MAGNITUDE = Decimal("1000000000")
MAX_INPUT_DECIMAL_SCALE = 6
MAX_CURRENCY_SCALE = 4
_HOST = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
CURRENCY_MINOR_UNITS = {"INR": 2, "USD": 2, "EUR": 2, "GBP": 2, "JPY": 0}
EnumT = TypeVar("EnumT", bound=StrEnum)


class ComponentValueClass(StrEnum):
    GUARANTEED = "guaranteed"
    CONDITIONAL = "conditional"
    ESTIMATED = "estimated"


class RouteLayer(StrEnum):
    """The route-graph position a component occupies, per `docs/PURCHASE-OPTIMIZER.md`.

    Optional: a component with no declared layer is still ranked and shown,
    just without this explicit categorization.
    """

    COUPON = "coupon"
    PORTAL = "portal"
    ISSUER_NETWORK_OFFER = "issuer_network_offer"
    CARD_EARN = "card_earn"
    MILESTONE = "milestone"
    REDEMPTION = "redemption"


class Freshness(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"


class LinkClass(StrEnum):
    OFFICIAL = "official"
    THIRD_PARTY = "third_party"
    AFFILIATE = "affiliate"


class ActionLinkReviewState(StrEnum):
    """Human review state of the URL a route would ask a user to follow."""

    APPROVED = "approved"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


class EvidenceTier(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


def _currency(value: str) -> None:
    if len(value) != 3 or not value.isalpha() or not value.isupper():
        raise ValueError("currency must be a three-letter uppercase alphabetic code")


def _anonymous_https_url(value: str, field: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(f"{field} must be an anonymous HTTPS URL")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"{field} has an invalid HTTPS port") from exc
    if port is not None and not 1 <= port <= 65535:
        raise ValueError(f"{field} has an invalid HTTPS port")


def canonical_https_origin(value: str, field: str, *, origin_entry: bool) -> str:
    """Return a DNS-only HTTPS origin; IP/IPv6 literals are intentionally unsupported."""
    _anonymous_https_url(value, field)
    parsed = urlparse(value)
    if origin_entry and (parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise ValueError(f"{field} must not contain a path, query, or fragment")
    host = parsed.hostname
    if host is None:
        raise ValueError(f"{field} must have a DNS host")
    try:
        canonical_host = host.encode("idna").decode("ascii").casefold()
    except UnicodeError as exc:
        raise ValueError(f"{field} must have an IDNA-canonical DNS host") from exc
    if not _HOST.fullmatch(canonical_host):
        raise ValueError(f"{field} must have a DNS host; IP and IPv6 literals are not supported")
    port = parsed.port
    return f"https://{canonical_host}" if port in {None, 443} else f"https://{canonical_host}:{port}"


def canonical_https_url(value: str, field: str) -> str:
    """Return a source URL with an IDNA-canonical public DNS HTTPS authority."""
    origin = canonical_https_origin(value, field, origin_entry=False)
    parsed = urlparse(value)
    suffix = parsed.path
    if parsed.query:
        suffix += f"?{parsed.query}"
    if parsed.fragment:
        suffix += f"#{parsed.fragment}"
    return f"{origin}{suffix}"


def _canonical_benefit_rule_id(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", value
    ):
        raise ValueError("benefit_rule_id must be a canonical lowercase UUID")
    try:
        parsed = uuid.UUID(value)
        if str(parsed) != value or parsed.int == 0 or parsed.version not in {1, 2, 3, 4, 5}:
            raise ValueError("benefit_rule_id must be a canonical lowercase UUID")
    except ValueError as exc:
        raise ValueError("benefit_rule_id must be a canonical lowercase UUID") from exc


def _money(value: Decimal, field: str, *, allow_negative: bool = False) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{field} must be a finite Decimal")
    if not allow_negative and value < 0:
        raise ValueError(f"{field} must be non-negative")
    if abs(value) > MAX_MONETARY_MAGNITUDE:
        raise ValueError(f"{field} exceeds the maximum monetary magnitude")
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int):
        raise ValueError(f"{field} must have a numeric Decimal exponent")
    scale = max(0, -exponent)
    if scale > MAX_INPUT_DECIMAL_SCALE:
        raise ValueError(f"{field} exceeds the maximum decimal scale")


@dataclass(frozen=True)
class UserFee:
    """A user-entered cost; the pure engine never persists it."""

    label: str
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if not isinstance(self.label, str) or not self.label.strip():
            raise ValueError("a fee needs a label")
        _money(self.amount, "fee amount")
        _currency(self.currency)
        if self.currency not in CURRENCY_MINOR_UNITS:
            raise ValueError("fee currency is unsupported pending a deterministic minor-unit mapping")


@dataclass(frozen=True)
class PurchaseScenario:
    amount: Decimal
    currency: str
    as_of: date
    user_fees: tuple[UserFee, ...] = ()
    allowed_link_classes: frozenset[LinkClass] = frozenset(LinkClass)
    admitted_action_origins: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        _money(self.amount, "purchase amount")
        if self.amount <= 0:
            raise ValueError("purchase amount must be positive")
        _currency(self.currency)
        if self.currency not in CURRENCY_MINOR_UNITS:
            raise ValueError("currency is unsupported pending a deterministic minor-unit mapping")
        allowed_link_classes = _enum_set(self.allowed_link_classes, LinkClass, "allowed_link_classes")
        if not allowed_link_classes:
            raise ValueError("allowed_link_classes must not be empty")
        admitted_origins = frozenset(
            canonical_https_origin(origin, "admitted_action_origin", origin_entry=True)
            for origin in self.admitted_action_origins
        )
        if not admitted_origins:
            raise ValueError("admitted_action_origins must not be empty")
        user_fees = tuple(self.user_fees)
        _fees_match_currency_and_are_unique(user_fees, self.currency, "scenario")
        object.__setattr__(self, "allowed_link_classes", allowed_link_classes)
        object.__setattr__(self, "admitted_action_origins", admitted_origins)
        object.__setattr__(self, "user_fees", user_fees)


@dataclass(frozen=True)
class RouteComponent:
    """One independently evidenced route layer, expressed in its own currency."""

    id: str
    label: str
    benefit_rule_id: str
    value_class: ComponentValueClass
    currency: str
    value_min: Decimal
    value_max: Decimal
    source_refs: tuple[str, ...]
    evidence_tier: EvidenceTier
    freshness: Freshness
    verified_on: date
    reviewed: bool
    benefit_state: str = "verified"
    compatible_with: frozenset[str] = frozenset()
    conditions: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    expires_on: date | None = None
    per_transaction_cap: Decimal | None = None
    remaining_allowance: Decimal | None = None
    cap_group: str | None = None
    time_limited: bool = False
    valuation_name: str | None = None
    layer: RouteLayer | None = None

    def __post_init__(self) -> None:
        if not self.id or not self.label or not self.benefit_rule_id or not self.source_refs:
            raise ValueError("a component needs an ID, label, canonical benefit rule ID, and source reference")
        if self.benefit_state != "verified":
            raise ValueError("optimizer accepts only verified benefit state")
        _canonical_benefit_rule_id(self.benefit_rule_id)
        _currency(self.currency)
        value_class = _enum(self.value_class, ComponentValueClass, "value_class")
        evidence_tier = _enum(self.evidence_tier, EvidenceTier, "evidence_tier")
        freshness = _enum(self.freshness, Freshness, "freshness")
        layer = None if self.layer is None else _enum(self.layer, RouteLayer, "layer")
        source_refs = tuple(canonical_https_url(source_ref, "source_ref") for source_ref in self.source_refs)
        _money(self.value_min, "component minimum")
        _money(self.value_max, "component maximum")
        if self.value_max < self.value_min:
            raise ValueError("component values must be ordered")
        if value_class is ComponentValueClass.GUARANTEED and self.value_min != self.value_max:
            raise ValueError("guaranteed components must have one fixed value")
        if value_class is ComponentValueClass.ESTIMATED and not self.valuation_name:
            raise ValueError("estimated components require a named valuation assumption")
        for value in (self.per_transaction_cap, self.remaining_allowance):
            if value is not None:
                _money(value, "component cap or allowance")
        if self.cap_group is not None and not self.cap_group:
            raise ValueError("cap_group must be non-empty when present")
        object.__setattr__(self, "value_class", value_class)
        object.__setattr__(self, "evidence_tier", evidence_tier)
        object.__setattr__(self, "freshness", freshness)
        object.__setattr__(self, "layer", layer)
        object.__setattr__(self, "source_refs", source_refs)
        object.__setattr__(self, "compatible_with", frozenset(self.compatible_with))
        object.__setattr__(self, "conditions", tuple(self.conditions))
        object.__setattr__(self, "assumptions", tuple(self.assumptions))


@dataclass(frozen=True)
class RouteCandidate:
    """A complete, user-followed purchase route; it never executes the route."""

    id: str
    label: str
    components: tuple[RouteComponent, ...]
    instructions: tuple[str, ...]
    link_class: LinkClass
    official_reference: str
    action_link_review_state: ActionLinkReviewState
    route_fees: tuple[UserFee, ...] = ()

    def __post_init__(self) -> None:
        if not self.id or not self.label or not self.components or not self.instructions:
            raise ValueError("a route needs an ID, label, component, and instruction")
        link_class = _enum(self.link_class, LinkClass, "link_class")
        action_link_review_state = _enum(
            self.action_link_review_state,
            ActionLinkReviewState,
            "action_link_review_state",
        )
        components = tuple(self.components)
        route_fees = tuple(self.route_fees)
        official_reference = canonical_https_url(self.official_reference, "official_reference")
        component_ids = [component.id for component in components]
        if len(component_ids) != len(set(component_ids)):
            raise ValueError("route component IDs must be unique")
        _fees_are_unique(route_fees, "route")
        object.__setattr__(self, "link_class", link_class)
        object.__setattr__(self, "action_link_review_state", action_link_review_state)
        object.__setattr__(self, "components", components)
        object.__setattr__(self, "instructions", tuple(self.instructions))
        object.__setattr__(self, "route_fees", route_fees)
        object.__setattr__(self, "official_reference", official_reference)


@dataclass(frozen=True)
class ComponentContribution:
    id: str
    label: str
    benefit_rule_id: str
    value_class: ComponentValueClass
    currency: str
    value_min: Decimal
    value_max: Decimal
    source_refs: tuple[str, ...]
    evidence_tier: EvidenceTier
    verified_on: date
    expires_on: date | None
    conditions: tuple[str, ...]
    assumptions: tuple[str, ...]
    per_transaction_cap: Decimal | None = None
    remaining_allowance: Decimal | None = None
    layer: RouteLayer | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "value_class", _enum(self.value_class, ComponentValueClass, "value_class"))
        object.__setattr__(self, "evidence_tier", _enum(self.evidence_tier, EvidenceTier, "evidence_tier"))
        object.__setattr__(self, "source_refs", tuple(self.source_refs))
        object.__setattr__(self, "conditions", tuple(self.conditions))
        object.__setattr__(self, "assumptions", tuple(self.assumptions))


@dataclass(frozen=True)
class RankedRoute:
    route_id: str
    label: str
    guaranteed_before_fees: Decimal
    scenario_fees: Decimal
    route_fees: Decimal
    total_fees: Decimal
    net_guaranteed: Decimal
    conditional_min: Decimal
    conditional_max: Decimal
    estimated_min: Decimal
    estimated_max: Decimal
    components: tuple[ComponentContribution, ...]
    assumptions: tuple[str, ...]
    source_refs: tuple[str, ...]
    explanation: tuple[str, ...]
    link_class: LinkClass
    official_reference: str
    value_class_totals_are_non_additive: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "link_class", _enum(self.link_class, LinkClass, "link_class"))
        object.__setattr__(self, "components", tuple(self.components))
        object.__setattr__(self, "assumptions", tuple(self.assumptions))
        object.__setattr__(self, "source_refs", tuple(self.source_refs))
        object.__setattr__(self, "explanation", tuple(self.explanation))


@dataclass(frozen=True)
class RejectedRoute:
    route_id: str
    label: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class OptimizationResult:
    currency: str
    as_of: date
    ranked_routes: tuple[RankedRoute, ...]
    rejected_routes: tuple[RejectedRoute, ...]
    status: str
    guidance: str


def _enum(value: object, enum_type: type[EnumT], field: str) -> EnumT:  # noqa: UP047
    if not isinstance(value, str):
        raise ValueError(f"{field} is unsupported")
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} is unsupported") from exc


def _enum_set(values: object, enum_type: type[LinkClass], field: str) -> frozenset[LinkClass]:
    if not isinstance(values, (frozenset, set, tuple, list)):
        raise ValueError(f"{field} must be an iterable of link classes")
    return frozenset(_enum(value, enum_type, field) for value in values)


def _fees_are_unique(fees: tuple[UserFee, ...], scope: str) -> None:
    labels = [fee.label.strip().casefold() for fee in fees]
    if len(labels) != len(set(labels)):
        raise ValueError(f"{scope} fee labels must be unique case-insensitively")


def _fees_match_currency_and_are_unique(fees: tuple[UserFee, ...], currency: str, scope: str) -> None:
    _fees_are_unique(fees, scope)
    if any(fee.currency != currency for fee in fees):
        raise ValueError(f"{scope} fee currency must match scenario currency")
