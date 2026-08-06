from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import date, timedelta
from decimal import Decimal
from uuid import NAMESPACE_DNS, NAMESPACE_URL, uuid1, uuid3, uuid4, uuid5

import pytest

from mycard_benefits.optimizer import (
    ComponentValueClass,
    EvidenceTier,
    Freshness,
    LinkClass,
    PurchaseScenario,
    RouteCandidate,
    RouteComponent,
    UserFee,
    optimize,
)

AS_OF = date(2026, 8, 6)


def test_values_fees_and_conditional_ranges_remain_separate() -> None:
    scenario = _scenario(user_fees=(UserFee("SYNTHETIC-ONLY-SCENARIO-FEE", Decimal("10"), "INR"),))
    route = _route(
        "SYNTHETIC-ONLY-ROUTE",
        _compatible_components((
            _component("guaranteed", "guaranteed", "50"),
            _component("conditional", "conditional", "20", value_max="100"),
            _component("estimated", "estimated", "5", value_max="30"),
        )),
        route_fees=(UserFee("SYNTHETIC-ONLY-ROUTE-FEE", Decimal("5"), "INR"),),
    )

    result = optimize(scenario, (route,))
    ranked = result.ranked_routes[0]

    assert (ranked.guaranteed_before_fees, ranked.scenario_fees, ranked.route_fees) == (
        Decimal("50"), Decimal("10"), Decimal("5"),
    )
    assert ranked.net_guaranteed == Decimal("35")
    assert (ranked.conditional_min, ranked.conditional_max) == (Decimal("20"), Decimal("100"))
    assert (ranked.estimated_min, ranked.estimated_max) == (Decimal("5"), Decimal("30"))
    assert "not included in net guaranteed value" in " ".join(ranked.explanation)
    assert "expiry is unknown" in " ".join(ranked.explanation)


def test_evidence_age_boundary_future_and_unreviewed_are_fail_closed() -> None:
    scenario = _scenario()
    valid_at_90 = _route("SYNTHETIC-ONLY-AT-90", (_component("at90", "guaranteed", "1", verified_on=AS_OF - timedelta(days=90)),))
    too_old = _route("SYNTHETIC-ONLY-OLD", (_component("old", "guaranteed", "1", verified_on=AS_OF - timedelta(days=91)),))
    future = _route("SYNTHETIC-ONLY-FUTURE", (_component("future", "guaranteed", "1", verified_on=AS_OF + timedelta(days=1)),))
    unreviewed = _route("SYNTHETIC-ONLY-UNREVIEWED", (_component("unreviewed", "guaranteed", "1", reviewed=False),))
    unknown = _route("SYNTHETIC-ONLY-UNKNOWN", (_component("unknown", "guaranteed", "1", freshness=Freshness.UNKNOWN),))

    result = optimize(scenario, (valid_at_90, too_old, future, unreviewed, unknown))

    assert [route.route_id for route in result.ranked_routes] == ["SYNTHETIC-ONLY-AT-90"]
    reasons = {route.route_id: route.reasons for route in result.rejected_routes}
    assert "older than 90 days" in reasons["SYNTHETIC-ONLY-OLD"][0]
    assert "after the scenario date" in reasons["SYNTHETIC-ONLY-FUTURE"][0]
    assert "not human reviewed" in reasons["SYNTHETIC-ONLY-UNREVIEWED"][0]
    assert "freshness is unknown" in reasons["SYNTHETIC-ONLY-UNKNOWN"][0]


def test_three_component_compatibility_must_be_mutual_for_every_pair() -> None:
    first = _component("first", "guaranteed", "1", compatible_with=frozenset({"second", "third"}))
    second = _component("second", "guaranteed", "1", compatible_with=frozenset({"first"}))
    third = _component("third", "guaranteed", "1", compatible_with=frozenset({"first", "second"}))

    result = optimize(_scenario(), (_route("SYNTHETIC-ONLY-THREE", (first, second, third)),))

    assert result.ranked_routes == ()
    assert result.rejected_routes[0].reasons == (
        "second and third: stacking compatibility is not explicitly mutual",
    )


