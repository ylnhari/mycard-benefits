from __future__ import annotations

import json
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from mycard_benefits.catalog import Catalog, CatalogLoadError, load_catalog
from mycard_benefits.catalog.model import BenefitCategory, InheritanceRule, RuleOwner
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

CATALOG_ROOT = Path(__file__).parents[1] / "catalog"
SYNTHETIC_CATALOG_ROOT = Path(__file__).parent / "fixtures" / "synthetic_catalog"


def test_synthetic_catalog_loads_deterministically() -> None:
    first = load_catalog(SYNTHETIC_CATALOG_ROOT)
    second = load_catalog(SYNTHETIC_CATALOG_ROOT)

    assert first == second
    offering = first.offering_by_slug("synthetic-example-in-visa")
    assert offering is not None
    assert offering.network_id == "visa"
    assert [item.id for item in first.benefits_for(offering.id, date(2026, 8, 6))] == [
        "33333333-3333-4333-8333-333333333333"
    ]


def test_catalog_benefits_for_never_falls_back_outside_inheritance_interval() -> None:
    catalog = load_catalog(SYNTHETIC_CATALOG_ROOT)
    source = next(item for item in catalog.benefits if item.benefit_type == "reward_points")
    target_offering = catalog.offering_by_slug("synthetic-example-in-mc")
    assert target_offering is not None
    inherited = source.__class__(
        **{
            **source.__dict__,
            "id": "88888888-8888-4888-8888-888888888888",
            "offering_id": target_offering.id,
            "inheritance": InheritanceRule(
                RuleOwner("network", "SYNTHETIC-ONLY-NETWORK", "SYNTHETIC-ONLY Network"),
                source.id,
                source.offering_id,
                target_offering.id,
                "visa",
                "mastercard",
                "synthetic-cobrand",
                None,
                "approved",
                True,
                date(2027, 1, 1),
                date(2027, 12, 31),
            ),
        }
    )
    bounded = Catalog(release=catalog.release, offerings=catalog.offerings, benefits=(source, inherited))
    for as_of, expected in (
        (date(2026, 12, 31), False),
        (date(2027, 1, 1), True),
        (date(2027, 6, 15), True),
        (date(2027, 12, 31), True),
        (date(2028, 1, 1), False),
    ):
        assert (inherited in bounded.benefits_for(target_offering.id, as_of)) is expected


def test_default_as_of_normalizes_release_timestamp_to_utc_date() -> None:
    catalog = load_catalog(SYNTHETIC_CATALOG_ROOT)
    shifted = replace(
        catalog,
        release=replace(
            catalog.release,
            generated_at=datetime(2026, 8, 7, 1, tzinfo=timezone(timedelta(hours=5))),
        ),
    )
    assert shifted.default_as_of == date(2026, 8, 6)


def test_india_starter_catalog_contains_real_product_variants() -> None:
    catalog = load_catalog(CATALOG_ROOT)

    assert len(catalog.offerings) >= 68
    tata_neu = catalog.offering_by_slug("hdfc-tata-neu-rupay-select-credit")
    regalia = catalog.offering_by_slug("hdfc-regalia-gold-credit")
    assert tata_neu is not None
    assert tata_neu.display_name == "Tata Neu Infinity HDFC Bank RuPay Select Credit Card"
    assert tata_neu.network_id == "rupay-select"
    assert regalia is not None
    assert regalia.display_name == "HDFC Bank Regalia Gold Credit Card"


def test_consumer_visible_catalog_keeps_rescued_states_separate_from_activation() -> None:
    catalog = load_catalog(CATALOG_ROOT)

    visible = catalog.consumer_visible_benefits()
    assert len(visible) == 60
    assert {
        state: sum(rule.state == state for rule in visible)
        for state in ("verified", "check_before_use", "sources_differ")
    } == {"verified": 1, "check_before_use": 53, "sources_differ": 6}

    verified = next(rule for rule in visible if rule.state == "verified")
    assert verified.status == "active"
    assert any(assertion.review_state == "approved" for assertion in verified.evidence)
    check_before_use = next(rule for rule in visible if rule.state == "check_before_use")
    assert check_before_use.status == "needs_review"
    assert check_before_use.id not in {
        rule.id for rule in catalog.benefits_for(check_before_use.offering_id)
    }

    divergent = next(rule for rule in visible if rule.source_divergence)
    assert divergent.state == "sources_differ"
    assert len(divergent.source_divergence) == 2
    assert {claim["benefit_type"] for claim in divergent.source_divergence} == {
        "priority_pass",
        "lounge",
    }


