"""Read-only public catalog API routes.

The application factory owns router registration.  This module deliberately has
no dependency on the vault, application state, or filesystem paths in responses.
"""

from __future__ import annotations

import json
import re
import secrets
import threading
import time
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .conflicts import explain_conflict
from .loader import Catalog, CatalogLoadError, load_catalog
from .model import (
    BenefitRule,
    EvidenceAssertion,
    Offering,
    ProductRelationship,
    is_current_approved_evidence,
)


class _PublicModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceSummary(_PublicModel):
    source_policy_class: str
    source_tier: int
    source_url: str
    content_sha256: str
    retrieved_at: str
    effective_from: date | None
    effective_to: date | None
    confidence: str
    state: str
    approved_review_count: int
    personalized: bool


class ConflictSummary(_PublicModel):
    """A conflicting benefit, resolved regardless of its own review status.

    The main `/benefits` listing only returns active (and, opt-in,
    historical/superseded) rules, so a conflicting `needs_review` rule would
    otherwise be invisible to a client that only loaded the active list.
    This summary is embedded directly on the benefit that names the
    conflict so the conflict is never silently dropped by that filtering.
    """

    id: str
    title: str
    state: str
    best_source_tier: int
    more_authoritative_id: str | None


class QuantitySummary(_PublicModel):
    metric: str
    value: int | float
    unit: str
    basis: str
    scope: str | None
    period: str
    cap: dict[str, Any] | None


class BenefitSummary(_PublicModel):
    id: str
    offering_id: str
    benefit_type: str
    title: str
    state: str
    effective_from: date | None
    effective_to: date | None
    end_date_known: bool
    rule_version: int
    supersedes: str | None = None
    eligibility: list[dict[str, Any]]
    allowance: dict[str, Any] | None
    quantities: list[QuantitySummary]
    provider: str | None = None
    official_reference: str | None = None
    redemption_steps: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    category: str | None = None
    conditions: list[dict[str, Any]] = Field(default_factory=list)
    earn: dict[str, Any] | None = None
    conversion: dict[str, Any] | None = None
    valuations: list[dict[str, str]] = Field(default_factory=list)
    value_class: str | None = None
    conflicts_with: list[str]
    conflicts: list[ConflictSummary]
    evidence: list[EvidenceSummary]
    not_claimed: list[str] = Field(default_factory=list)
    source_divergence: list[dict[str, Any]] = Field(default_factory=list)


class OfferingSummary(_PublicModel):
    id: str
    slug: str
    display_name: str
    issuer_id: str
    product_variant_id: str
    network_id: str
    market: str
    co_brand_id: str | None
    cohort_id: str | None
    aliases: list[str]
    effective_from: date | None
    effective_to: date | None


class RelationshipSummary(_PublicModel):
    id: str
    from_offering_id: str
    to_offering_id: str
    relationship_type: str
    effective_from: date | None
    effective_to: date | None
    review_state: str
    evidence: list[EvidenceSummary]


class ReleaseSummary(_PublicModel):
    schema_version: str
    release_id: str
    generated_at: str
    market_scope: list[str]


class PublicCatalogExport(_PublicModel):
    """A deliberately narrow, current public-catalog interchange document."""

    export_schema_version: str
    as_of: date
    release: ReleaseSummary
    offerings: list[OfferingSummary]
    benefits: list[BenefitSummary]
    relationships: list[RelationshipSummary]


class OfferingDetail(OfferingSummary):
    as_of: date
    benefits: list[BenefitSummary]
    relationships: list[RelationshipSummary]


class DiscoveryResult(_PublicModel):
    """A benefit with its public offering context for deterministic discovery."""

    benefit: BenefitSummary
    offering: OfferingSummary
    matched_terms: list[str]
    exact_match: bool
    date_usable: bool
    state: str
    owned_match: bool = False


class CatalogUnavailable(_PublicModel):
    detail: str = "Catalog unavailable"


AsOf = Annotated[date | None, Query(description="ISO date; defaults to the catalog release date")]


@dataclass(frozen=True)
class OwnedDiscoveryState:
    rule_ids: frozenset[str]
    inventory_empty: bool
    ownership_revision: str


OwnedRuleReader = Any

_DISCOVERY_SESSION_COOKIE = "mycard_discovery_session"
_CURSOR_MAX_LENGTH = 96
_CURSOR_TTL_SECONDS = 300
_CURSOR_CACHE_LIMIT = 512


