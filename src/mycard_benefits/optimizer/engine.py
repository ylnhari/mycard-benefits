"""Fail-closed, explainable ranking of complete contemplated-purchase routes."""

from __future__ import annotations

from collections.abc import Iterable
from decimal import ROUND_HALF_EVEN, Decimal

from .model import (
    CURRENCY_MINOR_UNITS,
    ActionLinkReviewState,
    ComponentContribution,
    ComponentValueClass,
    EvidenceTier,
    Freshness,
    OptimizationResult,
    PurchaseScenario,
    RankedRoute,
    RejectedRoute,
    RouteCandidate,
    RouteComponent,
    canonical_https_origin,
)

MAX_EVIDENCE_AGE_DAYS = 90
MAX_TIME_LIMITED_EVIDENCE_AGE_DAYS = 30


def optimize(scenario: PurchaseScenario, candidates: tuple[RouteCandidate, ...]) -> OptimizationResult:
    """Rank eligible routes without combining conditional or estimated value with cash."""
    route_ids = [candidate.id for candidate in candidates]
    if len(route_ids) != len(set(route_ids)):
        raise ValueError("route IDs must be unique")
    for candidate in candidates:
        for component in candidate.components:
            if component.benefit_state != "verified":
                raise ValueError("optimizer accepts only verified benefit state")
    evaluated: list[RankedRoute] = []
    rejected: list[RejectedRoute] = []
    for candidate in candidates:
        _validate_route_fees(scenario, candidate)
        reasons = _rejection_reasons(scenario, candidate)
        if reasons:
            rejected.append(RejectedRoute(candidate.id, candidate.label, tuple(reasons)))
        else:
            evaluated.append(_ranked_route(scenario, candidate))
    evaluated.sort(key=_ranking_key)
    return OptimizationResult(
        currency=scenario.currency,
        as_of=scenario.as_of,
        ranked_routes=tuple(evaluated),
        rejected_routes=tuple(sorted(rejected, key=lambda item: item.route_id)),
        status="verified_routes_available" if evaluated else "no_verified_route",
        guidance=(
            "Compare only the verified routes shown; no purchase action is taken."
            if evaluated
            else "No verified route is available for this scenario; do not infer or take a purchase action."
        ),
    )


def _rejection_reasons(scenario: PurchaseScenario, candidate: RouteCandidate) -> list[str]:
    reasons: list[str] = []
    if candidate.link_class not in scenario.allowed_link_classes:
        reasons.append(f"{candidate.link_class.value} routes are hidden by the user")
    action_origin = canonical_https_origin(
        candidate.official_reference, "official_reference", origin_entry=False
    )
    if action_origin not in scenario.admitted_action_origins:
        reasons.append("action route origin is not in the caller-admitted action origin set")
    if candidate.action_link_review_state is not ActionLinkReviewState.APPROVED:
        reasons.append("action link is not human reviewed")
    cap_group_amounts: dict[str, Decimal | None] = {}
    benefit_rule_ids: set[str] = set()
    for component in candidate.components:
        if component.benefit_rule_id in benefit_rule_ids:
            reasons.append(f"{component.benefit_rule_id}: canonical benefit rule appears more than once")
        benefit_rule_ids.add(component.benefit_rule_id)
        if component.currency != scenario.currency:
            reasons.append(f"{component.id}: currency does not match scenario")
        if component.freshness is not Freshness.FRESH:
            reasons.append(f"{component.id}: source freshness is {component.freshness.value}")
        if not component.reviewed:
            reasons.append(f"{component.id}: source is not human reviewed")
        age = (scenario.as_of - component.verified_on).days
        if age < 0:
            reasons.append(f"{component.id}: source verification is after the scenario date")
        else:
            maximum_age = MAX_TIME_LIMITED_EVIDENCE_AGE_DAYS if component.time_limited else MAX_EVIDENCE_AGE_DAYS
            if age > maximum_age:
                reasons.append(f"{component.id}: evidence is older than {maximum_age} days")
        if component.expires_on is not None and component.expires_on < scenario.as_of:
            reasons.append(f"{component.id}: component expired before the scenario date")
        if component.cap_group is not None:
            if component.per_transaction_cap is None:
                reasons.append(f"{component.id}: a cap_group member must declare a per_transaction_cap")
            elif component.cap_group in cap_group_amounts and cap_group_amounts[component.cap_group] != component.per_transaction_cap:
                reasons.append(f"{component.cap_group}: shared cap_group members must declare the same per_transaction_cap")
            else:
                cap_group_amounts[component.cap_group] = component.per_transaction_cap
    reasons.extend(_compatibility_rejections(candidate.components))
    return reasons


