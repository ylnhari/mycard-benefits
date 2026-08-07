from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from mycard_benefits.catalog import CatalogLoadError, load_catalog

CATALOG_ROOT = Path(__file__).parents[1] / "catalog"


def test_synthetic_catalog_loads_deterministically() -> None:
    first = load_catalog(CATALOG_ROOT)
    second = load_catalog(CATALOG_ROOT)

    assert first == second
    offering = first.offering_by_slug("synthetic-example-in-visa")
    assert offering is not None
    assert offering.network_id == "visa"
    assert [item.id for item in first.benefits_for(offering.id, date(2026, 8, 6))] == [
        "33333333-3333-4333-8333-333333333333"
    ]


def test_india_starter_catalog_contains_real_product_variants() -> None:
    catalog = load_catalog(CATALOG_ROOT)

    assert len(catalog.offerings) >= 69
    tata_neu = catalog.offering_by_slug("hdfc-tata-neu-rupay-select-credit")
    regalia = catalog.offering_by_slug("hdfc-regalia-gold-credit")
    assert tata_neu is not None
    assert tata_neu.display_name == "Tata Neu Infinity HDFC Bank RuPay Select Credit Card"
    assert tata_neu.network_id == "rupay-select"
    assert regalia is not None
    assert regalia.display_name == "HDFC Bank Regalia Gold Credit Card"


def test_tracked_import_sample_uses_known_catalog_offerings() -> None:
    catalog = load_catalog(CATALOG_ROOT)
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


def _copy_catalog(destination: Path) -> None:
    for relative in ("schema/release.json", "offerings/synthetic-example-in.json", "benefits/synthetic-example-reward.json"):
        source = CATALOG_ROOT / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
