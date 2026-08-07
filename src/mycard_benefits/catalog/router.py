"""Read-only public catalog API routes.

The application factory owns router registration.  This module deliberately has
no dependency on the vault, application state, or filesystem paths in responses.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from .loader import Catalog, CatalogLoadError, load_catalog
from .model import BenefitRule, EvidenceAssertion, Offering, ProductRelationship


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
    review_state: str
    approved_review_count: int


class BenefitSummary(_PublicModel):
    id: str
    offering_id: str
    benefit_type: str
    title: str
    status: str
    review_tier: str
    effective_from: date | None
    effective_to: date | None
    end_date_known: bool
    rule_version: int
    supersedes: str | None = None
    eligibility: list[dict[str, Any]]
    allowance: dict[str, Any] | None
    conflicts_with: list[str]
    evidence: list[EvidenceSummary]


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


class OfferingDetail(OfferingSummary):
    as_of: date
    benefits: list[BenefitSummary]
    relationships: list[RelationshipSummary]


class CatalogUnavailable(_PublicModel):
    detail: str = "Catalog unavailable"


AsOf = Annotated[date | None, Query(description="ISO date; defaults to the catalog release date")]


def create_catalog_router(catalog_dir: Path) -> APIRouter:
    """Create deterministic catalog endpoints rooted at one configured directory.

    The loader is invoked per request so invalid or changed files never remain
    silently active.  All loader errors collapse to a generic unavailable error.
    """
    router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])

    def catalog_or_unavailable() -> Catalog:
        try:
            return load_catalog(catalog_dir)
        except (CatalogLoadError, OSError):
            raise HTTPException(status_code=503, detail="Catalog unavailable") from None

    @router.get("/offerings", response_model=list[OfferingSummary], responses={503: {"model": CatalogUnavailable}})
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
        "/offerings/{slug}",
        response_model=OfferingDetail,
        responses={404: {"description": "Offering not found"}, 503: {"model": CatalogUnavailable}},
    )
    def offering_detail(slug: str, as_of: AsOf = None) -> OfferingDetail:
        catalog = catalog_or_unavailable()
        effective_date = _effective_date(catalog, as_of)
        offering = catalog.offering_by_slug(slug)
        if offering is None or not _in_range(effective_date, offering.effective_from, offering.effective_to):
            raise HTTPException(status_code=404, detail="Offering not found")
        return OfferingDetail(
            **_offering_summary(offering).model_dump(),
            as_of=effective_date,
            benefits=[_benefit_summary(rule) for rule in catalog.benefits_for(offering.id, effective_date)],
            relationships=[
                _relationship_summary(rel)
                for rel in catalog.relationships
                if rel.from_offering_id == offering.id or rel.to_offering_id == offering.id
            ],
        )

    @router.get("/benefits", response_model=list[BenefitSummary], responses={503: {"model": CatalogUnavailable}})
    def list_benefits(
        offering_slug: str | None = None,
        benefit_type: str | None = None,
        include_historical: bool = False,
        as_of: AsOf = None,
    ) -> list[BenefitSummary]:
        catalog = catalog_or_unavailable()
        effective_date = _effective_date(catalog, as_of)
        offering_id = _offering_id_for_slug(catalog, offering_slug, effective_date)
        valid_statuses = {"active", "historical", "superseded"} if include_historical else {"active"}
        rules = [
            rule
            for rule in catalog.benefits
            if rule.status in valid_statuses
            and (include_historical or _in_range(effective_date, rule.effective_from, rule.effective_to))
            and (offering_id is None or rule.offering_id == offering_id)
            and (benefit_type is None or rule.benefit_type == benefit_type)
        ]
        return [_benefit_summary(rule) for rule in rules]

    @router.get("/relationships", response_model=list[RelationshipSummary], responses={503: {"model": CatalogUnavailable}})
    def list_relationships() -> list[RelationshipSummary]:
        catalog = catalog_or_unavailable()
        return [_relationship_summary(rel) for rel in catalog.relationships]

    return router


def _effective_date(catalog: Catalog, requested: date | None) -> date:
    return requested or catalog.release.generated_at.date()


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


def _benefit_summary(rule: BenefitRule) -> BenefitSummary:
    return BenefitSummary(
        id=rule.id,
        offering_id=rule.offering_id,
        benefit_type=rule.benefit_type,
        title=rule.title,
        status=rule.status,
        review_tier=rule.review_tier,
        effective_from=rule.effective_from,
        effective_to=rule.effective_to,
        end_date_known=rule.end_date_known,
        rule_version=rule.rule_version,
        supersedes=rule.supersedes,
        eligibility=[dict(predicate) for predicate in rule.eligibility],
        allowance=dict(rule.allowance) if rule.allowance is not None else None,
        conflicts_with=list(rule.conflicts_with),
        evidence=[_evidence_summary(assertion) for assertion in rule.evidence],
    )


def _evidence_summary(assertion: EvidenceAssertion) -> EvidenceSummary:
    return EvidenceSummary(
        source_policy_class=assertion.source_policy_class,
        source_tier=assertion.source_tier,
        source_url=assertion.url,
        content_sha256=assertion.content_sha256,
        retrieved_at=assertion.retrieved_at.isoformat(),
        effective_from=assertion.effective_from,
        effective_to=assertion.effective_to,
        confidence=assertion.confidence,
        review_state=assertion.review_state,
        approved_review_count=sum(review.decision == "approved" for review in assertion.reviews),
    )


def _in_range(value: date, start: date | None, end: date | None) -> bool:
    return (start is None or start <= value) and (end is None or value <= end)


def _relationship_summary(rel: ProductRelationship) -> RelationshipSummary:
    return RelationshipSummary(
        id=rel.id,
        from_offering_id=rel.from_offering_id,
        to_offering_id=rel.to_offering_id,
        relationship_type=rel.relationship_type,
        effective_from=rel.effective_from,
        effective_to=rel.effective_to,
        review_state=rel.review_state,
    )