@dataclass(frozen=True)
class _DiscoveryCursor:
    query_state: str
    catalog_revision: str
    ownership_revision: str
    session_id: str
    offset: int
    result_ids: tuple[str, ...]
    inventory_empty: bool
    expires_at: float


class _DiscoveryCursorStore:
    def __init__(self) -> None:
        self._items: OrderedDict[str, _DiscoveryCursor] = OrderedDict()
        self._lock = threading.Lock()

    def issue(self, **values: object) -> str:
        now = time.monotonic()
        with self._lock:
            self._discard_expired(now)
            while len(self._items) >= _CURSOR_CACHE_LIMIT:
                self._items.popitem(last=False)
            token = f"d1_{secrets.token_urlsafe(24)}"
            self._items[token] = _DiscoveryCursor(
                **values, expires_at=now + _CURSOR_TTL_SECONDS  # type: ignore[arg-type]
            )
        return token

    def consume(self, token: str, *, query_state: str, catalog_revision: str,
                ownership_revision: str, session_id: str) -> _DiscoveryCursor:
        if len(token) > _CURSOR_MAX_LENGTH or not re.fullmatch(r"d1_[A-Za-z0-9_-]{32}", token):
            raise HTTPException(status_code=400, detail="Invalid discovery cursor")
        now = time.monotonic()
        with self._lock:
            self._discard_expired(now)
            cursor = self._items.get(token)
            if cursor is None:
                raise _restart_search()
            if (
                cursor.query_state != query_state
                or cursor.catalog_revision != catalog_revision
                or cursor.ownership_revision != ownership_revision
                or cursor.session_id != session_id
            ):
                self._items.pop(token, None)
                raise _restart_search()
            self._items.pop(token, None)
            return cursor

    def _discard_expired(self, now: float) -> None:
        for token, item in list(self._items.items()):
            if item.expires_at <= now:
                self._items.pop(token, None)


def _restart_search() -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"code": "restart_required", "message": "Search results changed. Restart search."},
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


def _catalog_revision(catalog: Catalog) -> str:
    release = catalog.release
    return f"{release.schema_version}:{release.release_id}:{release.generated_at.isoformat()}"


def _discovery_query_state(**values: object) -> str:
    def text_value(key: str) -> str | None:
        value = values.get(key)
        return value if isinstance(value, str) else None

    normalized = {
        "q": _fold(text_value("q")),
        "category": _fold(text_value("category")),
        "issuer": _fold(text_value("issuer")),
        "network": _fold(text_value("network")),
        "merchant": _fold(text_value("merchant")),
        "status": _fold(text_value("status")),
        "offering_id": str(values.get("offering_id") or "").casefold(),
        "cap": _fold(text_value("cap")),
        "condition": _fold(text_value("condition")),
        "claim_channel": _fold(text_value("claim_channel")),
        "date_usable": values.get("date_usable") is True,
        "page_size": values.get("page_size"),
        "owned_only": values.get("owned_only") is True,
        "as_of": str(values.get("as_of")),
        "order": "owned_first,date_usable,exact_match,title,benefit_id",
    }
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"))


def _discovery_session_id(request: Request, response: Response, *, cursor: str | None) -> str:
    cookie = request.cookies.get(_DISCOVERY_SESSION_COOKIE)
    if isinstance(cookie, str) and re.fullmatch(r"s1_[A-Za-z0-9_-]{32}", cookie):
        return cookie
    if cursor is not None:
        raise _restart_search()
    value = f"s1_{secrets.token_urlsafe(24)}"
    response.set_cookie(_DISCOVERY_SESSION_COOKIE, value, max_age=_CURSOR_TTL_SECONDS,
                        httponly=True, samesite="strict", path="/api/v1/catalog/discovery")
    return value


