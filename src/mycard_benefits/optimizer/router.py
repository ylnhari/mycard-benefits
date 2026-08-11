"""Narrow, ephemeral loopback API adapter for the pure route optimizer.

The endpoint accepts a fully self-contained planned-purchase scenario plus
candidate routes, runs the reviewed engine in-process, and returns the ranked
and rejected routes with the engine's provenance, assumptions, value classes,
and rejection reasons.  The request and response are never persisted or
logged, errors never echo request values, and every response carries
``Cache-Control: no-store``.  All semantic validation and ranking stay in the
reviewed engine; this adapter adds only structural bounds.

The request body is read through a bounded stream: a declared
``Content-Length`` over the limit is rejected before any body is read, and
chunked bodies are rejected the moment the accumulated bytes cross the limit
without buffering past it.  The endpoint declares the request and response
models in the OpenAPI document so ``/api/docs`` documents the request body and
the ``200``, ``413``, and ``422`` responses.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ValidationError,
    WithJsonSchema,
    field_validator,
)

from .engine import optimize
from .model import (
    ActionLinkReviewState,
    ComponentValueClass,
    EvidenceTier,
    Freshness,
    LinkClass,
    PurchaseScenario,
    RouteCandidate,
    RouteComponent,
    RouteLayer,
    UserFee,
    canonical_https_origin,
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

_NO_STORE = {"Cache-Control": "no-store"}


class _RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


def _reject_float(value: object) -> object:
    if isinstance(value, float):
        raise ValueError("money must be a decimal string or an integer, not a JSON number")
    return value


Money = Annotated[
    Decimal,
    BeforeValidator(_reject_float),
    WithJsonSchema(
        {
            "oneOf": [
                {"type": "string", "pattern": r"^-?\d+(\.\d{1,6})?$"},
                {"type": "integer"},
            ],
            "description": "exact money as a decimal string or an integer",
        }
    ),
]
MoneyResponse = Annotated[
    Decimal,
    WithJsonSchema({"type": "string", "description": "exact money as a decimal string"}),
]
Text = Annotated[str, Field(min_length=1, max_length=MAX_TEXT_LENGTH)]
LongText = Annotated[str, Field(min_length=1, max_length=MAX_LONG_TEXT_LENGTH)]
UrlText = Annotated[
    str,
    Field(min_length=1, max_length=MAX_URL_LENGTH, description="anonymous HTTPS URL"),
]


def _require_unique(values: list[Any], message: str) -> list[Any]:
    if len(values) != len(set(values)):
        raise ValueError(message)
    return values


def _require_unique_origins(values: list[str]) -> list[str]:
    seen: set[str] = set()
    for origin in values:
        try:
            canonical = canonical_https_origin(
                origin, "admitted_action_origin", origin_entry=True
            )
        except ValueError:
            canonical = origin.casefold()
        if canonical in seen:
            raise ValueError("admitted action origins must be unique")
        seen.add(canonical)
    return values


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
    admitted_action_origins: list[UrlText] = Field(min_length=1, max_length=MAX_ORIGINS)

    @field_validator("allowed_link_classes")
    @classmethod
    def _no_duplicate_link_classes(cls, values: list[LinkClass]) -> list[LinkClass]:
        return _require_unique(values, "allowed link classes must be unique")

    @field_validator("admitted_action_origins")
    @classmethod
    def _no_duplicate_origins(cls, values: list[str]) -> list[str]:
        return _require_unique_origins(values)


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
    benefit_state: Literal["verified"] = "verified"
    compatible_with: list[Text] = Field(default_factory=list, max_length=MAX_COMPATIBLE)
    conditions: list[LongText] = Field(default_factory=list, max_length=MAX_CONDITIONS)
    assumptions: list[LongText] = Field(default_factory=list, max_length=MAX_ASSUMPTIONS)
    expires_on: date | None = None
    per_transaction_cap: Money | None = None
    remaining_allowance: Money | None = None
    cap_group: Text | None = None
    time_limited: bool = False
    valuation_name: Text | None = None
    layer: RouteLayer | None = None

    @field_validator("compatible_with")
    @classmethod
    def _no_duplicate_stacking_refs(cls, values: list[str]) -> list[str]:
        return _require_unique(values, "stacking references must be unique")


class RoutePayload(_RequestModel):
    id: Text
    label: Text
    components: list[ComponentPayload] = Field(min_length=1, max_length=MAX_COMPONENTS_PER_ROUTE)
    instructions: list[LongText] = Field(min_length=1, max_length=MAX_INSTRUCTIONS)
    link_class: LinkClass
    official_reference: UrlText
    action_link_review_state: ActionLinkReviewState
    route_fees: list[FeePayload] = Field(default_factory=list, max_length=MAX_ROUTE_FEES)

    @field_validator("components")
    @classmethod
    def _no_duplicate_component_ids(
        cls, components: list[ComponentPayload]
    ) -> list[ComponentPayload]:
        ids = [component.id for component in components]
        if len(ids) != len(set(ids)):
            raise ValueError("component IDs must be unique within a route")
        return components


class OptimizerRequest(_RequestModel):
    scenario: ScenarioPayload
    routes: list[RoutePayload] = Field(min_length=1, max_length=MAX_ROUTES)


class ComponentContributionResponse(_ResponseModel):
    id: str
    label: str
    benefit_rule_id: str
    value_class: ComponentValueClass
    currency: str
    value_min: MoneyResponse
    value_max: MoneyResponse
    source_refs: list[str]
    evidence_tier: EvidenceTier
    verified_on: date
    expires_on: date | None
    conditions: list[str]
    assumptions: list[str]
    per_transaction_cap: MoneyResponse | None
    remaining_allowance: MoneyResponse | None
    layer: RouteLayer | None


class RankedRouteResponse(_ResponseModel):
    route_id: str
    label: str
    guaranteed_before_fees: MoneyResponse
    scenario_fees: MoneyResponse
    route_fees: MoneyResponse
    total_fees: MoneyResponse
    net_guaranteed: MoneyResponse
    conditional_min: MoneyResponse
    conditional_max: MoneyResponse
    estimated_min: MoneyResponse
    estimated_max: MoneyResponse
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


class OversizeErrorResponse(_ResponseModel):
    detail: str


class ValidationErrorItemResponse(_ResponseModel):
    loc: list[str]
    msg: str
    type: str


class ValidationErrorResponse(_ResponseModel):
    detail: list[ValidationErrorItemResponse] | str


async def _read_bounded_body(request: Request) -> bytes | None:
    length_header = request.headers.get("content-length")
    if length_header is not None:
        try:
            declared = int(length_header)
        except ValueError:
            declared = None
        if declared is not None and declared > MAX_REQUEST_BYTES:
            return None
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        if total + len(chunk) > MAX_REQUEST_BYTES:
            return None
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks)


def _error(status_code: int, detail: object) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail},
        headers=_NO_STORE,
    )


def create_optimizer_router() -> APIRouter:
    """Create the single ephemeral optimizer endpoint.

    The endpoint has no state, performs no file or network I/O, reads no
    vault, catalog, or user data, and never persists or logs the request or
    response.  Oversized or malformed bodies are rejected before the engine
    runs; stale, unreviewed, inactive, incompatible, or ineligible routes are
    dropped by the engine and returned as rejection reasons.
    """
    router = APIRouter(prefix="/api/v1/optimizer", tags=["optimizer"])

    @router.post("/routes", response_model=OptimizationResultResponse)
    async def optimize_routes(request: Request) -> JSONResponse:
        body = await _read_bounded_body(request)
        if body is None:
            return _error(413, "request body exceeds the size limit")
        try:
            payload = OptimizerRequest.model_validate_json(body)
        except ValidationError as exc:
            return _error(422, _validation_detail(exc))
        try:
            result = optimize(
                _scenario(payload.scenario),
                tuple(_route(route) for route in payload.routes),
            )
        except ValueError as exc:
            return _error(422, str(exc))
        response = OptimizationResultResponse.model_validate(result)
        return JSONResponse(
            content=response.model_dump(mode="json"),
            headers=_NO_STORE,
        )

    return router


def _validation_detail(exc: ValidationError) -> list[dict[str, list[str] | str]]:
    detail: list[dict[str, list[str] | str]] = []
    for error in exc.errors():
        detail.append(
            {
                "loc": [str(part) for part in error["loc"]],
                "msg": str(error["msg"]),
                "type": str(error["type"]),
            }
        )
    return detail


def _rewrite_defs_to_components(node: Any) -> None:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            node["$ref"] = "#/components/schemas/" + ref[len("#/$defs/") :]
        for value in node.values():
            _rewrite_defs_to_components(value)
    elif isinstance(node, list):
        for value in node:
            _rewrite_defs_to_components(value)


def install_optimizer_openapi_schema(schema: dict[str, Any]) -> None:
    """Document the optimizer request body and responses in the OpenAPI schema."""
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    for model in (
        OptimizerRequest,
        OptimizationResultResponse,
        OversizeErrorResponse,
        ValidationErrorResponse,
    ):
        model_schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
        for name, definition in model_schema.pop("$defs", {}).items():
            _rewrite_defs_to_components(definition)
            components.setdefault(name, definition)
        _rewrite_defs_to_components(model_schema)
        components.setdefault(model.__name__, model_schema)
    operation = schema["paths"]["/api/v1/optimizer/routes"]["post"]
    operation["requestBody"] = {
        "required": True,
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/OptimizerRequest"}}
        },
    }
    responses = operation.setdefault("responses", {})
    responses["200"] = {
        "description": "Ranked and rejected routes",
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/OptimizationResultResponse"}
            }
        },
    }
    responses["413"] = {
        "description": "Request body exceeds the 128 KiB size limit",
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/OversizeErrorResponse"}}
        },
    }
    responses["422"] = {
        "description": "Structural or semantic validation failed",
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/ValidationErrorResponse"}}
        },
    }


def _scenario(payload: ScenarioPayload) -> PurchaseScenario:
    return PurchaseScenario(
        amount=payload.amount,
        currency=payload.currency,
        as_of=payload.as_of,
        user_fees=tuple(_fee(fee) for fee in payload.user_fees),
        allowed_link_classes=frozenset(payload.allowed_link_classes),
        admitted_action_origins=frozenset(payload.admitted_action_origins),
    )


def _route(payload: RoutePayload) -> RouteCandidate:
    return RouteCandidate(
        id=payload.id,
        label=payload.label,
        components=tuple(_component(component) for component in payload.components),
        instructions=tuple(payload.instructions),
        link_class=payload.link_class,
        official_reference=payload.official_reference,
        action_link_review_state=payload.action_link_review_state,
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
        benefit_state=payload.benefit_state,
        compatible_with=frozenset(payload.compatible_with),
        conditions=tuple(payload.conditions),
        assumptions=tuple(payload.assumptions),
        expires_on=payload.expires_on,
        per_transaction_cap=payload.per_transaction_cap,
        remaining_allowance=payload.remaining_allowance,
        cap_group=payload.cap_group,
        time_limited=payload.time_limited,
        valuation_name=payload.valuation_name,
        layer=payload.layer,
    )


def _fee(payload: FeePayload) -> UserFee:
    return UserFee(label=payload.label, amount=payload.amount, currency=payload.currency)
