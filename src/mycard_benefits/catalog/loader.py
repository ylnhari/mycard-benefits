"""Deterministic loader and fail-closed validator for public catalog JSON."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .model import (
    BenefitRule,
    EvidenceAssertion,
    HumanReview,
    Offering,
    ProductRelationship,
    ReleaseMetadata,
)


class CatalogLoadError(ValueError):
    """Raised when a catalog is malformed, ambiguous, or unsafe to activate."""


_SOURCE_CLASSES = {
    "administering_terms",
    "issuer_document",
    "network_rule",
    "merchant_terms",
    "regulatory_context",
    "discovery_only",
}
_BENEFIT_TYPES = {
    "reward_points", "conversion", "movie", "hotel", "food", "cashback",
    "voucher", "meet_and_greet", "lounge", "priority_pass", "other",
}
_RULE_STATUS = {"active", "historical", "needs_review", "superseded"}
_RELATIONSHIP_TYPES = {"renamed", "legacy", "cloned", "reskinned"}
_RELATIONSHIP_REVIEW_STATE = {"approved", "needs_review"}
_CONFIDENCE = {"high", "medium", "low"}
_REVIEW_STATE = {"approved", "needs_review", "reviewed", "rejected", "superseded"}
_REVIEW_TIERS = {"standard", "enhanced", "high_impact", "ambiguous"}
_REVIEW_DECISIONS = {"approved", "rejected"}
_PREDICATE_OPERATORS = {"equals", "in", "not_in", "gte", "lte", "between", "exists"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class Catalog:
    release: ReleaseMetadata
    offerings: tuple[Offering, ...]
    benefits: tuple[BenefitRule, ...]
    relationships: tuple[ProductRelationship, ...]

    def offering_by_slug(self, slug: str) -> Offering | None:
        return next((item for item in self.offerings if item.slug == slug), None)

    def benefits_for(self, offering_id: str, as_of: date | None = None) -> tuple[BenefitRule, ...]:
        as_of = as_of or self.release.generated_at.date()
        return tuple(
            rule for rule in self.benefits
            if rule.offering_id == offering_id
            and rule.status == "active"
            and _in_date_range(as_of, rule.effective_from, rule.effective_to)
        )

    def historical_benefits_for(self, offering_id: str) -> tuple[BenefitRule, ...]:
        """Return expired, superseded, and historical rules for an offering."""
        return tuple(
            rule for rule in self.benefits
            if rule.offering_id == offering_id
            and rule.status in {"historical", "superseded"}
        )


def load_catalog(root: str | Path) -> Catalog:
    """Load only JSON catalog assets and reject invalid/review-only active claims."""
    root = Path(root)
    release_raw = _read_json(root / "schema" / "release.json")
    release = _parse_release(release_raw, "schema/release.json")
    offerings = tuple(_parse_offering(raw, path) for path, raw in _read_many(root / "offerings"))
    benefits = tuple(_parse_benefit(raw, path) for path, raw in _read_many(root / "benefits", allow_empty=True))
    relationships = tuple(
        _parse_relationship(raw, path)
        for path, raw in _read_many(root / "relationships", allow_empty=True)
    )
    _validate_cross_records(release, offerings, benefits, relationships)
    return Catalog(release=release, offerings=offerings, benefits=benefits, relationships=relationships)


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
    required = {"id", "slug", "display_name", "issuer_id", "product_variant_id", "network_id", "market", "aliases"}
    optional = {"co_brand_id", "cohort_id", "effective_from", "effective_to"}
    _require_exact_keys(raw, required, optional, path)
    slug = _nonempty(raw["slug"], path, "slug")
    if not _SLUG.fullmatch(slug):
        raise CatalogLoadError(f"{path}: slug must be lowercase kebab-case")
    effective_from, effective_to = _date_range(raw, path)
    return Offering(
        id=_uuid(raw["id"], path, "id"), slug=slug,
        display_name=_nonempty(raw["display_name"], path, "display_name"),
        issuer_id=_nonempty(raw["issuer_id"], path, "issuer_id"),
        product_variant_id=_nonempty(raw["product_variant_id"], path, "product_variant_id"),
        network_id=_nonempty(raw["network_id"], path, "network_id"),
        market=_market(raw["market"], path),
        co_brand_id=_optional_string(raw.get("co_brand_id"), path, "co_brand_id"),
        cohort_id=_optional_string(raw.get("cohort_id"), path, "cohort_id"),
        aliases=tuple(_string_list(raw["aliases"], path, "aliases")),
        effective_from=effective_from, effective_to=effective_to,
    )


def _parse_benefit(raw: dict[str, Any], path: str) -> BenefitRule:
    required = {"id", "offering_id", "benefit_type", "title", "status", "review_tier", "eligibility", "evidence", "conflicts_with"}
    optional = {"effective_from", "effective_to", "allowance", "rule_version", "supersedes"}
    _require_exact_keys(raw, required, optional, path)
    benefit_type = _nonempty(raw["benefit_type"], path, "benefit_type")
    if benefit_type not in _BENEFIT_TYPES:
        raise CatalogLoadError(f"{path}: unsupported benefit_type {benefit_type!r}")
    status = _nonempty(raw["status"], path, "status")
    if status not in _RULE_STATUS:
        raise CatalogLoadError(f"{path}: unsupported status {status!r}")
    review_tier = _nonempty(raw["review_tier"], path, "review_tier")
    if review_tier not in _REVIEW_TIERS:
        raise CatalogLoadError(f"{path}: unsupported review_tier {review_tier!r}")
    effective_from, effective_to = _date_range(raw, path)
    end_date_known = effective_to is not None
    rule_version_raw = raw.get("rule_version", 1)
    if not isinstance(rule_version_raw, int) or rule_version_raw < 1:
        raise CatalogLoadError(f"{path}: rule_version must be a positive integer")
    supersedes = None
    if "supersedes" in raw and raw["supersedes"] is not None:
        supersedes = _uuid(raw["supersedes"], path, "supersedes")
    eligibility = tuple(_predicate(item, path) for item in _object_list(raw["eligibility"], path, "eligibility"))
    evidence = tuple(_assertion(item, path) for item in _object_list(raw["evidence"], path, "evidence"))
    if not evidence:
        raise CatalogLoadError(f"{path}: evidence must not be empty")
    allowance = raw.get("allowance")
    if allowance is not None and not isinstance(allowance, dict):
        raise CatalogLoadError(f"{path}: allowance must be an object when present")
    rule = BenefitRule(
        id=_uuid(raw["id"], path, "id"), offering_id=_uuid(raw["offering_id"], path, "offering_id"),
        benefit_type=benefit_type, title=_nonempty(raw["title"], path, "title"), status=status, review_tier=review_tier,
        effective_from=effective_from, effective_to=effective_to,
        end_date_known=end_date_known, rule_version=rule_version_raw, supersedes=supersedes,
        eligibility=eligibility,
        allowance=allowance, evidence=evidence,
        conflicts_with=tuple(_string_list(raw["conflicts_with"], path, "conflicts_with")),
    )
    if status == "active":
        _validate_active_review_gate(rule, path)
    return rule


def _parse_relationship(raw: dict[str, Any], path: str) -> ProductRelationship:
    required = {"id", "from_offering_id", "to_offering_id", "relationship_type", "review_state"}
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
    effective_from, effective_to = _date_range(raw, path)
    return ProductRelationship(
        id=_uuid(raw["id"], path, "id"),
        from_offering_id=from_id,
        to_offering_id=to_id,
        relationship_type=rel_type,
        effective_from=effective_from,
        effective_to=effective_to,
        review_state=review_state,
    )


def _assertion(raw: dict[str, Any], path: str) -> EvidenceAssertion:
    required = {"id", "source_policy_class", "url", "content_sha256", "retrieved_at", "confidence", "review_state", "reviews"}
    _require_exact_keys(raw, required, {"effective_from", "effective_to"}, path)
    source_class = _nonempty(raw["source_policy_class"], path, "source_policy_class")
    if source_class not in _SOURCE_CLASSES:
        raise CatalogLoadError(f"{path}: unsupported source_policy_class {source_class!r}")
    url = _nonempty(raw["url"], path, "url")
    parsed_url = urlparse(url)
    if parsed_url.scheme != "https" or not parsed_url.netloc or parsed_url.username or parsed_url.password:
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
    if review_state == "approved" and not reviews:
        raise CatalogLoadError(f"{path}: approved evidence requires a human review record")
    if review_state == "approved" and ("approved" not in decisions or "rejected" in decisions):
        raise CatalogLoadError(f"{path}: approved evidence requires only approving review decisions")
    if review_state == "rejected" and "rejected" not in decisions:
        raise CatalogLoadError(f"{path}: rejected evidence requires a rejecting review decision")
    return EvidenceAssertion(_uuid(raw["id"], path, "assertion.id"), source_class, url, digest,
                             retrieved_at, effective_from,
                             effective_to, confidence, review_state, reviews)


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
        raise CatalogLoadError(f"{path}: active benefit requires approved medium/high-confidence evidence")
    reviewers = {
        review.reviewer_id
        for assertion in active_evidence
        for review in assertion.reviews
        if review.decision == "approved"
    }
    required_reviewers = 2 if rule.review_tier in {"enhanced", "high_impact", "ambiguous"} else 1
    if len(reviewers) < required_reviewers:
        raise CatalogLoadError(
            f"{path}: active {rule.review_tier} benefit requires {required_reviewers} distinct approved human reviews"
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
            raise CatalogLoadError(f"benefit {rule.id}: conflicts_with must name other known benefits")
        for assertion in rule.evidence:
            if assertion.retrieved_at > release.generated_at:
                raise CatalogLoadError(f"benefit {rule.id}: evidence retrieval is after the release")
            if any(review.reviewed_at > release.generated_at for review in assertion.reviews):
                raise CatalogLoadError(f"benefit {rule.id}: review is after the release")
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
    _detect_cycle(dag_edges)


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


def _detect_cycle(adjacency: dict[str, list[str]]) -> None:
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
                        raise CatalogLoadError(
                            "relationship graph contains a cycle in renamed/legacy edges"
                        )
                    if color.get(neighbor, WHITE) == WHITE:
                        stack.append(neighbor)
            else:
                stack.pop()
                color[node] = BLACK
