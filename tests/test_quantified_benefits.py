from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from mycard_benefits.catalog import CatalogLoadError, load_catalog

ROOT = Path(__file__).parents[1]
CATALOG_ROOT = ROOT / "catalog"
SYNTHETIC_ROOT = ROOT / "tests" / "fixtures" / "synthetic_catalog"


def _copy_synthetic_catalog(destination: Path) -> Path:
    shutil.copytree(SYNTHETIC_ROOT, destination)
    return destination


def _valid_quantity() -> dict[str, object]:
    return {
        "metric": "rate_percent",
        "value": 0.5,
        "unit": "percent",
        "basis": "spend",
        "scope": "amazon.in",
        "period": "statement_cycle",
        "cap": None,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("metric", "not-a-metric"),
        ("unit", "rupees"),
        ("basis", "cardholder"),
        ("scope", "unlisted-merchant"),
        ("period", "whenever"),
    ],
)
def test_quantity_closed_vocabularies_fail_closed(
    tmp_path: Path, field: str, value: str
) -> None:
    catalog_root = _copy_synthetic_catalog(tmp_path / "catalog")
    path = catalog_root / "benefits" / "synthetic-example-reward.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    quantity = _valid_quantity()
    quantity[field] = value
    payload["quantities"] = [quantity]
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CatalogLoadError, match="unsupported quantity"):
        load_catalog(catalog_root)


def test_quantity_projection_is_optional_for_existing_records(tmp_path: Path) -> None:
    catalog = load_catalog(_copy_synthetic_catalog(tmp_path / "catalog"))

    assert catalog.benefits
    assert all(rule.quantities == () for rule in catalog.benefits)


def test_present_quantities_must_be_a_list(tmp_path: Path) -> None:
    catalog_root = _copy_synthetic_catalog(tmp_path / "catalog")
    path = catalog_root / "benefits" / "synthetic-example-reward.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["quantities"] = None
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CatalogLoadError, match="quantities must be a list of objects"):
        load_catalog(catalog_root)


def test_real_catalog_quantities_preserve_clear_numbers_and_decimals() -> None:
    catalog = load_catalog(CATALOG_ROOT)

    amazon = next(rule for rule in catalog.benefits if rule.id == "73470acf-67c0-56a1-8b27-7329d2748dad")
    assert amazon.quantities[0].metric == "rate_percent"
    assert amazon.quantities[0].value == 5
    assert amazon.quantities[0].unit == "percent"
    assert amazon.quantities[0].basis == "spend"
    assert amazon.quantities[0].scope == "amazon.in"
    assert amazon.quantities[0].period == "statement_cycle"

    axis = next(rule for rule in catalog.benefits if rule.title == "Axis NEO BookMyShow discount")
    assert axis.quantities[0].value == 10
    assert axis.quantities[0].cap == {"value": 100, "unit": "inr", "period": "month"}

    insurance = next(
        rule for rule in catalog.benefits if rule.title == "DBS Aspire debit insurance matrix"
    )
    assert {quantity.value for quantity in insurance.quantities} == {
        50_000,
        75_000,
        200_000,
        500_000,
        10_000_000,
    }

    foreign_exchange = next(
        rule
        for rule in catalog.benefits
        if rule.title == "Regalia Gold stated redemption, balance-transfer and foreign-currency charges"
    )
    assert {quantity.value for quantity in foreign_exchange.quantities} == {1.75, 2}


def test_quantity_coverage_report_accounts_for_projection_gaps() -> None:
    report = json.loads(
        (CATALOG_ROOT / "coverage" / "quantities.json").read_text(encoding="utf-8")
    )
    benefits = list((CATALOG_ROOT / "benefits").glob("*.json"))
    loaded = load_catalog(CATALOG_ROOT)
    expected_with_quantities = sum(bool(rule.quantities) for rule in loaded.benefits)

    assert report["benefit_count"] == len(benefits)
    assert report["benefits_with_quantities"] == expected_with_quantities
    # Counted from the catalog, not frozen. The guarantee is that the report
    # describes the catalog it was generated from; a literal number turns
    # adding a sourced benefit that introduces one new allowance key into a
    # failure, which says nothing about whether the report is honest.
    distinct_keys = {
        key
        for path in benefits
        for key in (json.loads(path.read_text(encoding="utf-8")).get("allowance") or {})
    }
    assert report["distinct_allowance_keys"] == len(distinct_keys)
    # The point of the report is that gaps are recorded rather than hidden, so
    # every key is accounted for as either mapped or unmapped.
    assert report["mapped_key_count"] + report["unmapped_key_count"] >= len(distinct_keys)
    unmapped = {(item["key"], item["reason"]): item["count"] for item in report["unmapped_keys"]}
    assert unmapped[("cap_inr_by_subtype", "nested subtype map is not modelled")] == 1
    assert unmapped[("partner_and_transfer_terms", "prose terms are not a numeric quantity")] == 1
    assert unmapped[("not_claimed", "an evidence gap is not a numeric quantity")] == 1
    assert unmapped[
        (
            "validation_swipe_inr",
            "a qualifying validation transaction is a condition, not a benefit quantity",
        )
    ] == 4