def test_rescued_states_never_reach_optimizer_purchase_routes() -> None:
    catalog = load_catalog(CATALOG_ROOT)
    as_of = date(2026, 8, 10)
    active_rules = catalog.visible_benefits(as_of)
    display_rules = catalog.consumer_visible_benefits(as_of)
    active_ids = {rule.id for rule in active_rules}
    uncertain_rules = tuple(rule for rule in display_rules if rule.state != "verified")

    assert active_ids
    assert all(rule.state == "verified" for rule in active_rules)
    assert active_ids.isdisjoint(rule.id for rule in uncertain_rules)

    def route_for(rule, *, reviewed: bool, benefit_state: str = "verified") -> RouteCandidate:
        component = RouteComponent(
            id=f"component-{rule.id}",
            label=rule.title,
            benefit_rule_id=rule.id,
            value_class=ComponentValueClass.GUARANTEED,
            currency="INR",
            value_min=Decimal("1"),
            value_max=Decimal("1"),
            source_refs=("https://example.com/terms",),
            evidence_tier=EvidenceTier.HIGH,
            freshness=Freshness.FRESH,
            verified_on=as_of,
            reviewed=reviewed,
            benefit_state=benefit_state,
        )
        return RouteCandidate(
            id=f"route-{rule.id}",
            label=rule.title,
            components=(component,),
            instructions=("Follow the official terms.",),
            link_class=LinkClass.OFFICIAL,
            official_reference="https://example.com/terms",
            action_link_review_state=ActionLinkReviewState.APPROVED,
        )

    with pytest.raises(ValueError, match="only verified benefit state"):
        route_for(uncertain_rules[0], reviewed=False, benefit_state="check_before_use")

    result = optimize(
        PurchaseScenario(
            amount=Decimal("100"),
            currency="INR",
            as_of=as_of,
            allowed_link_classes=frozenset({LinkClass.OFFICIAL}),
            admitted_action_origins=frozenset({"https://example.com"}),
        ),
        (route_for(active_rules[0], reviewed=True),),
    )
    assert [route.route_id for route in result.ranked_routes] == [f"route-{active_rules[0].id}"]
    assert result.rejected_routes == ()


def test_tracked_import_sample_uses_known_catalog_offerings() -> None:
    catalog = load_catalog(SYNTHETIC_CATALOG_ROOT)
    sample_path = Path(__file__).parents[1] / "samples" / "card-import.example.json"
    sample = json.loads(sample_path.read_text(encoding="utf-8"))

    assert sample["cards"]
    assert all(
        catalog.offering_by_slug(card["offering_id"]) is not None for card in sample["cards"]
    )


def test_active_rule_requires_approved_evidence(tmp_path: Path) -> None:
    _copy_catalog(tmp_path)
    path = tmp_path / "benefits" / "synthetic-example-reward.json"
    payload = json.loads(path.read_text())
    payload["evidence"][0]["review_state"] = "needs_review"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CatalogLoadError, match="active benefit requires approved"):
        load_catalog(tmp_path)


