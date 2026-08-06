"""Source admission and network-boundary checks.

This module deliberately does not perform network I/O.  A future runner must
call these guards before every request and after every response, including
redirects.  Keeping the policy independent makes it testable without touching
the internet.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import IntEnum, StrEnum
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlsplit, urlunsplit


class AdmissionError(ValueError):
    """An admission record is malformed or cannot authorize automation."""


class RetrievalBlocked(RuntimeError):
    """Retrieval must stop and await human review; callers must not retry."""


class SourceTier(IntEnum):
    ADMINISTERING_TERMS = 1
    ISSUER_DOCUMENT = 2
    NETWORK_RULE = 3
    MERCHANT_TERMS = 4
    REGULATORY_CONTEXT = 5
    DISCOVERY_ONLY = 6


class IngestionClass(StrEnum):
    LICENSED = "A"
    PUBLIC_PERMITTED = "B"
    MANUAL_ONLY = "C"
    EXCLUDED = "D"


class AdmissionStatus(StrEnum):
    CANDIDATE = "candidate"
    APPROVED = "approved"
    SUSPENDED = "suspended"
    RETIRED = "retired"


_HASH = re.compile(r"^[0-9a-f]{64}$")
_BLOCK_TEXT = re.compile(
    rb"(?:captcha|verify\s+(?:that\s+)?you\s+are\s+human|sign\s*in|log\s*in|access\s+denied)",
    re.IGNORECASE,
)
_BLOCK_STATUSES: Final = frozenset({401, 403, 407, 409, 423, 429})
_SAFE_REQUEST_HEADERS: Final = frozenset(
    {"accept", "accept-language", "if-modified-since", "if-none-match", "user-agent"}
)
_MAX_RESPONSE_BYTES: Final = 16 * 1024 * 1024


@dataclass(frozen=True)
class SourceAdmission:
    id: str
    name: str
    tier: SourceTier
    ingestion_class: IngestionClass
    status: AdmissionStatus
    url_prefixes: tuple[str, ...]
    cadence_seconds: int
    max_age_days: int
    time_limited: bool
    robots_url: str
    robots_sha256: str
    terms_url: str
    terms_sha256: str
    reviewed_at: date
    human_reviewer_id: str | None

    @property
    def allows_automation(self) -> bool:
        return (
            self.status is AdmissionStatus.APPROVED
            and self.ingestion_class in {IngestionClass.LICENSED, IngestionClass.PUBLIC_PERMITTED}
            and self.human_reviewer_id is not None
        )

    def authorize_url(self, value: str) -> str:
        """Return a canonical admitted URL or fail without making a request."""
        if not self.allows_automation:
            raise AdmissionError("source is not approved for automated retrieval")
        target = _canonical_public_url(value)
        if not any(_within_prefix(target, prefix) for prefix in self.url_prefixes):
            raise AdmissionError("URL is outside the admitted source scope")
        return target


@dataclass(frozen=True)
class EvidenceCandidate:
    id: str
    admission_id: str
    source_url: str
    retrieved_at: datetime
    content_sha256: str
    content_type: str
    review_state: str = "needs_review"

    @classmethod
    def from_public_response(
        cls,
        admission: SourceAdmission,
        *,
        url: str,
        body: bytes,
        content_type: str,
        retrieved_at: datetime | None = None,
    ) -> EvidenceCandidate:
        canonical = admission.authorize_url(url)
        if len(body) > _MAX_RESPONSE_BYTES:
            raise RetrievalBlocked("response exceeded the admitted safety limit")
        return cls(
            id=str(uuid.uuid4()),
            admission_id=admission.id,
            source_url=canonical,
            retrieved_at=retrieved_at or datetime.now(UTC),
            content_sha256=hashlib.sha256(body).hexdigest(),
            content_type=content_type.split(";", 1)[0].strip().lower(),
        )


def load_admission(path: str | Path) -> SourceAdmission:
    """Load one reviewed JSON admission record with strict validation."""
    try:
        raw: Any = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdmissionError("cannot read source admission") from exc
    if not isinstance(raw, dict):
        raise AdmissionError("source admission must be an object")
    required = {
        "id",
        "name",
        "tier",
        "ingestion_class",
        "status",
        "url_prefixes",
        "cadence_seconds",
        "max_age_days",
        "time_limited",
        "robots_url",
        "robots_sha256",
        "terms_url",
        "terms_sha256",
        "reviewed_at",
        "human_reviewer_id",
    }
    if set(raw) != required:
        raise AdmissionError("source admission fields do not match the schema")
    try:
        prefixes_raw = raw["url_prefixes"]
        if not isinstance(prefixes_raw, list) or not prefixes_raw:
            raise AdmissionError("url_prefixes must be a non-empty list")
        prefixes = tuple(_canonical_public_url(item) for item in prefixes_raw)
        admission = SourceAdmission(
            id=str(uuid.UUID(_string(raw["id"], "id"))),
            name=_string(raw["name"], "name"),
            tier=SourceTier(_strict_int(raw["tier"], "tier")),
            ingestion_class=IngestionClass(_string(raw["ingestion_class"], "ingestion_class")),
            status=AdmissionStatus(_string(raw["status"], "status")),
            url_prefixes=prefixes,
            cadence_seconds=_strict_int(raw["cadence_seconds"], "cadence_seconds"),
            max_age_days=_strict_int(raw["max_age_days"], "max_age_days"),
            time_limited=_strict_bool(raw["time_limited"], "time_limited"),
            robots_url=_canonical_public_url(raw["robots_url"]),
            robots_sha256=_digest(raw["robots_sha256"], "robots_sha256"),
            terms_url=_canonical_public_url(raw["terms_url"]),
            terms_sha256=_digest(raw["terms_sha256"], "terms_sha256"),
            reviewed_at=date.fromisoformat(_string(raw["reviewed_at"], "reviewed_at")),
            human_reviewer_id=(
                _string(raw["human_reviewer_id"], "human_reviewer_id")
                if raw["human_reviewer_id"] is not None
                else None
            ),
        )
    except (TypeError, ValueError) as exc:
        if isinstance(exc, AdmissionError):
            raise
        raise AdmissionError("source admission contains an invalid value") from exc
    _validate_admission(admission)
    return admission


def prepare_public_request(
    admission: SourceAdmission,
    url: str,
    *,
    headers: dict[str, str] | None = None,
) -> tuple[str, dict[str, str]]:
    """Validate an anonymous GET request and return normalized safe headers."""
    target = admission.authorize_url(url)
    prepared = {
        "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9",
        "User-Agent": "MyCardBenefits/0.1 (+public-benefits-research; respectful-fetcher)",
    }
    for name, value in (headers or {}).items():
        if name.lower() not in _SAFE_REQUEST_HEADERS:
            raise AdmissionError("request header is not allowed for public retrieval")
        if not isinstance(value, str) or "\r" in value or "\n" in value:
            raise AdmissionError("request header value is invalid")
        prepared[name] = value
    return target, prepared


def assess_public_response(
    *,
    status_code: int,
    content_type: str,
    body_preview: bytes = b"",
    content_length: int | None = None,
) -> None:
    """Stop on access challenges, unsafe types, or unexpectedly large content."""
    if status_code in _BLOCK_STATUSES:
        raise RetrievalBlocked("source returned an access or rate-limit challenge")
    if 300 <= status_code < 400:
        raise RetrievalBlocked("redirect requires a fresh admitted-URL policy check")
    if status_code < 200 or status_code >= 300:
        raise RetrievalBlocked("source returned an unexpected response")
    media_type = content_type.split(";", 1)[0].strip().lower()
    if media_type not in {"text/html", "application/xhtml+xml", "application/pdf"}:
        raise RetrievalBlocked("source returned an unsupported content type")
    if content_length is not None and (content_length < 0 or content_length > _MAX_RESPONSE_BYTES):
        raise RetrievalBlocked("response exceeded the admitted safety limit")
    if _BLOCK_TEXT.search(body_preview[:8192]):
        raise RetrievalBlocked("source presented a login, CAPTCHA, or access challenge")


def _validate_admission(admission: SourceAdmission) -> None:
    if admission.cadence_seconds < 900:
        raise AdmissionError("cadence must be at least 900 seconds")
    max_allowed_age = 30 if admission.time_limited else 90
    if not 1 <= admission.max_age_days <= max_allowed_age:
        raise AdmissionError("max_age_days exceeds the source freshness policy")
    for prefix in admission.url_prefixes:
        if not _same_origin(prefix, admission.robots_url):
            raise AdmissionError("robots_url must share an admitted origin")
    if admission.status is AdmissionStatus.APPROVED and not admission.human_reviewer_id:
        raise AdmissionError("approved sources require a human reviewer identity")
    if (
        admission.ingestion_class in {IngestionClass.MANUAL_ONLY, IngestionClass.EXCLUDED}
        and admission.status is AdmissionStatus.APPROVED
    ):
        raise AdmissionError("manual-only or excluded sources cannot authorize automation")


def _canonical_public_url(value: Any) -> str:
    raw = _string(value, "URL")
    parsed = urlsplit(raw)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise AdmissionError("source URLs must be anonymous HTTPS URLs")
    if parsed.port not in (None, 443):
        raise AdmissionError("source URLs may not use a nonstandard port")
    host = parsed.hostname.rstrip(".").lower()
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if host == "localhost" or host.endswith(".localhost") or (address and not address.is_global):
        raise AdmissionError("source URLs may not target local or private networks")
    path = parsed.path or "/"
    return urlunsplit(("https", host, path, parsed.query, ""))


def _within_prefix(target: str, prefix: str) -> bool:
    target_parts = urlsplit(target)
    prefix_parts = urlsplit(prefix)
    prefix_path = prefix_parts.path.rstrip("/") or "/"
    target_path = target_parts.path.rstrip("/") or "/"
    return (
        target_parts.scheme == prefix_parts.scheme
        and target_parts.netloc == prefix_parts.netloc
        and (target_path == prefix_path or target_path.startswith(prefix_path.rstrip("/") + "/"))
    )


def _same_origin(left: str, right: str) -> bool:
    left_parts = urlsplit(left)
    right_parts = urlsplit(right)
    return (left_parts.scheme, left_parts.netloc) == (right_parts.scheme, right_parts.netloc)


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AdmissionError(f"{field} must be a non-empty string")
    return value.strip()


def _strict_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AdmissionError(f"{field} must be an integer")
    return int(value)


def _strict_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise AdmissionError(f"{field} must be a boolean")
    return value


def _digest(value: Any, field: str) -> str:
    digest = _string(value, field)
    if not _HASH.fullmatch(digest):
        raise AdmissionError(f"{field} must be a lowercase SHA-256 digest")
    return digest
