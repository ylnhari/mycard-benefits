"""Validate the plain JSON research rescue before the candidate package is removed."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
BENEFIT_DIR = ROOT / "catalog" / "benefits"
SCHEMA_PATH = ROOT / "catalog" / "schema" / "rescued-benefit.schema.json"
EXPECTED_COUNT = 60
EXPECTED_SOURCE_URL_COUNT = 30
EXPECTED_CONTENT_SHA256_COUNT = 32
EXPECTED_STATES = {
    "verified": 1,
    "check_before_use": 53,
    "sources_differ": 6,
}
STATE_VALUES = set(EXPECTED_STATES)
SOURCE_POLICY_CLASSES = {
    "administering_terms",
    "issuer_document",
    "network_rule",
    "merchant_terms",
    "regulatory_context",
    "discovery_only",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
SOURCE_DIVERGENCE_EXCEPTION_DATE = "2026-08-10"
SOURCE_DIVERGENCE_EXCEPTIONS = {
    "indusind-legend-visa-bookmyshow-bogo.json": (
        f"{SOURCE_DIVERGENCE_EXCEPTION_DATE}: one provenance URL is retained; "
        "no alternative claim value was preserved"
    ),
    "indusind-legend-visa-signature-bookmyshow-bogo.json": (
        f"{SOURCE_DIVERGENCE_EXCEPTION_DATE}: one provenance URL is retained; "
        "no alternative claim value was preserved"
    ),
    "rbl-play-monthly-bookmyshow-movie-and-food-offer.json": (
        f"{SOURCE_DIVERGENCE_EXCEPTION_DATE}: one provenance URL is retained; "
        "no alternative claim value was preserved"
    ),
    "regalia-gold-accelerated-reward-points-at-designated-merchants.json": (
        f"{SOURCE_DIVERGENCE_EXCEPTION_DATE}: two provenance URLs are retained; "
        "no alternative claim value was preserved"
    ),
    "regalia-gold-reward-point-travel-and-cashback-redemption-limits.json": (
        f"{SOURCE_DIVERGENCE_EXCEPTION_DATE}: two provenance URLs are retained; "
        "no alternative claim value was preserved"
    ),
}


def _slug(value: str) -> str:
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def _read_schema() -> dict[str, object]:
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {SCHEMA_PATH}: {exc}") from exc
    if not isinstance(schema, dict):
        raise ValueError("rescue schema must be a JSON object")
    return schema


def _jsonschema_errors(record: object, schema: dict[str, object]) -> list[str]:
    """Require the checked-in JSON Schema validator instead of failing open."""
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError:
        return ["jsonschema dependency is unavailable; refusing to validate without it"]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [error.message for error in sorted(validator.iter_errors(record), key=str)]


def _fallback_schema_errors(record: object, schema: dict[str, object]) -> list[str]:
    """Small dependency-free check for the constraints used by this schema."""
    errors: list[str] = []
    if not isinstance(record, dict):
        return ["record is not an object"]
    required = schema.get("required", [])
    properties = schema.get("properties", {})
    if not isinstance(required, list) or not isinstance(properties, dict):
        return ["rescue schema has invalid top-level constraints"]
    missing = [key for key in required if key not in record]
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")
    unknown = sorted(set(record) - set(properties))
    if unknown:
        errors.append(f"unexpected fields: {', '.join(unknown)}")
    for key, value in record.items():
        if key not in properties:
            continue
        if key in {"id", "offering_id"}:
            try:
                UUID(value)
            except (AttributeError, ValueError, TypeError):
                errors.append(f"{key} is not a UUID")
        elif key in {"title", "benefit_type", "category"} and (
            not isinstance(value, str) or not value
        ):
            errors.append(f"{key} must be a non-empty string")
        elif key == "allowance" and not isinstance(value, dict):
            errors.append("allowance must be an object")
        elif key in {"eligibility", "conditions", "exclusions", "redemption_steps", "not_claimed"} and not isinstance(value, list):
            errors.append(f"{key} must be an array")
        elif key == "provider" and value is not None and (not isinstance(value, str) or not value):
            errors.append("provider must be null or a non-empty string")
        elif key in {"effective_from", "effective_to"} and value is not None and (
            not isinstance(value, str) or DATE_RE.fullmatch(value) is None
        ):
            errors.append(f"{key} must be null or YYYY-MM-DD")
        elif key == "end_date_known" and not isinstance(value, bool):
            errors.append("end_date_known must be boolean")
        elif key == "source_url":
            parsed = urlparse(value) if isinstance(value, str) else None
            if parsed is None or parsed.scheme != "https" or not parsed.hostname:
                errors.append("source_url must be an HTTPS URL")
        elif key == "source_policy_class" and value not in SOURCE_POLICY_CLASSES:
            errors.append("source_policy_class is not an allowed value")
        elif key == "content_sha256" and value is not None and (
            not isinstance(value, str) or SHA256_RE.fullmatch(value) is None
        ):
            errors.append("content_sha256 must be null or 64 lowercase hex characters")
        elif key == "state" and value not in STATE_VALUES:
            errors.append("state is not an allowed value")
    return errors


def _provenance_urls(record: dict[str, object]) -> set[str]:
    provenance = record.get("provenance")
    if not isinstance(provenance, list):
        return set()
    return {
        item["source_url"]
        for item in provenance
        if isinstance(item, dict) and isinstance(item.get("source_url"), str)
    }


def _source_divergence_failure(record: dict[str, object]) -> str | None:
    if record.get("state") != "sources_differ":
        return None
    provenance_urls = _provenance_urls(record)
    if len(provenance_urls) < 2:
        return "fewer than two distinct provenance source_url values"
    divergence = record.get("source_divergence")
    if not isinstance(divergence, list) or len(divergence) < 2:
        return "two or more distinct provenance URLs require source_divergence"
    divergence_urls = {
        item["source_url"]
        for item in divergence
        if isinstance(item, dict) and isinstance(item.get("source_url"), str)
    }
    if len(divergence_urls) != len(divergence):
        return "source_divergence entries must have distinct source_url values"
    if divergence_urls != provenance_urls:
        return "source_divergence URLs must equal the distinct provenance URLs"
    return None


def _validate_record(path: Path, record: object, schema: dict[str, object]) -> None:
    errors = _jsonschema_errors(record, schema) or _fallback_schema_errors(record, schema)
    if errors:
        raise ValueError(f"{path.name}: schema validation failed: {'; '.join(errors)}")
    if not isinstance(record, dict):
        raise ValueError(f"{path.name}: record is not an object")
    expected_slug = _slug(str(record["title"]))
    if path.stem != expected_slug and not path.stem.startswith(f"{expected_slug}-"):
        raise ValueError(f"{path.name}: filename is not a slug of the title")
    if record["end_date_known"] != (record["effective_to"] is not None):
        raise ValueError(f"{path.name}: end_date_known disagrees with effective_to")
    source_url = record["source_url"]
    provenance_urls = _provenance_urls(record)
    if not isinstance(source_url, str) or source_url not in provenance_urls:
        raise ValueError(
            f"{path.name}: top-level source_url is not present in the record provenance"
        )


def validate() -> tuple[int, int, Counter[str]]:
    schema = _read_schema()
    paths = sorted(BENEFIT_DIR.glob("*.json"))
    if len(paths) != EXPECTED_COUNT:
        raise ValueError(f"expected {EXPECTED_COUNT} benefit files, found {len(paths)}")
    records: list[dict[str, object]] = []
    for path in paths:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"{path.name}: invalid JSON: {exc}") from exc
        _validate_record(path, record, schema)
        assert isinstance(record, dict)
        records.append(record)
    ids = [record["id"] for record in records]
    if len(set(ids)) != len(ids):
        raise ValueError("benefit IDs are not unique")
    titles = [record["title"] for record in records]
    if len(set(titles)) != len(titles):
        raise ValueError("benefit titles are not unique")
    source_urls = {record["source_url"] for record in records}
    if len(source_urls) != EXPECTED_SOURCE_URL_COUNT:
        raise ValueError(
            f"expected {EXPECTED_SOURCE_URL_COUNT} distinct source_url values, found {len(source_urls)}"
        )
    content_hashes = {
        record["content_sha256"]
        for record in records
        if isinstance(record["content_sha256"], str)
    }
    if len(content_hashes) != EXPECTED_CONTENT_SHA256_COUNT:
        raise ValueError(
            "expected "
            f"{EXPECTED_CONTENT_SHA256_COUNT} distinct content_sha256 values, "
            f"found {len(content_hashes)}"
        )
    states = Counter(str(record["state"]) for record in records)
    if dict(states) != EXPECTED_STATES:
        raise ValueError(f"expected state counts {EXPECTED_STATES}, found {dict(states)}")
    source_divergence_failures: dict[str, str] = {}
    for path, record in zip(paths, records, strict=True):
        failure = _source_divergence_failure(record)
        if failure is not None:
            source_divergence_failures[path.name] = failure
    expected_exceptions = set(SOURCE_DIVERGENCE_EXCEPTIONS)
    actual_failures = set(source_divergence_failures)
    if actual_failures != expected_exceptions:
        details = "; ".join(
            f"{name}: {source_divergence_failures.get(name, 'exception no longer failing')}"
            for name in sorted(actual_failures | expected_exceptions)
        )
        raise ValueError(
            "sources_differ exception set drifted; expected "
            f"{sorted(expected_exceptions)}, found {sorted(actual_failures)}; {details}"
        )
    tata = next(
        record
        for record in records
        if record["title"] == "Tata Neu Infinity domestic lounge voucher milestone"
    )
    not_claimed = tata.get("not_claimed")
    if not isinstance(not_claimed, list):
        allowance = tata.get("allowance")
        not_claimed = allowance.get("not_claimed") if isinstance(allowance, dict) else None
    if not isinstance(not_claimed, list) or "unconditional 8 visits per year" not in not_claimed:
        raise ValueError("Tata lounge record lost its not_claimed safeguard")
    return len(records), len(source_urls), states


def main() -> int:
    print(f"Known source-divergence exceptions: {len(SOURCE_DIVERGENCE_EXCEPTIONS)}")
    try:
        count, source_count, states = validate()
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Validated {count} rescued benefits")
    print(f"Distinct source_url values: {source_count}")
    print(f"Distinct content_sha256 values: {EXPECTED_CONTENT_SHA256_COUNT}")
    print(f"State counts: {dict(states)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