def create_catalog_router(
    catalog_dir: Path, *, owned_rule_reader: OwnedRuleReader | None = None
) -> APIRouter:
    """Create deterministic catalog endpoints rooted at one configured directory.

    The loader is invoked per request so invalid or changed files never remain
    silently active.  All loader errors collapse to a generic unavailable error.
    """
    router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])
    cursor_store = _DiscoveryCursorStore()

    def catalog_or_unavailable() -> Catalog:
        try:
            return load_catalog(catalog_dir)
        except (CatalogLoadError, OSError):
            raise HTTPException(status_code=503, detail="Catalog unavailable") from None

    @router.get(
        "/offerings",
        response_model=list[OfferingSummary],
        responses={503: {"model": CatalogUnavailable}},
    )
    def list_offerings(as_of: AsOf = None) -> list[OfferingSummary]:
        catalog = catalog_or_unavailable()
        effective_date = _effective_date(catalog, as_of)
        return [
            _offering_summary(offering)
            for offering in catalog.offerings
            if _in_range(effective_date, offering.effective_from, offering.effective_to)
        ]

    @router.get(
        "/offerings/match",
        response_model=list[OfferingSummary],
        responses={503: {"model": CatalogUnavailable}},
    )
    def match_offerings(
        issuer_id: Annotated[str, Query(min_length=1)],
        product_variant_id: Annotated[str, Query(min_length=1)],
        network_id: Annotated[str, Query(min_length=1)],
        market: Annotated[str, Query(min_length=2, max_length=2)],
        co_brand_id: str | None = None,
        cohort_id: str | None = None,
        as_of: AsOf = None,
    ) -> list[OfferingSummary]:
        catalog = catalog_or_unavailable()
        effective_date = _effective_date(catalog, as_of)
        return [
            _offering_summary(offering)
            for offering in catalog.offerings
            if _in_range(effective_date, offering.effective_from, offering.effective_to)
            and offering.issuer_id == issuer_id
            and offering.product_variant_id == product_variant_id
            and offering.network_id == network_id
            and offering.market == market.upper()
            and (co_brand_id is None or offering.co_brand_id == co_brand_id)
            and (cohort_id is None or offering.cohort_id == cohort_id)
        ]

    @router.get(
        "/export",
        response_model=PublicCatalogExport,
        responses={503: {"model": CatalogUnavailable}},
    )
    def export_current_catalog() -> JSONResponse:
        """Return only current, schema-bounded public catalog data.

        The export intentionally derives from the same public summary builders
        as the read-only API rather than serializing source files or internal
        dataclasses.  It includes no local paths, raw evidence, reviewer IDs,
        vault fields, or runtime state and is always non-cacheable.
        """
        try:
            catalog = load_catalog(catalog_dir)
        except (CatalogLoadError, OSError):
            return JSONResponse(
                status_code=503,
                content={"detail": "Catalog unavailable"},
                headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
            )
        export = _public_catalog_export(catalog)
        return JSONResponse(
            content=export.model_dump(mode="json"),
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        )

    @router.get(
        "/offerings/{slug}",
        response_model=OfferingDetail,
        responses={404: {"description": "Offering not found"}, 503: {"model": CatalogUnavailable}},
    )
    def offering_detail(slug: str, as_of: AsOf = None) -> OfferingDetail:
        catalog = catalog_or_unavailable()
        effective_date = _effective_date(catalog, as_of)
        offering = catalog.offering_by_slug(slug)
        if offering is None or not _in_range(
            effective_date, offering.effective_from, offering.effective_to
        ):
            raise HTTPException(status_code=404, detail="Offering not found")
        visible_rules = catalog.consumer_visible_benefits(effective_date)
        benefit_by_id = _conflict_visible_rules(catalog, effective_date)
        return OfferingDetail(
            **_offering_summary(offering).model_dump(),
            as_of=effective_date,
            benefits=[
                _benefit_summary(rule, benefit_by_id) for rule in visible_rules
                if rule.offering_id == offering.id
            ],
            relationships=[
                _relationship_summary(rel)
                for rel in catalog.relationships
                if (rel.from_offering_id == offering.id or rel.to_offering_id == offering.id)
                and _in_range(effective_date, rel.effective_from, rel.effective_to)
            ],
        )

    @router.get(
        "/benefits",
        response_model=list[BenefitSummary],
        responses={503: {"model": CatalogUnavailable}},
    )
    def list_benefits(
        offering_slug: str | None = None,
        benefit_type: str | None = None,
        include_historical: bool = False,
        as_of: AsOf = None,
    ) -> list[BenefitSummary]:
        catalog = catalog_or_unavailable()
        effective_date = _effective_date(catalog, as_of)
        offering_id = _offering_id_for_slug(catalog, offering_slug, effective_date)
        visible_rules = catalog.consumer_visible_benefits(
            effective_date, include_historical=include_historical
        )
        benefit_by_id = _conflict_visible_rules(catalog, effective_date)
        rules = [
            rule
            for rule in visible_rules
            if (offering_id is None or rule.offering_id == offering_id)
            and (benefit_type is None or rule.benefit_type == benefit_type)
        ]
        return [_benefit_summary(rule, benefit_by_id) for rule in rules]

    @router.get(
        "/discovery",
        response_model=list[DiscoveryResult],
        responses={503: {"model": CatalogUnavailable}},
    )
    def discover_benefits(
        request: Request,
        response: Response,
        q: Annotated[str | None, Query(max_length=300)] = None,
        category: str | None = None,
        issuer: str | None = None,
        network: str | None = None,
        merchant: str | None = None,
        status: str | None = None,
        date_usable: bool | None = None,
        offering_id: str | None = None,
        cap: str | None = None,
        condition: str | None = None,
        claim_channel: str | None = None,
        page_size: Annotated[int, Query(ge=1, le=50)] = 25,
        cursor: Annotated[str | None, Query(max_length=_CURSOR_MAX_LENGTH)] = None,
        owned_only: bool = False,
        as_of: AsOf = None,
    ) -> list[DiscoveryResult]:
        """Search public facts only; no network, model, or private data is used."""
        catalog = catalog_or_unavailable()
        effective_date = _effective_date(catalog, as_of)
        query_state = _discovery_query_state(
            q=q, category=category, issuer=issuer, network=network,
            merchant=merchant, status=status, date_usable=date_usable,
            offering_id=offering_id, cap=cap, condition=condition,
            claim_channel=claim_channel, page_size=page_size,
            owned_only=owned_only, as_of=effective_date,
        )
        catalog_revision = _catalog_revision(catalog)
        session_id = _discovery_session_id(request, response, cursor=cursor)
        owned_rule_ids: set[str] = set()
        inventory_empty = False
        ownership_revision = "public-only"
        if owned_rule_reader is not None:
            try:
                state = owned_rule_reader(catalog)
                if not isinstance(state, OwnedDiscoveryState):
                    raise ValueError("owned discovery state is invalid")
                owned_rule_ids = set(state.rule_ids)
                inventory_empty = state.inventory_empty
                ownership_revision = state.ownership_revision
            except Exception as exc:
                if cursor is not None:
                    raise _restart_search() from None
                if owned_only:
                    code = getattr(exc, "code", "generic")
                    raise HTTPException(
                        status_code=503,
                        detail={"code": code if isinstance(code, str) else "generic", "message": "Private card inventory unavailable; owned-only discovery cannot run."},
                        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
                    ) from None
                ownership_revision = "private-unavailable"
        if owned_only and owned_rule_reader is None:
            raise HTTPException(
                status_code=503,
                detail={"code": "generic", "message": "Private card inventory unavailable; owned-only discovery cannot run."},
                headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
            )
        snapshot = (
            cursor_store.consume(
                cursor, query_state=query_state, catalog_revision=catalog_revision,
                ownership_revision=ownership_revision, session_id=session_id,
            ) if cursor is not None else None
        )
        query = _tokens(q or "")
        filters = {
            "category": _fold(category), "issuer": _fold(issuer),
            "network": _fold(network), "merchant": _fold(merchant),
            "status": _fold(status), "offering_id": offering_id,
            "cap": _fold(cap), "condition": _fold(condition),
            "claim_channel": _fold(claim_channel),
        }
        offering_by_id = {item.id: item for item in catalog.offerings}
        benefit_by_id = _conflict_visible_rules(catalog, effective_date)
        results: list[tuple[DiscoveryResult, bool]] = []
        for rule in catalog.benefits:
            offering = offering_by_id.get(rule.offering_id)
            if offering is None:
                continue
            usable = rule.status == "active" and _in_range(
                effective_date, rule.effective_from, rule.effective_to
            )
            evidence_status = _evidence_status(rule, effective_date)
            if filters["category"] and _fold(rule.benefit_type) != filters["category"]:
                continue
            if filters["issuer"] and filters["issuer"] not in _fold(offering.issuer_id):
                continue
            if filters["network"] and filters["network"] not in _fold(offering.network_id):
                continue
            if filters["offering_id"] and rule.offering_id != filters["offering_id"]:
                continue
            if filters["status"] and filters["status"] not in {_fold(rule.status), evidence_status}:
                continue
            if date_usable is True and not usable:
                continue
            if filters["merchant"] and filters["merchant"] not in _search_text(rule, offering):
                continue
            haystack = _search_text(rule, offering)
            if filters["cap"] and filters["cap"] not in _fold(json.dumps(rule.allowance or {}, sort_keys=True)):
                continue
            if filters["condition"] and filters["condition"] not in _fold(json.dumps(rule.eligibility, sort_keys=True)):
                continue
            if filters["claim_channel"] and filters["claim_channel"] not in haystack:
                continue
            matched = [token for token in query if token in haystack]
            if query and len(matched) != len(query):
                continue
            results.append((DiscoveryResult(
                benefit=_benefit_summary(rule, benefit_by_id),
                offering=_offering_summary(offering),
                matched_terms=matched,
                exact_match=bool(query and _fold(q or "") in haystack),
                date_usable=usable,
                state=evidence_status,
                owned_match=rule.id in owned_rule_ids,
            ), rule.id in owned_rule_ids))
        if owned_only:
            results = [item for item in results if item[1]]
        results.sort(key=lambda item: (
            not item[1] if owned_rule_reader is not None else False,
            not item[0].date_usable, not item[0].exact_match,
            item[0].benefit.title.casefold(), item[0].benefit.id,
        ))
        result_ids = tuple(item[0].benefit.id for item in results)
        offset = snapshot.offset if snapshot is not None else 0
        if snapshot is not None and result_ids != snapshot.result_ids:
            raise _restart_search()
        page_end = min(len(results), offset + page_size)
        response.headers["X-Discovery-Next-Cursor"] = (
            cursor_store.issue(
                query_state=query_state,
                catalog_revision=catalog_revision,
                ownership_revision=ownership_revision,
                session_id=session_id,
                offset=page_end,
                result_ids=result_ids,
                inventory_empty=inventory_empty,
            ) if page_end < len(results) else ""
        )
        response.headers.update({"Cache-Control": "no-store", "Pragma": "no-cache"})
        if owned_only:
            response.headers["X-Discovery-Owned-State"] = "empty" if inventory_empty else "available"
            if inventory_empty:
                response.headers["X-Discovery-Owned-Reason"] = "no_local_cards"
        facets = {
            "category": sorted({item[0].benefit.benefit_type for item in results}),
            "state": sorted({item[0].state for item in results}),
        }
        response.headers["X-Discovery-Facets"] = json.dumps(facets, separators=(",", ":"))
        return [item[0] for item in results[offset:page_end]]

    @router.get(
        "/relationships",
        response_model=list[RelationshipSummary],
        responses={503: {"model": CatalogUnavailable}},
    )
    def list_relationships(as_of: AsOf = None) -> list[RelationshipSummary]:
        catalog = catalog_or_unavailable()
        effective_date = _effective_date(catalog, as_of)
        return [
            _relationship_summary(rel)
            for rel in catalog.relationships
            if _in_range(effective_date, rel.effective_from, rel.effective_to)
        ]

    return router


