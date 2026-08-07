from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from mycard_benefits.catalog import CatalogLoadError, load_catalog

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


def test_tracked_import_sample_uses_known_catalog_offerings() -> None:
    catalog = load_catalog(SYNTHETIC_CATALOG_ROOT)
    sample_path = Path(__file__).parents[1] / "samples" / "card-import.example.json"
    sample = json.loads(sample_path.read_text(encoding="utf-8"))

    assert sample["cards"]
    assert all(catalog.offering_by_slug(card["offering_id"]) is not None for card in sample["cards"])


def test_active_rule_requires_approved_evidence(tmp_path: Path) -> None:
    _copy_catalog(tmp_path)
    path = tmp_path / "benefits" / "synthetic-example-reward.json"
    payload = json.loads(path.read_text())
    payload["evidence"][0]["review_state"] = "needs_review"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CatalogLoadError, match="active benefit requires approved"):
        load_catalog(tmp_path)


def test_active_rule_requires_distinct_immutable_human_reviews(tmp_path: Path) -> None:
    _copy_catalog(tmp_path)
    path = tmp_path / "benefits" / "synthetic-example-reward.json"
    payload = json.loads(path.read_text())
    payload["evidence"][0]["reviews"] = []
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CatalogLoadError, match="human review record"):
        load_catalog(tmp_path)

    payload["review_tier"] = "high_impact"
    payload["evidence"][0]["reviews"] = [{
        "id": "55555555-5555-4555-8555-555555555555",
        "reviewer_id": "SYNTHETIC-ONLY-REVIEWER",
        "reviewed_at": "2026-08-06T00:00:00Z",
        "decision": "approved",
    }]
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CatalogLoadError, match="2 distinct approved human reviews"):
        load_catalog(tmp_path)

    payload["evidence"][0]["reviews"].append({
        "id": "66666666-6666-4666-8666-666666666666",
        "reviewer_id": "SYNTHETIC-ONLY-SECOND-REVIEWER",
        "reviewed_at": "2026-08-06T00:00:00Z",
        "decision": "approved",
    })
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_catalog(tmp_path).benefits[0].review_tier == "high_impact"


def test_duplicate_reviewer_identity_is_rejected(tmp_path: Path) -> None:
    _copy_catalog(tmp_path)
    path = tmp_path / "benefits" / "synthetic-example-reward.json"
    payload = json.loads(path.read_text())
    payload["evidence"][0]["reviews"].append({
        "id": "66666666-6666-4666-8666-666666666666",
        "reviewer_id": "SYNTHETIC-ONLY-REVIEWER",
        "reviewed_at": "2026-08-06T01:00:00Z",
        "decision": "approved",
    })
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
    schema = json.loads((CATALOG_ROOT / "schema" / "catalog.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    records = [
        CATALOG_ROOT / "schema" / "release.json",
        *(CATALOG_ROOT / "offerings").glob("*.json"),
        *(CATALOG_ROOT / "benefits").glob("*.json"),
    ]
    for path in records:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert not list(validator.iter_errors(payload)), path


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
    # Add a reverse renamed edge to create A → B → A cycle
    reverse = {
        "id": "88888888-8888-4888-8888-888888888888",
        "from_offering_id": "22222222-2222-4222-8222-222222222233",
        "to_offering_id": "22222222-2222-4222-8222-222222222222",
        "relationship_type": "renamed",
        "review_state": "approved",
    }
    # First change the existing edge to renamed so both are DAG-checked
    path = tmp_path / "relationships" / "synthetic-example-relationship.json"
    payload = json.loads(path.read_text())
    payload["relationship_type"] = "renamed"
    path.write_text(json.dumps(payload), encoding="utf-8")
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
