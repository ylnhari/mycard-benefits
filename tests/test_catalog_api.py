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


def test_consumer_catalog_api_surfaces_rescued_states_and_divergence() -> None:
    app = FastAPI()
    app.include_router(create_catalog_router(CATALOG_ROOT))
    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/benefits")

    assert response.status_code == 200
    benefits = response.json()
    # Derived from the catalog, not frozen: the guarantee is that the API
    # publishes every benefit in exactly one of the three consumer states, so a
    # legitimately added benefit should not read as a regression here.
    published = len(list((CATALOG_ROOT / "benefits").glob("*.json")))
    assert len(benefits) == published
    counts = {
        state: sum(item["state"] == state for item in benefits)
        for state in ("verified", "check_before_use", "sources_differ")
    }
    assert sum(counts.values()) == published
    assert counts["verified"] <= 1
    def scalar_strings(value: object) -> list[str]:
        if isinstance(value, dict):
            return [item for child in value.values() for item in scalar_strings(child)]
        if isinstance(value, list):
            return [item for child in value for item in scalar_strings(child)]
        return [value.casefold()] if isinstance(value, str) else []

    def object_keys(value: object) -> list[str]:
        if isinstance(value, dict):
            return list(value) + [item for child in value.values() for item in object_keys(child)]
        if isinstance(value, list):
            return [item for child in value for item in object_keys(child)]
        return []

    assert {
        "needs_review", "superseded", "historical", "approved", "stale", "active", "conflict", "expired"
    }.isdisjoint(scalar_strings(benefits))
    assert {"status", "review_tier", "review_state", "evidence_status"}.isdisjoint(object_keys(benefits))
    assert any(item["not_claimed"] for item in benefits)
    divergent = next(item for item in benefits if item["source_divergence"])
    assert divergent["state"] == "sources_differ"
    assert len(divergent["source_divergence"]) == 2
    assert {claim["benefit_type"] for claim in divergent["source_divergence"]} == {
        "priority_pass",
        "lounge",
    }


