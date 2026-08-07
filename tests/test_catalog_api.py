from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from mycard_benefits.catalog.router import create_catalog_router

CATALOG_ROOT = Path(__file__).parents[1] / "catalog"
SYNTHETIC_CATALOG_ROOT = Path(__file__).parent / "fixtures" / "synthetic_catalog"
OFFERING_SLUG = "synthetic-example-in-visa"


def test_production_catalog_api_contains_no_synthetic_or_invalid_urls() -> None:
    app = FastAPI()
    app.include_router(create_catalog_router(CATALOG_ROOT))
    with TestClient(app) as client:
        offerings = client.get("/api/v1/catalog/offerings")
        assert offerings.status_code == 200
        offerings_data = offerings.json()
        assert len(offerings_data) >= 68
        assert "synthetic-example-in-visa" not in [item["slug"] for item in offerings_data]
        assert "example.invalid" not in offerings.text
        assert "synthetic" not in offerings.text.lower()

        detail = client.get("/api/v1/catalog/offerings/synthetic-example-in-visa")
        assert detail.status_code == 404

        benefits = client.get("/api/v1/catalog/benefits")
        assert benefits.status_code == 200
        assert "example.invalid" not in benefits.text
        assert "synthetic" not in benefits.text.lower()


def test_list_and_detail_are_date_aware_and_deterministic(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        default = client.get("/api/v1/catalog/offerings")
        dated = client.get("/api/v1/catalog/offerings", params={"as_of": "2026-08-06"})

        assert default.status_code == dated.status_code == 200
        assert default.json() == dated.json()
        assert OFFERING_SLUG in [item["slug"] for item in default.json()]

        detail = client.get(f"/api/v1/catalog/offerings/{OFFERING_SLUG}", params={"as_of": "2026-08-06"})
        assert detail.status_code == 200
        body = detail.json()
        assert body["as_of"] == "2026-08-06"
        assert body["benefits"][0]["benefit_type"] == "reward_points"
        assert body["benefits"][0]["review_tier"] == "standard"
        assert body["benefits"][0]["evidence"][0]["source_url"] == "https://example.invalid/synthetic-terms"
        assert body["benefits"][0]["evidence"][0]["approved_review_count"] == 1
        assert "path" not in json.dumps(body).lower()
        assert "body" not in body["benefits"][0]["evidence"][0]

        before = client.get(f"/api/v1/catalog/offerings/{OFFERING_SLUG}", params={"as_of": "2025-12-31"})
        assert before.status_code == 404


def test_matching_requires_canonical_dimensions_and_filters_exactly(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        params = {
            "issuer_id": "synthetic-issuer",
            "product_variant_id": "synthetic-tier",
            "network_id": "visa",
            "market": "in",
            "co_brand_id": "synthetic-cobrand",
            "cohort_id": "synthetic-2026",
        }
        match = client.get("/api/v1/catalog/offerings/match", params=params)
        assert match.status_code == 200
        assert [item["slug"] for item in match.json()] == [OFFERING_SLUG]

        params["network_id"] = "mastercard"
        assert client.get("/api/v1/catalog/offerings/match", params=params).json() == []
        assert client.get("/api/v1/catalog/offerings/match").status_code == 422


def test_benefit_filtering_and_unknown_offering_are_safe(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get(
            "/api/v1/catalog/benefits",
            params={"offering_slug": OFFERING_SLUG, "benefit_type": "reward_points", "as_of": "2026-08-06"},
        )
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert client.get("/api/v1/catalog/benefits", params={"offering_slug": "missing"}).status_code == 404
        assert client.get("/api/v1/catalog/benefits", params={"as_of": "not-a-date"}).status_code == 422


def test_invalid_catalog_is_generic_service_unavailable(tmp_path: Path) -> None:
    _copy_catalog(tmp_path)
    path = tmp_path / "benefits" / "synthetic-example-reward.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["evidence"][0]["content_sha256"] = "invalid"
    path.write_text(json.dumps(payload), encoding="utf-8")

    app = FastAPI()
    app.include_router(create_catalog_router(tmp_path))
    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/offerings")

    assert response.status_code == 503
    assert response.json() == {"detail": "Catalog unavailable"}
    assert str(tmp_path) not in response.text


def _client(destination: Path) -> TestClient:
    _copy_catalog(destination)
    app = FastAPI()
    app.include_router(create_catalog_router(destination))
    return TestClient(app)


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


# ---- MC-021: relationship API tests ----


def test_offering_detail_includes_relationships(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        detail = client.get(f"/api/v1/catalog/offerings/{OFFERING_SLUG}")
        assert detail.status_code == 200
        body = detail.json()
        assert "relationships" in body
        assert len(body["relationships"]) == 1
        rel = body["relationships"][0]
        assert rel["relationship_type"] == "reskinned"
        assert rel["review_state"] == "approved"


def test_relationships_endpoint_returns_all(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/api/v1/catalog/relationships")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["from_offering_id"] == "22222222-2222-4222-8222-222222222222"


# ---- MC-070: temporal and versioned benefits API tests ----


def test_benefits_api_returns_temporal_and_versioning_fields(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/api/v1/catalog/benefits")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        b = data[0]
        assert b["effective_to"] is None
        assert b["end_date_known"] is False
        assert b["rule_version"] == 1
        assert b["supersedes"] is None


def test_benefits_api_include_historical_parameter(tmp_path: Path) -> None:
    _copy_catalog(tmp_path)
    path = tmp_path / "benefits" / "synthetic-example-reward.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["status"] = "historical"
    path.write_text(json.dumps(payload), encoding="utf-8")

    app = FastAPI()
    app.include_router(create_catalog_router(tmp_path))
    with TestClient(app) as client:
        # Default: active rules only -> empty
        res_default = client.get("/api/v1/catalog/benefits")
        assert res_default.status_code == 200
        assert res_default.json() == []

        # With include_historical=true -> returns historical rule
        res_hist = client.get("/api/v1/catalog/benefits", params={"include_historical": "true"})
        assert res_hist.status_code == 200
        assert len(res_hist.json()) == 1
        assert res_hist.json()[0]["status"] == "historical"


# ---- MC-093: provenance metadata API tests ----


def test_benefits_api_returns_evidence_source_tier(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/api/v1/catalog/benefits")
        assert response.status_code == 200
        evidence = response.json()[0]["evidence"][0]
        assert evidence["source_policy_class"] == "issuer_document"
        assert evidence["source_tier"] == 2
        assert evidence["source_url"].startswith("https://")
        assert len(evidence["content_sha256"]) == 64
        assert evidence["approved_review_count"] >= 1