def test_active_rule_requires_one_immutable_human_review_at_every_tier(tmp_path: Path) -> None:
    _copy_catalog(tmp_path)
    path = tmp_path / "benefits" / "synthetic-example-reward.json"
    payload = json.loads(path.read_text())
    payload["evidence"][0]["reviews"] = []
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CatalogLoadError, match="human review record"):
        load_catalog(tmp_path)

    payload["review_tier"] = "high_impact"
    payload["evidence"][0]["reviews"] = [
        {
            "id": "55555555-5555-4555-8555-555555555555",
            "reviewer_id": "SYNTHETIC-ONLY-REVIEWER",
            "reviewed_at": "2026-08-06T00:00:00Z",
            "decision": "approved",
        }
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert load_catalog(tmp_path).benefits[0].review_tier == "high_impact"


def test_duplicate_reviewer_identity_is_rejected(tmp_path: Path) -> None:
    _copy_catalog(tmp_path)
    path = tmp_path / "benefits" / "synthetic-example-reward.json"
    payload = json.loads(path.read_text())
    payload["evidence"][0]["reviews"].append(
        {
            "id": "66666666-6666-4666-8666-666666666666",
            "reviewer_id": "SYNTHETIC-ONLY-REVIEWER",
            "reviewed_at": "2026-08-06T01:00:00Z",
            "decision": "approved",
        }
    )
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CatalogLoadError, match="duplicate .* reviewers"):
        load_catalog(tmp_path)


def test_review_timestamps_decisions_and_unknown_fields_fail_closed(tmp_path: Path) -> None:
    _copy_catalog(tmp_path)
    path = tmp_path / "benefits" / "synthetic-example-reward.json"
    payload = json.loads(path.read_text())
    payload["evidence"][0]["reviews"][0]["reviewed_at"] = "2025-01-01T00:00:00Z"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CatalogLoadError, match="cannot predate"):
        load_catalog(tmp_path)

    payload["evidence"][0]["reviews"][0]["reviewed_at"] = "2026-08-06T00:00:00Z"
    payload["evidence"][0]["reviews"][0]["decision"] = "rejected"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CatalogLoadError, match="approved evidence"):
        load_catalog(tmp_path)

    payload["evidence"][0]["reviews"][0]["decision"] = "approved"
    payload["unexpected"] = "SYNTHETIC-ONLY"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CatalogLoadError, match="unexpected fields"):
        load_catalog(tmp_path)