def _validate_route_fees(scenario: PurchaseScenario, candidate: RouteCandidate) -> None:
    all_fees = scenario.user_fees + candidate.route_fees
    labels = [fee.label.strip().casefold() for fee in all_fees]
    if len(labels) != len(set(labels)):
        raise ValueError("scenario and route fee labels must be unique case-insensitively")
    if any(fee.currency != scenario.currency for fee in candidate.route_fees):
        raise ValueError("route fee currency must match scenario currency")


def _compatibility_rejections(components: tuple[RouteComponent, ...]) -> list[str]:
    reasons: list[str] = []
    for index, left in enumerate(components):
        for right in components[index + 1 :]:
            if right.id not in left.compatible_with or left.id not in right.compatible_with:
                first, second = sorted((left.id, right.id))
                reasons.append(f"{first} and {second}: stacking compatibility is not explicitly mutual")
    return reasons


def _ranked_route(scenario: PurchaseScenario, candidate: RouteCandidate) -> RankedRoute:
    contributions = _contributions(scenario, candidate.components)
    guaranteed = _quantize(_total(contributions, ComponentValueClass.GUARANTEED, "value_max"), scenario)
    conditional_min = _quantize(_total(contributions, ComponentValueClass.CONDITIONAL, "value_min"), scenario)
    conditional_max = _quantize(_total(contributions, ComponentValueClass.CONDITIONAL, "value_max"), scenario)
    estimated_min = _quantize(_total(contributions, ComponentValueClass.ESTIMATED, "value_min"), scenario)
    estimated_max = _quantize(_total(contributions, ComponentValueClass.ESTIMATED, "value_max"), scenario)
    scenario_fees = _quantize(sum((fee.amount for fee in scenario.user_fees), Decimal("0")), scenario)
    route_fees = _quantize(sum((fee.amount for fee in candidate.route_fees), Decimal("0")), scenario)
    total_fees = _quantize(scenario_fees + route_fees, scenario)
    assumptions = _unique_sorted(
        assumption for component in candidate.components for assumption in component.assumptions
    )
    source_refs = _unique_sorted(ref for component in candidate.components for ref in component.source_refs)
    fragility = sum(len(component.conditions) for component in candidate.components)
    unknown_expiry = [component.id for component in candidate.components if component.expires_on is None]
    expiry_explanation = (
        f"expiry is unknown for {', '.join(sorted(unknown_expiry))}; this is not treated as perpetual"
        if unknown_expiry
        else "all component expiry dates are explicitly recorded"
    )
    return RankedRoute(
        route_id=candidate.id,
        label=candidate.label,
        guaranteed_before_fees=guaranteed,
        scenario_fees=scenario_fees,
        route_fees=route_fees,
        total_fees=total_fees,
        net_guaranteed=_quantize(guaranteed - total_fees, scenario),
        conditional_min=conditional_min,
        conditional_max=conditional_max,
        estimated_min=estimated_min,
        estimated_max=estimated_max,
        components=contributions,
        assumptions=assumptions,
        source_refs=source_refs,
        explanation=(
            f"net guaranteed value is {guaranteed} minus total fees of {total_fees}",
            f"conditional value of {conditional_min} to {conditional_max} is not included in net guaranteed value",
            f"estimated redemption value of {estimated_min} to {estimated_max} is not included in net guaranteed value",
            f"route has {fragility} stated condition(s) and {len(candidate.components)} component(s)",
            expiry_explanation,
        ),
        link_class=candidate.link_class,
        official_reference=candidate.official_reference,
    )


