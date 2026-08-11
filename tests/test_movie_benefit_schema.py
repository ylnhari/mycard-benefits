from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mycard_benefits.catalog import CatalogLoadError, load_catalog
from mycard_benefits.catalog.router import create_catalog_router

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "synthetic_catalog"
MOVIE_FIXTURE = FIXTURE_ROOT / "benefits" / "synthetic-example-movie.json"


def _catalog_with_movie(tmp_path: Path, mutate=None) -> Path:
    for relative in (
        "schema/release.json",
        "offerings/synthetic-example-in.json",
        "offerings/synthetic-example-in-mc.json",
        "benefits/synthetic-example-reward.json",
        "benefits/synthetic-example-movie.json",
        "relationships/synthetic-example-relationship.json",
    ):
        source = FIXTURE_ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    if mutate is not None:
        path = tmp_path / "benefits" / "synthetic-example-movie.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        mutate(payload)
        path.write_text(json.dumps(payload), encoding="utf-8")
    return tmp_path


def test_valid_movie_fixture_preserves_fulfillment_metadata() -> None:
    catalog = load_catalog(FIXTURE_ROOT)
    movie = next(rule for rule in catalog.benefits if rule.benefit_type == "movie")

    assert movie.status == "needs_review"
    assert movie.provider == "SYNTHETIC-ONLY-TICKETING-PROVIDER"
    assert movie.official_reference == "https://example.invalid/synthetic-movie-terms"
    assert len(movie.redemption_steps) == 3
    assert movie.exclusions == ("SYNTHETIC-ONLY: excluded showtimes or inventory may apply",)
    assert movie.allowance == {"unit": "tickets", "period": "month", "cap": 2}
    assert movie.eligibility[0]["field"] == "purchase.channel"
    assert movie.effective_to is not None
    # Needs-review rules are never active claims, even when their dates match.
    assert movie not in catalog.benefits_for(movie.offering_id)


def test_catalog_json_schema_declares_anonymous_https_references() -> None:
    schema = json.loads(
        (Path(__file__).parents[1] / "catalog" / "schema" / "catalog.schema.json").read_text(
            encoding="utf-8"
        )
    )
    definition = schema["$defs"]["anonymousHttpsUri"]
    assert definition["pattern"].startswith("^https://")
    assert "[^/@?#]" in definition["pattern"]
    assert "#" in definition["pattern"]
    assert schema["$defs"]["benefit"]["properties"]["official_reference"] == {
        "$ref": "#/$defs/anonymousHttpsUri"
    }


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("provider", None, "missing required fields"),
        ("official_reference", None, "missing required fields"),
        ("redemption_steps", None, "missing required fields"),
        ("exclusions", None, "missing required fields"),
        ("provider", 42, "provider must be a non-empty string"),
        ("official_reference", "http://synthetic.invalid/terms", "anonymous HTTPS URL"),
        ("official_reference", "https://user:pass@example.invalid/terms", "anonymous HTTPS URL"),
        ("official_reference", "https://example.invalid/terms#fragment", "anonymous HTTPS URL"),
        ("redemption_steps", [], "at least one item"),
        ("redemption_steps", "not-a-list", "redemption_steps must be a list"),
        ("exclusions", "not-a-list", "exclusions must be a list"),
        ("exclusions", ["SYNTHETIC-ONLY-duplicate", "SYNTHETIC-ONLY-duplicate"], "duplicate"),
    ],
)
def test_movie_metadata_malformed_boundaries_fail_closed(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    def mutate(payload: dict[str, object]) -> None:
        if value is None:
            del payload[field]
        else:
            payload[field] = value

    with pytest.raises(CatalogLoadError, match=message):
        load_catalog(_catalog_with_movie(tmp_path, mutate))


def test_movie_metadata_bounds_and_non_movie_fields_fail_closed(tmp_path: Path) -> None:
    def too_many_steps(payload: dict[str, object]) -> None:
        payload["redemption_steps"] = [f"SYNTHETIC-ONLY-step-{index}" for index in range(13)]

    with pytest.raises(CatalogLoadError, match="at most 12"):
        load_catalog(_catalog_with_movie(tmp_path / "steps", too_many_steps))

    def long_exclusion(payload: dict[str, object]) -> None:
        payload["exclusions"] = ["SYNTHETIC-ONLY-" + "x" * 240]

    with pytest.raises(CatalogLoadError, match="exceed 240"):
        load_catalog(_catalog_with_movie(tmp_path / "exclusion", long_exclusion))

    def non_movie_metadata(payload: dict[str, object]) -> None:
        reward = tmp_path / "non-movie" / "benefits" / "synthetic-example-reward.json"
        reward_payload = json.loads(reward.read_text(encoding="utf-8"))
        reward_payload["provider"] = "SYNTHETIC-ONLY-provider"
        reward.write_text(json.dumps(reward_payload), encoding="utf-8")

    with pytest.raises(CatalogLoadError, match="only valid for benefit_type 'movie'"):
        load_catalog(_catalog_with_movie(tmp_path / "non-movie", non_movie_metadata))


def test_movie_metadata_is_returned_by_catalog_api_without_activating_review_state(tmp_path: Path) -> None:
    catalog = load_catalog(_catalog_with_movie(tmp_path))
    movie = next(rule for rule in catalog.benefits if rule.benefit_type == "movie")
    assert movie.status == "needs_review"
    assert movie.evidence[0].review_state == "needs_review"
    assert movie.evidence[0].source_tier == 2


def test_approved_movie_metadata_is_serialized_by_public_api(tmp_path: Path) -> None:
    def approve(payload: dict[str, object]) -> None:
        payload["status"] = "active"
        evidence = payload["evidence"]
        assert isinstance(evidence, list)
        assertion = evidence[0]
        assert isinstance(assertion, dict)
        assertion["review_state"] = "approved"
        assertion["confidence"] = "high"
        assertion["reviews"] = [{
            "id": "55555555-5555-4555-8555-555555555556",
            "reviewer_id": "SYNTHETIC-ONLY-MOVIE-REVIEWER",
            "reviewed_at": "2026-08-06T00:00:00Z",
            "decision": "approved",
        }]

    root = _catalog_with_movie(tmp_path, approve)
    app = FastAPI()
    app.include_router(create_catalog_router(root))
    response = TestClient(app).get("/api/v1/catalog/benefits", params={"benefit_type": "movie"})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["provider"] == "SYNTHETIC-ONLY-TICKETING-PROVIDER"
    assert body[0]["official_reference"].startswith("https://")
    assert body[0]["redemption_steps"]
    assert body[0]["exclusions"]