def test_caps_currency_shared_cap_and_expiry_are_fail_closed_or_clamped() -> None:
    capped = _route(
        "SYNTHETIC-ONLY-CAPPED",
        (_component("capped", "guaranteed", "200", per_transaction_cap=Decimal("80"), remaining_allowance=Decimal("50")),),
    )
    currency = _route("SYNTHETIC-ONLY-CURRENCY", (_component("currency", "guaranteed", "1", currency="USD"),))
    duplicate_cap = _route(
        "SYNTHETIC-ONLY-SHARED-CAP",
        _compatible_pair(
            _component("first-cap", "guaranteed", "1", cap_group="SYNTHETIC-ONLY-CAP"),
            _component("second-cap", "guaranteed", "1", cap_group="SYNTHETIC-ONLY-CAP"),
        ),
    )
    expired = _route("SYNTHETIC-ONLY-EXPIRED", (_component("expired", "guaranteed", "1", expires_on=AS_OF - timedelta(days=1)),))

    result = optimize(_scenario(), (capped, currency, duplicate_cap, expired))

    assert result.ranked_routes[0].net_guaranteed == Decimal("50")
    reasons = {route.route_id: route.reasons for route in result.rejected_routes}
    assert "currency does not match scenario" in reasons["SYNTHETIC-ONLY-CURRENCY"][0]
    assert "shared cap allocation" in reasons["SYNTHETIC-ONLY-SHARED-CAP"][0]
    assert "expired" in reasons["SYNTHETIC-ONLY-EXPIRED"][0]


def test_ties_are_deterministic_and_use_stalest_source_before_affiliate_penalty() -> None:
    newer = _route("SYNTHETIC-ONLY-NEWER", (_component("newer", "guaranteed", "10", verified_on=AS_OF),))
    older = _route("SYNTHETIC-ONLY-OLDER", (_component("older", "guaranteed", "10", verified_on=AS_OF - timedelta(days=1)),))
    affiliate = _route(
        "SYNTHETIC-ONLY-AFFILIATE",
        (_component("affiliate", "guaranteed", "10", verified_on=AS_OF),),
        link_class=LinkClass.AFFILIATE,
    )
    result = optimize(_scenario(), (affiliate, older, newer))

    assert [route.route_id for route in result.ranked_routes] == [
        "SYNTHETIC-ONLY-NEWER", "SYNTHETIC-ONLY-AFFILIATE", "SYNTHETIC-ONLY-OLDER",
    ]
    reversed_result = optimize(_scenario(), tuple(reversed((affiliate, older, newer))))
    assert reversed_result.ranked_routes == result.ranked_routes


def test_freshness_tie_break_uses_the_stalest_component_in_a_route() -> None:
    multi_layer = _route(
        "SYNTHETIC-ONLY-MULTI",
        _compatible_pair(
            _component("multi-new", "guaranteed", "5", verified_on=AS_OF),
            _component("multi-old", "guaranteed", "5", verified_on=AS_OF - timedelta(days=10)),
        ),
    )
    uniformly_fresher = _route(
        "SYNTHETIC-ONLY-UNIFORM",
        (_component("uniform", "guaranteed", "10", verified_on=AS_OF - timedelta(days=1)),),
    )

    result = optimize(_scenario(), (multi_layer, uniformly_fresher))

    assert [route.route_id for route in result.ranked_routes] == [
        "SYNTHETIC-ONLY-UNIFORM", "SYNTHETIC-ONLY-MULTI",
    ]


def test_fragility_estimated_only_hidden_affiliate_and_fees_exceeding_value() -> None:
    simple = _route("SYNTHETIC-ONLY-SIMPLE", (_component("simple", "guaranteed", "10"),))
    fragile = _route(
        "SYNTHETIC-ONLY-FRAGILE",
        (_component("fragile", "guaranteed", "10", conditions=("SYNTHETIC-ONLY-CONDITION",)),),
    )
    estimated = _route("SYNTHETIC-ONLY-ESTIMATED", (_component("estimated", "estimated", "5", value_max="10"),))
    expensive = _route(
        "SYNTHETIC-ONLY-EXPENSIVE",
        (_component("expensive", "guaranteed", "2"),),
        route_fees=(UserFee("SYNTHETIC-ONLY-FEE", Decimal("3"), "INR"),),
    )
    affiliate = _route(
        "SYNTHETIC-ONLY-HIDDEN",
        (_component("hidden", "guaranteed", "99"),),
        link_class=LinkClass.AFFILIATE,
    )
    scenario = _scenario(allowed_link_classes=frozenset({LinkClass.OFFICIAL}))

    result = optimize(scenario, (fragile, estimated, expensive, affiliate, simple))

    assert [route.route_id for route in result.ranked_routes] == [
        "SYNTHETIC-ONLY-SIMPLE", "SYNTHETIC-ONLY-FRAGILE", "SYNTHETIC-ONLY-ESTIMATED", "SYNTHETIC-ONLY-EXPENSIVE",
    ]
    assert result.ranked_routes[2].net_guaranteed == Decimal("0")
    assert result.ranked_routes[3].net_guaranteed == Decimal("-1")
    assert result.rejected_routes[0].reasons == ("affiliate routes are hidden by the user",)