def test_committed_catalog_records_satisfy_draft_2020_12_schema() -> None:
    schema = json.loads(
        (CATALOG_ROOT / "schema" / "catalog.schema.json").read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    records = [
        CATALOG_ROOT / "schema" / "release.json",
        *(CATALOG_ROOT / "offerings").glob("*.json"),
    ]
    legacy_benefits = []
    benefit_sources = (
        (CATALOG_ROOT / "benefits").glob("*.json"),
        (Path(__file__).parent / "fixtures" / "synthetic_catalog" / "benefits").glob("*.json"),
    )
    for source in benefit_sources:
        for path in source:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if "state" not in payload and "provenance" not in payload:
                legacy_benefits.append(path)
    assert legacy_benefits
    records.extend(legacy_benefits)
    for path in records:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert not list(validator.iter_errors(payload)), path


def test_typed_benefit_schema_covers_public_rules_and_dated_inheritance(tmp_path: Path) -> None:
    _copy_catalog(tmp_path)
    path = tmp_path / "benefits" / "synthetic-example-reward.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    source_id = "66666666-6666-4666-8666-666666666666"
    source = dict(payload)
    source["id"] = source_id
    source["status"] = "historical"
    (path.parent / "synthetic-source-reward.json").write_text(json.dumps(source), encoding="utf-8")
    payload.update(
        {
            "category": "miles",
            "owners": [
                {
                    "kind": "network",
                    "id": "SYNTHETIC-ONLY-NETWORK",
                    "display_name": "SYNTHETIC-ONLY Network",
                }
            ],
            "conditions": [
                {"type": condition, "operator": "exists"}
                for condition in (
                    "welcome",
                    "milestone",
                    "annual_fee_waiver",
                    "renewal",
                    "spend_triggered",
                    "geography",
                    "currency",
                    "channel",
                    "mcc",
                    "time_window",
                )
            ],
            "earn": {
                "currency": "SYNTHETIC-ONLY-POINT",
                "rate": "2",
                "basis": "per synthetic unit",
                "scope": "synthetic checkout",
                "cap": {"period": "month", "amount": 100},
                "exclusions": ["SYNTHETIC-ONLY excluded item"],
                "rounding": "floor",
                "reversal": "reverse on refund",
                "expiry": {"kind": "unknown"},
            },
            "conversion": {
                "partner_id": "SYNTHETIC-ONLY-PARTNER",
                "ratio": "2:1",
                "fee": {"currency": "SYNTHETIC-ONLY-CURRENCY", "amount": "1"},
                "minimum": 100,
                "increment": 100,
                "expiry": {"kind": "unknown"},
                "redemption_options": ["SYNTHETIC-ONLY redemption path"],
            },
            "valuations": [
                {
                    "name": "SYNTHETIC-ONLY named range",
                    "redemption_path": "SYNTHETIC-ONLY award path",
                    "currency": "SYNTHETIC-ONLY-CURRENCY",
                    "minimum": "0.01",
                    "maximum": "0.03",
                }
            ],
            "value_class": "estimated",
            "inheritance": {
                "owner": {
                    "kind": "network",
                    "id": "SYNTHETIC-ONLY-NETWORK",
                    "display_name": "SYNTHETIC-ONLY Network",
                },
                "source_benefit_id": source_id,
                "source_offering_id": payload["offering_id"],
                "target_offering_id": payload["offering_id"],
                "source_network_id": "visa",
                "target_network_id": "visa",
                "source_co_brand_id": "synthetic-cobrand",
                "target_co_brand_id": "synthetic-cobrand",
                "review_state": "approved",
                "opt_in": True,
                "effective_from": "2026-02-01",
                "effective_to": "2026-12-31",
            },
        }
    )
    path.write_text(json.dumps(payload), encoding="utf-8")
    catalog = load_catalog(tmp_path)
    rule = next(item for item in catalog.benefits if item.id == payload["id"])
    assert rule.category is BenefitCategory.MILES
    assert rule.earn is not None and rule.earn.rounding == "floor"
    assert rule.conversion is not None and rule.conversion.increment == 100
    assert rule.valuations[0].minimum != rule.valuations[0].maximum
    assert rule.inheritance is not None and rule.inheritance.applies(date(2026, 6, 1))
    assert not rule.inheritance.applies(date(2027, 1, 1))


def test_every_public_category_has_a_validated_synthetic_shape(tmp_path: Path) -> None:
    for category in BenefitCategory:
        destination = tmp_path / category.value
        _copy_catalog(destination)
        path = destination / "benefits" / "synthetic-example-reward.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["benefit_type"] = category.value
        payload["category"] = category.value
        if category is BenefitCategory.MOVIE:
            payload.update(
                {
                    "status": "needs_review",
                    "provider": "SYNTHETIC-ONLY provider",
                    "official_reference": "https://example.invalid/synthetic-terms",
                    "redemption_steps": ["SYNTHETIC-ONLY verify terms"],
                    "exclusions": [],
                }
            )
        path.write_text(json.dumps(payload), encoding="utf-8")
        assert load_catalog(destination).benefits[0].category is category


def test_condition_predicates_evaluate_without_transaction_ingestion() -> None:
    from mycard_benefits.catalog.model import ConditionPredicate

    assert ConditionPredicate("channel", "equals", "synthetic").evaluate("synthetic")
    assert ConditionPredicate("mcc", "in", [1, 2]).evaluate(2)
    assert ConditionPredicate("spend_triggered", "between", [10, 20]).evaluate(15)
    assert ConditionPredicate("welcome", "exists").evaluate("user-set")
    assert not ConditionPredicate("currency", "equals", "USD").evaluate("INR")


def test_typed_benefit_inputs_fail_closed(tmp_path: Path) -> None:
    _copy_catalog(tmp_path)
    path = tmp_path / "benefits" / "synthetic-example-reward.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["category"] = "ambiguous-category"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CatalogLoadError, match="unsupported category"):
        load_catalog(tmp_path)

    payload["category"] = "reward_points"
    payload["valuations"] = [
        {
            "name": "SYNTHETIC-ONLY single",
            "redemption_path": "SYNTHETIC-ONLY path",
            "currency": "SYNTHETIC-ONLY-CURRENCY",
            "minimum": "1",
            "maximum": "1",
        }
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CatalogLoadError, match="range"):
        load_catalog(tmp_path)

    payload.pop("valuations")
    payload["inheritance"] = {
        "owner": {
            "kind": "network",
            "id": "SYNTHETIC-ONLY-NETWORK",
            "display_name": "SYNTHETIC-ONLY Network",
        },
        "source_benefit_id": payload["id"],
        "opt_in": False,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CatalogLoadError, match="opt_in true"):
        load_catalog(tmp_path)


@pytest.mark.parametrize("field,value", [("minimum", True), ("increment", False), ("minimum", -1)])
def test_conversion_numeric_bounds_reject_hostile_values(
    tmp_path: Path, field: str, value: object
) -> None:
    _copy_catalog(tmp_path)
    path = tmp_path / "benefits" / "synthetic-example-reward.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["conversion"] = {
        "partner_id": "SYNTHETIC-ONLY-PARTNER",
        "ratio": "1:1",
        "fee": None,
        "minimum": 1,
        "increment": 1,
        "expiry": None,
        "redemption_options": ["SYNTHETIC-ONLY path"],
    }
    payload["conversion"][field] = value
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CatalogLoadError):
        load_catalog(tmp_path)