def _effective_date(catalog: Catalog, requested: date | None) -> date:
    return requested or catalog.default_as_of


def _public_catalog_export(catalog: Catalog) -> PublicCatalogExport:
    """Build the strict current public view without exposing source records."""
    as_of = _effective_date(catalog, None)
    offerings = [
        _offering_summary(offering)
        for offering in catalog.offerings
        if _in_range(as_of, offering.effective_from, offering.effective_to)
    ]
    current_offering_ids = {offering.id for offering in offerings}
    eligible_benefits: list[tuple[BenefitRule, tuple[EvidenceAssertion, ...]]] = []
    for rule in catalog.benefits:
        if (
            rule.offering_id not in current_offering_ids
            or rule.status != "active"
            or not _in_range(as_of, rule.effective_from, rule.effective_to)
        ):
            continue
        evidence = _current_approved_evidence(rule.evidence, as_of)
        if evidence:
            eligible_benefits.append((rule, evidence))
    benefit_by_id = {rule.id: rule for rule, _evidence in eligible_benefits}
    benefits = [
        _benefit_summary(rule, benefit_by_id, evidence=evidence)
        for rule, evidence in eligible_benefits
    ]
    relationships = []
    for relationship in catalog.relationships:
        if (
            relationship.from_offering_id not in current_offering_ids
            or relationship.to_offering_id not in current_offering_ids
            or relationship.review_state != "approved"
            or not _in_range(as_of, relationship.effective_from, relationship.effective_to)
        ):
            continue
        evidence = _current_approved_evidence(relationship.evidence, as_of)
        if evidence:
            relationships.append(_relationship_summary(relationship, evidence=evidence))
    return PublicCatalogExport(
        export_schema_version="public-catalog-export-v1",
        as_of=as_of,
        release=ReleaseSummary(
            schema_version=catalog.release.schema_version,
            release_id=catalog.release.release_id,
            generated_at=catalog.release.generated_at.isoformat(),
            market_scope=list(catalog.release.market_scope),
        ),
        offerings=offerings,
        benefits=benefits,
        relationships=relationships,
    )