def test_validation_duplicate_routes_currency_and_purity() -> None:
    with pytest.raises(ValueError, match="currency"):
        PurchaseScenario(Decimal("1"), "1N2", AS_OF)
    with pytest.raises(ValueError, match="currency"):
        _component("invalid", "guaranteed", "1", currency="inr")
    with pytest.raises(ValueError, match="official_reference"):
        RouteCandidate("x", "x", (_component("x", "guaranteed", "1"),), ("x",), LinkClass.OFFICIAL, "")
    with pytest.raises(ValueError, match="anonymous HTTPS"):
        _component("http", "guaranteed", "1", source_ref="http://example.invalid/source")
    with pytest.raises(ValueError, match="anonymous HTTPS"):
        _route("SYNTHETIC-ONLY-BAD-URL", (_component("url", "guaranteed", "1"),), official_reference="javascript:alert(1)")
    with pytest.raises(ValueError, match="invalid HTTPS port"):
        _route("SYNTHETIC-ONLY-BAD-PORT", (_component("port", "guaranteed", "1"),), official_reference="https://example.invalid:99999")
    with pytest.raises(ValueError, match="named valuation"):
        _component("unvalued", "estimated", "1", valuation_name=None)
    route = _route("SYNTHETIC-ONLY-DUPLICATE", (_component("pure", "guaranteed", "200"),))
    with pytest.raises(ValueError, match="route IDs"):
        optimize(_scenario(), (route, route))

    result = optimize(_scenario(), (route,))
    assert route.components[0].value_max == Decimal("200")
    assert result.ranked_routes[0].components[0].value_max == Decimal("100")
    with pytest.raises(FrozenInstanceError):
        result.ranked_routes[0].net_guaranteed = Decimal("0")  # type: ignore[misc]


def test_class_budgets_allocate_in_route_order_and_keep_contributions_consistent() -> None:
    route = _route(
        "SYNTHETIC-ONLY-BUDGET",
        _compatible_components((
            _component("first", "conditional", "40", value_max="70"),
            _component("second", "conditional", "40", value_max="70"),
            _component("third", "conditional", "1", value_max="1"),
        )),
    )

    result = optimize(_scenario(), (route,))
    ranked = result.ranked_routes[0]

    assert [(item.value_min, item.value_max) for item in ranked.components] == [
        (Decimal("40"), Decimal("70")), (Decimal("30"), Decimal("30")), (Decimal("0"), Decimal("0")),
    ]
    assert (ranked.conditional_min, ranked.conditional_max) == (Decimal("70"), Decimal("100"))


def test_time_limited_rules_use_thirty_day_recency_while_general_rules_use_ninety() -> None:
    timely = _route(
        "SYNTHETIC-ONLY-TIMELY",
        (_component("timely", "guaranteed", "1", time_limited=True, verified_on=AS_OF - timedelta(days=30)),),
    )
    expired_evidence = _route(
        "SYNTHETIC-ONLY-TIME-OLD",
        (_component("time-old", "guaranteed", "1", time_limited=True, verified_on=AS_OF - timedelta(days=31)),),
    )
    general = _route(
        "SYNTHETIC-ONLY-GENERAL", (_component("general", "guaranteed", "1", verified_on=AS_OF - timedelta(days=31)),)
    )

    result = optimize(_scenario(), (timely, expired_evidence, general))

    assert {route.route_id for route in result.ranked_routes} == {"SYNTHETIC-ONLY-TIMELY", "SYNTHETIC-ONLY-GENERAL"}
    assert "older than 30 days" in result.rejected_routes[0].reasons[0]


