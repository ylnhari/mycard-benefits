"""Strict, public-only boarding-pass destination workflows.

This module deliberately stays separate from the released benefit catalog and
from the private vault.  A workflow can describe the shape of an indirect
benefit without making that benefit active.  Publication requires an approved
workflow, complete effective dates, known qualifying-flight terms, and
current approved evidence.  Local planning accepts only value-minimized facts
and is never exposed as an HTTP request model.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal, Self
from urllib.parse import urlparse

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


WorkflowId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9][a-z0-9._-]*$",
    ),
]
PublicText = Annotated[str, Field(min_length=1, max_length=300)]
ScopeValue = Annotated[
    str,
    Field(
        min_length=2,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9 _./-]*$",
    ),
]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

ReviewState = Literal["approved", "needs_review", "blocked", "rejected"]
EvidenceReviewState = Literal["approved", "needs_review", "blocked", "rejected"]
EffectiveState = Literal["active", "future", "expired", "unknown"]
PublicationState = Literal["reviewed_active", "candidate"]
SourcePolicyClass = Literal[
    "administering_terms",
    "issuer_document",
    "network_rule",
    "merchant_terms",
    "regulatory_context",
    "discovery_only",
]
Confidence = Literal["high", "medium", "low"]

_SOURCE_TIERS = {
    "administering_terms": 1,
    "issuer_document": 2,
    "network_rule": 3,
    "merchant_terms": 4,
    "regulatory_context": 5,
    "discovery_only": 6,
}
def _https_url(value: str, field_name: str) -> str:
    """Validate a link before it can cross the public UI boundary."""

    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or any(character.isspace() for character in value)
    ):
        raise ValueError(f"{field_name} must be an HTTPS URL without credentials or fragments")
    return value


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("retrieved_at must be timezone-aware")
    return value


class DestinationScope(_StrictModel):
    """A closed destination scope; ``unknown`` never matches a plan."""

    kind: Literal["any", "airport_code", "country_code", "region", "unknown"]
    values: list[ScopeValue] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_values(self) -> Self:
        if len({item.casefold() for item in self.values}) != len(self.values):
            raise ValueError("destination scope values must be unique")
        if self.kind in {"any", "unknown"} and self.values:
            raise ValueError("any and unknown destination scopes cannot list values")
        if self.kind not in {"any", "unknown"} and not self.values:
            raise ValueError("a bounded destination scope requires at least one value")
        return self


class QualifyingFlightPredicate(_StrictModel):
    """Facts needed to evaluate the flight, independent of the paying card."""

    payment_card_dependency: Literal["independent", "same_card", "unknown"]
    boarding_pass: Literal["required", "optional", "unknown"]
    departure_date: Literal["required", "optional", "unknown"]
    arrival_date: Literal["required", "optional", "unknown"]


class EvidenceChecklistItem(_StrictModel):
    id: WorkflowId
    label: PublicText
    evidence_kind: Literal[
        "boarding_pass",
        "arrival_details",
        "identity_confirmation",
        "claim_reference",
        "other",
        "unknown",
    ]
    required: bool = True


class ClaimStep(_StrictModel):
    id: WorkflowId
    order: int = Field(ge=1, le=32)
    instruction: PublicText
    channel: Literal[
        "official_portal",
        "issuer_support",
        "merchant_support",
        "manual",
        "unknown",
    ]
    manual_action_required: bool = True

    @field_validator("manual_action_required")
    @classmethod
    def require_explicit_action(cls, value: bool) -> bool:
        if not value:
            raise ValueError("claim steps must remain explicit human actions")
        return value


class DeadlineRule(_StrictModel):
    kind: Literal["days_after_arrival", "days_after_departure", "unknown"]
    offset_days: int | None = Field(default=None, ge=0, le=3650)

    @model_validator(mode="after")
    def validate_offset(self) -> Self:
        if self.kind == "unknown" and self.offset_days is not None:
            raise ValueError("an unknown deadline cannot include an offset")
        if self.kind != "unknown" and self.offset_days is None:
            raise ValueError("a known deadline requires an offset")
        return self


class ReminderOffset(_StrictModel):
    days_before_deadline: int = Field(ge=0, le=3650)
    label: PublicText


class WorkflowProvenance(_StrictModel):
    source_policy_class: SourcePolicyClass
    source_url: str = Field(min_length=1, max_length=2048)
    content_sha256: Sha256
    retrieved_at: datetime
    effective_from: date | None = None
    effective_to: date | None = None
    confidence: Confidence
    review_state: EvidenceReviewState
    approved_review_count: int = Field(ge=0, le=2)
    locator: PublicText

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str) -> str:
        return _https_url(value, "source_url")

    @field_validator("retrieved_at")
    @classmethod
    def validate_retrieved_at(cls, value: datetime) -> datetime:
        return _aware_datetime(value)

    @model_validator(mode="after")
    def validate_dates_and_review(self) -> Self:
        if (
            self.effective_from is not None
            and self.effective_to is not None
            and self.effective_to < self.effective_from
        ):
            raise ValueError("provenance effective_to cannot precede effective_from")
        if self.review_state == "approved" and self.approved_review_count < 1:
            raise ValueError("approved provenance requires an approved human-review count")
        if self.source_policy_class == "discovery_only" and self.review_state == "approved":
            raise ValueError("discovery-only provenance cannot be approved")
        return self

    @property
    def source_tier(self) -> int:
        """Derive, rather than accept, the numeric source tier."""

        return _SOURCE_TIERS[self.source_policy_class]

    def is_current_approved(self, as_of: date) -> bool:
        return (
            self.review_state == "approved"
            and self.confidence in {"high", "medium"}
            and self.approved_review_count >= 1
            and self.retrieved_at.astimezone(UTC).date() <= as_of
            and (self.effective_from is None or self.effective_from <= as_of)
            and (self.effective_to is None or as_of <= self.effective_to)
        )


class DestinationWorkflow(_StrictModel):
    """A public workflow definition, not a private claim or upload record."""

    id: WorkflowId
    official_benefit_id: WorkflowId
    official_rule_id: WorkflowId
    eligible_offering_ids: list[WorkflowId] = Field(min_length=1, max_length=32)
    title: PublicText
    qualifying_flight: QualifyingFlightPredicate
    destination_scope: DestinationScope
    evidence_checklist: list[EvidenceChecklistItem] = Field(min_length=1, max_length=16)
    claim_steps: list[ClaimStep] = Field(min_length=1, max_length=16)
    claim_channel: Literal[
        "official_portal",
        "issuer_support",
        "merchant_support",
        "manual",
        "unknown",
    ]
    official_url: str = Field(min_length=1, max_length=2048)
    deadline: DeadlineRule
    reminder_offsets: list[ReminderOffset] = Field(default_factory=list, max_length=16)
    exclusions: list[PublicText] = Field(min_length=1, max_length=16)
    provenance: list[WorkflowProvenance] = Field(min_length=1, max_length=16)
    effective_from: date | None = None
    effective_to: date | None = None
    review_state: ReviewState

    @field_validator("official_url")
    @classmethod
    def validate_official_url(cls, value: str) -> str:
        return _https_url(value, "official_url")

    @field_validator("eligible_offering_ids")
    @classmethod
    def validate_offering_ids(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("eligible offering IDs must be unique")
        return values

    @model_validator(mode="after")
    def validate_shape(self) -> Self:
        if (
            self.effective_from is not None
            and self.effective_to is not None
            and self.effective_to < self.effective_from
        ):
            raise ValueError("workflow effective_to cannot precede effective_from")
        checklist_ids = [item.id for item in self.evidence_checklist]
        if len(set(checklist_ids)) != len(checklist_ids):
            raise ValueError("evidence checklist IDs must be unique")
        step_ids = [item.id for item in self.claim_steps]
        if len(set(step_ids)) != len(step_ids):
            raise ValueError("claim step IDs must be unique")
        if [step.order for step in self.claim_steps] != list(range(1, len(self.claim_steps) + 1)):
            raise ValueError("claim steps must be ordered consecutively from one")
        reminder_days = [item.days_before_deadline for item in self.reminder_offsets]
        if len(set(reminder_days)) != len(reminder_days):
            raise ValueError("reminder offsets must be unique")
        return self

    def effective_state(self, as_of: date) -> EffectiveState:
        """Return a state that never treats a missing end date as perpetual."""

        if self.effective_from is None or self.effective_to is None:
            return "unknown"
        if as_of < self.effective_from:
            return "future"
        if as_of > self.effective_to:
            return "expired"
        return "active"

    def has_known_terms(self) -> bool:
        return (
            self.qualifying_flight.payment_card_dependency != "unknown"
            and self.qualifying_flight.boarding_pass != "unknown"
            and self.qualifying_flight.departure_date != "unknown"
            and self.qualifying_flight.arrival_date != "unknown"
            and self.destination_scope.kind != "unknown"
            and self.claim_channel != "unknown"
            and self.deadline.kind != "unknown"
            and all(item.evidence_kind != "unknown" for item in self.evidence_checklist)
            and all(step.channel != "unknown" for step in self.claim_steps)
        )

    def is_publishable(self, as_of: date) -> bool:
        return (
            self.review_state == "approved"
            and self.effective_state(as_of) == "active"
            and self.has_known_terms()
            and all(item.is_current_approved(as_of) for item in self.provenance)
        )


class WorkflowProvenanceSummary(_StrictModel):
    source_policy_class: SourcePolicyClass
    source_tier: int
    source_url: str
    content_sha256: Sha256
    retrieved_at: datetime
    effective_from: date | None
    effective_to: date | None
    confidence: Confidence
    review_state: EvidenceReviewState
    approved_review_count: int
    locator: PublicText


class DestinationWorkflowSummary(_StrictModel):
    id: WorkflowId
    official_benefit_id: WorkflowId
    official_rule_id: WorkflowId
    eligible_offering_ids: list[WorkflowId]
    title: PublicText
    qualifying_flight: QualifyingFlightPredicate
    destination_scope: DestinationScope
    evidence_checklist: list[EvidenceChecklistItem]
    claim_steps: list[ClaimStep]
    claim_channel: Literal[
        "official_portal",
        "issuer_support",
        "merchant_support",
        "manual",
        "unknown",
    ]
    official_url: str
    deadline: DeadlineRule
    reminder_offsets: list[ReminderOffset]
    exclusions: list[PublicText]
    provenance: list[WorkflowProvenanceSummary]
    effective_from: date | None
    effective_to: date | None
    review_state: ReviewState
    effective_state: EffectiveState
    publication_state: PublicationState


class DestinationWorkflowCollection(_StrictModel):
    schema_version: Literal["destination-workflow-v1"]
    as_of: date
    workflows: list[DestinationWorkflowSummary]
    candidates: list[DestinationWorkflowSummary]


LocalDestinationCode = Annotated[
    str,
    Field(min_length=2, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9 _./-]*$"),
]


class LocalFlightPlan(_StrictModel):
    """Value-minimized local facts; intentionally no card, passenger, or file fields."""

    workflow_id: WorkflowId
    departure_date: date | None = None
    arrival_date: date | None = None
    destination: LocalDestinationCode | None = None
    boarding_pass_available: bool | None = None
    checked_evidence_ids: list[WorkflowId] = Field(default_factory=list, max_length=16)

    @field_validator("checked_evidence_ids")
    @classmethod
    def validate_checked_ids(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("checked evidence IDs must be unique")
        return values


class LocalWorkflowPlanResult(_StrictModel):
    workflow_id: WorkflowId
    status: Literal["ready", "incomplete", "unknown", "suppressed"]
    reasons: list[str]
    deadline: date | None = None
    reminders: list[date] = Field(default_factory=list)


def _scope_matches(scope: DestinationScope, destination: str | None) -> bool | None:
    if scope.kind == "unknown" or destination is None:
        return None
    if scope.kind == "any":
        return True
    normalized = destination.strip().casefold()
    return normalized in {item.casefold() for item in scope.values}


def _deadline_for(workflow: DestinationWorkflow, plan: LocalFlightPlan) -> date | None:
    if workflow.deadline.offset_days is None:
        return None
    if workflow.deadline.kind == "days_after_arrival":
        anchor = plan.arrival_date
    elif workflow.deadline.kind == "days_after_departure":
        anchor = plan.departure_date
    else:
        anchor = None
    return anchor + timedelta(days=workflow.deadline.offset_days) if anchor else None


def _suppressed_reasons(workflow: DestinationWorkflow, as_of: date) -> list[str]:
    reasons: list[str] = []
    if workflow.review_state != "approved" or not all(
        item.is_current_approved(as_of) for item in workflow.provenance
    ):
        reasons.append("workflow_not_approved")
    effective = workflow.effective_state(as_of)
    if effective == "expired":
        reasons.append("workflow_expired")
    elif effective == "future":
        reasons.append("workflow_not_yet_effective")
    elif effective == "unknown":
        reasons.append("workflow_effective_dates_unknown")
    if not workflow.has_known_terms():
        reasons.append("workflow_terms_unknown")
    return reasons


def plan_local_workflow(
    workflow: DestinationWorkflow,
    plan: LocalFlightPlan,
    *,
    as_of: date,
) -> LocalWorkflowPlanResult:
    """Evaluate only local readiness, never eligibility or a claim.

    ``None`` means an unknown fact.  Unknown or unapproved workflow data is
    never converted to a positive result.
    """

    if plan.workflow_id != workflow.id:
        return LocalWorkflowPlanResult(
            workflow_id=workflow.id,
            status="suppressed",
            reasons=["workflow_id_mismatch"],
        )
    suppressed = _suppressed_reasons(workflow, as_of)
    if suppressed:
        return LocalWorkflowPlanResult(
            workflow_id=workflow.id,
            status="suppressed",
            reasons=suppressed,
        )

    unknown: list[str] = []
    incomplete: list[str] = []
    predicate = workflow.qualifying_flight
    if predicate.payment_card_dependency != "independent":
        unknown.append("card_payment_dependency_not_independent")
    if predicate.arrival_date == "required" and plan.arrival_date is None:
        unknown.append("arrival_date_unknown")
    if predicate.departure_date == "required" and plan.departure_date is None:
        unknown.append("departure_date_unknown")
    if predicate.boarding_pass == "required":
        if plan.boarding_pass_available is None:
            unknown.append("boarding_pass_state_unknown")
        elif not plan.boarding_pass_available:
            incomplete.append("boarding_pass_not_marked_available")
    destination_match = _scope_matches(workflow.destination_scope, plan.destination)
    if destination_match is None and workflow.destination_scope.kind != "any":
        unknown.append("destination_unknown")
    elif destination_match is False:
        incomplete.append("destination_outside_scope")
    expected_ids = {item.id for item in workflow.evidence_checklist if item.required}
    checked_ids = set(plan.checked_evidence_ids)
    if not checked_ids.issubset({item.id for item in workflow.evidence_checklist}):
        unknown.append("checklist_item_unknown")
    elif not expected_ids.issubset(checked_ids):
        incomplete.append("evidence_checklist_incomplete")

    flight_date = plan.arrival_date or plan.departure_date
    if flight_date is not None:
        if workflow.effective_from is None or workflow.effective_to is None:
            unknown.append("workflow_effective_dates_unknown")
        elif not workflow.effective_from <= flight_date <= workflow.effective_to:
            incomplete.append("flight_outside_effective_dates")

    deadline = _deadline_for(workflow, plan)
    if workflow.deadline.kind != "unknown" and deadline is None:
        unknown.append("deadline_anchor_unknown")
    reminders = (
        sorted(
            deadline - timedelta(days=item.days_before_deadline)
            for item in workflow.reminder_offsets
        )
        if deadline is not None
        else []
    )
    if unknown:
        return LocalWorkflowPlanResult(
            workflow_id=workflow.id,
            status="unknown",
            reasons=unknown,
            deadline=deadline,
            reminders=reminders,
        )
    if incomplete:
        return LocalWorkflowPlanResult(
            workflow_id=workflow.id,
            status="incomplete",
            reasons=incomplete,
            deadline=deadline,
            reminders=reminders,
        )
    return LocalWorkflowPlanResult(
        workflow_id=workflow.id,
        status="ready",
        reasons=[],
        deadline=deadline,
        reminders=reminders,
    )


def _workflow_summary(
    workflow: DestinationWorkflow,
    *,
    as_of: date,
    publication_state: PublicationState,
) -> DestinationWorkflowSummary:
    payload = workflow.model_dump()
    payload["effective_state"] = workflow.effective_state(as_of)
    payload["publication_state"] = publication_state
    payload["provenance"] = [
        {
            **item.model_dump(),
            "source_tier": item.source_tier,
        }
        for item in workflow.provenance
    ]
    return DestinationWorkflowSummary.model_validate(payload)


def create_destination_workflow_router(
    workflows: tuple[DestinationWorkflow, ...] = (),
    candidates: tuple[DestinationWorkflow, ...] | None = None,
) -> APIRouter:
    """Create the read-only public workflow endpoint.

    ``workflows`` is explicit so production code cannot accidentally turn a
    candidate into an active catalog record.  The default candidate is a
    source-bound Travel Edge example with no active benefit claim.
    """

    reviewed_workflows = tuple(workflows)
    candidate_workflows = (
        (REGALIA_GOLD_TRAVEL_EDGE_CANDIDATE,)
        if candidates is None
        else tuple(candidates)
    )
    router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])

    @router.get("/destination-workflows", response_model=DestinationWorkflowCollection)
    def list_destination_workflows(
        response: Response,
        as_of: date | None = None,
    ) -> DestinationWorkflowCollection:
        effective_date = as_of or date.today()
        response.headers.update({"Cache-Control": "no-store", "Pragma": "no-cache"})
        return DestinationWorkflowCollection(
            schema_version="destination-workflow-v1",
            as_of=effective_date,
            workflows=[
                _workflow_summary(
                    workflow,
                    as_of=effective_date,
                    publication_state="reviewed_active",
                )
                for workflow in reviewed_workflows
                if workflow.is_publishable(effective_date)
            ],
            candidates=[
                _workflow_summary(
                    workflow,
                    as_of=effective_date,
                    publication_state="candidate",
                )
                for workflow in candidate_workflows
                if workflow.review_state in {"needs_review", "blocked"}
            ],
        )

    return router


REGALIA_GOLD_TRAVEL_EDGE_CANDIDATE = DestinationWorkflow.model_validate(
    {
        "id": "regalia-gold-travel-edge-candidate",
        "official_benefit_id": "regalia-gold-travel-edge",
        "official_rule_id": "regalia-gold-travel-edge-rule",
        "eligible_offering_ids": ["83a6036e-bd88-5cb8-aa8f-676521050f68"],
        "title": "HDFC Bank Regalia Gold Travel Edge — review candidate",
        "qualifying_flight": {
            "payment_card_dependency": "independent",
            "boarding_pass": "required",
            "departure_date": "unknown",
            "arrival_date": "unknown",
        },
        "destination_scope": {"kind": "unknown", "values": []},
        "evidence_checklist": [
            {
                "id": "boarding-pass",
                "label": "Boarding-pass evidence, retained locally only",
                "evidence_kind": "boarding_pass",
            },
            {
                "id": "arrival-details",
                "label": "Arrival and destination terms confirmed by a human reviewer",
                "evidence_kind": "unknown",
            },
        ],
        "claim_steps": [
            {
                "id": "confirm-current-terms",
                "order": 1,
                "instruction": "Confirm the current official terms before taking any claim action.",
                "channel": "unknown",
                "manual_action_required": True,
            }
        ],
        "claim_channel": "unknown",
        "official_url": "https://www.hdfc.bank.in/content/dam/hdfcbankpws/in/en/personal-banking/discover-products/cards/credit-cards/regalia-gold-credit-card/pdfs/regalia-gold-travel-edge-tnc.pdf",
        "deadline": {"kind": "unknown", "offset_days": None},
        "reminder_offsets": [],
        "exclusions": [
            "Blocked source evidence is not an active benefit claim.",
            "No benefit amount, destination rule, deadline, or eligibility is asserted.",
            "This app never uploads a boarding pass or submits a claim.",
        ],
        "provenance": [
            {
                "source_policy_class": "issuer_document",
                "source_url": "https://www.hdfc.bank.in/content/dam/hdfcbankpws/in/en/personal-banking/discover-products/cards/credit-cards/regalia-gold-credit-card/pdfs/regalia-gold-travel-edge-tnc.pdf",
                "content_sha256": "d8da03f067f5247bbaf47aa86280f0c84ecefc65de19bb23595b117d8a578208",
                "retrieved_at": "2026-08-09T12:00:00Z",
                "effective_from": "2026-01-01",
                "effective_to": None,
                "confidence": "low",
                "review_state": "blocked",
                "approved_review_count": 0,
                "locator": "Travel Edge terms, source-bound review record",
            }
        ],
        "effective_from": "2026-01-01",
        "effective_to": None,
        "review_state": "needs_review",
    }
)


__all__ = [
    "ClaimStep",
    "DeadlineRule",
    "DestinationScope",
    "DestinationWorkflow",
    "DestinationWorkflowCollection",
    "DestinationWorkflowSummary",
    "EvidenceChecklistItem",
    "LocalFlightPlan",
    "LocalWorkflowPlanResult",
    "QualifyingFlightPredicate",
    "REGALIA_GOLD_TRAVEL_EDGE_CANDIDATE",
    "ReminderOffset",
    "WorkflowProvenance",
    "WorkflowProvenanceSummary",
    "create_destination_workflow_router",
    "plan_local_workflow",
]