def test_food_benefit_remains_loadable(tmp_path: Path) -> None:
    _copy_catalog(tmp_path)
    path = tmp_path / "benefits" / "synthetic-example-reward.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["benefit_type"] = payload["category"] = "food"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_catalog(tmp_path).benefits[0].category is BenefitCategory.FOOD


def test_unknown_offering_and_bad_hash_are_rejected(tmp_path: Path) -> None:
    _copy_catalog(tmp_path)
    path = tmp_path / "benefits" / "synthetic-example-reward.json"
    payload = json.loads(path.read_text())
    payload["offering_id"] = "55555555-5555-4555-8555-555555555555"
    payload["evidence"][0]["content_sha256"] = "not-a-digest"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CatalogLoadError, match="SHA-256"):
        load_catalog(tmp_path)


def test_conflicts_must_reference_another_known_rule(tmp_path: Path) -> None:
    _copy_catalog(tmp_path)
    path = tmp_path / "benefits" / "synthetic-example-reward.json"
    payload = json.loads(path.read_text())
    payload["conflicts_with"] = [payload["id"]]
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CatalogLoadError, match="conflicts_with"):
        load_catalog(tmp_path)


def test_production_catalog_contains_no_synthetic_records_or_invalid_urls() -> None:
    catalog = load_catalog(CATALOG_ROOT)
    assert catalog.offerings
    for offering in catalog.offerings:
        assert "synthetic" not in offering.slug.lower()
        assert "synthetic" not in offering.display_name.lower()
        assert "synthetic" not in offering.issuer_id.lower()
        assert "example.invalid" not in offering.slug.lower()
        for alias in offering.aliases:
            assert "synthetic" not in alias.lower()
    for rule in catalog.benefits:
        assert "synthetic" not in rule.title.lower()
        for assertion in rule.evidence:
            assert not assertion.url.endswith(".invalid")
            assert "example.invalid" not in assertion.url.lower()
            for review in assertion.reviews:
                assert "synthetic" not in review.reviewer_id.lower()


def _copy_catalog(destination: Path) -> None:
    for relative in (
        "schema/release.json",
        "offerings/synthetic-example-in.json",
        "offerings/synthetic-example-in-mc.json",
        "benefits/synthetic-example-reward.json",
        "relationships/synthetic-example-relationship.json",
    ):
        source = SYNTHETIC_CATALOG_ROOT / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


# ---- MC-021: relationship graph tests ----


def test_relationship_graph_loads_and_validates(tmp_path: Path) -> None:
    _copy_catalog(tmp_path)
    catalog = load_catalog(tmp_path)
    assert len(catalog.relationships) == 1
    rel = catalog.relationships[0]
    assert rel.relationship_type == "reskinned"
    assert rel.from_offering_id == "22222222-2222-4222-8222-222222222222"
    assert rel.to_offering_id == "22222222-2222-4222-8222-222222222233"
    assert rel.review_state == "approved"