def test_official_only_filters_all_other_link_classes_and_evidence_precedes_affiliate_penalty() -> None:
    official = _route("SYNTHETIC-ONLY-OFFICIAL", (_component("official", "guaranteed", "10", evidence_tier=EvidenceTier.LOW),))
    third_party = _route(
        "SYNTHETIC-ONLY-THIRD", (_component("third", "guaranteed", "10"),), link_class=LinkClass.THIRD_PARTY
    )
    affiliate = _route(
        "SYNTHETIC-ONLY-AFFILIATE-BEST", (_component("affiliate-best", "guaranteed", "10", evidence_tier=EvidenceTier.HIGH),), link_class=LinkClass.AFFILIATE
    )
    official_only = optimize(_scenario(allowed_link_classes=frozenset({LinkClass.OFFICIAL})), (official, third_party, affiliate))
    comparison = optimize(_scenario(), (affiliate, official))

    assert [route.route_id for route in official_only.ranked_routes] == ["SYNTHETIC-ONLY-OFFICIAL"]
    assert {route.route_id for route in official_only.rejected_routes} == {"SYNTHETIC-ONLY-THIRD", "SYNTHETIC-ONLY-AFFILIATE-BEST"}
    assert [route.route_id for route in comparison.ranked_routes] == ["SYNTHETIC-ONLY-AFFILIATE-BEST", "SYNTHETIC-ONLY-OFFICIAL"]


def test_worst_evidence_tier_breaks_otherwise_equal_routes_after_freshness_and_fragility() -> None:
    high = _route("SYNTHETIC-ONLY-HIGH", (_component("high", "guaranteed", "10", evidence_tier=EvidenceTier.HIGH),))
    low = _route("SYNTHETIC-ONLY-LOW", (_component("low", "guaranteed", "10", evidence_tier=EvidenceTier.LOW),))

    result = optimize(_scenario(), (low, high))

    assert [route.route_id for route in result.ranked_routes] == ["SYNTHETIC-ONLY-HIGH", "SYNTHETIC-ONLY-LOW"]


def test_canonical_benefit_rule_identity_prevents_alias_double_counting() -> None:
    rule_id = _rule_id("canonical-rule")
    aliases = _compatible_pair(
        _component(
            "alias-one",
            "guaranteed",
            "40",
            benefit_rule_id=rule_id,
            cap_group="SYNTHETIC-ONLY-CAP-ONE",
            source_ref="https://example.invalid/synthetic-alias-one",
        ),
        _component(
            "alias-two",
            "guaranteed",
            "40",
            benefit_rule_id=rule_id,
            cap_group="SYNTHETIC-ONLY-CAP-TWO",
            source_ref="https://example.invalid/synthetic-alias-two",
        ),
    )
    route = _route("SYNTHETIC-ONLY-ALIASES", aliases)

    result = optimize(_scenario(), (route,))

    assert result.ranked_routes == ()
    assert result.rejected_routes[0].reasons == (
        f"{rule_id}: canonical benefit rule appears more than once",
    )


def test_official_routes_require_a_caller_approved_origin() -> None:
    approved = _route("SYNTHETIC-ONLY-APPROVED", (_component("approved", "guaranteed", "1"),))
    mislabeled = _route(
        "SYNTHETIC-ONLY-MISLABELED",
        (_component("mislabeled", "guaranteed", "1"),),
        official_reference="https://affiliate.invalid/synthetic",
    )

    result = optimize(_scenario(), (approved, mislabeled))

    assert [route.route_id for route in result.ranked_routes] == ["SYNTHETIC-ONLY-APPROVED"]
    assert result.rejected_routes[0].reasons == (
        "official route origin is not in the caller-approved origin set",
    )


def test_money_is_finite_bounded_scaled_and_outputs_are_quantized() -> None:
    with pytest.raises(ValueError, match="finite Decimal"):
        PurchaseScenario(Decimal("NaN"), "INR", AS_OF)
    with pytest.raises(ValueError, match="finite Decimal"):
        UserFee("SYNTHETIC-ONLY-NAN", Decimal("Infinity"), "INR")
    with pytest.raises(ValueError, match="maximum monetary magnitude"):
        _component("huge", "guaranteed", "1E+10")
    with pytest.raises(ValueError, match="maximum decimal scale"):
        _component("precise", "guaranteed", "1.0000001")
    with pytest.raises(ValueError, match="finite Decimal"):
        _component("infinite-cap", "guaranteed", "1", per_transaction_cap=Decimal("-Infinity"))

    scenario = _scenario(amount=Decimal("100.000000"))
    route = _route("SYNTHETIC-ONLY-ROUNDING", (_component("rounding", "guaranteed", "1.235"),))
    result = optimize(scenario, (route,))

    assert result.ranked_routes[0].components[0].value_max == Decimal("1.24")
    assert result.ranked_routes[0].net_guaranteed == Decimal("1.24")


