from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from mycard_benefits.app import create_app
from mycard_benefits.config import Settings
from mycard_benefits.destination_workflow import (
    REGALIA_GOLD_TRAVEL_EDGE_CANDIDATE,
    DestinationWorkflow,
    LocalFlightPlan,
    create_destination_workflow_router,
    plan_local_workflow,
)

ROOT = Path(__file__).parents[1]


def _synthetic_workflow_payload() -> dict[str, object]:
    return {
        "id": "synthetic-destination-workflow",
        "official_benefit_id": "synthetic-benefit-rule",
        "official_rule_id": "synthetic-benefit-rule-v1",
        "eligible_offering_ids": ["synthetic-offering"],
        "title": "SYNTHETIC-ONLY destination workflow",
        "qualifying_flight": {
            "payment_card_dependency": "independent",
            "boarding_pass": "required",
            "departure_date": "optional",
            "arrival_date": "required",
        },
        "destination_scope": {"kind": "country_code", "values": ["IN"]},
        "evidence_checklist": [
            {
                "id": "boarding-pass",
                "label": "SYNTHETIC-ONLY boarding-pass evidence available locally",
                "evidence_kind": "boarding_pass",
                "required": True,
            },
            {
                "id": "arrival-details",
                "label": "SYNTHETIC-ONLY arrival details checked",
                "evidence_kind": "arrival_details",
                "required": True,
            },
        ],
        "claim_steps": [
            {
                "id": "check-official-terms",
                "order": 1,
                "instruction": "SYNTHETIC-ONLY check the official terms manually.",
                "channel": "official_portal",
                "manual_action_required": True,
            }
        ],
        "claim_channel": "official_portal",
        "official_url": "https://example.invalid/synthetic-destination-terms",
        "deadline": {"kind": "days_after_arrival", "offset_days": 7},
        "reminder_offsets": [
            {"days_before_deadline": 2, "label": "SYNTHETIC-ONLY two days before"},
            {"days_before_deadline": 1, "label": "SYNTHETIC-ONLY one day before"},
        ],
        "exclusions": ["SYNTHETIC-ONLY no purchase or claim is submitted"],
        "provenance": [
            {
                "source_policy_class": "issuer_document",
                "source_url": "https://example.invalid/synthetic-destination-terms",
                "content_sha256": "a" * 64,
                "retrieved_at": "2026-08-01T00:00:00Z",
                "effective_from": "2026-01-01",
                "effective_to": "2026-12-31",
                "confidence": "high",
                "review_state": "approved",
                "approved_review_count": 1,
                "locator": "SYNTHETIC-ONLY terms section",
            }
        ],
        "effective_from": "2026-01-01",
        "effective_to": "2026-12-31",
        "review_state": "approved",
    }


def _synthetic_workflow() -> DestinationWorkflow:
    return DestinationWorkflow.model_validate(_synthetic_workflow_payload())


def _ready_plan(workflow: DestinationWorkflow) -> LocalFlightPlan:
    return LocalFlightPlan(
        workflow_id=workflow.id,
        arrival_date=date(2026, 8, 10),
        destination="IN",
        boarding_pass_available=True,
        checked_evidence_ids=[item.id for item in workflow.evidence_checklist],
    )


def test_workflow_shape_is_strict_and_links_are_safe() -> None:
    workflow = _synthetic_workflow()
    assert workflow.qualifying_flight.payment_card_dependency == "independent"
    assert workflow.provenance[0].source_tier == 2
    assert workflow.effective_state(date(2026, 8, 10)) == "active"

    extra = _synthetic_workflow_payload()
    extra["unexpected"] = "SYNTHETIC-ONLY"
    with pytest.raises(ValidationError):
        DestinationWorkflow.model_validate(extra)

    unsafe_link = _synthetic_workflow_payload()
    unsafe_link["official_url"] = "http://example.invalid/terms"
    with pytest.raises(ValidationError):
        DestinationWorkflow.model_validate(unsafe_link)

    unknown_scope = _synthetic_workflow_payload()
    unknown_scope["destination_scope"] = {"kind": "country_code", "values": []}
    with pytest.raises(ValidationError):
        DestinationWorkflow.model_validate(unknown_scope)

    missing_end = DestinationWorkflow.model_validate(
        {**_synthetic_workflow_payload(), "effective_to": None}
    )
    assert missing_end.effective_state(date(2026, 8, 10)) == "unknown"
    assert not missing_end.is_publishable(date(2026, 8, 10))


