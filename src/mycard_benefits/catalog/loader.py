"""Deterministic loader and fail-closed validator for public catalog JSON."""

from __future__ import annotations

import json
import math
import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

from .model import (
    BenefitCategory,
    BenefitQuantity,
    BenefitRule,
    ConditionPredicate,
    ConversionRule,
    EarnRule,
    EvidenceAssertion,
    HumanReview,
    InheritanceRule,
    Offering,
    ProductRelationship,
    ReleaseMetadata,
    RuleOwner,
    ValuationRange,
)
from .quantities import (
    QUANTITY_BASES,
    QUANTITY_METRICS,
    QUANTITY_PERIODS,
    QUANTITY_SCOPES,
    QUANTITY_UNITS,
)


class CatalogLoadError(ValueError):
    """Raised when a catalog is malformed, ambiguous, or unsafe to activate."""


@dataclass(frozen=True)
class ConflictReference:
    source: BenefitRule
    target: BenefitRule | None
    target_id: str
    resolution: str


_SOURCE_CLASSES = {
    "administering_terms",
    "issuer_document",
    "network_rule",
    "merchant_terms",
    "regulatory_context",
    "discovery_only",
}
_BENEFIT_TYPES = {item.value for item in BenefitCategory}
_RULE_STATUS = {"active", "historical", "needs_review", "superseded"}
_RELATIONSHIP_TYPES = {"renamed", "legacy", "cloned", "reskinned"}
_RELATIONSHIP_REVIEW_STATE = {"approved", "needs_review"}
_CONFIDENCE = {"high", "medium", "low"}
_REVIEW_STATE = {"approved", "needs_review", "reviewed", "rejected", "superseded"}
_REVIEW_TIERS = {"standard", "enhanced", "high_impact", "ambiguous"}
_REVIEW_DECISIONS = {"approved", "rejected"}
_RESCUED_STATES = {"verified", "check_before_use", "sources_differ"}
_PREDICATE_OPERATORS = {"equals", "in", "not_in", "gte", "lte", "between", "exists"}
_CONDITION_TYPES = {
    "welcome",
    "milestone",
    "annual_fee_waiver",
    "renewal",
    "spend_triggered",
    "geography",
    "currency",
    "channel",
    "mcc",
    "time_window",
}
_OWNER_KINDS = {"issuer", "network", "co_brand", "merchant", "membership", "event"}
_VALUE_CLASSES = {"guaranteed", "conditional", "estimated"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_QUANTITIES_MISSING = object()


@dataclass(frozen=True)
class Catalog:
    release: ReleaseMetadata
    offerings: tuple[Offering, ...]
    benefits: tuple[BenefitRule, ...]
    relationships: tuple[ProductRelationship, ...] = ()

    def offering_by_slug(self, slug: str) -> Offering | None:
        return next((item for item in self.offerings if item.slug == slug), None)

    @property
    def default_as_of(self) -> date:
        """Return the release's canonical UTC calendar date for date queries."""
        return self.release.generated_at.astimezone(UTC).date()

    @staticmethod
    def _benefit_applies(rule: BenefitRule, as_of: date) -> bool:
        return _in_date_range(as_of, rule.effective_from, rule.effective_to) and (
            rule.inheritance is None or rule.inheritance.applies(as_of)
        )

    def benefits_for(self, offering_id: str, as_of: date | None = None) -> tuple[BenefitRule, ...]:
        as_of = as_of or self.default_as_of
        return tuple(
            rule
            for rule in self.benefits
            if rule.offering_id == offering_id
            and rule.status == "active"
            and self._benefit_applies(rule, as_of)
        )

    def consumer_visible_benefits(
        self, as_of: date | None = None, *, include_historical: bool = False
    ) -> tuple[BenefitRule, ...]:
        """Return public records meant for consumer display.

        Governance status remains authoritative for activation and eligibility
        callers. Rescued records deliberately use a separate three-value
        ``state`` so a consumer can see a bounded source-backed record with a
        warning without turning it into an approved active rule.
        """
        as_of = as_of or self.default_as_of
        consumer_states = {"verified", "check_before_use", "sources_differ"}
        return tuple(
            rule
            for rule in self.benefits
            if (
                rule.state in consumer_states and self._benefit_applies(rule, as_of)
            )
            or (
                rule.state is None
                and (
                    (rule.status == "active" and self._benefit_applies(rule, as_of))
                    or (
                        include_historical
                        and rule.status in {"historical", "superseded"}
                        and (rule.inheritance is None or rule.inheritance.applies(as_of))
                    )
                )
            )
        )

    def consumer_visible_benefits_for(
        self, offering_id: str, as_of: date | None = None
    ) -> tuple[BenefitRule, ...]:
        """Return consumer-display records for one public offering."""
        return tuple(
            rule
            for rule in self.consumer_visible_benefits(as_of)
            if rule.offering_id == offering_id
        )

    def visible_benefits(
        self, as_of: date | None = None, *, include_historical: bool = False
    ) -> tuple[BenefitRule, ...]:
        """Return benefits publishable on a date, including inheritance bounds."""
        as_of = as_of or self.default_as_of
        return tuple(
            rule
            for rule in self.benefits
            if (
                (rule.status == "active" and self._benefit_applies(rule, as_of))
                or (
                    include_historical
                    and rule.status in {"historical", "superseded"}
                    and (rule.inheritance is None or rule.inheritance.applies(as_of))
                )
            )
        )

    def historical_benefits_for(
        self, offering_id: str, as_of: date | None = None
    ) -> tuple[BenefitRule, ...]:
        """Return expired, superseded, and historical rules for an offering."""
        as_of = as_of or self.default_as_of
        return tuple(
            rule
            for rule in self.benefits
            if rule.offering_id == offering_id
            and rule.status in {"historical", "superseded"}
            and (rule.inheritance is None or rule.inheritance.applies(as_of))
        )

    def conflicts_for(
        self, offering_id: str, as_of: date | None = None
    ) -> tuple[tuple[BenefitRule, BenefitRule], ...]:
        """Return explicit, unresolved public-rule conflicts for one offering.

        Conflict declarations are reviewed catalog data, not an eligibility
        evaluator.  A pair remains visible until a later catalog release
        removes or resolves it; this method never chooses a winning rule.
        """
        references = self.conflict_references_for(offering_id, as_of)
        pairs: list[tuple[BenefitRule, BenefitRule]] = []
        seen: set[tuple[str, str]] = set()
        for reference in references:
            if reference.target is None or reference.resolution != "resolved":
                continue
            key = (min(reference.source.id, reference.target.id), max(reference.source.id, reference.target.id))
            if key not in seen:
                seen.add(key)
                left, right = sorted((reference.source, reference.target), key=lambda item: item.id)
                pairs.append((left, right))
        return tuple(sorted(pairs, key=lambda pair: (pair[0].id, pair[1].id)))

    def conflict_references_for(
        self, offering_id: str, as_of: date | None = None
    ) -> tuple[ConflictReference, ...]:
        """Resolve every declaration without dropping an unsafe target.

        The returned references are deliberately broader than ``conflicts_for``:
        callers that render review state can retain missing, inactive, or
        scope-incompatible declarations rather than treating them as resolved.
        """
        effective_date = as_of or self.release.generated_at.date()
        local_offering = next((item for item in self.offerings if item.id == offering_id), None)
        if local_offering is None or not _in_date_range(
            effective_date, local_offering.effective_from, local_offering.effective_to
        ):
            return ()
        all_rules = {rule.id: rule for rule in self.benefits}
        effective_rules = {
            rule.id: rule
            for rule in self.benefits
            if rule.status in {"active", "needs_review"}
            and _in_date_range(effective_date, rule.effective_from, rule.effective_to)
        }
        sources = sorted(
            (rule for rule in effective_rules.values() if rule.offering_id == offering_id),
            key=lambda rule: rule.id,
        )
        offerings = {item.id: item for item in self.offerings}
        references: list[ConflictReference] = []
        seen: set[tuple[str, str]] = set()
        for source in sources:
            for target_id in source.conflicts_with:
                key = (source.id, target_id)
                if key in seen:
                    continue
                seen.add(key)
                target = all_rules.get(target_id)
                if target is None:
                    references.append(ConflictReference(source, None, target_id, "missing"))
                    continue
                target_offering = offerings.get(target.offering_id)
                if target_offering is None:
                    references.append(ConflictReference(source, target, target_id, "missing_offering"))
                    continue
                if not _in_date_range(
                    effective_date, target_offering.effective_from, target_offering.effective_to
                ):
                    references.append(ConflictReference(source, target, target_id, "offering_out_of_scope"))
                    continue
                if target.id not in effective_rules or target.status != "active":
                    resolution = "needs_review" if target.status == "needs_review" else "inactive"
                    references.append(ConflictReference(source, target, target_id, resolution))
                    continue
                if not _conflict_scope_compatible(self.release, local_offering, target_offering):
                    references.append(ConflictReference(source, target, target_id, "incompatible"))
                    continue
                source_resolution = "resolved" if source.status == "active" else "needs_review"
                references.append(ConflictReference(source, target, target_id, source_resolution))
        # Reciprocal declarations describe one conflict, while one-way
        # declarations remain valid and explicit.  Keep deterministic order.
        unique: dict[tuple[str, str], ConflictReference] = {}
        for reference in references:
            pair = (min(reference.source.id, reference.target_id), max(reference.source.id, reference.target_id))
            if reference.resolution == "resolved":
                unique[pair] = reference
            else:
                unique[(reference.source.id, reference.target_id)] = reference
        return tuple(sorted(unique.values(), key=lambda item: (item.source.id, item.target_id)))


def load_catalog(root: str | Path) -> Catalog:
    """Load only JSON catalog assets and reject invalid/review-only active claims."""
    root = Path(root)
    release_raw = _read_json(root / "schema" / "release.json")
    release = _parse_release(release_raw, "schema/release.json")
    offerings = tuple(_parse_offering(raw, path) for path, raw in _read_many(root / "offerings"))
    benefits = tuple(
        _parse_benefit(raw, path) for path, raw in _read_many(root / "benefits", allow_empty=True)
    )
    relationships = tuple(
        _parse_relationship(raw, path)
        for path, raw in _read_many(root / "relationships", allow_empty=True)
    )
    _validate_cross_records(release, offerings, benefits, relationships)
    return Catalog(
        release=release, offerings=offerings, benefits=benefits, relationships=relationships
    )


def _read_many(directory: Path, allow_empty: bool = False) -> Iterable[tuple[str, dict[str, Any]]]:
    if not directory.is_dir():
        if allow_empty:
            return
        raise CatalogLoadError(f"missing catalog directory: {directory}")
    files = sorted(directory.glob("*.json"))
    if not files and not allow_empty:
        raise CatalogLoadError(f"catalog directory has no JSON records: {directory}")
    for path in files:
        yield str(path), _read_json(path)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogLoadError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CatalogLoadError(f"{path}: top-level value must be an object")
    return payload


def _parse_release(raw: dict[str, Any], path: str) -> ReleaseMetadata:
    _require_exact_keys(
        raw,
        {"schema_version", "release_id", "generated_at", "market_scope"},
        path=path,
    )
    return ReleaseMetadata(
        schema_version=_nonempty(raw["schema_version"], path, "schema_version"),
        release_id=_uuid(raw["release_id"], path, "release_id"),
        generated_at=_datetime(raw["generated_at"], path, "generated_at"),
        market_scope=tuple(_string_list(raw["market_scope"], path, "market_scope")),
    )


def _parse_offering(raw: dict[str, Any], path: str) -> Offering:
    required = {
        "id",
        "slug",
        "display_name",
        "issuer_id",
        "product_variant_id",
        "network_id",
        "market",
        "aliases",
    }
    optional = {"co_brand_id", "cohort_id", "effective_from", "effective_to"}
    _require_exact_keys(raw, required, optional, path)
    slug = _nonempty(raw["slug"], path, "slug")
    if not _SLUG.fullmatch(slug):
        raise CatalogLoadError(f"{path}: slug must be lowercase kebab-case")
    effective_from, effective_to = _date_range(raw, path)
    return Offering(
        id=_uuid(raw["id"], path, "id"),
        slug=slug,
        display_name=_nonempty(raw["display_name"], path, "display_name"),
        issuer_id=_nonempty(raw["issuer_id"], path, "issuer_id"),
        product_variant_id=_nonempty(raw["product_variant_id"], path, "product_variant_id"),
        network_id=_nonempty(raw["network_id"], path, "network_id"),
        market=_market(raw["market"], path),
        co_brand_id=_optional_string(raw.get("co_brand_id"), path, "co_brand_id"),
        cohort_id=_optional_string(raw.get("cohort_id"), path, "cohort_id"),
        aliases=tuple(_string_list(raw["aliases"], path, "aliases")),
        effective_from=effective_from,
        effective_to=effective_to,
    )


def _parse_benefit(raw: dict[str, Any], path: str) -> BenefitRule:
    """Parse either the legacy reviewed rule or the rescued public shape.

    Stage 1 deliberately kept the rescue files in their source-native shape.
    The parser below lets the retained catalog/read surfaces consume them
    without rewriting records or borrowing metadata from a private store.
    """
    if "state" in raw or "provenance" in raw:
        return _parse_rescued_benefit(raw, path)
    return _parse_legacy_benefit(raw, path)


_RESCUED_REQUIRED_FIELDS = {
    "id",
    "offering_id",
    "title",
    "benefit_type",
    "category",
    "allowance",
    "eligibility",
    "conditions",
    "exclusions",
    "redemption_steps",
    "provider",
    "effective_from",
    "effective_to",
    "end_date_known",
    "source_url",
    "source_policy_class",
    "content_sha256",
    "state",
}
_RESCUED_OPTIONAL_FIELDS = {
    "retrieved_at",
    "not_claimed",
    "provenance",
    "source_divergence",
    # These fields are retained by the one legacy-shaped verified record.
    "status",
    "review_tier",
    "rule_version",
    "owners",
    "evidence",
    "conflicts_with",
    "value_class",
    "quantities",
}
_RESCUED_METADATA_FIELDS = {
    "end_date_known",
    "source_url",
    "source_policy_class",
    "content_sha256",
    "retrieved_at",
    "state",
    "provenance",
    "source_divergence",
    "not_claimed",
}


def _parse_rescued_benefit(raw: dict[str, Any], path: str) -> BenefitRule:
    state = _nonempty(raw.get("state"), path, "state")
    if state not in _RESCUED_STATES:
        raise CatalogLoadError(f"{path}: unsupported rescued state {state!r}")

    # The verified Tata milestone record still carries the legacy reviewed
    # fields. Parse those fields through the existing gate and only attach the
    # rescue metadata; this avoids fabricating a review tier or evidence.
    if {"status", "review_tier", "evidence"}.issubset(raw):
        legacy_raw = {
            key: value for key, value in raw.items() if key not in _RESCUED_METADATA_FIELDS
        }
        rescue_benefit_type = _nonempty(raw["benefit_type"], path, "benefit_type")
        if rescue_benefit_type != "movie":
            legacy_raw = {
                key: value
                for key, value in legacy_raw.items()
                if key not in {"provider", "redemption_steps", "exclusions"}
            }
        rule = _parse_legacy_benefit(legacy_raw, path, rescue_mode=True)
        if rescue_benefit_type != "movie":
            provider = raw.get("provider")
            if provider is not None:
                provider = _bounded_text(provider, path, "provider", max_length=160)
            rule = replace(
                rule,
                provider=provider,
                redemption_steps=tuple(
                    _bounded_string_list(
                        raw.get("redemption_steps", []),
                        path,
                        "redemption_steps",
                        max_items=12,
                        max_length=240,
                        allow_empty=True,
                    )
                ),
                exclusions=tuple(
                    _bounded_string_list(
                        raw.get("exclusions", []),
                        path,
                        "exclusions",
                        max_items=32,
                        max_length=240,
                        allow_empty=True,
                    )
                ),
            )
        if state != "verified" and rule.status == "active":
            raise CatalogLoadError(
                f"{path}: rescued state {state!r} cannot carry an active legacy rule"
            )
        if "provenance" in raw:
            _parse_rescued_provenance(raw, path, state)
        return replace(
            rule,
            state=state,
            not_claimed=_parse_rescued_not_claimed(raw, path),
            source_divergence=_parse_source_divergence(raw, path, ()),
        )

    _require_exact_keys(raw, _RESCUED_REQUIRED_FIELDS, _RESCUED_OPTIONAL_FIELDS, path)
    return _parse_rescued_only_benefit(raw, path, state)


def _parse_rescued_only_benefit(
    raw: dict[str, Any], path: str, state: str
) -> BenefitRule:
    benefit_type = _nonempty(raw["benefit_type"], path, "benefit_type")
    if benefit_type not in _BENEFIT_TYPES:
        raise CatalogLoadError(f"{path}: unsupported benefit_type {benefit_type!r}")
    category = _enum(raw["category"], BenefitCategory, path, "category")
    effective_from, effective_to = _date_range(raw, path)
    if raw["end_date_known"] is not (effective_to is not None):
        raise CatalogLoadError(f"{path}: end_date_known disagrees with effective_to")

    allowance = raw["allowance"]
    if not isinstance(allowance, dict):
        raise CatalogLoadError(f"{path}: allowance must be an object")
    _validate_rescued_value(allowance, path, "allowance")
    eligibility_items = _object_list(raw["eligibility"], path, "eligibility")
    if len(eligibility_items) > 32:
        raise CatalogLoadError(f"{path}: eligibility has too many items")
    eligibility = tuple(_predicate(item, path) for item in eligibility_items)
    condition_items = _object_list(raw["conditions"], path, "conditions")
    if len(condition_items) > 32:
        raise CatalogLoadError(f"{path}: conditions has too many items")
    conditions = tuple(_parse_condition(item, path) for item in condition_items)
    quantities = _parse_quantities(
        raw.get("quantities", _QUANTITIES_MISSING),
        path,
    )

    exclusions = tuple(
        _bounded_string_list(
            raw["exclusions"], path, "exclusions", max_items=32, max_length=240, allow_empty=True
        )
    )
    redemption_steps = tuple(
        _bounded_string_list(
            raw["redemption_steps"],
            path,
            "redemption_steps",
            max_items=12,
            max_length=240,
            allow_empty=True,
        )
    )
    provider = raw["provider"]
    if provider is not None:
        provider = _bounded_text(provider, path, "provider", max_length=160)

    source_url = _anonymous_https_url(raw["source_url"], path, "source_url")
    source_policy_class = _nonempty(raw["source_policy_class"], path, "source_policy_class")
    if source_policy_class not in _SOURCE_CLASSES:
        raise CatalogLoadError(f"{path}: unsupported source_policy_class {source_policy_class!r}")
    content_sha256 = _nonempty(raw["content_sha256"], path, "content_sha256")
    if not _SHA256.fullmatch(content_sha256):
        raise CatalogLoadError(f"{path}: content_sha256 must be a lowercase SHA-256 digest")
    if "retrieved_at" in raw:
        _datetime(raw["retrieved_at"], path, "retrieved_at")
    evidence = _parse_rescued_provenance(raw, path, state)
    primary = next((item for item in evidence if item.url == source_url), None)
    if primary is None:
        raise CatalogLoadError(f"{path}: source_url is not present in provenance")
    if primary.source_policy_class != source_policy_class:
        raise CatalogLoadError(f"{path}: source_policy_class disagrees with provenance")
    if primary.content_sha256 != content_sha256:
        raise CatalogLoadError(f"{path}: content_sha256 disagrees with provenance")

    review_tier = raw.get("review_tier")
    if review_tier is not None:
        review_tier = _nonempty(review_tier, path, "review_tier")
        if review_tier not in _REVIEW_TIERS:
            raise CatalogLoadError(f"{path}: unsupported review_tier {review_tier!r}")
    status = "active" if state == "verified" else "needs_review"
    if raw.get("status") is not None and raw["status"] != status:
        raise CatalogLoadError(f"{path}: status disagrees with rescued state")
    rule_version = raw.get("rule_version", 1)
    if not isinstance(rule_version, int) or rule_version < 1:
        raise CatalogLoadError(f"{path}: rule_version must be a positive integer")
    owners = _parse_owners(raw.get("owners", []), path)
    value_class = raw.get("value_class")
    if value_class is not None and value_class not in _VALUE_CLASSES:
        raise CatalogLoadError(f"{path}: unsupported value_class {value_class!r}")
    conflicts_with = tuple(_string_list(raw.get("conflicts_with", []), path, "conflicts_with"))
    source_divergence = _parse_source_divergence(raw, path, evidence)
    rule = BenefitRule(
        id=_uuid(raw["id"], path, "id"),
        offering_id=_uuid(raw["offering_id"], path, "offering_id"),
        benefit_type=benefit_type,
        title=_nonempty(raw["title"], path, "title"),
        status=status,
        review_tier=review_tier,
        effective_from=effective_from,
        effective_to=effective_to,
        eligibility=eligibility,
        allowance=allowance,
        evidence=evidence,
        conflicts_with=conflicts_with,
        rule_version=rule_version,
        provider=provider,
        redemption_steps=redemption_steps,
        exclusions=exclusions,
        category=category,
        owners=owners,
        conditions=conditions,
        value_class=value_class,
        state=state,
        not_claimed=_parse_rescued_not_claimed(raw, path),
        source_divergence=source_divergence,
        quantities=quantities,
    )
    if state == "verified":
        _validate_active_review_gate(rule, path)
    return rule


def _parse_rescued_not_claimed(raw: dict[str, Any], path: str) -> tuple[str, ...]:
    if "not_claimed" not in raw:
        return ()
    return tuple(
        _bounded_string_list(
            raw["not_claimed"],
            path,
            "not_claimed",
            max_items=32,
            max_length=240,
            allow_empty=True,
        )
    )


def _parse_rescued_provenance(
    raw: dict[str, Any], path: str, state: str
) -> tuple[EvidenceAssertion, ...]:
    provenance = raw.get("provenance")
    if not isinstance(provenance, list) or not provenance:
        raise CatalogLoadError(f"{path}: rescued provenance must not be empty")
    assertions: list[EvidenceAssertion] = []
    for index, item in enumerate(provenance):
        if not isinstance(item, dict):
            raise CatalogLoadError(f"{path}: provenance[{index}] must be an object")
        item_path = f"{path} provenance[{index}]"
        review_state = item.get("review_state")
        reviews = item.get("reviews")
        if state == "verified" and (review_state is None or reviews is None):
            raise CatalogLoadError(
                f"{item_path}: verified provenance requires review_state and reviews"
            )
        normalized = {
            "id": item.get("id"),
            "source_policy_class": item.get("source_policy_class"),
            "url": item.get("source_url"),
            "content_sha256": item.get("content_sha256"),
            "retrieved_at": item.get("retrieved_at"),
            "confidence": item.get("confidence"),
            "review_state": review_state or "needs_review",
            "reviews": reviews if reviews is not None else [],
            "effective_from": item.get("effective_from"),
            "effective_to": item.get("effective_to"),
            "personalized": item.get("personalized", False),
            "source_observation_id": item.get("source_observation_id"),
            "hash_kind": item.get("hash_kind"),
        }
        assertions.append(_assertion(normalized, item_path))
    _unique((item.id for item in assertions), f"{path} provenance IDs")
    return tuple(assertions)


def _parse_source_divergence(
    raw: dict[str, Any], path: str, evidence: tuple[EvidenceAssertion, ...]
) -> tuple[dict[str, Any], ...]:
    if "source_divergence" not in raw:
        return ()
    items = _object_list(raw["source_divergence"], path, "source_divergence")
    if len(items) < 2:
        raise CatalogLoadError(f"{path}: source_divergence must contain at least two claims")
    urls: set[str] = set()
    parsed: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        item_path = f"{path} source_divergence[{index}]"
        _require_exact_keys(
            item,
            {"source_url", "benefit_type", "category", "allowance", "effective_from"},
            {"source_policy_class", "content_sha256", "retrieved_at", "effective_to"},
            item_path,
        )
        url = _anonymous_https_url(item["source_url"], item_path, "source_url")
        if url in urls:
            raise CatalogLoadError(f"{path}: source_divergence URLs must be distinct")
        urls.add(url)
        claim_type = _nonempty(item["benefit_type"], item_path, "benefit_type")
        if claim_type not in _BENEFIT_TYPES:
            raise CatalogLoadError(f"{item_path}: unsupported benefit_type {claim_type!r}")
        _enum(item["category"], BenefitCategory, item_path, "category")
        if not isinstance(item["allowance"], dict):
            raise CatalogLoadError(f"{item_path}: allowance must be an object")
        _validate_rescued_value(item["allowance"], item_path, "allowance")
        _date_range(item, item_path)
        if "source_policy_class" in item:
            source_class = _nonempty(item["source_policy_class"], item_path, "source_policy_class")
            if source_class not in _SOURCE_CLASSES:
                raise CatalogLoadError(f"{item_path}: unsupported source_policy_class {source_class!r}")
        digest = item.get("content_sha256")
        if digest is not None and (not isinstance(digest, str) or not _SHA256.fullmatch(digest)):
            raise CatalogLoadError(f"{item_path}: invalid content_sha256")
        if "retrieved_at" in item:
            _datetime(item["retrieved_at"], item_path, "retrieved_at")
        parsed.append(dict(item))
    evidence_urls = {item.url for item in evidence}
    if evidence and urls != evidence_urls:
        raise CatalogLoadError(f"{path}: source_divergence URLs must equal provenance URLs")
    return tuple(parsed)


def _parse_legacy_benefit(
    raw: dict[str, Any], path: str, *, rescue_mode: bool = False
) -> BenefitRule:
    required = {
        "id",
        "offering_id",
        "benefit_type",
        "title",
        "status",
        "review_tier",
        "eligibility",
        "evidence",
        "conflicts_with",
    }
    optional = {
        "effective_from",
        "effective_to",
        "allowance",
        "rule_version",
        "supersedes",
        "provider",
        "official_reference",
        "redemption_steps",
        "exclusions",
        "category",
        "owners",
        "conditions",
        "earn",
        "conversion",
        "valuations",
        "value_class",
        "inheritance",
        "benefit_shape",
        "quantities",
    }
    _require_exact_keys(raw, required, optional, path)
    benefit_type = _nonempty(raw["benefit_type"], path, "benefit_type")
    if benefit_type not in _BENEFIT_TYPES:
        raise CatalogLoadError(f"{path}: unsupported benefit_type {benefit_type!r}")
    benefit_shape = raw.get("benefit_shape", "ordinary")
    if benefit_shape not in {
        "ordinary",
        "event_triggered",
        "document_triggered",
        "boarding_pass_or_destination",
        "external_qualification",
        "affiliate_or_portal",
        "unusual_indirect",
        "other",
    }:
        raise CatalogLoadError(f"{path}: unsupported benefit_shape {benefit_shape!r}")
    status = _nonempty(raw["status"], path, "status")
    if status not in _RULE_STATUS:
        raise CatalogLoadError(f"{path}: unsupported status {status!r}")
    review_tier = _nonempty(raw["review_tier"], path, "review_tier")
    if review_tier not in _REVIEW_TIERS:
        raise CatalogLoadError(f"{path}: unsupported review_tier {review_tier!r}")
    effective_from, effective_to = _date_range(raw, path)
    rule_version_raw = raw.get("rule_version", 1)
    if not isinstance(rule_version_raw, int) or rule_version_raw < 1:
        raise CatalogLoadError(f"{path}: rule_version must be a positive integer")
    supersedes = None
    if "supersedes" in raw and raw["supersedes"] is not None:
        supersedes = _uuid(raw["supersedes"], path, "supersedes")
    eligibility_items = _object_list(raw["eligibility"], path, "eligibility")
    if len(eligibility_items) > 32:
        raise CatalogLoadError(f"{path}: eligibility has too many items")
    eligibility = tuple(_predicate(item, path) for item in eligibility_items)
    evidence = tuple(
        _assertion(item, path) for item in _object_list(raw["evidence"], path, "evidence")
    )
    if not evidence:
        raise CatalogLoadError(f"{path}: evidence must not be empty")
    allowance = raw.get("allowance")
    if allowance is not None and not isinstance(allowance, dict):
        raise CatalogLoadError(f"{path}: allowance must be an object when present")
    if allowance is not None:
        if rescue_mode:
            _validate_rescued_value(allowance, path, "allowance")
        else:
            _validate_bounded_value(allowance, path, "allowance")
    provider, official_reference, redemption_steps, exclusions = _parse_movie_metadata(
        raw, path, benefit_type
    )
    category = _enum(raw.get("category", benefit_type), BenefitCategory, path, "category")
    owners = _parse_owners(raw.get("owners", []), path)
    condition_items = _object_list(raw.get("conditions", []), path, "conditions")
    if len(condition_items) > 32:
        raise CatalogLoadError(f"{path}: conditions has too many items")
    conditions = tuple(_parse_condition(item, path) for item in condition_items)
    quantities = _parse_quantities(
        raw.get("quantities", _QUANTITIES_MISSING),
        path,
    )
    earn = _parse_earn(raw.get("earn"), path)
    conversion = _parse_conversion(raw.get("conversion"), path)
    valuations = _parse_valuations(raw.get("valuations", []), path)
    value_class = raw.get("value_class")
    if value_class is not None and value_class not in _VALUE_CLASSES:
        raise CatalogLoadError(f"{path}: unsupported value_class {value_class!r}")
    inheritance = _parse_inheritance(raw.get("inheritance"), path)
    rule = BenefitRule(
        id=_uuid(raw["id"], path, "id"),
        offering_id=_uuid(raw["offering_id"], path, "offering_id"),
        benefit_type=benefit_type,
        title=_nonempty(raw["title"], path, "title"),
        status=status,
        review_tier=review_tier,
        effective_from=effective_from,
        effective_to=effective_to,
        eligibility=eligibility,
        allowance=allowance,
        evidence=evidence,
        conflicts_with=tuple(_string_list(raw["conflicts_with"], path, "conflicts_with")),
        rule_version=rule_version_raw,
        supersedes=supersedes,
        provider=provider,
        official_reference=official_reference,
        redemption_steps=redemption_steps,
        exclusions=exclusions,
        category=category,
        owners=owners,
        conditions=conditions,
        earn=earn,
        conversion=conversion,
        valuations=valuations,
        value_class=value_class,
        inheritance=inheritance,
        benefit_shape=benefit_shape,
        quantities=quantities,
    )
    if status == "active":
        _validate_active_review_gate(rule, path)
    return rule


def _enum(value: Any, enum_type: type[BenefitCategory], path: str, field: str) -> BenefitCategory:
    if not isinstance(value, str):
        raise CatalogLoadError(f"{path}: {field} must be a string")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise CatalogLoadError(f"{path}: unsupported {field} {value!r}") from exc


def _parse_condition(raw: dict[str, Any], path: str) -> ConditionPredicate:
    _require_exact_keys(raw, {"type", "operator"}, {"value"}, path)
    condition_type = _nonempty(raw["type"], path, "condition.type")
    if condition_type not in _CONDITION_TYPES:
        raise CatalogLoadError(f"{path}: unsupported condition type {condition_type!r}")
    operator = _nonempty(raw["operator"], path, "condition.operator")
    if operator not in _PREDICATE_OPERATORS:
        raise CatalogLoadError(f"{path}: unsupported condition operator {operator!r}")
    if operator != "exists" and "value" not in raw:
        raise CatalogLoadError(f"{path}: condition {condition_type!r} requires a value")
    condition_value = raw.get("value")
    if isinstance(condition_value, (list, dict)):
        _validate_bounded_value(condition_value, path, "condition.value")
    elif condition_value is not None and not isinstance(condition_value, (str, int, float, bool)):
        raise CatalogLoadError(f"{path}: condition.value has unsupported type")
    return ConditionPredicate(condition_type, operator, condition_value)


def _parse_quantities(value: Any, path: str) -> tuple[BenefitQuantity, ...]:
    """Validate the optional normalized projection with closed vocabularies."""

    if value is _QUANTITIES_MISSING:
        return ()
    items = _object_list(value, path, "quantities")
    if len(items) > 64:
        raise CatalogLoadError(f"{path}: quantities has too many items")
    parsed: list[BenefitQuantity] = []
    for index, item in enumerate(items):
        item_path = f"{path} quantities[{index}]"
        _require_exact_keys(
            item,
            {"metric", "value", "unit", "basis", "scope", "period", "cap"},
            path=item_path,
        )
        metric = _nonempty(item["metric"], item_path, "quantity.metric")
        if metric not in QUANTITY_METRICS:
            raise CatalogLoadError(f"{item_path}: unsupported quantity metric {metric!r}")
        quantity_value = _quantity_number(item["value"], item_path, "quantity.value")
        unit = _nonempty(item["unit"], item_path, "quantity.unit")
        if unit not in QUANTITY_UNITS:
            raise CatalogLoadError(f"{item_path}: unsupported quantity unit {unit!r}")
        basis = _nonempty(item["basis"], item_path, "quantity.basis")
        if basis not in QUANTITY_BASES:
            raise CatalogLoadError(f"{item_path}: unsupported quantity basis {basis!r}")
        scope = item["scope"]
        if scope is not None:
            scope = _nonempty(scope, item_path, "quantity.scope")
            if scope not in QUANTITY_SCOPES:
                raise CatalogLoadError(f"{item_path}: unsupported quantity scope {scope!r}")
        period = _nonempty(item["period"], item_path, "quantity.period")
        if period not in QUANTITY_PERIODS:
            raise CatalogLoadError(f"{item_path}: unsupported quantity period {period!r}")
        cap = item["cap"]
        if cap is not None:
            if not isinstance(cap, dict):
                raise CatalogLoadError(f"{item_path}: quantity.cap must be an object or null")
            _require_exact_keys(cap, {"value", "unit", "period"}, path=f"{item_path} cap")
            cap_value = _quantity_number(cap["value"], item_path, "quantity.cap.value")
            cap_unit = _nonempty(cap["unit"], item_path, "quantity.cap.unit")
            if cap_unit not in QUANTITY_UNITS:
                raise CatalogLoadError(
                    f"{item_path}: unsupported quantity cap unit {cap_unit!r}"
                )
            cap_period = _nonempty(cap["period"], item_path, "quantity.cap.period")
            if cap_period not in QUANTITY_PERIODS:
                raise CatalogLoadError(
                    f"{item_path}: unsupported quantity cap period {cap_period!r}"
                )
            cap = {"value": cap_value, "unit": cap_unit, "period": cap_period}
        parsed.append(
            BenefitQuantity(
                metric=metric,
                value=quantity_value,
                unit=unit,
                basis=basis,
                scope=scope,
                period=period,
                cap=cap,
            )
        )
    return tuple(parsed)


def _quantity_number(value: Any, path: str, field: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CatalogLoadError(f"{path}: {field} must be a JSON number")
    if isinstance(value, float) and not math.isfinite(value):
        raise CatalogLoadError(f"{path}: {field} must be finite")
    if value < 0:
        raise CatalogLoadError(f"{path}: {field} must not be negative")
    return value


def _parse_owners(value: Any, path: str) -> tuple[RuleOwner, ...]:
    owners = _object_list(value, path, "owners")
    if len(owners) > 16:
        raise CatalogLoadError(f"{path}: owners has too many items")
    result = []
    for item in owners:
        _require_exact_keys(item, {"kind", "id", "display_name"}, path=path)
        kind = _nonempty(item["kind"], path, "owner.kind")
        if kind not in _OWNER_KINDS:
            raise CatalogLoadError(f"{path}: unsupported owner kind {kind!r}")
        result.append(
            RuleOwner(
                cast(Any, kind),
                _nonempty(item["id"], path, "owner.id"),
                _bounded_text(item["display_name"], path, "owner.display_name", max_length=160),
            )
        )
    if len({(item.kind, item.id) for item in result}) != len(result):
        raise CatalogLoadError(f"{path}: duplicate rule owners")
    return tuple(result)


def _parse_earn(value: Any, path: str) -> EarnRule | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise CatalogLoadError(f"{path}: earn must be an object")
    required = {"currency", "rate", "basis", "scope"}
    _require_keys(value, required, path)
    _require_exact_keys(
        value, required, {"cap", "exclusions", "rounding", "reversal", "expiry"}, path
    )
    exclusions = tuple(
        _bounded_string_list(
            value.get("exclusions", []),
            path,
            "earn.exclusions",
            max_items=32,
            max_length=160,
            allow_empty=True,
        )
    )
    cap, expiry = value.get("cap"), value.get("expiry")
    if cap is not None and not isinstance(cap, dict):
        raise CatalogLoadError(f"{path}: earn.cap must be an object or null")
    if expiry is not None and not isinstance(expiry, dict):
        raise CatalogLoadError(f"{path}: earn.expiry must be an object or null")
    if cap is not None:
        _validate_bounded_value(cap, path, "earn.cap")
    if expiry is not None:
        _validate_bounded_value(expiry, path, "earn.expiry")
    _decimal(value["rate"], path, "earn.rate", positive=True)
    return EarnRule(
        _bounded_text(value["currency"], path, "earn.currency", max_length=64),
        _bounded_text(value["rate"], path, "earn.rate", max_length=64),
        _bounded_text(value["basis"], path, "earn.basis", max_length=120),
        _bounded_text(value["scope"], path, "earn.scope", max_length=120),
        cap,
        exclusions,
        _optional_string(value.get("rounding"), path, "earn.rounding"),
        _optional_string(value.get("reversal"), path, "earn.reversal"),
        expiry,
    )


def _parse_conversion(value: Any, path: str) -> ConversionRule | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise CatalogLoadError(f"{path}: conversion must be an object")
    required = {
        "partner_id",
        "ratio",
        "fee",
        "minimum",
        "increment",
        "expiry",
        "redemption_options",
    }
    _require_exact_keys(value, required, path=path)
    minimum, increment = value["minimum"], value["increment"]
    if minimum is not None and (
        isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 0
    ):
        raise CatalogLoadError(f"{path}: conversion.minimum must be a non-negative integer or null")
    if increment is not None and (
        isinstance(increment, bool) or not isinstance(increment, int) or increment <= 0
    ):
        raise CatalogLoadError(f"{path}: conversion.increment must be a positive integer or null")
    _ratio(value["ratio"], path, "conversion.ratio")
    if value["fee"] is not None:
        if not isinstance(value["fee"], dict):
            raise CatalogLoadError(f"{path}: conversion.fee must be an object or null")
        _validate_bounded_value(value["fee"], path, "conversion.fee")
    if value["expiry"] is not None:
        if not isinstance(value["expiry"], dict):
            raise CatalogLoadError(f"{path}: conversion.expiry must be an object or null")
        _validate_bounded_value(value["expiry"], path, "conversion.expiry")
    return ConversionRule(
        _bounded_text(value["partner_id"], path, "conversion.partner_id", max_length=160),
        _bounded_text(value["ratio"], path, "conversion.ratio", max_length=64),
        value["fee"],
        minimum,
        increment,
        value["expiry"],
        tuple(
            _bounded_string_list(
                value["redemption_options"],
                path,
                "conversion.redemption_options",
                max_items=16,
                max_length=160,
                allow_empty=False,
            )
        ),
    )


def _parse_valuations(value: Any, path: str) -> tuple[ValuationRange, ...]:
    result = []
    items = _object_list(value, path, "valuations")
    if len(items) > 32:
        raise CatalogLoadError(f"{path}: valuations has too many items")
    for item in items:
        _require_exact_keys(
            item, {"name", "redemption_path", "currency", "minimum", "maximum"}, path=path
        )
        minimum, maximum = (
            _bounded_text(item["minimum"], path, "valuation.minimum", max_length=64),
            _bounded_text(item["maximum"], path, "valuation.maximum", max_length=64),
        )
        min_value, max_value = (
            _decimal(minimum, path, "valuation.minimum"),
            _decimal(maximum, path, "valuation.maximum"),
        )
        if min_value < 0 or max_value < 0 or max_value <= min_value:
            raise CatalogLoadError(f"{path}: valuation must be a range, not a single value")
        result.append(
            ValuationRange(
                _bounded_text(item["name"], path, "valuation.name", max_length=160),
                _bounded_text(
                    item["redemption_path"], path, "valuation.redemption_path", max_length=240
                ),
                _nonempty(item["currency"], path, "valuation.currency"),
                minimum,
                maximum,
            )
        )
    return tuple(result)


def _parse_inheritance(value: Any, path: str) -> InheritanceRule | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise CatalogLoadError(f"{path}: inheritance must be an object")
    if value.get("opt_in") is not True:
        raise CatalogLoadError(f"{path}: inheritance must be explicitly opt_in true")
    _require_exact_keys(
        value,
        {
            "owner",
            "source_benefit_id",
            "source_offering_id",
            "target_offering_id",
            "source_network_id",
            "target_network_id",
            "source_co_brand_id",
            "target_co_brand_id",
            "review_state",
            "opt_in",
            "effective_from",
            "effective_to",
        },
        path=path,
    )
    owner_values = _parse_owners([value["owner"]], path)
    start, end = _date_range(value, path)
    if start is None or end is None:
        raise CatalogLoadError(f"{path}: inheritance requires effective_from and effective_to")
    review_state = _nonempty(value["review_state"], path, "inheritance.review_state")
    if review_state not in {"approved", "needs_review"}:
        raise CatalogLoadError(f"{path}: invalid inheritance review_state")
    return InheritanceRule(
        owner_values[0],
        _uuid(value["source_benefit_id"], path, "inheritance.source_benefit_id"),
        _uuid(value["source_offering_id"], path, "inheritance.source_offering_id"),
        _uuid(value["target_offering_id"], path, "inheritance.target_offering_id"),
        _bounded_text(
            value["source_network_id"], path, "inheritance.source_network_id", max_length=160
        ),
        _bounded_text(
            value["target_network_id"], path, "inheritance.target_network_id", max_length=160
        ),
        _optional_string(value["source_co_brand_id"], path, "inheritance.source_co_brand_id"),
        _optional_string(value["target_co_brand_id"], path, "inheritance.target_co_brand_id"),
        review_state,
        True,
        start,
        end,
    )


def _parse_movie_metadata(
    raw: dict[str, Any], path: str, benefit_type: str
) -> tuple[str | None, str | None, tuple[str, ...], tuple[str, ...]]:
    """Parse the bounded, public fulfillment metadata for movie rules.

    Conditions remain the canonical ``eligibility`` predicates and allowance
    remains the canonical cap/usage structure shared by every benefit type.
    Movie rules add only the provider, official reference, redemption steps,
    and explicit exclusions needed to explain a ticket/voucher offer.
    """
    fields = {"provider", "official_reference", "redemption_steps", "exclusions"}
    present = fields & raw.keys()
    if benefit_type != "movie":
        if present:
            unexpected = ", ".join(sorted(present))
            raise CatalogLoadError(
                f"{path}: movie metadata is only valid for benefit_type 'movie' ({unexpected})"
            )
        return None, None, (), ()
    missing = sorted(fields - raw.keys())
    if missing:
        raise CatalogLoadError(
            f"{path}: movie benefit missing required fields: {', '.join(missing)}"
        )
    provider = _bounded_text(raw["provider"], path, "provider", max_length=160)
    official_reference = _anonymous_https_url(raw["official_reference"], path, "official_reference")
    redemption_steps = _bounded_string_list(
        raw["redemption_steps"],
        path,
        "redemption_steps",
        max_items=12,
        max_length=240,
        allow_empty=False,
    )
    exclusions = _bounded_string_list(
        raw["exclusions"], path, "exclusions", max_items=32, max_length=240, allow_empty=True
    )
    return provider, official_reference, tuple(redemption_steps), tuple(exclusions)


def _parse_relationship(raw: dict[str, Any], path: str) -> ProductRelationship:
    required = {
        "id",
        "from_offering_id",
        "to_offering_id",
        "relationship_type",
        "review_state",
        "evidence",
    }
    _require_exact_keys(raw, required, {"effective_from", "effective_to"}, path)
    rel_type = _nonempty(raw["relationship_type"], path, "relationship_type")
    if rel_type not in _RELATIONSHIP_TYPES:
        raise CatalogLoadError(f"{path}: unsupported relationship_type {rel_type!r}")
    review_state = _nonempty(raw["review_state"], path, "review_state")
    if review_state not in _RELATIONSHIP_REVIEW_STATE:
        raise CatalogLoadError(f"{path}: unsupported relationship review_state {review_state!r}")
    from_id = _uuid(raw["from_offering_id"], path, "from_offering_id")
    to_id = _uuid(raw["to_offering_id"], path, "to_offering_id")
    if from_id == to_id:
        raise CatalogLoadError(f"{path}: relationship must not reference itself")
    evidence = tuple(
        _assertion(item, path) for item in _object_list(raw["evidence"], path, "evidence")
    )
    if not evidence:
        raise CatalogLoadError(f"{path}: relationship evidence must not be empty")
    effective_from, effective_to = _date_range(raw, path)
    rel = ProductRelationship(
        id=_uuid(raw["id"], path, "id"),
        from_offering_id=from_id,
        to_offering_id=to_id,
        relationship_type=rel_type,
        effective_from=effective_from,
        effective_to=effective_to,
        review_state=review_state,
        evidence=evidence,
    )
    if review_state == "approved":
        _validate_approved_relationship_evidence(rel, path)
    return rel


def _assertion(raw: dict[str, Any], path: str) -> EvidenceAssertion:
    required = {
        "id",
        "source_policy_class",
        "url",
        "content_sha256",
        "retrieved_at",
        "confidence",
        "review_state",
        "reviews",
    }
    _require_exact_keys(
        raw,
        required,
        {
            "effective_from",
            "effective_to",
            "personalized",
            "source_observation_id",
            "hash_kind",
        },
        path,
    )
    personalized = raw.get("personalized", False)
    if not isinstance(personalized, bool):
        raise CatalogLoadError(f"{path}: personalized must be a boolean")
    source_class = _nonempty(raw["source_policy_class"], path, "source_policy_class")
    if source_class not in _SOURCE_CLASSES:
        raise CatalogLoadError(f"{path}: unsupported source_policy_class {source_class!r}")
    url = _nonempty(raw["url"], path, "url")
    parsed_url = urlparse(url)
    if (
        parsed_url.scheme != "https"
        or not parsed_url.netloc
        or parsed_url.username
        or parsed_url.password
    ):
        raise CatalogLoadError(f"{path}: evidence url must be an anonymous HTTPS URL")
    digest = _nonempty(raw["content_sha256"], path, "content_sha256")
    if not _SHA256.fullmatch(digest):
        raise CatalogLoadError(f"{path}: content_sha256 must be a lowercase SHA-256 digest")
    confidence = _nonempty(raw["confidence"], path, "confidence")
    review_state = _nonempty(raw["review_state"], path, "review_state")
    if confidence not in _CONFIDENCE or review_state not in _REVIEW_STATE:
        raise CatalogLoadError(f"{path}: invalid confidence or review_state")
    effective_from, effective_to = _date_range(raw, path)
    retrieved_at = _datetime(raw["retrieved_at"], path, "retrieved_at")
    reviews = tuple(_review(item, path) for item in _object_list(raw["reviews"], path, "reviews"))
    _unique((item.id for item in reviews), f"{path} review IDs")
    _unique((item.reviewer_id for item in reviews), f"{path} reviewers")
    if any(item.reviewed_at < retrieved_at for item in reviews):
        raise CatalogLoadError(f"{path}: a review cannot predate its evidence retrieval")
    decisions = {item.decision for item in reviews}
    if review_state == "approved" and source_class == "discovery_only":
        raise CatalogLoadError(f"{path}: discovery_only (tier 6) evidence cannot be approved")
    if review_state == "approved" and personalized:
        raise CatalogLoadError(f"{path}: personalized or login-only evidence cannot be approved as a public fact")
    if review_state == "approved" and not reviews:
        raise CatalogLoadError(f"{path}: approved evidence requires a human review record")
    if review_state == "approved" and ("approved" not in decisions or "rejected" in decisions):
        raise CatalogLoadError(
            f"{path}: approved evidence requires only approving review decisions"
        )
    if review_state == "rejected" and "rejected" not in decisions:
        raise CatalogLoadError(f"{path}: rejected evidence requires a rejecting review decision")
    return EvidenceAssertion(
        _uuid(raw["id"], path, "assertion.id"),
        source_class,
        url,
        digest,
        retrieved_at,
        effective_from,
        effective_to,
        confidence,
        review_state,
        reviews,
        personalized=personalized,
        source_observation_id=_optional_string(
            raw.get("source_observation_id"), path, "source_observation_id"
        ),
        hash_kind=_optional_string(raw.get("hash_kind"), path, "hash_kind"),
    )


def _review(raw: dict[str, Any], path: str) -> HumanReview:
    _require_exact_keys(raw, {"id", "reviewer_id", "reviewed_at", "decision"}, path=path)
    decision = _nonempty(raw["decision"], path, "review.decision")
    if decision not in _REVIEW_DECISIONS:
        raise CatalogLoadError(f"{path}: unsupported review decision {decision!r}")
    return HumanReview(
        id=_uuid(raw["id"], path, "review.id"),
        reviewer_id=_nonempty(raw["reviewer_id"], path, "review.reviewer_id"),
        reviewed_at=_datetime(raw["reviewed_at"], path, "review.reviewed_at"),
        decision=decision,
    )


def _validate_active_review_gate(rule: BenefitRule, path: str) -> None:
    if any(not assertion.reviews for assertion in rule.evidence):
        raise CatalogLoadError(f"{path}: active benefit evidence requires a human review record")
    active_evidence = [
        item
        for item in rule.evidence
        if item.review_state == "approved" and item.confidence in {"high", "medium"}
    ]
    if not active_evidence:
        raise CatalogLoadError(
            f"{path}: active benefit requires approved medium/high-confidence evidence"
        )
    reviewers = {
        review.reviewer_id
        for assertion in active_evidence
        for review in assertion.reviews
        if review.decision == "approved"
    }
    if not reviewers:
        raise CatalogLoadError(
            f"{path}: active {rule.review_tier} benefit requires at least 1 approved human review"
        )


def _validate_approved_relationship_evidence(rel: ProductRelationship, path: str) -> None:
    if any(not assertion.reviews for assertion in rel.evidence):
        raise CatalogLoadError(
            f"{path}: approved relationship evidence requires a human review record"
        )
    active_evidence = [
        item
        for item in rel.evidence
        if item.review_state == "approved" and item.confidence in {"high", "medium"}
    ]
    if not active_evidence:
        raise CatalogLoadError(
            f"{path}: approved relationship requires approved medium/high-confidence evidence"
        )
    reviewers = {
        review.reviewer_id
        for assertion in active_evidence
        for review in assertion.reviews
        if review.decision == "approved"
    }
    if not reviewers:
        raise CatalogLoadError(
            f"{path}: approved relationship requires at least 1 approved human review"
        )


def _predicate(raw: dict[str, Any], path: str) -> dict[str, Any]:
    _require_keys(raw, {"field", "operator"}, path)
    field = _nonempty(raw["field"], path, "eligibility.field")
    operator = _nonempty(raw["operator"], path, "eligibility.operator")
    if operator not in _PREDICATE_OPERATORS:
        raise CatalogLoadError(f"{path}: unsupported eligibility operator {operator!r}")
    if operator != "exists" and "value" not in raw:
        raise CatalogLoadError(f"{path}: eligibility {field!r} requires a value")
    return dict(raw)


def _validate_cross_records(
    release: ReleaseMetadata,
    offerings: tuple[Offering, ...],
    benefits: tuple[BenefitRule, ...],
    relationships: tuple[ProductRelationship, ...] = (),
) -> None:
    _unique((item.id for item in offerings), "offering IDs")
    _unique((item.slug for item in offerings), "offering slugs")
    aliases = [alias.casefold() for item in offerings for alias in item.aliases]
    _unique(aliases, "offering aliases")
    offering_ids = {item.id for item in offerings}
    _unique((item.id for item in benefits), "benefit IDs")
    benefit_ids = {item.id for item in benefits}
    for rule in benefits:
        if rule.offering_id not in offering_ids:
            raise CatalogLoadError(f"benefit {rule.id}: unknown offering_id")
        if rule.id in rule.conflicts_with or not set(rule.conflicts_with) <= benefit_ids:
            raise CatalogLoadError(
                f"benefit {rule.id}: conflicts_with must name other known benefits"
            )
        for assertion in rule.evidence:
            if assertion.retrieved_at > release.generated_at:
                raise CatalogLoadError(
                    f"benefit {rule.id}: evidence retrieval is after the release"
                )
            if any(review.reviewed_at > release.generated_at for review in assertion.reviews):
                raise CatalogLoadError(f"benefit {rule.id}: review is after the release")
        if rule.inheritance is not None:
            inheritance = rule.inheritance
            if inheritance.source_benefit_id == rule.id:
                raise CatalogLoadError(f"benefit {rule.id}: inheritance cannot reference itself")
            if inheritance.source_benefit_id not in benefit_ids:
                raise CatalogLoadError(
                    f"benefit {rule.id}: inheritance references unknown source benefit"
                )
            source = next(item for item in benefits if item.id == inheritance.source_benefit_id)
            target_offering = next(item for item in offerings if item.id == rule.offering_id)
            source_offering = next(item for item in offerings if item.id == source.offering_id)
            if (
                source.offering_id != inheritance.source_offering_id
                or rule.offering_id != inheritance.target_offering_id
            ):
                raise CatalogLoadError(
                    f"benefit {rule.id}: inheritance offering binding does not match records"
                )
            if (
                source_offering.network_id != inheritance.source_network_id
                or target_offering.network_id != inheritance.target_network_id
            ):
                raise CatalogLoadError(
                    f"benefit {rule.id}: inheritance network binding does not match offerings"
                )
            if (
                source_offering.co_brand_id != inheritance.source_co_brand_id
                or target_offering.co_brand_id != inheritance.target_co_brand_id
            ):
                raise CatalogLoadError(
                    f"benefit {rule.id}: inheritance co-brand binding does not match offerings"
                )
            if rule.status == "active" and inheritance.review_state != "approved":
                raise CatalogLoadError(
                    f"benefit {rule.id}: active inherited benefits require approved inheritance review"
                )
    # ---- conflicting-assertion symmetry: a recorded conflict must be mutual, never one-sided ----
    benefit_by_id_for_conflicts = {rule.id: rule for rule in benefits}
    for rule in benefits:
        for other_id in rule.conflicts_with:
            other = benefit_by_id_for_conflicts[other_id]
            if rule.id not in other.conflicts_with:
                raise CatalogLoadError(
                    f"benefit {rule.id}: conflicts_with {other_id} but {other_id} does not conflict back"
                )
    # ---- supersession integrity ----
    benefit_by_id = {rule.id: rule for rule in benefits}
    supersedes_edges: dict[str, list[str]] = {}
    for rule in benefits:
        if rule.supersedes is not None:
            if rule.supersedes == rule.id:
                raise CatalogLoadError(f"benefit {rule.id}: cannot supersede itself")
            if rule.supersedes not in benefit_ids:
                raise CatalogLoadError(
                    f"benefit {rule.id}: supersedes unknown benefit {rule.supersedes}"
                )
            prior_rule = benefit_by_id[rule.supersedes]
            if prior_rule.offering_id != rule.offering_id:
                raise CatalogLoadError(
                    f"benefit {rule.id}: cannot supersede rule {rule.supersedes} from a different offering"
                )
            if prior_rule.benefit_type != rule.benefit_type:
                raise CatalogLoadError(
                    f"benefit {rule.id}: cannot supersede rule {rule.supersedes} of a different benefit_type ({prior_rule.benefit_type!r} vs {rule.benefit_type!r})"
                )
            if rule.rule_version <= prior_rule.rule_version:
                raise CatalogLoadError(
                    f"benefit {rule.id}: rule_version ({rule.rule_version}) must be strictly greater than superseded rule_version ({prior_rule.rule_version})"
                )
            if prior_rule.status not in {"superseded", "historical"}:
                raise CatalogLoadError(
                    f"benefit {rule.id}: supersedes benefit {rule.supersedes} with status {prior_rule.status!r}"
                )
            supersedes_edges[rule.id] = [rule.supersedes]
    _detect_cycle(supersedes_edges, "benefit supersession chain contains a cycle")
    # ---- relationship graph integrity ----
    _unique((item.id for item in relationships), "relationship IDs")
    edges: set[tuple[str, str, str]] = set()
    for rel in relationships:
        if rel.from_offering_id not in offering_ids:
            raise CatalogLoadError(f"relationship {rel.id}: unknown from_offering_id")
        if rel.to_offering_id not in offering_ids:
            raise CatalogLoadError(f"relationship {rel.id}: unknown to_offering_id")
        edge = (rel.from_offering_id, rel.to_offering_id, rel.relationship_type)
        if edge in edges:
            raise CatalogLoadError(f"relationship {rel.id}: duplicate edge")
        edges.add(edge)
    # DAG enforcement for renamed and legacy edges — no cycles allowed
    dag_edges: dict[str, list[str]] = {}
    for rel in relationships:
        if rel.relationship_type in {"renamed", "legacy"}:
            dag_edges.setdefault(rel.from_offering_id, []).append(rel.to_offering_id)
    _detect_cycle(dag_edges, "relationship graph contains a cycle in renamed/legacy edges")


def _require_keys(raw: dict[str, Any], keys: set[str], path: str) -> None:
    missing = sorted(keys - raw.keys())
    if missing:
        raise CatalogLoadError(f"{path}: missing required fields: {', '.join(missing)}")


def _require_exact_keys(
    raw: dict[str, Any],
    required: set[str],
    optional: set[str] | None = None,
    path: str = "record",
) -> None:
    optional = optional or set()
    _require_keys(raw, required, path)
    unexpected = sorted(raw.keys() - required - optional)
    if unexpected:
        raise CatalogLoadError(f"{path}: unexpected fields: {', '.join(unexpected)}")


def _uuid(value: Any, path: str, field: str) -> str:
    value = _nonempty(value, path, field)
    try:
        return str(uuid.UUID(value))
    except ValueError as exc:
        raise CatalogLoadError(f"{path}: {field} must be a UUID") from exc


def _date_range(raw: dict[str, Any], path: str) -> tuple[date | None, date | None]:
    start = _optional_date(raw.get("effective_from"), path, "effective_from")
    end = _optional_date(raw.get("effective_to"), path, "effective_to")
    if start and end and end < start:
        raise CatalogLoadError(f"{path}: effective_to precedes effective_from")
    return start, end


def _optional_date(value: Any, path: str, field: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(_nonempty(value, path, field))
    except ValueError as exc:
        raise CatalogLoadError(f"{path}: {field} must be an ISO date") from exc


def _datetime(value: Any, path: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(_nonempty(value, path, field).replace("Z", "+00:00"))
    except ValueError as exc:
        raise CatalogLoadError(f"{path}: {field} must be an ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CatalogLoadError(f"{path}: {field} must include a timezone")
    return parsed


def _market(value: Any, path: str) -> str:
    market = _nonempty(value, path, "market")
    if not re.fullmatch(r"[A-Z]{2}", market):
        raise CatalogLoadError(f"{path}: market must be an ISO 3166-1 alpha-2 code")
    return market


def _nonempty(value: Any, path: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CatalogLoadError(f"{path}: {field} must be a non-empty string")
    return value


def _decimal(value: Any, path: str, field: str, *, positive: bool = False) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise CatalogLoadError(f"{path}: {field} must be a finite decimal")
    if isinstance(value, float) and not math.isfinite(value):
        raise CatalogLoadError(f"{path}: {field} must be finite")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise CatalogLoadError(f"{path}: {field} must be a finite decimal") from exc
    if not parsed.is_finite() or (positive and parsed <= 0) or (not positive and parsed < 0):
        raise CatalogLoadError(f"{path}: {field} has an invalid bound")
    exponent = parsed.as_tuple().exponent
    if isinstance(exponent, int) and abs(exponent) > 18:
        raise CatalogLoadError(f"{path}: {field} has unsafe precision")
    return parsed


def _ratio(value: Any, path: str, field: str) -> None:
    text = _bounded_text(value, path, field, max_length=64)
    parts = text.split(":")
    if len(parts) == 1:
        _decimal(text, path, field, positive=True)
    elif len(parts) == 2:
        numerator, denominator = (_decimal(part, path, field, positive=True) for part in parts)
        if denominator == 0 or numerator / denominator <= 0:
            raise CatalogLoadError(f"{path}: {field} must be a positive ratio")
    else:
        raise CatalogLoadError(f"{path}: {field} must be a positive ratio")


def _validate_bounded_value(value: Any, path: str, field: str, *, depth: int = 0) -> None:
    if depth > 3:
        raise CatalogLoadError(f"{path}: {field} is too deeply nested")
    if isinstance(value, bool):
        raise CatalogLoadError(f"{path}: {field} must not use booleans as numbers")
    if isinstance(value, (int, float)):
        _decimal(value, path, field)
        return
    if isinstance(value, str):
        _bounded_text(value, path, field, max_length=160)
        return
    if isinstance(value, list):
        if len(value) > 32:
            raise CatalogLoadError(f"{path}: {field} has too many items")
        for item in value:
            _validate_bounded_value(item, path, field, depth=depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > 16:
            raise CatalogLoadError(f"{path}: {field} has too many fields")
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 80:
                raise CatalogLoadError(f"{path}: {field} has an invalid key")
            _validate_bounded_value(item, path, f"{field}.{key}", depth=depth + 1)
        return
    raise CatalogLoadError(f"{path}: {field} has an unsupported value")


def _validate_rescued_value(value: Any, path: str, field: str, *, depth: int = 0) -> None:
    """Validate rescue payload values while retaining their JSON scalar types."""
    if depth > 3:
        raise CatalogLoadError(f"{path}: {field} is too deeply nested")
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        _decimal(value, path, field)
        return
    if isinstance(value, str):
        _bounded_text(value, path, field, max_length=160)
        return
    if isinstance(value, list):
        if len(value) > 32:
            raise CatalogLoadError(f"{path}: {field} has too many items")
        for item in value:
            _validate_rescued_value(item, path, field, depth=depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > 16:
            raise CatalogLoadError(f"{path}: {field} has too many fields")
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 80:
                raise CatalogLoadError(f"{path}: {field} has an invalid key")
            _validate_rescued_value(item, path, f"{field}.{key}", depth=depth + 1)
        return
    raise CatalogLoadError(f"{path}: {field} has an unsupported value")


def _bounded_text(value: Any, path: str, field: str, *, max_length: int) -> str:
    text = _nonempty(value, path, field)
    if len(text) > max_length:
        raise CatalogLoadError(f"{path}: {field} exceeds {max_length} characters")
    return text


def _anonymous_https_url(value: Any, path: str, field: str) -> str:
    url = _bounded_text(value, path, field, max_length=2048)
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise CatalogLoadError(f"{path}: {field} must be an anonymous HTTPS URL without a fragment")
    return url


def _bounded_string_list(
    value: Any,
    path: str,
    field: str,
    *,
    max_items: int,
    max_length: int,
    allow_empty: bool,
) -> list[str]:
    values = _string_list(value, path, field)
    if not allow_empty and not values:
        raise CatalogLoadError(f"{path}: {field} must contain at least one item")
    if len(values) > max_items:
        raise CatalogLoadError(f"{path}: {field} must contain at most {max_items} items")
    for item in values:
        if len(item) > max_length:
            raise CatalogLoadError(f"{path}: {field} items exceed {max_length} characters")
    return values


def _optional_string(value: Any, path: str, field: str) -> str | None:
    return None if value is None else _nonempty(value, path, field)


def _string_list(value: Any, path: str, field: str) -> list[str]:
    if not isinstance(value, list):
        raise CatalogLoadError(f"{path}: {field} must be a list")
    strings = [_nonempty(item, path, field) for item in value]
    _unique(strings, f"{path} {field}")
    return strings


def _object_list(value: Any, path: str, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise CatalogLoadError(f"{path}: {field} must be a list of objects")
    return value


def _unique(values: Iterable[str], label: str) -> None:
    values = list(values)
    if len(values) != len(set(values)):
        raise CatalogLoadError(f"duplicate {label}")


def _in_date_range(value: date, start: date | None, end: date | None) -> bool:
    return (start is None or start <= value) and (end is None or value <= end)


def _conflict_scope_compatible(
    release: ReleaseMetadata, local: Offering, target: Offering
) -> bool:
    """Require both offerings to belong to the same effective catalog scope."""
    return local.market == target.market and local.market in release.market_scope


def _detect_cycle(
    adjacency: dict[str, list[str]],
    error_message: str = "relationship graph contains a cycle in renamed/legacy edges",
) -> None:
    """Raise CatalogLoadError if the directed graph contains a cycle."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {node: WHITE for node in adjacency}
    for targets in adjacency.values():
        for t in targets:
            color.setdefault(t, WHITE)

    for start in list(color):
        if color[start] != WHITE:
            continue
        stack = [start]
        while stack:
            node = stack[-1]
            if color[node] == WHITE:
                color[node] = GRAY
                for neighbor in adjacency.get(node, []):
                    if color.get(neighbor, WHITE) == GRAY:
                        raise CatalogLoadError(error_message)
                    if color.get(neighbor, WHITE) == WHITE:
                        stack.append(neighbor)
            else:
                stack.pop()
                color[node] = BLACK