def _offering_id_for_slug(catalog: Catalog, slug: str | None, as_of: date) -> str | None:
    if slug is None:
        return None
    offering = catalog.offering_by_slug(slug)
    if offering is None or not _in_range(as_of, offering.effective_from, offering.effective_to):
        raise HTTPException(status_code=404, detail="Offering not found")
    return offering.id


def _offering_summary(offering: Offering) -> OfferingSummary:
    return OfferingSummary(
        id=offering.id,
        slug=offering.slug,
        display_name=offering.display_name,
        issuer_id=offering.issuer_id,
        product_variant_id=offering.product_variant_id,
        network_id=offering.network_id,
        market=offering.market,
        co_brand_id=offering.co_brand_id,
        cohort_id=offering.cohort_id,
        aliases=list(offering.aliases),
        effective_from=offering.effective_from,
        effective_to=offering.effective_to,
    )


def _conflict_visible_rules(catalog: Catalog, as_of: date) -> dict[str, BenefitRule]:
    offering_by_id = {offering.id: offering for offering in catalog.offerings}
    return {
        rule.id: rule
        for rule in catalog.benefits
        if _in_range(as_of, rule.effective_from, rule.effective_to)
        and (rule.inheritance is None or rule.inheritance.applies(as_of))
        and (offering := offering_by_id.get(rule.offering_id)) is not None
        and _in_range(as_of, offering.effective_from, offering.effective_to)
    }