def test_independent_card_trigger_calculates_checklist_deadline_and_reminders() -> None:
    workflow = _synthetic_workflow()
    result = plan_local_workflow(workflow, _ready_plan(workflow), as_of=date(2026, 8, 10))

    assert result.status == "ready"
    assert result.reasons == []
    assert result.deadline == date(2026, 8, 17)
    assert result.reminders == [date(2026, 8, 15), date(2026, 8, 16)]
    assert set(LocalFlightPlan.model_fields) == {
        "workflow_id",
        "departure_date",
        "arrival_date",
        "destination",
        "boarding_pass_available",
        "checked_evidence_ids",
    }
    serialized = _ready_plan(workflow).model_dump_json()
    for forbidden in ("pan", "cvv", "pin", "passenger", "booking_reference", "file"):
        assert forbidden not in serialized.casefold()


def test_unknown_expired_and_unapproved_workflows_are_suppressed() -> None:
    workflow = _synthetic_workflow()
    unknown = plan_local_workflow(
        workflow,
        LocalFlightPlan(workflow_id=workflow.id, boarding_pass_available=True),
        as_of=date(2026, 8, 10),
    )
    assert unknown.status == "unknown"
    assert "arrival_date_unknown" in unknown.reasons

    expired_workflow = workflow.model_copy(update={"effective_to": date(2026, 7, 31)})
    expired = plan_local_workflow(
        expired_workflow, _ready_plan(expired_workflow), as_of=date(2026, 8, 10)
    )
    assert expired.status == "suppressed"
    assert "workflow_expired" in expired.reasons
    assert expired.deadline is None

    unapproved_workflow = workflow.model_copy(update={"review_state": "needs_review"})
    unapproved = plan_local_workflow(
        unapproved_workflow, _ready_plan(unapproved_workflow), as_of=date(2026, 8, 10)
    )
    assert unapproved.status == "suppressed"
    assert unapproved.reasons == ["workflow_not_approved"]

    candidate = REGALIA_GOLD_TRAVEL_EDGE_CANDIDATE
    assert candidate.review_state == "needs_review"
    assert not candidate.is_publishable(date(2026, 8, 10))


def test_public_api_filters_activation_and_surfaces_travel_edge_candidate() -> None:
    app = FastAPI()
    app.include_router(
        create_destination_workflow_router(
            workflows=(_synthetic_workflow(),),
            candidates=(REGALIA_GOLD_TRAVEL_EDGE_CANDIDATE,),
        )
    )
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/catalog/destination-workflows", params={"as_of": "2026-08-10"}
        )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    body = response.json()
    assert body["schema_version"] == "destination-workflow-v1"
    assert [item["id"] for item in body["workflows"]] == ["synthetic-destination-workflow"]
    assert body["workflows"][0]["publication_state"] == "reviewed_active"
    assert body["workflows"][0]["provenance"][0]["source_tier"] == 2
    assert [item["id"] for item in body["candidates"]] == [
        "regalia-gold-travel-edge-candidate"
    ]
    assert body["candidates"][0]["review_state"] == "needs_review"
    assert body["candidates"][0]["publication_state"] == "candidate"
    assert "pan" not in response.text.casefold()


def test_removed_workflow_surface_is_read_only_and_not_in_the_dashboard(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        catalog_dir=ROOT / "tests" / "fixtures" / "synthetic_catalog",
        port=8777,
    )
    with TestClient(create_app(settings)) as client:
        response = client.get(
            "/api/v1/catalog/destination-workflows", params={"as_of": "2026-08-10"}
        )
        validation_error = client.get(
            "/api/v1/catalog/destination-workflows", params={"as_of": "not-a-date"}
        )
        page = client.get("/")

    assert response.status_code == 200
    assert response.json()["workflows"] == []
    assert response.json()["candidates"][0]["review_state"] == "needs_review"
    assert response.headers["cache-control"] == "no-store"
    assert validation_error.status_code == 422
    assert validation_error.headers["cache-control"] == "no-store"
    assert validation_error.headers["pragma"] == "no-cache"
    assert page.headers["cache-control"] == "no-store"
    assert page.headers["pragma"] == "no-cache"
    assert 'data-view="benefits"' in page.text
    assert 'data-view="search"' in page.text
    assert 'data-view="which-card"' not in page.text
    assert 'id="workflowPlanForm"' not in page.text
    assert 'id="workflowChecklist"' not in page.text
    assert 'input type="file"' not in page.text

    script = (ROOT / "src" / "mycard_benefits" / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    workflow_slice = script[script.index("function setWorkflowStatus") : script.index("async function boot")]
    assert 'fetch("/api/v1/catalog/destination-workflows"' in workflow_slice
    assert 'method: "POST"' not in workflow_slice
    assert "FormData" not in workflow_slice
    assert "localStorage" not in workflow_slice
    assert "downloadWorkflowReminder" in workflow_slice