def _contributions(
    scenario: PurchaseScenario, components: tuple[RouteComponent, ...]
) -> tuple[ComponentContribution, ...]:
    budget = _quantize(scenario.amount, scenario)
    remaining_by_class = {value_class: budget for value_class in ComponentValueClass}
    remaining_by_cap_group: dict[str, Decimal] = {}
    return tuple(
        _contribution(scenario, component, remaining_by_class, remaining_by_cap_group)
        for component in components
    )


def _contribution(
    scenario: PurchaseScenario,
    component: RouteComponent,
    remaining_by_class: dict[ComponentValueClass, Decimal],
    remaining_by_cap_group: dict[str, Decimal],
) -> ComponentContribution:
    limit = min(
        value
        for value in (scenario.amount, component.per_transaction_cap, component.remaining_allowance)
        if value is not None
    )
    limit = min(limit, remaining_by_class[component.value_class])
    if component.cap_group is not None and component.per_transaction_cap is not None:
        # _rejection_reasons already guarantees every member of this group declared
        # the same per_transaction_cap, so seeding lazily from that value is safe.
        group_remaining = remaining_by_cap_group.setdefault(component.cap_group, component.per_transaction_cap)
        limit = min(limit, group_remaining)
    contribution = ComponentContribution(
        id=component.id,
        label=component.label,
        benefit_rule_id=component.benefit_rule_id,
        value_class=component.value_class,
        currency=component.currency,
        value_min=_quantize(min(component.value_min, limit), scenario),
        value_max=_quantize(min(component.value_max, limit), scenario),
        source_refs=component.source_refs,
        evidence_tier=component.evidence_tier,
        verified_on=component.verified_on,
        expires_on=component.expires_on,
        conditions=component.conditions,
        assumptions=component.assumptions,
        per_transaction_cap=component.per_transaction_cap,
        remaining_allowance=component.remaining_allowance,
        layer=component.layer,
    )
    remaining_by_class[component.value_class] -= contribution.value_max
    if component.cap_group is not None and component.cap_group in remaining_by_cap_group:
        remaining_by_cap_group[component.cap_group] -= contribution.value_max
    return contribution


def _total(
    contributions: tuple[ComponentContribution, ...],
    value_class: ComponentValueClass,
    attribute: str,
) -> Decimal:
    return sum(
        (getattr(component, attribute) for component in contributions if component.value_class is value_class),
        Decimal("0"),
    )


def _ranking_key(route: RankedRoute) -> tuple[Decimal, int, int, int, int, str]:
    fragility = sum(len(component.conditions) for component in route.components)
    stalest_verification = min(component.verified_on.toordinal() for component in route.components)
    worst_evidence_tier = min(_evidence_tier_rank(component.evidence_tier) for component in route.components)
    return (
        -route.net_guaranteed,
        fragility,
        -stalest_verification,
        -worst_evidence_tier,
        len(route.components),
        route.route_id,
    )


def _unique_sorted(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(set(values)))


def _evidence_tier_rank(tier: EvidenceTier) -> int:
    return {EvidenceTier.HIGH: 3, EvidenceTier.MEDIUM: 2, EvidenceTier.LOW: 1}[tier]


def _quantize(value: Decimal, scenario: PurchaseScenario) -> Decimal:
    quantum = Decimal("1").scaleb(-CURRENCY_MINOR_UNITS[scenario.currency])
    return value.quantize(quantum, rounding=ROUND_HALF_EVEN)
