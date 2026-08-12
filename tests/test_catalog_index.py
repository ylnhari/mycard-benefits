from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from mycard_benefits.catalog.index import (
    CatalogIndex,
    CatalogIndexStaleError,
    build_catalog_index,
)
from mycard_benefits.sqlite_readonly import read_only_sqlite_connection

SYNTHETIC_CATALOG_ROOT = Path(__file__).parent / "fixtures" / "synthetic_catalog"


def _catalog_with_quantities_and_rewards(tmp_path: Path) -> tuple[Path, str, str]:
    root = tmp_path / "catalog"
    shutil.copytree(SYNTHETIC_CATALOG_ROOT, root)
    first_offering = "22222222-2222-4222-8222-222222222222"
    second_offering = "22222222-2222-4222-8222-222222222233"

    movie_path = root / "benefits" / "synthetic-example-movie.json"
    movie = json.loads(movie_path.read_text(encoding="utf-8"))
    movie["status"] = "active"
    movie["evidence"][0]["confidence"] = "high"
    movie["evidence"][0]["review_state"] = "approved"
    movie["evidence"][0]["reviews"] = [{
        "id": "55555555-5555-4555-8555-555555555555",
        "reviewer_id": "SYNTHETIC-ONLY-REVIEWER",
        "reviewed_at": "2026-08-06T00:00:00Z",
        "decision": "approved",
    }]
    movie["quantities"] = [{
        "metric": "count",
        "value": 2,
        "unit": "tickets",
        "basis": "transaction",
        "scope": None,
        "period": "month",
        "cap": {"value": 2, "unit": "tickets", "period": "month"},
    }]
    movie_path.write_text(json.dumps(movie, indent=2), encoding="utf-8")

    offering_path = root / "offerings" / "synthetic-example-in-mc.json"
    offering = json.loads(offering_path.read_text(encoding="utf-8"))
    offering["id"] = second_offering
    offering_path.write_text(json.dumps(offering, indent=2), encoding="utf-8")

    rewards = root / "rewards"
    rewards.mkdir()
    common = {
        "schema_version": "1.0.0",
        "currency": {"code": "SYNTHETIC-ONLY-POINTS", "display_name": "Synthetic points"},
        "category_earn": [],
        "expiry": {"months": 12, "from": "end_of_credit_month"},
        "source_url": "https://example.invalid/synthetic-reward-terms",
        "source_policy_class": "issuer_document",
        "content_sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
        "retrieved_at": "2026-08-06T00:00:00Z",
        "state": "check_before_use",
        "review_state": "needs_review",
    }
    known = {
        **common,
        "offering_id": first_offering,
        "offering_slug": "synthetic-example-in-visa",
        "base_earn": {"points_per_inr": 2},
        "valuation": {"inr_per_point": 0.5, "basis": "issuer_stated"},
    }
    unknown = {
        **common,
        "offering_id": second_offering,
        "offering_slug": "synthetic-example-in-mc",
        "base_earn": {"points_per_inr": 1},
        "valuation": {"inr_per_point": None, "basis": None},
    }
    (rewards / "synthetic-example-in-visa.json").write_text(
        json.dumps(known, indent=2), encoding="utf-8"
    )
    (rewards / "synthetic-example-in-mc.json").write_text(
        json.dumps(unknown, indent=2), encoding="utf-8"
    )
    return root, first_offering, second_offering


def test_index_rebuild_is_byte_deterministic_and_exposes_real_numbers(tmp_path: Path) -> None:
    root, first_offering, second_offering = _catalog_with_quantities_and_rewards(tmp_path)
    first_path = build_catalog_index(root, tmp_path / "data-one")
    second_path = build_catalog_index(root, tmp_path / "data-two")

    assert first_path.read_bytes() == second_path.read_bytes()
    index = CatalogIndex.open(root, tmp_path / "data-one")

    movie = index.optimizer_candidates(
        "movie",
        metric="count",
        unit="tickets",
        offering_ids=[first_offering],
    )
    assert len(movie.rows) == 1
    assert movie.rows[0].value == 2
    assert movie.rows[0].cap_value == 2
    assert movie.excluded_unknown_count == 0

    expiring = index.next_expiring_benefits()
    assert expiring[0].benefit_id == "33333333-3333-4333-8333-333333333334"
    assert expiring[0].effective_to == date(2026, 12, 31)

    rewards = index.rank_rewards(offering_ids=[first_offering, second_offering])
    assert len(rewards.rows) == 1
    assert rewards.rows[0].offering_id == first_offering
    assert rewards.rows[0].points_per_inr == 2
    assert rewards.rows[0].valuation_inr_per_point == 0.5
    assert rewards.rows[0].value_inr_per_rupee == 1.0
    assert rewards.excluded_unknown_count == 1


def test_unknown_quantities_and_valuations_are_not_zero(tmp_path: Path) -> None:
    root, first_offering, second_offering = _catalog_with_quantities_and_rewards(tmp_path)
    index_path = build_catalog_index(root, tmp_path / "data")
    index = CatalogIndex.open(root, tmp_path / "data")

    no_quantity = index.best_for_category(
        "reward_points",
        metric="count",
        unit="points",
        offering_ids=[first_offering],
    )
    assert no_quantity.rows == ()
    assert no_quantity.excluded_unknown_count == 1

    with read_only_sqlite_connection(index_path) as connection:
        valuation = connection.execute(
            "SELECT valuation_inr_per_point FROM reward_records WHERE offering_id = ?",
            (second_offering,),
        ).fetchone()[0]
    assert valuation is None
    with (
        pytest.raises(sqlite3.OperationalError),
        read_only_sqlite_connection(index_path) as connection,
    ):
        connection.execute("CREATE TABLE must_not_write(name TEXT)")


def test_catalog_changes_make_the_existing_index_stale(tmp_path: Path) -> None:
    root, _, _ = _catalog_with_quantities_and_rewards(tmp_path)
    build_catalog_index(root, tmp_path / "data")
    benefit_path = root / "benefits" / "synthetic-example-movie.json"
    benefit = json.loads(benefit_path.read_text(encoding="utf-8"))
    benefit["title"] = "SYNTHETIC-ONLY changed after build"
    benefit_path.write_text(json.dumps(benefit, indent=2), encoding="utf-8")

    with pytest.raises(CatalogIndexStaleError):
        CatalogIndex.open(root, tmp_path / "data")