def test_relationship_self_reference_rejected(tmp_path: Path) -> None:
    _copy_catalog(tmp_path)
    path = tmp_path / "relationships" / "synthetic-example-relationship.json"
    payload = json.loads(path.read_text())
    payload["to_offering_id"] = payload["from_offering_id"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CatalogLoadError, match="must not reference itself"):
        load_catalog(tmp_path)


def test_relationship_unknown_offering_rejected(tmp_path: Path) -> None:
    _copy_catalog(tmp_path)
    path = tmp_path / "relationships" / "synthetic-example-relationship.json"
    payload = json.loads(path.read_text())
    payload["to_offering_id"] = "99999999-9999-4999-8999-999999999999"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CatalogLoadError, match="unknown to_offering_id"):
        load_catalog(tmp_path)


def test_relationship_cycle_rejected(tmp_path: Path) -> None:
    _copy_catalog(tmp_path)
    path = tmp_path / "relationships" / "synthetic-example-relationship.json"
    payload = json.loads(path.read_text())
    payload["relationship_type"] = "renamed"
    path.write_text(json.dumps(payload), encoding="utf-8")

    reverse = {
        "id": "88888888-8888-4888-8888-888888888888",
        "from_offering_id": "22222222-2222-4222-8222-222222222233",
        "to_offering_id": "22222222-2222-4222-8222-222222222222",
        "relationship_type": "renamed",
        "review_state": "approved",
        "evidence": payload["evidence"],
    }
    reverse_path = tmp_path / "relationships" / "reverse.json"
    reverse_path.write_text(json.dumps(reverse), encoding="utf-8")
    with pytest.raises(CatalogLoadError, match="cycle"):
        load_catalog(tmp_path)


def test_relationship_bad_review_state_rejected(tmp_path: Path) -> None:
    _copy_catalog(tmp_path)
    path = tmp_path / "relationships" / "synthetic-example-relationship.json"
    payload = json.loads(path.read_text())
    payload["review_state"] = "rejected"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CatalogLoadError, match="unsupported relationship review_state"):
        load_catalog(tmp_path)


def test_relationship_requires_valid_approved_evidence(tmp_path: Path) -> None:
    _copy_catalog(tmp_path)
    path = tmp_path / "relationships" / "synthetic-example-relationship.json"
    payload = json.loads(path.read_text())
    payload["evidence"][0]["review_state"] = "needs_review"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(
        CatalogLoadError,
        match="approved relationship requires approved medium/high-confidence evidence",
    ):
        load_catalog(tmp_path)


def test_names_never_infer_relationships(tmp_path: Path) -> None:
    """Similarly-named offerings must not produce auto-inferred edges."""
    _copy_catalog(tmp_path)
    # Remove all explicit relationships
    for f in (tmp_path / "relationships").glob("*.json"):
        f.unlink()
    catalog = load_catalog(tmp_path)
    # Two offerings with similar names — no inferred relationship
    assert len(catalog.offerings) == 2
    assert len(catalog.relationships) == 0


# ---- MC-070: temporal and versioned benefits tests ----


def test_missing_end_date_means_unknown_not_perpetual(tmp_path: Path) -> None:
    _copy_catalog(tmp_path)
    catalog = load_catalog(tmp_path)
    rule = catalog.benefits[0]
    assert rule.effective_to is None
    assert rule.end_date_known is False
    assert rule.rule_version == 1
    assert rule.supersedes is None


def test_expired_and_superseded_rules_remain_historical(tmp_path: Path) -> None:
    _copy_catalog(tmp_path)
    path = tmp_path / "benefits" / "synthetic-example-reward.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["status"] = "historical"
    path.write_text(json.dumps(payload), encoding="utf-8")

    catalog = load_catalog(tmp_path)
    offering_id = payload["offering_id"]
    assert catalog.benefits_for(offering_id) == ()
    historical = catalog.historical_benefits_for(offering_id)
    assert len(historical) == 1
    assert historical[0].status == "historical"