def _conflict_summaries(rule: BenefitRule, benefit_by_id: dict[str, BenefitRule]) -> list[ConflictSummary]:
    summaries: list[ConflictSummary] = []
    for conflict_id in rule.conflicts_with:
        conflicting = benefit_by_id.get(conflict_id)
        if conflicting is None:
            continue
        explanation = explain_conflict(rule, conflicting)
        summaries.append(
            ConflictSummary(
                id=conflicting.id,
                title=conflicting.title,
                state=_consumer_state(conflicting),
                best_source_tier=explanation.conflicting_best_tier,
                more_authoritative_id=explanation.more_authoritative_benefit_id,
            )
        )
    return summaries


def _benefit_summary(
    rule: BenefitRule,
    benefit_by_id: dict[str, BenefitRule],
    *,
    evidence: tuple[EvidenceAssertion, ...] | None = None,
) -> BenefitSummary:
    state = _consumer_state(rule)
    return BenefitSummary(
        id=rule.id,
        offering_id=rule.offering_id,
        benefit_type=rule.benefit_type,
        title=rule.title,
        state=state,
        effective_from=rule.effective_from,
        effective_to=rule.effective_to,
        end_date_known=rule.end_date_known,
        rule_version=rule.rule_version,
        supersedes=rule.supersedes,
        eligibility=[dict(predicate) for predicate in rule.eligibility],
        allowance=dict(rule.allowance) if rule.allowance is not None else None,
        quantities=[
            QuantitySummary(
                metric=quantity.metric,
                value=quantity.value,
                unit=quantity.unit,
                basis=quantity.basis,
                scope=quantity.scope,
                period=quantity.period,
                cap=quantity.cap,
            )
            for quantity in rule.quantities
        ],
        provider=rule.provider,
        official_reference=rule.official_reference,
        redemption_steps=list(rule.redemption_steps),
        exclusions=list(rule.exclusions),
        category=rule.category.value if rule.category else None,
        conditions=[
            {
                "type": item.type,
                "operator": item.operator,
                **({"value": item.value} if item.operator != "exists" else {}),
            }
            for item in rule.conditions
        ],
        earn=_dataclass_dict(rule.earn),
        conversion=_dataclass_dict(rule.conversion),
        valuations=[
            {
                "name": item.name,
                "redemption_path": item.redemption_path,
                "currency": item.currency,
                "minimum": item.minimum,
                "maximum": item.maximum,
            }
            for item in rule.valuations
        ],
        value_class=rule.value_class,
        conflicts_with=[
            conflict_id for conflict_id in rule.conflicts_with if conflict_id in benefit_by_id
        ],
        conflicts=_conflict_summaries(rule, benefit_by_id),
        evidence=[
            _evidence_summary(assertion, state)
            for assertion in (rule.evidence if evidence is None else evidence)
        ],
        not_claimed=list(rule.not_claimed),
        source_divergence=[dict(item) for item in rule.source_divergence],
    )