def test_canonical_rule_ids_and_origins_are_strict_and_ports_are_exact() -> None:
    canonical = _rule_id("strict")
    bypasses = (f" {canonical}", canonical.upper(), f"urn:uuid:{canonical}", f"{{{canonical}}}", "０" * 36, "not-a-uuid")
    for bypass in bypasses:
        with pytest.raises(ValueError, match="canonical lowercase UUID"):
            _component("bypass", "guaranteed", "1", benefit_rule_id=bypass)

    host_case = optimize(
        _scenario(approved_official_origins=frozenset({"https://EXAMPLE.invalid"})),
        (_route("SYNTHETIC-ONLY-HOST-CASE", (_component("host-case", "guaranteed", "1"),)),),
    )
    default_port = optimize(
        _scenario(),
        (_route("SYNTHETIC-ONLY-DEFAULT-PORT", (_component("default-port", "guaranteed", "1"),), official_reference="https://example.invalid:443/path"),),
    )
    non_default = optimize(
        _scenario(),
        (_route("SYNTHETIC-ONLY-8443", (_component("8443", "guaranteed", "1"),), official_reference="https://example.invalid:8443/path"),),
    )
    admitted_8443 = optimize(
        _scenario(approved_official_origins=frozenset({"https://example.invalid:8443"})),
        (_route("SYNTHETIC-ONLY-8443-ADMITTED", (_component("8443-admitted", "guaranteed", "1"),), official_reference="https://example.invalid:8443/path"),),
    )

    assert host_case.ranked_routes
    assert default_port.ranked_routes
    assert "origin is not" in non_default.rejected_routes[0].reasons[0]
    assert admitted_8443.ranked_routes
    with pytest.raises(ValueError, match="path, query, or fragment"):
        _scenario(approved_official_origins=frozenset({"https://example.invalid/path?query=1"}))
    with pytest.raises(ValueError, match="anonymous HTTPS"):
        _route("SYNTHETIC-ONLY-USERINFO", (_component("userinfo", "guaranteed", "1"),), official_reference="https://user@example.invalid")
    with pytest.raises(ValueError, match="DNS host"):
        _route("SYNTHETIC-ONLY-IP", (_component("ip", "guaranteed", "1"),), official_reference="https://127.0.0.1/path")
    with pytest.raises(ValueError, match="DNS host"):
        _route("SYNTHETIC-ONLY-IPV6", (_component("ipv6", "guaranteed", "1"),), official_reference="https://[::1]/path")


def test_fixed_currency_minor_units_round_inr_and_jpy_and_reject_unknown_currency() -> None:
    inr = optimize(_scenario(), (_route("SYNTHETIC-ONLY-INR", (_component("inr", "guaranteed", "1.235"),)),))
    jpy_scenario = PurchaseScenario(
        amount=Decimal("100"),
        currency="JPY",
        as_of=AS_OF,
        approved_official_origins=frozenset({"https://example.invalid"}),
    )
    jpy = optimize(jpy_scenario, (_route("SYNTHETIC-ONLY-JPY", (_component("jpy", "guaranteed", "1.5", currency="JPY"),)),))

    assert inr.ranked_routes[0].net_guaranteed == Decimal("1.24")
    assert jpy.ranked_routes[0].net_guaranteed == Decimal("2")
    with pytest.raises(ValueError, match="unsupported"):
        PurchaseScenario(Decimal("1"), "AUD", AS_OF)