def test_list_and_detail_are_date_aware_and_deterministic(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        default = client.get("/api/v1/catalog/offerings")
        dated = client.get("/api/v1/catalog/offerings", params={"as_of": "2026-08-06"})

        assert default.status_code == dated.status_code == 200
        assert default.json() == dated.json()
        assert OFFERING_SLUG in [item["slug"] for item in default.json()]

        detail = client.get(
            f"/api/v1/catalog/offerings/{OFFERING_SLUG}", params={"as_of": "2026-08-06"}
        )
        assert detail.status_code == 200
        body = detail.json()
        assert body["as_of"] == "2026-08-06"
        assert body["benefits"][0]["benefit_type"] == "reward_points"
        assert body["benefits"][0]["state"] == "verified"
        assert (
            body["benefits"][0]["evidence"][0]["source_url"]
            == "https://example.invalid/synthetic-terms"
        )
        assert body["benefits"][0]["evidence"][0]["approved_review_count"] == 1
        assert "path" not in json.dumps(body).lower()
        assert "body" not in body["benefits"][0]["evidence"][0]

        before = client.get(
            f"/api/v1/catalog/offerings/{OFFERING_SLUG}", params={"as_of": "2025-12-31"}
        )
        assert before.status_code == 404


def test_matching_requires_canonical_dimensions_and_filters_exactly(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        params = {
            "issuer_id": "synthetic-issuer",
            "product_variant_id": "synthetic-tier",
            "network": "visa",
            "market": "in",
            "co_brand_id": "synthetic-cobrand",
            "cohort_id": "synthetic-2026",
        }
        match = client.get("/api/v1/catalog/offerings/match", params=params)
        assert match.status_code == 200
        assert [item["slug"] for item in match.json()] == [OFFERING_SLUG]

        params["network"] = "mastercard"
        assert client.get("/api/v1/catalog/offerings/match", params=params).json() == []
        assert client.get("/api/v1/catalog/offerings/match").status_code == 422


def test_benefit_filtering_and_unknown_offering_are_safe(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get(
            "/api/v1/catalog/benefits",
            params={
                "offering_slug": OFFERING_SLUG,
                "benefit_type": "reward_points",
                "as_of": "2026-08-06",
            },
        )
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert (
            client.get("/api/v1/catalog/benefits", params={"offering_slug": "missing"}).status_code
            == 404
        )
        assert (
            client.get("/api/v1/catalog/benefits", params={"as_of": "not-a-date"}).status_code
            == 422
        )


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


def test_current_public_catalog_export_is_schema_bounded_and_never_cached(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/api/v1/catalog/export")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    body = response.json()
    assert set(body) == {
        "export_schema_version",
        "as_of",
        "release",
        "offerings",
        "benefits",
        "relationships",
    }
    assert body["export_schema_version"] == "public-catalog-export-v1"
    assert set(body["release"]) == {"schema_version", "release_id", "generated_at", "market_scope"}
    assert body["offerings"] and body["benefits"]
    serialized = json.dumps(body).casefold()
    for forbidden in ("pan", "cvv", "pin", "cardholder", "vault", "private", "reviewer_id", "path"):
        assert forbidden not in serialized


def test_catalog_export_includes_only_current_approved_evidence(tmp_path: Path) -> None:
    _copy_catalog(tmp_path)
    path = tmp_path / "benefits" / "synthetic-example-reward.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    candidate = dict(payload["evidence"][0])
    candidate["id"] = "99999999-9999-4999-8999-999999999999"
    candidate["url"] = "https://example.invalid/needs-review-candidate"
    candidate["content_sha256"] = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    candidate["review_state"] = "needs_review"
    payload["evidence"].append(candidate)
    stale = dict(payload["evidence"][0])
    stale["id"] = "99999999-9999-4999-8999-999999999998"
    stale["url"] = "https://example.invalid/stale-evidence"
    stale["effective_to"] = "2026-08-05"
    payload["evidence"].append(stale)
    rejected = dict(payload["evidence"][0])
    rejected["id"] = "99999999-9999-4999-8999-999999999997"
    rejected["url"] = "https://example.invalid/rejected-evidence"
    rejected["review_state"] = "rejected"
    rejected["reviews"] = [
        {
            **rejected["reviews"][0],
            "id": "88888888-8888-4888-8888-888888888887",
            "decision": "rejected",
        }
    ]
    payload["evidence"].append(rejected)
    path.write_text(json.dumps(payload), encoding="utf-8")

    app = FastAPI()
    app.include_router(create_catalog_router(tmp_path))
    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/export")

    assert response.status_code == 200
    evidence = response.json()["benefits"][0]["evidence"]
    assert [item["source_url"] for item in evidence] == [
        "https://example.invalid/synthetic-terms"
    ]
    serialized = json.dumps(response.json())
    assert "needs-review-candidate" not in serialized
    assert "99999999-9999-4999-8999-999999999999" not in serialized
    assert "stale-evidence" not in serialized
    assert "rejected-evidence" not in serialized


def test_catalog_export_fails_closed_and_is_never_cached(tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(create_catalog_router(tmp_path))
    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/export")

    assert response.status_code == 503
    assert response.json() == {"detail": "Catalog unavailable"}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
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
        assert len(data[0]["evidence"]) >= 1
        assert data[0]["evidence"][0]["source_url"].startswith("https://")


def test_inheritance_is_date_bounded_across_api_consumers_and_conflicts(tmp_path: Path) -> None:
    _copy_catalog(tmp_path)
    source_path = tmp_path / "benefits" / "synthetic-example-reward.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    target = dict(source)
    target.update(
        {
            "id": "88888888-8888-4888-8888-888888888888",
            "offering_id": "22222222-2222-4222-8222-222222222233",
            "title": "Synthetic inherited reward",
            "conflicts_with": [source["id"]],
            "inheritance": {
                "owner": {"kind": "network", "id": "SYNTHETIC-ONLY-NETWORK", "display_name": "SYNTHETIC-ONLY Network"},
                "source_benefit_id": source["id"],
                "source_offering_id": source["offering_id"],
                "target_offering_id": "22222222-2222-4222-8222-222222222233",
                "source_network_id": "visa",
                "target_network_id": "mastercard",
                "source_co_brand_id": "synthetic-cobrand",
                "target_co_brand_id": None,
                "review_state": "approved",
                "opt_in": True,
                "effective_from": "2027-01-01",
                "effective_to": "2027-12-31",
            },
        }
    )
    source["conflicts_with"] = [target["id"]]
    source_path.write_text(json.dumps(source), encoding="utf-8")
    (tmp_path / "benefits" / "synthetic-inherited-reward.json").write_text(
        json.dumps(target), encoding="utf-8"
    )
    app = FastAPI()
    app.include_router(create_catalog_router(tmp_path))
    with TestClient(app) as client:
        for as_of, expected in (
            ("2026-12-31", False),
            ("2027-01-01", True),
            ("2027-06-15", True),
            ("2027-12-31", True),
            ("2028-01-01", False),
        ):
            params = {"as_of": as_of}
            all_benefits = client.get("/api/v1/catalog/benefits", params=params)
            assert all_benefits.status_code == 200
            ids = {item["id"] for item in all_benefits.json()}
            assert (target["id"] in ids) is expected
            assert (target["id"] in set(all_benefits.json()[0]["conflicts_with"])) is expected

            detail = client.get(
                "/api/v1/catalog/offerings/synthetic-example-in-mc", params=params
            )
            assert detail.status_code == 200
            assert bool(detail.json()["benefits"]) is expected

            relationships = client.get("/api/v1/catalog/relationships", params=params)
            assert relationships.status_code == 200

        # A filtered inherited conflict is never left as a dangling public ID.
        outside = client.get("/api/v1/catalog/benefits", params={"as_of": "2026-12-31"}).json()
        assert all(target["id"] not in item["conflicts_with"] for item in outside)


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


def test_benefits_api_exposes_structured_public_fields(tmp_path: Path) -> None:
    _copy_catalog(tmp_path)
    path = tmp_path / "benefits" / "synthetic-example-reward.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
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
            "conditions": [{"type": "channel", "operator": "in", "value": ["synthetic"]}],
            "earn": {
                "currency": "SYNTHETIC-ONLY",
                "rate": "2",
                "basis": "unit",
                "scope": "synthetic",
                "cap": None,
                "exclusions": [],
                "rounding": None,
                "reversal": None,
                "expiry": None,
            },
            "conversion": {
                "partner_id": "SYNTHETIC-ONLY",
                "ratio": "1:1",
                "fee": None,
                "minimum": 1,
                "increment": 1,
                "expiry": None,
                "redemption_options": ["SYNTHETIC-ONLY"],
            },
            "valuations": [
                {
                    "name": "SYNTHETIC-ONLY",
                    "redemption_path": "SYNTHETIC-ONLY",
                    "currency": "SYNTHETIC-ONLY",
                    "minimum": "1",
                    "maximum": "2",
                }
            ],
            "value_class": "estimated",
        }
    )
    path.write_text(json.dumps(payload), encoding="utf-8")
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(create_catalog_router(tmp_path))
    response = TestClient(app).get("/api/v1/catalog/benefits")
    assert response.status_code == 200
    item = response.json()[0]
    assert {
        "category",
        "conditions",
        "earn",
        "conversion",
        "valuations",
        "value_class",
    } <= item.keys()
    # "owners" and "inheritance" were deliberately dropped from the consumer
    # contract: rule authorship and rule-descent mechanics are internal, and a
    # cardholder learns nothing from either. Assert they stay gone.
    assert not {"owners", "inheritance"} & item.keys()
    assert item["conditions"][0]["type"] == "channel"


def test_benefits_api_include_historical_parameter(tmp_path: Path) -> None:
    _copy_catalog(tmp_path)
    path = tmp_path / "benefits" / "synthetic-example-reward.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    # Active rule effective from 2026-01-01 to 2026-06-01
    payload["status"] = "active"
    payload["effective_from"] = "2026-01-01"
    payload["effective_to"] = "2026-06-01"
    path.write_text(json.dumps(payload), encoding="utf-8")

    # Historical rule
    hist_payload = dict(payload)
    hist_payload["id"] = "99999999-9999-4999-8999-999999999999"
    hist_payload["status"] = "historical"
    hist_path = tmp_path / "benefits" / "synthetic-example-reward-hist.json"
    hist_path.write_text(json.dumps(hist_payload), encoding="utf-8")

    app = FastAPI()
    app.include_router(create_catalog_router(tmp_path))
    with TestClient(app) as client:
        # Querying as of 2026-08-01: active rule is expired (outside date range)
        res_default = client.get("/api/v1/catalog/benefits", params={"as_of": "2026-08-01"})
        assert res_default.status_code == 200
        assert res_default.json() == []

        # With include_historical=true: active rule is STILL excluded (outside date range), but historical rule is returned!
        res_hist = client.get(
            "/api/v1/catalog/benefits", params={"include_historical": "true", "as_of": "2026-08-01"}
        )
        assert res_hist.status_code == 200
        data = res_hist.json()
        assert len(data) == 1
        assert data[0]["id"] == "99999999-9999-4999-8999-999999999999"
        assert data[0]["state"] == "check_before_use"


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


def test_discovery_normalizes_natural_text_and_returns_public_context(tmp_path: Path) -> None:
    movie_source = SYNTHETIC_CATALOG_ROOT / "benefits" / "synthetic-example-movie.json"
    movie_target = tmp_path / "benefits" / "synthetic-example-movie.json"
    movie_target.parent.mkdir(parents=True, exist_ok=True)
    movie_target.write_text(movie_source.read_text(encoding="utf-8"), encoding="utf-8")
    with _client(tmp_path) as client:
        response = client.get("/api/v1/catalog/discovery", params={"q": "SYNTHETIC movie"})
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        result = data[0]
        assert result["benefit"]["state"] == "check_before_use"
        assert result["offering"]["id"] == result["benefit"]["offering_id"]
        assert result["matched_terms"] == ["synthetic", "movie"]
        assert result["date_usable"] is False

        # Currency and punctuation normalization does not turn an absent fact
        # into an offer; the fixture has no 600-off assertion.
        assert client.get("/api/v1/catalog/discovery", params={"q": "₹600 off"}).json() == []
        assert client.get("/api/v1/catalog/discovery", params={"status": "needs_review"}).json()
