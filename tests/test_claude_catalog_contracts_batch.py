"""Deterministic tests for batch 4 of the Claude 30-task run.

Covers MC-096 (contribution/PR schema), MC-097 (conflicting assertions are
preserved with an authority explanation), and three general public-catalog
contract hardening tasks: consumer-contract key sets (18), provenance/
effective-date display without raw evidence (19), and unverified/unknown
catalog-state rendering (20).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mycard_benefits.catalog.conflicts import (
    ConflictExplanation,
    explain_all_conflicts,
    explain_conflict,
)
from mycard_benefits.catalog.contribution import (
    ContributionValidationError,
    validate_contribution_disclosure,
)
from mycard_benefits.catalog.loader import CatalogLoadError, load_catalog
from mycard_benefits.catalog.model import BenefitRule, EvidenceAssertion, HumanReview
from mycard_benefits.catalog.router import create_catalog_router

_CONSUMER_BENEFIT_FIELDS = {
    "id", "offering_id", "benefit_type", "title", "state",
    "effective_from", "effective_to", "end_date_known", "rule_version", "supersedes",
    "eligibility", "allowance", "quantities", "provider", "official_reference", "redemption_steps",
    "exclusions", "conflicts_with", "conflicts", "evidence", "not_claimed",
    "source_divergence",
    # Approved into the lock on 2026-08-10 after review. These were serialised
    # before anyone locked the contract; each was checked against what the
    # consumer path actually reads rather than blessed as a group.
    # "owners" and "inheritance" were removed instead: rule authorship and
    # rule-descent mechanics are internal, and a cardholder learns nothing
    # from either.
    "category", "conditions", "earn", "conversion", "valuations", "value_class",
}
_CONSUMER_EVIDENCE_FIELDS = {
    "source_policy_class", "source_tier", "source_url", "content_sha256",
    "retrieved_at", "effective_from", "effective_to", "confidence", "state",
    "approved_review_count", "personalized",
}
_PREEXISTING_CONSUMER_DRIFT_FIELDS = {
    "category", "owners", "conditions", "earn", "conversion", "valuations",
    "value_class", "inheritance",
}
_FORBIDDEN_CONSUMER_KEYS = {
    "status", "review_tier", "review_state", "evidence_status",
}
_FORBIDDEN_CONSUMER_SCALARS = {
    "needs_review", "superseded", "historical", "approved", "stale",
}


def _json_objects(value: object):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _json_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _json_objects(child)


def _json_scalars(value: object):
    if isinstance(value, dict):
        for child in value.values():
            yield from _json_scalars(child)
    elif isinstance(value, list):
        for child in value:
            yield from _json_scalars(child)
    elif isinstance(value, str):
        yield value


def _assert_consumer_body_has_no_governance_vocabulary(body: object) -> None:
    for obj in _json_objects(body):
        assert _FORBIDDEN_CONSUMER_KEYS.isdisjoint(obj), obj
    assert _FORBIDDEN_CONSUMER_SCALARS.isdisjoint(set(_json_scalars(body))), body

ROOT = Path(__file__).parents[1]
CATALOG_ROOT = ROOT / "catalog"


# ---- MC-096: contribution/PR schema with conflict-of-interest disclosure -


def _disclosure(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "summary": "SYNTHETIC-ONLY summary of the change",
        "primary_sources": ["https://example.invalid/synthetic-terms"],
        "has_conflict_of_interest": False,
        "conflict_of_interest_detail": None,
        "uses_only_synthetic_or_public_fixtures": True,
    }
    payload.update(overrides)
    return payload


def test_valid_disclosure_round_trips() -> None:
    disclosure = validate_contribution_disclosure(_disclosure())
    assert disclosure.has_conflict_of_interest is False
    assert disclosure.primary_sources == ("https://example.invalid/synthetic-terms",)


def test_conflict_of_interest_requires_a_non_empty_detail() -> None:
    with pytest.raises(ContributionValidationError, match="conflict_of_interest_detail is required"):
        validate_contribution_disclosure(_disclosure(has_conflict_of_interest=True))
    disclosure = validate_contribution_disclosure(
        _disclosure(has_conflict_of_interest=True, conflict_of_interest_detail="SYNTHETIC-ONLY employed by the issuer")
    )
    assert disclosure.has_conflict_of_interest is True


def test_conflict_of_interest_detail_must_stay_empty_when_no_conflict_is_disclosed() -> None:
    with pytest.raises(ContributionValidationError, match="must be empty"):
        validate_contribution_disclosure(_disclosure(conflict_of_interest_detail="stray detail"))


def test_disclosure_requires_at_least_one_https_primary_source() -> None:
    with pytest.raises(ContributionValidationError, match="primary_sources"):
        validate_contribution_disclosure(_disclosure(primary_sources=[]))
    with pytest.raises(ContributionValidationError, match="anonymous HTTPS URL"):
        validate_contribution_disclosure(_disclosure(primary_sources=["http://example.invalid/insecure"]))


def test_disclosure_rejects_missing_and_unexpected_fields() -> None:
    raw = _disclosure()
    del raw["summary"]
    with pytest.raises(ContributionValidationError, match="missing required disclosure fields"):
        validate_contribution_disclosure(raw)
    raw = _disclosure()
    raw["extra_field"] = "not allowed"
    with pytest.raises(ContributionValidationError, match="unexpected disclosure fields"):
        validate_contribution_disclosure(raw)


def test_disclosure_must_confirm_synthetic_or_public_fixtures_only() -> None:
    with pytest.raises(ContributionValidationError, match="synthetic or already-public fixtures"):
        validate_contribution_disclosure(_disclosure(uses_only_synthetic_or_public_fixtures=False))


def test_pull_request_template_mirrors_the_validated_disclosure_schema() -> None:
    template = (ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md").read_text(encoding="utf-8")
    for field in (
        "summary:",
        "primary_sources:",
        "has_conflict_of_interest:",
        "conflict_of_interest_detail:",
        "uses_only_synthetic_or_public_fixtures:",
    ):
        assert field in template
    assert "conflict of interest" in template.lower()


# ---- MC-097: conflicting assertions are preserved with an authority note -


def _evidence(*, tier_class: str) -> EvidenceAssertion:
    return EvidenceAssertion(
        id="50000000-0000-4000-8000-000000000001",
        source_policy_class=tier_class,
        url="https://example.invalid/synthetic-terms",
        content_sha256="a" * 64,
        retrieved_at=datetime(2026, 8, 1, tzinfo=UTC),
        effective_from=None,
        effective_to=None,
        confidence="high",
        review_state="approved",
        reviews=(HumanReview(id="60000000-0000-4000-8000-000000000001", reviewer_id="SYNTHETIC-ONLY-r", reviewed_at=datetime(2026, 8, 1, tzinfo=UTC), decision="approved"),),
    )


def _rule(rule_id: str, *, tier_class: str, conflicts_with: tuple[str, ...] = ()) -> BenefitRule:
    return BenefitRule(
        id=rule_id,
        offering_id="70000000-0000-4000-8000-000000000001",
        benefit_type="cashback",
        title=f"SYNTHETIC-ONLY {rule_id}",
        status="active",
        review_tier="standard",
        effective_from=None,
        effective_to=None,
        eligibility=(),
        allowance=None,
        evidence=(_evidence(tier_class=tier_class),),
        conflicts_with=conflicts_with,
    )


def test_higher_source_tier_is_explained_as_more_authoritative_without_deleting_either_side() -> None:
    authoritative = _rule("80000000-0000-4000-8000-000000000001", tier_class="administering_terms", conflicts_with=("80000000-0000-4000-8000-000000000002",))
    weaker = _rule("80000000-0000-4000-8000-000000000002", tier_class="regulatory_context", conflicts_with=("80000000-0000-4000-8000-000000000001",))

    explanation = explain_conflict(authoritative, weaker)

    assert explanation.more_authoritative_benefit_id == authoritative.id
    assert explanation.benefit_best_tier == 1
    assert explanation.conflicting_best_tier == 5
    # explain_all_conflicts must still return the conflict for the weaker side, not hide it.
    by_id = {authoritative.id: authoritative, weaker.id: weaker}
    assert explain_all_conflicts(weaker, by_id) == (ConflictExplanation(weaker.id, authoritative.id, 5, 1, authoritative.id),)


def test_equal_tier_conflicts_are_reported_as_unresolved_not_guessed() -> None:
    a = _rule("80000000-0000-4000-8000-000000000003", tier_class="issuer_document", conflicts_with=("80000000-0000-4000-8000-000000000004",))
    b = _rule("80000000-0000-4000-8000-000000000004", tier_class="issuer_document", conflicts_with=("80000000-0000-4000-8000-000000000003",))
    explanation = explain_conflict(a, b)
    assert explanation.more_authoritative_benefit_id is None


def test_explain_conflict_refuses_an_unrecorded_pair() -> None:
    a = _rule("80000000-0000-4000-8000-000000000005", tier_class="issuer_document")
    b = _rule("80000000-0000-4000-8000-000000000006", tier_class="issuer_document")
    with pytest.raises(ValueError, match="not recorded"):
        explain_conflict(a, b)


def test_loader_rejects_a_one_sided_conflicts_with_edge(tmp_path: Path) -> None:
    # A minimal two-benefit catalog (one JSON object per file, matching the
    # real catalog layout) where only one side declares the conflict.
    import json

    (tmp_path / "schema").mkdir()
    (tmp_path / "offerings").mkdir()
    (tmp_path / "benefits").mkdir()
    release_id = "10000000-0000-4000-8000-000000000099"
    offering_id = "20000000-0000-4000-8000-000000000099"
    benefit_a = "30000000-0000-4000-8000-000000000001"
    benefit_b = "30000000-0000-4000-8000-000000000002"
    (tmp_path / "schema" / "release.json").write_text(
        json.dumps({"schema_version": "1", "release_id": release_id, "generated_at": "2026-08-08T00:00:00Z", "market_scope": ["IN"]}),
        encoding="utf-8",
    )
    (tmp_path / "offerings" / "offering.json").write_text(
        json.dumps({"id": offering_id, "slug": "synthetic-only-offering", "display_name": "SYNTHETIC-ONLY", "issuer_id": "synthetic-only-issuer", "product_variant_id": "synthetic-only-variant", "network": "unknown", "tier": None, "acceptance_marks": [], "lounge_programme": None, "market": "IN", "aliases": []}),
        encoding="utf-8",
    )
    evidence = {
        "id": "40000000-0000-4000-8000-000000000001",
        "source_policy_class": "issuer_document",
        "url": "https://example.invalid/synthetic-terms",
        "content_sha256": "a" * 64,
        "retrieved_at": "2026-08-01T00:00:00Z",
        "confidence": "high",
        "review_state": "approved",
        "reviews": [{"id": "60000000-0000-4000-8000-000000000001", "reviewer_id": "SYNTHETIC-ONLY-r", "reviewed_at": "2026-08-01T00:00:00Z", "decision": "approved"}],
    }

    def _benefit(bid: str, conflicts: list[str]) -> dict:
        return {
            "id": bid,
            "offering_id": offering_id,
            "benefit_type": "cashback",
            "title": f"SYNTHETIC-ONLY {bid}",
            "status": "active",
            "review_tier": "standard",
            "eligibility": [],
            "evidence": [evidence],
            "conflicts_with": conflicts,
        }

    (tmp_path / "benefits" / "benefit-a.json").write_text(json.dumps(_benefit(benefit_a, [benefit_b])), encoding="utf-8")
    (tmp_path / "benefits" / "benefit-b.json").write_text(json.dumps(_benefit(benefit_b, [])), encoding="utf-8")
    with pytest.raises(CatalogLoadError, match="does not conflict back"):
        load_catalog(tmp_path)


def test_api_conflict_summary_is_never_hidden_by_the_active_only_benefits_filter(tmp_path: Path) -> None:
    """Counterpart-review P1 fix for MC-097: an active benefit's conflict with a
    needs_review (or historical/superseded) benefit must still be visible,
    even though that conflicting benefit itself is excluded from the default
    active-only `/benefits` list."""
    import json

    (tmp_path / "schema").mkdir()
    (tmp_path / "offerings").mkdir()
    (tmp_path / "benefits").mkdir()
    release_id = "10000000-0000-4000-8000-000000000098"
    offering_id = "20000000-0000-4000-8000-000000000098"
    active_id = "30000000-0000-4000-8000-000000000011"
    needs_review_id = "30000000-0000-4000-8000-000000000012"
    (tmp_path / "schema" / "release.json").write_text(
        json.dumps({"schema_version": "1", "release_id": release_id, "generated_at": "2026-08-08T00:00:00Z", "market_scope": ["IN"]}),
        encoding="utf-8",
    )
    (tmp_path / "offerings" / "offering.json").write_text(
        json.dumps({"id": offering_id, "slug": "synthetic-only-offering-2", "display_name": "SYNTHETIC-ONLY 2", "issuer_id": "synthetic-only-issuer", "product_variant_id": "synthetic-only-variant", "network": "unknown", "tier": None, "acceptance_marks": [], "lounge_programme": None, "market": "IN", "aliases": []}),
        encoding="utf-8",
    )
    active_evidence = {
        "id": "40000000-0000-4000-8000-000000000011",
        "source_policy_class": "administering_terms",
        "url": "https://example.invalid/synthetic-active-terms",
        "content_sha256": "a" * 64,
        "retrieved_at": "2026-08-01T00:00:00Z",
        "confidence": "high",
        "review_state": "approved",
        "reviews": [{"id": "60000000-0000-4000-8000-000000000011", "reviewer_id": "SYNTHETIC-ONLY-r", "reviewed_at": "2026-08-01T00:00:00Z", "decision": "approved"}],
    }
    needs_review_evidence = {
        "id": "40000000-0000-4000-8000-000000000012",
        "source_policy_class": "discovery_only",
        "url": "https://example.invalid/synthetic-needs-review-terms",
        "content_sha256": "b" * 64,
        "retrieved_at": "2026-08-01T00:00:00Z",
        "confidence": "low",
        "review_state": "needs_review",
        "reviews": [],
    }
    active_benefit = {
        "id": active_id,
        "offering_id": offering_id,
        "benefit_type": "cashback",
        "title": "SYNTHETIC-ONLY Active Assertion",
        "status": "active",
        "review_tier": "standard",
        "eligibility": [],
        "evidence": [active_evidence],
        "conflicts_with": [needs_review_id],
    }
    needs_review_benefit = {
        "id": needs_review_id,
        "offering_id": offering_id,
        "benefit_type": "cashback",
        "title": "SYNTHETIC-ONLY Needs-Review Assertion",
        "status": "needs_review",
        "review_tier": "standard",
        "eligibility": [],
        "evidence": [needs_review_evidence],
        "conflicts_with": [active_id],
    }
    (tmp_path / "benefits" / "active.json").write_text(json.dumps(active_benefit), encoding="utf-8")
    (tmp_path / "benefits" / "needs-review.json").write_text(json.dumps(needs_review_benefit), encoding="utf-8")

    app = FastAPI()
    app.include_router(create_catalog_router(tmp_path))
    with TestClient(app) as client:
        default_list = client.get("/api/v1/catalog/benefits").json()
        historical_included = client.get("/api/v1/catalog/benefits", params={"include_historical": True}).json()

    # The needs_review benefit never appears in the list itself, by design...
    assert {item["id"] for item in default_list} == {active_id}
    assert {item["id"] for item in historical_included} == {active_id}
    # ...but the active benefit's own record must still surface the conflict.
    active_summary = default_list[0]
    assert active_summary["conflicts_with"] == [needs_review_id]
    assert len(active_summary["conflicts"]) == 1
    conflict = active_summary["conflicts"][0]
    assert conflict["id"] == needs_review_id
    assert conflict["state"] == "check_before_use"
    assert conflict["title"] == "SYNTHETIC-ONLY Needs-Review Assertion"
    # administering_terms (tier 1) beats discovery_only (tier 6): the active side wins.
    assert conflict["more_authoritative_id"] == active_id


# ---- Task 18: strict public catalog consumer-contract tests ---------------


def test_production_offering_and_benefit_response_shapes_are_locked() -> None:
    app = FastAPI()
    app.include_router(create_catalog_router(CATALOG_ROOT))
    with TestClient(app) as client:
        offerings = client.get("/api/v1/catalog/offerings").json()
        benefits = client.get("/api/v1/catalog/benefits").json()
        relationships = client.get("/api/v1/catalog/relationships").json()

    assert offerings and set(offerings[0]) == {
        "id", "slug", "display_name", "issuer_id", "product_variant_id", "network", "tier",
        "acceptance_marks", "lounge_programme", "market", "co_brand_id", "cohort_id", "aliases",
        "effective_from", "effective_to",
    }
    assert benefits
    _assert_consumer_body_has_no_governance_vocabulary(benefits)
    for benefit in benefits:
        actual_fields = set(benefit)
        assert actual_fields == _CONSUMER_BENEFIT_FIELDS, (
            "consumer benefit contract drift: "
            f"benefit_id={benefit['id']}, "
            f"missing={sorted(_CONSUMER_BENEFIT_FIELDS - actual_fields)}, "
            f"extra={sorted(actual_fields - _CONSUMER_BENEFIT_FIELDS)}, "
            "pre_existing_extra="
            f"{sorted((actual_fields - _CONSUMER_BENEFIT_FIELDS) & _PREEXISTING_CONSUMER_DRIFT_FIELDS)}"
        )
        for evidence in benefit["evidence"]:
            assert set(evidence) == _CONSUMER_EVIDENCE_FIELDS
    if relationships:
        assert "review_state" in relationships[0] and "evidence" in relationships[0]


def test_public_catalog_endpoints_never_require_authentication_or_touch_private_state() -> None:
    app = FastAPI()
    app.include_router(create_catalog_router(CATALOG_ROOT))
    with TestClient(app) as client:
        for path in ("/api/v1/catalog/offerings", "/api/v1/catalog/benefits", "/api/v1/catalog/relationships"):
            response = client.get(path)  # no auth header supplied anywhere in this test
            assert response.status_code == 200


# ---- Task 19: provenance/effective-date display without raw evidence -----


def test_evidence_summary_never_carries_raw_content_only_a_pointer_and_hash() -> None:
    app = FastAPI()
    app.include_router(create_catalog_router(CATALOG_ROOT))
    with TestClient(app) as client:
        benefits = client.get("/api/v1/catalog/benefits").json()
    forbidden_fields = {"raw_content", "content", "body", "text", "html", "screenshot"}
    for benefit in benefits:
        for evidence in benefit["evidence"]:
            assert forbidden_fields.isdisjoint(evidence.keys())
            assert len(evidence["content_sha256"]) == 64


# ---- Task 20: explicit unverified/unknown catalog-state rendering --------


def test_no_end_date_renders_as_explicitly_unknown_not_ongoing_or_blank() -> None:
    script = (ROOT / "src" / "mycard_benefits" / "static" / "app.js").read_text(encoding="utf-8")
    start = script.index("function benefitDates(benefit)")
    end = script.index("\n}", start)
    body = script[start:end]
    assert "No end date is recorded" in body
    assert "ongoing" not in body.lower()


def test_conflicting_assertions_are_rendered_not_silently_dropped() -> None:
    script = (ROOT / "src" / "mycard_benefits" / "static" / "app.js").read_text(encoding="utf-8")
    assert "function sourceDivergenceSection(benefit)" in script
    assert "benefit.source_divergence" in script
    assert "Recorded source differences" in script
    assert "See both retained source claims" in script
    # The rebuilt consumer surface keeps both source claims through the
    # source-divergence projection. It does not resolve a conflict by looking
    # up a filtered catalog item in the client.
    assert "state.benefits.find(item => item.id === conflict" not in script