def test_supersession_validation_and_cycle_prevention(tmp_path: Path) -> None:
    _copy_catalog(tmp_path)
    path = tmp_path / "benefits" / "synthetic-example-reward.json"
    v1_payload = json.loads(path.read_text(encoding="utf-8"))
    v1_id = v1_payload["id"]
    v1_payload["status"] = "superseded"
    v1_payload["rule_version"] = 1
    path.write_text(json.dumps(v1_payload), encoding="utf-8")

    v2_id = "88888888-8888-4888-8888-888888888888"
    v2_payload = dict(v1_payload)
    v2_payload["id"] = v2_id
    v2_payload["status"] = "active"
    v2_payload["rule_version"] = 2
    v2_payload["supersedes"] = v1_id
    v2_path = tmp_path / "benefits" / "synthetic-example-reward-v2.json"
    v2_path.write_text(json.dumps(v2_payload), encoding="utf-8")

    catalog = load_catalog(tmp_path)
    active = catalog.benefits_for(v1_payload["offering_id"])
    assert len(active) == 1
    assert active[0].id == v2_id
    assert active[0].rule_version == 2
    assert active[0].supersedes == v1_id

    # Test self-supersession failure
    v2_payload["supersedes"] = v2_id
    v2_path.write_text(json.dumps(v2_payload), encoding="utf-8")
    with pytest.raises(CatalogLoadError, match="cannot supersede itself"):
        load_catalog(tmp_path)

    # Test cross-offering supersession failure
    v2_payload["supersedes"] = v1_id
    v2_payload["offering_id"] = "22222222-2222-4222-8222-222222222233"
    v2_path.write_text(json.dumps(v2_payload), encoding="utf-8")
    with pytest.raises(CatalogLoadError, match="from a different offering"):
        load_catalog(tmp_path)
    v2_payload["offering_id"] = v1_payload["offering_id"]

    # Test cross-benefit-type supersession failure
    v2_payload["benefit_type"] = "lounge"
    v2_path.write_text(json.dumps(v2_payload), encoding="utf-8")
    with pytest.raises(CatalogLoadError, match="of a different benefit_type"):
        load_catalog(tmp_path)
    v2_payload["benefit_type"] = v1_payload["benefit_type"]

    # Test rule_version must be strictly greater failure
    v2_payload["rule_version"] = 1
    v2_path.write_text(json.dumps(v2_payload), encoding="utf-8")
    with pytest.raises(
        CatalogLoadError, match="must be strictly greater than superseded rule_version"
    ):
        load_catalog(tmp_path)
    v2_payload["rule_version"] = 2

    # Test superseding active rule failure
    v1_payload["status"] = "active"
    v1_path = tmp_path / "benefits" / "synthetic-example-reward.json"
    v1_path.write_text(json.dumps(v1_payload), encoding="utf-8")
    v2_payload["supersedes"] = v1_id
    v2_path.write_text(json.dumps(v2_payload), encoding="utf-8")
    with pytest.raises(CatalogLoadError, match="supersedes benefit .* with status 'active'"):
        load_catalog(tmp_path)

    # Test superseding unknown rule failure
    v2_payload["supersedes"] = "99999999-9999-4999-8999-999999999999"
    v2_path.write_text(json.dumps(v2_payload), encoding="utf-8")
    with pytest.raises(CatalogLoadError, match="unknown benefit"):
        load_catalog(tmp_path)


# ---- MC-093: provenance metadata per assertion tests ----


def test_evidence_provenance_tier_computation(tmp_path: Path) -> None:
    _copy_catalog(tmp_path)
    catalog = load_catalog(tmp_path)
    assertion = catalog.benefits[0].evidence[0]
    # issuer_document is tier 2
    assert assertion.source_policy_class == "issuer_document"
    assert assertion.source_tier == 2
    assert assertion.url.startswith("https://")
    assert assertion.content_sha256
    assert assertion.retrieved_at
    assert assertion.confidence == "high"
    assert assertion.review_state == "approved"
    assert len(assertion.reviews) >= 1


def test_approved_discovery_only_evidence_rejected(tmp_path: Path) -> None:
    _copy_catalog(tmp_path)
    path = tmp_path / "benefits" / "synthetic-example-reward.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["evidence"][0]["source_policy_class"] = "discovery_only"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CatalogLoadError, match="discovery_only .* cannot be approved"):
        load_catalog(tmp_path)
