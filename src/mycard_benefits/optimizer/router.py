"""Narrow, ephemeral loopback API adapter for the pure route optimizer.

The endpoint accepts a fully self-contained planned-purchase scenario plus
candidate routes, runs the reviewed engine in-process, and returns the ranked
and rejected routes with the engine's provenance, assumptions, value classes,
and rejection reasons.  The request and response are never persisted or
logged, errors never echo request values, and responses carry
``Cache-Control: no-store``.  All semantic validation and ranking stay in the
reviewed engine; this adapter adds only structural bounds.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError

from .engine import optimize
from .model import (
    ComponentValueClass,
    EvidenceTier,
    Freshness,
    LinkClass,
    PurchaseScenario,
    RouteCandidate,
    RouteComponent,
    UserFee,
)

MAX_REQUEST_BYTES = 128 * 1024
MAX_ROUTES = 20
MAX_COMPONENTS_PER_ROUTE = 8
MAX_USER_FEES = 5
MAX_ROUTE_FEES = 5
MAX_SOURCE_REFS = 8
MAX_COMPATIBLE = 8
MAX_CONDITIONS = 10
MAX_ASSUMPTIONS = 10
MAX_INSTRUCTIONS = 10
MAX_ORIGINS = 8
MAX_LINK_CLASSES = 3
MAX_TEXT_LENGTH = 200
MAX_LONG_TEXT_LENGTH = 300
MAX_URL_LENGTH = 2048


class _RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


def _reject_float(value: object) -> object:
    if isinstance(value, float):
        raise ValueError("money must be a decimal string or an integer, not a JSON number")
    return value


Money = Annotated[Decimal, BeforeValidator(_reject_float)]
Text = Annotated[str, Field(min_length=1, max_length=MAX_TEXT_LENGTH)]
LongText = Annotated[str, Field(min_length=1, max_length=MAX_LONG_TEXT_LENGTH)]
UrlText = Annotated[str, Field(min_length=1, max_length=MAX_URL_LENGTH)]


class FeePayload(_RequestModel):
    label: Text
    amount: Money
    currency: Text


class ScenarioPayload(_RequestModel):
    amount: Money
    currency: Text
    as_of: date
    user_fees: list[FeePayload] = Field(default_factory=list, max_length=MAX_USER_FEES)
    allowed_link_classes: list[LinkClass] = Field(min_length=1, max_length=MAX_LINK_CLASSES)
    approved_official_origins: list[UrlText] = Field(min_length=1, max_length=MAX_ORIGINS)


class ComponentPayload(_RequestModel):
    id: Text
    label: Text
    benefit_rule_id: Text
    value_class: ComponentValueClass
    currency: Text
    value_min: Money
    value_max: Money | None = None
    source_refs: list[UrlText] = Field(min_length=1, max_length=MAX_SOURCE_REFS)
    evidence_tier: EvidenceTier
    freshness: Freshness
    verified_on: date
    reviewed: bool
    compatible_with: list[Text] = Field(default_factory=list, max_length=MAX_COMPATIBLE)
    conditions: list[LongText] = Field(default_factory=list, max_length=MAX_CONDITIONS)
    assumptions: list[LongText] = Field(default_factory=list, max_length=MAX_ASSUMPTIONS)
    expires_on: date | None = None
    per_transaction_cap: Money | None = None
    remaining_allowance: Money | None = None
    cap_group: Text | None = None
    time_limited: bool = False
    valuation_name: Text | None = None


class RoutePayload(_RequestModel):
    id: Text
    label: Text
    components: list[ComponentPayload] = Field(min_length=1, max_length=MAX_COMPONENTS_PER_ROUTE)
    instructions: list[LongText] = Field(min_length=1, max_length=MAX_INSTRUCTIONS)
    link_class: LinkClass
    official_reference: UrlText
    route_fees: list[FeePayload] = Field(default_factory=list, max_length=MAX_ROUTE_FEES)


class OptimizerRequest(_RequestModel):
    scenario: ScenarioPayload
    routes: list[RoutePayload] = Field(min_length=1, max_length=MAX_ROUTES)


class ComponentContributionResponse(_ResponseModel):
    id: str
    label: str
    benefit_rule_id: str
    value_class: ComponentValueClass
    currency: str
    value_min: Decimal
    value_max: Decimal
    source_refs: list[str]
    evidence_tier: EvidenceTier
    verified_on: date
    expires_on: date | None
    conditions: list[str]
    assumptions: list[str]


class RankedRouteResponse(_ResponseModel):
    route_id: str
    label: str
    guaranteed_before_fees: Decimal
    scenario_fees: Decimal
    route_fees: Decimal
    total_fees: Decimal
    net_guaranteed: Decimal
    conditional_min: Decimal
    conditional_max: Decimal
    estimated_min: Decimal
    estimated_max: Decimal
    components: list[ComponentContributionResponse]
    assumptions: list[str]
    source_refs: list[str]
    explanation: list[str]
    link_class: LinkClass
    official_reference: str
    value_class_totals_are_non_additive: bool


class RejectedRouteResponse(_ResponseModel):
    route_id: str
    label: str
    reasons: list[str]


class OptimizationResultResponse(_ResponseModel):
    currency: str
    as_of: date
    ranked_routes: list[RankedRouteResponse]
    rejected_routes: list[RejectedRouteResponse]
    status: str
    guidance: str


def create_optimizer_router() -> APIRouter:
    """Create the single ephemeral optimizer endpoint.

    The endpoint has no state, performs no file or network I/O, reads no
    vault, catalog, or user data, and never persists or logs the request or
    response.  Oversized or malformed bodies are rejected before the engine
    runs; stale, unreviewed, inactive, incompatible, or ineligible routes are
    dropped by the engine and returned as rejection reasons.
    """
    router = APIRouter(prefix="/api/v1/optimizer", tags=["optimizer"])

    @router.post("/routes")
    async def optimize_routes(request: Request) -> JSONResponse:
        body = await request.body()
        if len(body) > MAX_REQUEST_BYTES:
            raise HTTPException(status_code=413, detail="request body exceeds the size limit")
        try:
            payload = OptimizerRequest.model_validate_json(body)
        except ValidationError as exc:
            raise _invalid_input(exc) from None
        try:
            result = optimize(
                _scenario(payload.scenario),
                tuple(_route(route) for route in payload.routes),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        response = OptimizationResultResponse.model_validate(result)
        return JSONResponse(
            content=response.model_dump(mode="json"),
            headers={"Cache-Control": "no-store"},
        )

    return router


def _invalid_input(exc: ValidationError) -> HTTPException:
    detail = [
        {"loc": [str(part) for part in error["loc"]], "msg": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]
    return HTTPException(status_code=422, detail=detail)


def _scenario(payload: ScenarioPayload) -> PurchaseScenario:
    return PurchaseScenario(
        amount=payload.amount,
        currency=payload.currency,
        as_of=payload.as_of,
        user_fees=tuple(_fee(fee) for fee in payload.user_fees),
        allowed_link_classes=frozenset(payload.allowed_link_classes),
        approved_official_origins=frozenset(payload.approved_official_origins),
    )


def _route(payload: RoutePayload) -> RouteCandidate:
    return RouteCandidate(
        id=payload.id,
        label=payload.label,
        components=tuple(_component(component) for component in payload.components),
        instructions=tuple(payload.instructions),
        link_class=payload.link_class,
        official_reference=payload.official_reference,
        route_fees=tuple(_fee(fee) for fee in payload.route_fees),
    )


def _component(payload: ComponentPayload) -> RouteComponent:
    return RouteComponent(
        id=payload.id,
        label=payload.label,
        benefit_rule_id=payload.benefit_rule_id,
        value_class=payload.value_class,
        currency=payload.currency,
        value_min=payload.value_min,
        value_max=payload.value_max if payload.value_max is not None else payload.value_min,
        source_refs=tuple(payload.source_refs),
        evidence_tier=payload.evidence_tier,
        freshness=payload.freshness,
        verified_on=payload.verified_on,
        reviewed=payload.reviewed,
        compatible_with=frozenset(payload.compatible_with),
        conditions=tuple(payload.conditions),
        assumptions=tuple(payload.assumptions),
        expires_on=payload.expires_on,
        per_transaction_cap=payload.per_transaction_cap,
        remaining_allowance=payload.remaining_allowance,
        cap_group=payload.cap_group,
        time_limited=payload.time_limited,
        valuation_name=payload.valuation_name,
    )


def _fee(payload: FeePayload) -> UserFee:
    return UserFee(label=payload.label, amount=payload.amount, currency=payload.currency)