def _dataclass_dict(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    result: dict[str, Any] = {}
    for key, item in vars(value).items():
        if isinstance(item, tuple):
            result[key] = list(item)
        elif hasattr(item, "value"):
            result[key] = item.value
        elif hasattr(item, "isoformat"):
            result[key] = item.isoformat()
        elif hasattr(item, "__dict__"):
            result[key] = _dataclass_dict(item)
        else:
            result[key] = item
    if "owner" in result and hasattr(value.owner, "__dict__"):
        result["owner"] = _dataclass_dict(value.owner)
    return result


def _evidence_summary(assertion: EvidenceAssertion, state: str) -> EvidenceSummary:
    return EvidenceSummary(
        source_policy_class=assertion.source_policy_class,
        source_tier=assertion.source_tier,
        source_url=assertion.url,
        content_sha256=assertion.content_sha256,
        retrieved_at=assertion.retrieved_at.isoformat(),
        effective_from=assertion.effective_from,
        effective_to=assertion.effective_to,
        confidence=assertion.confidence,
        state=state,
        approved_review_count=sum(review.decision == "approved" for review in assertion.reviews),
        personalized=assertion.personalized,
    )


def _in_range(value: date, start: date | None, end: date | None) -> bool:
    return (start is None or start <= value) and (end is None or value <= end)


def _fold(value: str | None) -> str:
    """Case/punctuation/currency-insensitive text used only for local search."""
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value).casefold()
    normalized = normalized.replace("₹", " inr ").replace("$", " usd ")
    return re.sub(r"[^a-z0-9]+", " ", normalized).strip()


def _tokens(value: str) -> list[str]:
    return [token for token in _fold(value).split() if token]


def _search_text(rule: BenefitRule, offering: Offering) -> str:
    values: list[str] = [
        rule.benefit_type, rule.title, rule.provider or "", offering.display_name,
        offering.slug, offering.issuer_id, offering.network_id, *offering.aliases,
        *rule.redemption_steps, *rule.exclusions,
    ]
    values.extend(json.dumps(item, sort_keys=True) for item in rule.eligibility)
    if rule.allowance is not None:
        values.append(json.dumps(rule.allowance, sort_keys=True))
    return _fold(" ".join(values))


def _consumer_state(rule: BenefitRule) -> str:
    """Project internal governance into the three safe consumer states."""
    if rule.state in {"verified", "check_before_use", "sources_differ"}:
        return rule.state
    if rule.status == "active":
        return "verified"
    return "check_before_use"


def _evidence_status(rule: BenefitRule, as_of: date) -> str:
    del as_of
    return _consumer_state(rule)


def _current_approved_evidence(
    assertions: tuple[EvidenceAssertion, ...], as_of: date
) -> tuple[EvidenceAssertion, ...]:
    return tuple(
        assertion
        for assertion in assertions
        if is_current_approved_evidence(assertion, as_of)
    )


def _relationship_summary(
    rel: ProductRelationship, *, evidence: tuple[EvidenceAssertion, ...] | None = None
) -> RelationshipSummary:
    return RelationshipSummary(
        id=rel.id,
        from_offering_id=rel.from_offering_id,
        to_offering_id=rel.to_offering_id,
        relationship_type=rel.relationship_type,
        effective_from=rel.effective_from,
        effective_to=rel.effective_to,
        review_state=rel.review_state,
        evidence=[
            _evidence_summary(
                assertion,
                "verified" if rel.review_state == "approved" else "check_before_use",
            )
            for assertion in (rel.evidence if evidence is None else evidence)
        ],
    )