def test_plain_string_enums_are_coerced_and_invalid_values_are_typed() -> None:
    scenario = PurchaseScenario(
        Decimal("1"), "INR", AS_OF,
        allowed_link_classes=frozenset({"official"}),  # type: ignore[arg-type]
        approved_official_origins=frozenset({"https://example.invalid"}),
    )
    component = replace(
        _component("strings", "guaranteed", "1"),
        value_class="guaranteed", evidence_tier="high", freshness="fresh",  # type: ignore[arg-type]
    )
    route = replace(_route("SYNTHETIC-ONLY-STRINGS", (component,)), link_class="official")  # type: ignore[arg-type]
    assert scenario.allowed_link_classes == frozenset({LinkClass.OFFICIAL})
    assert (component.value_class, component.evidence_tier, component.freshness, route.link_class) == (
        ComponentValueClass.GUARANTEED, EvidenceTier.HIGH, Freshness.FRESH, LinkClass.OFFICIAL,
    )
    with pytest.raises(ValueError, match="value_class"):
        replace(component, value_class="invalid")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="allowed_link_classes"):
        PurchaseScenario(Decimal("1"), "INR", AS_OF, allowed_link_classes=frozenset({"invalid"}), approved_official_origins=frozenset({"https://example.invalid"}))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="must not be empty"):
        PurchaseScenario(Decimal("1"), "INR", AS_OF, allowed_link_classes=frozenset(), approved_official_origins=frozenset({"https://example.invalid"}))
    with pytest.raises(ValueError, match="must not be empty"):
        PurchaseScenario(Decimal("1"), "INR", AS_OF, approved_official_origins=frozenset())


def test_public_dns_source_refs_uuid_versions_and_idna_are_strict() -> None:
    for source_ref in (
        "https://localhost/source", "https://127.0.0.1/source", "https://[::1]/source",
        "https://example.invalid./source", "https://-bad.invalid/source", "https://bad-.invalid/source",
        "https://example.invalid:99999/source",
    ):
        with pytest.raises(ValueError, match="DNS host|HTTPS port"):
            _component("bad-source", "guaranteed", "1", source_ref=source_ref)
    unicode_ref = _component("unicode-source", "guaranteed", "1", source_ref="https://täst.invalid/source")
    assert unicode_ref.source_refs == ("https://xn--tst-qla.invalid/source",)
    for rule_id in (str(uuid1()), str(uuid3(NAMESPACE_DNS, "synthetic")), str(uuid4()), str(uuid5(NAMESPACE_URL, "https://example.invalid/synthetic"))):
        assert _component("uuid", "guaranteed", "1", benefit_rule_id=rule_id).benefit_rule_id == rule_id
    with pytest.raises(ValueError, match="canonical lowercase UUID"):
        _component("nil", "guaranteed", "1", benefit_rule_id="00000000-0000-0000-0000-000000000000")


def test_no_verified_route_is_explicit_and_never_encourages_purchase() -> None:
    rejected = _route("SYNTHETIC-ONLY-STALE", (_component("stale", "guaranteed", "1", freshness=Freshness.STALE),))
    result = optimize(_scenario(), (rejected,))
    assert result.ranked_routes == ()
    assert (result.status, result.guidance) == (
        "no_verified_route",
        "No verified route is available for this scenario; do not infer or take a purchase action.",
    )


def test_value_class_budgets_are_separate_non_additive_and_exhaust_independently() -> None:
    route = _route(
        "SYNTHETIC-ONLY-CLASS-BUDGETS",
        _compatible_components((
            _component("g-one", "guaranteed", "80"), _component("g-two", "guaranteed", "80"),
            _component("e-one", "estimated", "80"), _component("e-two", "estimated", "80"),
        )),
    )
    ranked = optimize(_scenario(), (route,)).ranked_routes[0]
    assert (ranked.guaranteed_before_fees, ranked.estimated_min, ranked.estimated_max) == (
        Decimal("100"), Decimal("100"), Decimal("100"),
    )
    assert ranked.value_class_totals_are_non_additive is True
    assert not hasattr(ranked, "combined_total")


