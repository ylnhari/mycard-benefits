"""Deterministic tests for batch 5 of the Claude 30-task run: the optimizer
route-layer tasks MC-100 through MC-104.

Most of this contract already existed (per `docs/PURCHASE-OPTIMIZER.md`,
built by earlier batches): independent per-component evidence (MC-100 was
already true at the generic-component level), mutual-only stackability
(MC-101), separate non-additive value-class totals (MC-102), and a rejected
route always carrying explicit reasons (MC-104). This batch's real code
changes are: an explicit `RouteLayer` taxonomy naming the six route-graph
positions from the design doc (closing the literal "coupon/portal/issuer-
network/card-earn/milestone/redemption" naming gap in MC-100), and real
shared-`cap_group` budget allocation (MC-103 previously just rejected any
shared cap as "not implemented").
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from mycard_benefits.optimizer import (
    ActionLinkReviewState,
    ComponentValueClass,
    EvidenceTier,
    Freshness,
    LinkClass,
    PurchaseScenario,
    RouteCandidate,
    RouteComponent,
    optimize,
)
from mycard_benefits.optimizer.model import RouteLayer

AS_OF = date(2026, 8, 6)
ORIGIN = "https://example.invalid"


def _component(component_id: str, value_class: str, value: str, **overrides: object) -> RouteComponent:
    from uuid import NAMESPACE_URL, uuid5

    defaults: dict[str, object] = {
        "id": component_id,
        "label": f"SYNTHETIC-ONLY-{component_id}",
        "benefit_rule_id": str(uuid5(NAMESPACE_URL, f"{ORIGIN}/rule/{component_id}")),
        "value_class": ComponentValueClass(value_class),
        "currency": "INR",
        "value_min": Decimal(value),
        "value_max": Decimal(overrides.pop("value_max", value)),  # type: ignore[arg-type]
        "source_refs": (f"{ORIGIN}/{component_id}",),
        "evidence_tier": EvidenceTier.MEDIUM,
        "freshness": Freshness.FRESH,
        "verified_on": AS_OF,
        "reviewed": True,
    }
    defaults.update(overrides)
    return RouteComponent(**defaults)  # type: ignore[arg-type]


def _route(route_id: str, components: tuple[RouteComponent, ...], **overrides: object) -> RouteCandidate:
    defaults: dict[str, object] = {
        "id": route_id,
        "label": f"SYNTHETIC-ONLY-{route_id}",
        "components": components,
        "instructions": ("SYNTHETIC-ONLY-step",),
        "link_class": LinkClass.OFFICIAL,
        "official_reference": f"{ORIGIN}/route/{route_id}",
        "action_link_review_state": ActionLinkReviewState.APPROVED,
    }
    defaults.update(overrides)
    return RouteCandidate(**defaults)  # type: ignore[arg-type]


def _scenario(**overrides: object) -> PurchaseScenario:
    defaults: dict[str, object] = {
        "amount": Decimal("1000"),
        "currency": "INR",
        "as_of": AS_OF,
        "allowed_link_classes": frozenset(LinkClass),
        "admitted_action_origins": frozenset({ORIGIN}),
    }
    defaults.update(overrides)
    return PurchaseScenario(**defaults)  # type: ignore[arg-type]


def _compatible_pair(a: RouteComponent, b: RouteComponent) -> tuple[RouteComponent, RouteComponent]:
    from dataclasses import replace

    return (replace(a, compatible_with=frozenset({b.id})), replace(b, compatible_with=frozenset({a.id})))


# ---- MC-100: named route-graph layers -------------------------------------


def test_route_layer_enum_names_the_six_documented_graph_positions() -> None:
    assert {member.value for member in RouteLayer} == {
        "coupon", "portal", "issuer_network_offer", "card_earn", "milestone", "redemption",
    }


def test_component_layer_is_optional_and_carried_through_to_the_rank_unmutated() -> None:
    with_layer = _component("earn", "guaranteed", "10", layer=RouteLayer.CARD_EARN)
    without_layer = _component("bare", "guaranteed", "10")
    route = _route("SYNTHETIC-ONLY-LAYERS", _compatible_pair(with_layer, without_layer))

    ranked = optimize(_scenario(), (route,)).ranked_routes[0]

    by_id = {item.id: item for item in ranked.components}
    assert by_id["earn"].layer is RouteLayer.CARD_EARN
    assert by_id["bare"].layer is None


def test_invalid_layer_value_is_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="layer"):
        _component("bad-layer", "guaranteed", "10", layer="not-a-real-layer")  # type: ignore[arg-type]




def test_no_declared_compatibility_at_all_means_not_stackable_by_default() -> None:
    left = _component("left", "guaranteed", "5")
    right = _component("right", "guaranteed", "5")
    route = _route("SYNTHETIC-ONLY-NO-EVIDENCE", (left, right))

    result = optimize(_scenario(), (route,))

    assert result.ranked_routes == ()
    assert "stacking compatibility is not explicitly mutual" in result.rejected_routes[0].reasons[0]


def test_one_sided_compatibility_declaration_is_still_rejected() -> None:
    from dataclasses import replace

    left = _component("left-claims", "guaranteed", "5")
    right = _component("right-silent", "guaranteed", "5")
    left = replace(left, compatible_with=frozenset({right.id}))
    route = _route("SYNTHETIC-ONLY-ONE-SIDED", (left, right))

    result = optimize(_scenario(), (route,))

    assert result.ranked_routes == ()
    assert any("not explicitly mutual" in reason for reason in result.rejected_routes[0].reasons)


def test_mutual_pairwise_evidence_allows_stacking() -> None:
    a = _component("mutual-a", "guaranteed", "5")
    b = _component("mutual-b", "guaranteed", "5")
    route = _route("SYNTHETIC-ONLY-MUTUAL", _compatible_pair(a, b))

    result = optimize(_scenario(), (route,))

    assert [item.route_id for item in result.ranked_routes] == ["SYNTHETIC-ONLY-MUTUAL"]


# ---- MC-102: guaranteed/conditional/estimated totals never combine -------


def test_net_guaranteed_never_absorbs_conditional_or_estimated_value() -> None:
    route = _route(
        "SYNTHETIC-ONLY-SEPARATE-TOTALS",
        _compatible_pair(
            _component("g", "guaranteed", "10"),
            _component("c", "conditional", "500", value_max="900"),
        ),
    )
    ranked = optimize(_scenario(), (route,)).ranked_routes[0]
    assert ranked.net_guaranteed == Decimal("10")
    assert (ranked.conditional_min, ranked.conditional_max) == (Decimal("500"), Decimal("900"))
    # A naive combiner would produce 510-910; the contract forbids that shape entirely.
    assert ranked.value_class_totals_are_non_additive is True


def test_ranked_route_response_never_carries_a_combined_or_headline_total_field() -> None:
    route = _route("SYNTHETIC-ONLY-NO-HEADLINE", (_component("solo", "guaranteed", "10"),))
    ranked = optimize(_scenario(), (route,)).ranked_routes[0]
    from dataclasses import fields

    field_names = {f.name for f in fields(ranked)}
    for forbidden in ("total", "combined_value", "headline", "grand_total", "overall_value"):
        assert forbidden not in field_names


# ---- MC-103: cap arithmetic, including a real shared-cap allocation ------


def test_per_transaction_and_period_caps_apply_without_double_counting() -> None:
    route = _route(
        "SYNTHETIC-ONLY-INDEPENDENT-CAPS",
        _compatible_pair(
            _component("txn-cap", "guaranteed", "200", per_transaction_cap=Decimal("30")),
            _component("period-cap", "guaranteed", "200", remaining_allowance=Decimal("20")),
        ),
    )
    ranked = optimize(_scenario(), (route,)).ranked_routes[0]
    assert ranked.guaranteed_before_fees == Decimal("50")


def test_shared_cap_group_is_a_single_budget_not_independently_doubled() -> None:
    shared = _compatible_pair(
        _component("share-a", "guaranteed", "80", cap_group="SYNTHETIC-ONLY-GROUP", per_transaction_cap=Decimal("100")),
        _component("share-b", "guaranteed", "80", cap_group="SYNTHETIC-ONLY-GROUP", per_transaction_cap=Decimal("100")),
    )
    route = _route("SYNTHETIC-ONLY-SHARED-BUDGET", shared)
    ranked = optimize(_scenario(amount=Decimal("1000")), (route,)).ranked_routes[0]
    # 80 + 80 = 160 would double the 100 budget; the shared group must cap the pair at 100 total.
    assert ranked.guaranteed_before_fees == Decimal("100")


# ---- MC-104: a rejected route always carries explicit reasons ------------


def test_every_non_ranked_candidate_appears_in_rejected_routes_with_reasons() -> None:
    stale = _route("SYNTHETIC-ONLY-STALE-104", (_component("stale", "guaranteed", "1", freshness=Freshness.STALE),))
    expired = _route("SYNTHETIC-ONLY-EXPIRED-104", (_component("expired", "guaranteed", "1", expires_on=AS_OF - timedelta(days=1)),))
    good = _route("SYNTHETIC-ONLY-GOOD-104", (_component("good", "guaranteed", "1"),))

    result = optimize(_scenario(), (stale, expired, good))

    rejected_ids = {route.route_id for route in result.rejected_routes}
    assert rejected_ids == {"SYNTHETIC-ONLY-STALE-104", "SYNTHETIC-ONLY-EXPIRED-104"}
    assert all(route.reasons for route in result.rejected_routes)
    assert result.status == "verified_routes_available"


def test_all_routes_rejected_still_yields_explicit_reasons_and_honest_status() -> None:
    only_bad = _route("SYNTHETIC-ONLY-ALL-BAD", (_component("bad", "guaranteed", "1", reviewed=False),))
    result = optimize(_scenario(), (only_bad,))
    assert result.ranked_routes == ()
    assert result.status == "no_verified_route"
    assert result.rejected_routes[0].reasons
    assert "do not infer or take a purchase action" in result.guidance
