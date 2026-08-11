from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from mycard_benefits.catalog import load_catalog
from mycard_benefits.catalog.router import create_catalog_router

ROOT = Path(__file__).parents[1]
CATALOG_ROOT = ROOT / "catalog"
OFFERING_ID = "3eeb4094-d452-5a33-9061-0e8999cd6c89"
OFFERING_SLUG = "hdfc-tata-neu-rupay-select-credit"
BENEFIT_ID = "b3000001-0000-4000-8000-000000000006"


def test_owner_approved_tata_lounge_is_active_and_public_paths_expose_rescued_records() -> None:
    catalog = load_catalog(CATALOG_ROOT)
    rules = catalog.benefits_for(OFFERING_ID, date(2026, 8, 10))
    assert [rule.id for rule in rules] == [BENEFIT_ID]
    rule = rules[0]
    assert rule.status == "active"
    assert rule.effective_from == date(2025, 6, 10)
    assert rule.eligibility[0] == {
        "field": "calendar_quarter.eligible_net_posted_spend_inr",
        "operator": "gte",
        "value": 50000,
    }
    assert rule.allowance is not None
    assert rule.allowance["count"] == 2
    assert rule.allowance["period"] == "qualifying_calendar_quarter"
    assert rule.allowance["claim_window_days"] == 120
    assert rule.allowance["claim_route"] == (
        "issuer/GyFTR communication to the registered contact, followed by the "
        "issuer-linked GyFTR claim route using the registered mobile/OTP"
    )
    assert "vouchers_per_year" not in rule.allowance
    assert "voucher_validity_days" not in rule.allowance
    assert "direct_swipe_access" not in rule.allowance
    assert "rollover" not in rule.allowance
    assert rule.evidence[0].url.endswith("milestone_lounge_tataneu-cc.pdf")
    assert rule.evidence[0].content_sha256 == "974da629d3567911201ecd7a73329ca335f5506347438e363d4f42ea9880b62e"
    assert [review.reviewer_id for review in rule.evidence[0].reviews] == ["project-owner"]

    app = FastAPI()
    app.include_router(create_catalog_router(CATALOG_ROOT))
    with TestClient(app) as client:
        detail = client.get(f"/api/v1/catalog/offerings/{OFFERING_SLUG}")
        assert detail.status_code == 200
        detail_body = detail.json()
        detail_benefits = detail_body["benefits"]
        assert BENEFIT_ID in [item["id"] for item in detail_benefits]
        assert sum(item["state"] == "verified" for item in detail_benefits) == 1
        assert all(
            item["state"] in {"verified", "check_before_use", "sources_differ"}
            for item in detail_benefits
        )
        active_detail = next(item for item in detail_benefits if item["id"] == BENEFIT_ID)
        assert active_detail["official_reference"] is None
        assert active_detail["evidence"][0]["source_url"].endswith(
            "milestone_lounge_tataneu-cc.pdf"
        )
        discovery = client.get(
            "/api/v1/catalog/benefits",
            params={"offering_slug": OFFERING_SLUG, "benefit_type": "lounge"},
        )
        assert discovery.status_code == 200
        discovery_benefits = discovery.json()
        assert BENEFIT_ID in [item["id"] for item in discovery_benefits]
        assert sum(item["state"] == "verified" for item in discovery_benefits) == 1