def test_expiry_fee_currency_and_duplicate_fee_labels_are_fail_closed() -> None:
    ending_today = _route("SYNTHETIC-ONLY-ENDS-TODAY", (_component("today", "guaranteed", "1", expires_on=AS_OF),))
    expired_tomorrow = _route("SYNTHETIC-ONLY-EXPIRED-TOMORROW", (_component("tomorrow", "guaranteed", "1", expires_on=AS_OF - timedelta(days=1)),))
    result = optimize(_scenario(), (ending_today, expired_tomorrow))
    assert [item.route_id for item in result.ranked_routes] == ["SYNTHETIC-ONLY-ENDS-TODAY"]
    with pytest.raises(ValueError, match="fee currency"):
        _scenario(user_fees=(UserFee("SYNTHETIC-ONLY-FEE", Decimal("1"), "USD"),))
    with pytest.raises(ValueError, match="unsupported"):
        UserFee("SYNTHETIC-ONLY-UNKNOWN", Decimal("1"), "AUD")
    duplicate = _route("SYNTHETIC-ONLY-DUPLICATE-FEE", (_component("fee", "guaranteed", "1"),), route_fees=(UserFee("synthetic-only-fee", Decimal("1"), "INR"),))
    with pytest.raises(ValueError, match="fee labels"):
        optimize(_scenario(user_fees=(UserFee("SYNTHETIC-ONLY-FEE", Decimal("1"), "INR"),)), (duplicate,))


def test_input_collections_are_copied_and_zero_allowance_is_not_unlimited() -> None:
    source_refs = ["https://example.invalid/synthetic-deep"]
    conditions = ["SYNTHETIC-ONLY-CONDITION"]
    assumptions = ["SYNTHETIC-ONLY-ASSUMPTION"]
    component = replace(_component("deep", "guaranteed", "10"), source_refs=source_refs, conditions=conditions, assumptions=assumptions, remaining_allowance=Decimal("0"))  # type: ignore[arg-type]
    components = [component]
    instructions = ["SYNTHETIC-ONLY-INSTRUCTION"]
    route = replace(_route("SYNTHETIC-ONLY-DEEP", (component,)), components=components, instructions=instructions)  # type: ignore[arg-type]
    source_refs.append("https://example.invalid/mutated")
    conditions.append("SYNTHETIC-ONLY-MUTATED")
    assumptions.append("SYNTHETIC-ONLY-MUTATED")
    components.append(_component("extra", "guaranteed", "1"))
    instructions.append("SYNTHETIC-ONLY-MUTATED")
    assert component.source_refs == ("https://example.invalid/synthetic-deep",)
    assert component.conditions == ("SYNTHETIC-ONLY-CONDITION",)
    assert component.assumptions == ("SYNTHETIC-ONLY-ASSUMPTION",)
    assert route.components == (component,)
    assert route.instructions == ("SYNTHETIC-ONLY-INSTRUCTION",)
    ranked = optimize(_scenario(), (route,)).ranked_routes[0]
    assert ranked.guaranteed_before_fees == Decimal("0")


def test_ranking_order_uses_only_policy_factors_then_route_id() -> None:
    simple_older = _route("SYNTHETIC-ONLY-SIMPLE", (_component("simple", "guaranteed", "10", verified_on=AS_OF - timedelta(days=1)),))
    fragile_newer = _route("SYNTHETIC-ONLY-FRAGILE-NEW", (_component("fragile", "guaranteed", "10", conditions=("SYNTHETIC-ONLY-CONDITION",)),))
    fresh_low = _route("SYNTHETIC-ONLY-FRESH-LOW", (_component("fresh-low", "guaranteed", "10", evidence_tier=EvidenceTier.LOW),))
    old_high = _route("SYNTHETIC-ONLY-OLD-HIGH", (_component("old-high", "guaranteed", "10", evidence_tier=EvidenceTier.HIGH, verified_on=AS_OF - timedelta(days=1)),))
    high_multi = _route("SYNTHETIC-ONLY-HIGH-MULTI", _compatible_pair(_component("high-a", "guaranteed", "5", evidence_tier=EvidenceTier.HIGH), _component("high-b", "guaranteed", "5", evidence_tier=EvidenceTier.HIGH)))
    low_simple = _route("SYNTHETIC-ONLY-LOW-SIMPLE", (_component("low", "guaranteed", "10", evidence_tier=EvidenceTier.LOW),))
    affiliate_simple = _route("SYNTHETIC-ONLY-AFFILIATE-SIMPLE", (_component("affiliate", "guaranteed", "10"),), link_class=LinkClass.AFFILIATE)
    official_multi = _route("SYNTHETIC-ONLY-OFFICIAL-MULTI", _compatible_pair(_component("official-a", "guaranteed", "5"), _component("official-b", "guaranteed", "5")))
    route_a = _route("SYNTHETIC-ONLY-A", (_component("a", "guaranteed", "7"),))
    route_b = _route("SYNTHETIC-ONLY-B", (_component("b", "guaranteed", "7", value_max="7"),))
    result = optimize(_scenario(), (fragile_newer, simple_older, old_high, fresh_low, low_simple, high_multi, official_multi, affiliate_simple, route_b, route_a))
    ordered = [item.route_id for item in result.ranked_routes]
    assert ordered.index("SYNTHETIC-ONLY-SIMPLE") < ordered.index("SYNTHETIC-ONLY-FRAGILE-NEW")
    assert ordered.index("SYNTHETIC-ONLY-FRESH-LOW") < ordered.index("SYNTHETIC-ONLY-OLD-HIGH")
    assert ordered.index("SYNTHETIC-ONLY-HIGH-MULTI") < ordered.index("SYNTHETIC-ONLY-LOW-SIMPLE")
    assert ordered.index("SYNTHETIC-ONLY-AFFILIATE-SIMPLE") < ordered.index("SYNTHETIC-ONLY-OFFICIAL-MULTI")
    assert ordered.index("SYNTHETIC-ONLY-A") < ordered.index("SYNTHETIC-ONLY-B")


def _scenario(
    *,
    amount: Decimal = Decimal("100"),
    user_fees: tuple[UserFee, ...] = (),
    allowed_link_classes: frozenset[LinkClass] = frozenset(LinkClass),
    approved_official_origins: frozenset[str] = frozenset({"https://example.invalid"}),
) -> PurchaseScenario:
    return PurchaseScenario(
        amount=amount,
        currency="INR",
        as_of=AS_OF,
        user_fees=user_fees,
        allowed_link_classes=allowed_link_classes,
        approved_official_origins=approved_official_origins,
    )


def _route(
    route_id: str,
    components: tuple[RouteComponent, ...],
    *,
    link_class: LinkClass = LinkClass.OFFICIAL,
    route_fees: tuple[UserFee, ...] = (),
    official_reference: str = "https://example.invalid/synthetic-official",
) -> RouteCandidate:
    return RouteCandidate(
        id=route_id,
        label=route_id,
        components=components,
        instructions=("SYNTHETIC-ONLY-FOLLOW-INSTRUCTIONS",),
        link_class=link_class,
        official_reference=official_reference,
        route_fees=route_fees,
    )


def _component(
    component_id: str,
    value_class: str,
    value_min: str,
    *,
    value_max: str | None = None,
    currency: str = "INR",
    freshness: Freshness = Freshness.FRESH,
    verified_on: date = AS_OF,
    reviewed: bool = True,
    compatible_with: frozenset[str] = frozenset(),
    conditions: tuple[str, ...] = (),
    expires_on: date | None = None,
    per_transaction_cap: Decimal | None = None,
    remaining_allowance: Decimal | None = None,
    cap_group: str | None = None,
    time_limited: bool = False,
    evidence_tier: EvidenceTier = EvidenceTier.MEDIUM,
    valuation_name: str | None = "SYNTHETIC-ONLY-VALUATION",
    source_ref: str | None = None,
    benefit_rule_id: str | None = None,
) -> RouteComponent:
    return RouteComponent(
        id=component_id,
        label=f"SYNTHETIC-ONLY-{component_id}",
        benefit_rule_id=benefit_rule_id or _rule_id(component_id),
        value_class=ComponentValueClass(value_class),
        currency=currency,
        value_min=Decimal(value_min),
        value_max=Decimal(value_max or value_min),
        source_refs=(source_ref or f"https://example.invalid/synthetic-source-{component_id}",),
        evidence_tier=evidence_tier,
        freshness=freshness,
        verified_on=verified_on,
        reviewed=reviewed,
        compatible_with=compatible_with,
        conditions=conditions,
        expires_on=expires_on,
        per_transaction_cap=per_transaction_cap,
        remaining_allowance=remaining_allowance,
        cap_group=cap_group,
        time_limited=time_limited,
        valuation_name=valuation_name,
    )


def _compatible_pair(first: RouteComponent, second: RouteComponent) -> tuple[RouteComponent, ...]:
    return _compatible_components((first, second))


def _compatible_components(components: tuple[RouteComponent, ...]) -> tuple[RouteComponent, ...]:
    return tuple(
        replace(component, compatible_with=frozenset(other.id for other in components if other.id != component.id))
        for component in components
    )


def _rule_id(value: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"https://example.invalid/synthetic-rule/{value}"))
