"""Loopback-local, read-only private card envelope API."""

from __future__ import annotations

import json
import secrets
import threading
import time
import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from .. import data_location
from ..catalog.loader import CatalogLoadError, load_catalog
from ..config import remember_data_dir
from .core import (
    CardLifecycle,
    ChildRecordKind,
    ChildRecordLifecycle,
    VaultAccessError,
    VaultConflictError,
    VaultError,
    VaultSession,
    VaultStore,
)
from .keyring_store import (
    get_device_key,
    keyring_account,
    load_keyring,
    set_device_key,
    set_keyring_password,
)
from .personal_state import AttemptOutcome
from .protected import AuditLog

CardReader = Callable[[], tuple[dict[str, Any], ...]]

_EXPIRING_SOON_WINDOW_DAYS = 30
_NO_STORE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}
_DETAIL_MAX_FAILURES = 5
_DETAIL_LOCKOUT_SECONDS = 60.0
_DETAIL_DELAY_BASE_SECONDS = 0.25
_DETAIL_DELAY_MAX_SECONDS = 4.0
_KEYRING_REMEMBER_WARNING = (
    "The vault is unlocked, but the operating-system keyring could not save the passphrase. "
    "You can unlock with the passphrase next time."
)
_LOCATION_REMEMBER_WARNING = (
    "The vault is unlocked, but this selected data location could not be remembered. "
    "Use the same data-directory selection next time."
)
_DETAIL_SESSION_COOKIE = "mycard_detail_session"


class VaultUnavailable(Exception):
    """A classified, non-sensitive reason the private card list is unavailable."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class _BrowserVaultSession:
    session: VaultSession
    created_at: float
    last_activity: float


@dataclass
class _DetailCredentialAttempts:
    failures: int = 0
    locked_until: float = 0.0


class _PassphraseUnlockManager:
    """Process-local browser sessions; nothing here is persisted or serialized."""

    def __init__(self, vault_path: Path, *, idle_seconds: float = 300.0, absolute_seconds: float = 900.0) -> None:
        self._vault_path = vault_path
        self._idle_seconds = idle_seconds
        self._absolute_seconds = absolute_seconds
        self._sessions: dict[str, _BrowserVaultSession] = {}
        self._expired: set[str] = set()
        self._bootstrap_tokens: set[str] = set()
        self._attempts: list[float] = []
        self._detail_attempts = _DetailCredentialAttempts()
        self._lock = threading.RLock()

    def bootstrap(self) -> str:
        with self._lock:
            token = secrets.token_urlsafe(32)
            self._bootstrap_tokens.add(token)
            return token

    def consume_bootstrap(self, token: str) -> bool:
        with self._lock:
            if token not in self._bootstrap_tokens:
                return False
            self._bootstrap_tokens.remove(token)
            return True

    def rate_limited(self) -> bool:
        now = time.monotonic()
        with self._lock:
            self._attempts = [stamp for stamp in self._attempts if now - stamp < 60.0]
            return len(self._attempts) >= 5

    def record_attempt(self) -> None:
        with self._lock:
            self._attempts.append(time.monotonic())

    def detail_before_attempt(self) -> tuple[float, float]:
        """Return the enforced backoff and lockout remaining for detail auth."""
        now = time.monotonic()
        with self._lock:
            retry_after = max(0.0, self._detail_attempts.locked_until - now)
            if retry_after:
                return 0.0, retry_after
            failures = self._detail_attempts.failures
            delay = min(
                _DETAIL_DELAY_BASE_SECONDS * (2 ** max(failures - 1, 0)),
                _DETAIL_DELAY_MAX_SECONDS,
            )
            return delay, 0.0

    def detail_failure(self) -> float:
        """Record one failed code check and return any newly applied lockout."""
        now = time.monotonic()
        with self._lock:
            self._detail_attempts.failures += 1
            if self._detail_attempts.failures >= _DETAIL_MAX_FAILURES:
                self._detail_attempts.locked_until = now + _DETAIL_LOCKOUT_SECONDS
                return _DETAIL_LOCKOUT_SECONDS
            return 0.0

    def detail_success(self) -> None:
        with self._lock:
            self._detail_attempts = _DetailCredentialAttempts()

    def create(self, vault_session: VaultSession) -> str:
        now = time.monotonic()
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[token] = _BrowserVaultSession(vault_session, now, now)
        return token

    def get(self, token: str | None) -> VaultSession | None:
        if not token:
            return None
        now = time.monotonic()
        with self._lock:
            item = self._sessions.get(token)
            if item is None:
                return None
            if now - item.last_activity > self._idle_seconds or now - item.created_at > self._absolute_seconds or item.session.locked:
                item.session.lock()
                del self._sessions[token]
                self._expired.add(token)
                return None
            item.last_activity = now
            return item.session

    def expired(self, token: str | None) -> bool:
        if not token:
            return False
        with self._lock:
            return token in self._expired

    def lock(self, token: str | None) -> None:
        if not token:
            return
        with self._lock:
            item = self._sessions.pop(token, None)
            if item is not None:
                item.session.lock()


VAULT_DIAGNOSTIC_MESSAGES: dict[str, str] = {
    "demo": "Private card list is switched off in demo mode",
    "vault_missing": "No vault exists in this app's data folder yet",
    "passphrase_only": "The vault exists but was created without the operating-system keyring",
    "wrong_data_dir": "A keyring passphrase is stored for this data folder but no vault file is here",
    "locked": "The vault file exists but could not be opened",
    "keyring_unavailable": "The operating-system keyring could not be read",
    "generic": "Private card list unavailable",
    "expired": "The protected browser vault session expired and was locked",
}


def _safe_diagnostic_code(code: str) -> str:
    """Return a public diagnostic code without reflecting an exception value."""
    return code if code in VAULT_DIAGNOSTIC_MESSAGES else "generic"


def _expiry_signal_from_date(expiry_date: str, *, today: date) -> str:
    """Bucket a private expiry date into a coarse signal; the exact date never
    crosses this boundary. `today` is a `datetime.date`."""
    try:
        parsed = datetime.strptime(expiry_date, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("expiry_date is invalid") from None
    if parsed < today:
        return "expired"
    if parsed <= today + timedelta(days=_EXPIRING_SOON_WINDOW_DAYS):
        return "expiring_soon"
    return "active"


class _PrivateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PrivateChildRecordSummary(_PrivateModel):
    child_id: str
    parent_card_id: str
    kind: ChildRecordKind
    lifecycle: ChildRecordLifecycle
    created_at: str
    updated_at: str
    expiry_signal: Literal["expired", "expiring_soon", "active"] | None = None

    @field_validator("child_id", "parent_card_id")
    @classmethod
    def _validate_identifier(cls, value: str) -> str:
        uuid.UUID(value)
        return value

    @model_validator(mode="before")
    @classmethod
    def _derive_expiry_signal(cls, data: Any) -> Any:
        """Replace any incoming `expiry_date` with a bounded signal before this
        model's own field/extra-field validation runs, so an exact date can
        never reach a validated instance, let alone the HTTP response."""
        if not isinstance(data, dict) or "expiry_date" not in data:
            return data
        data = dict(data)
        expiry_date = data.pop("expiry_date")
        if expiry_date is not None:
            if not isinstance(expiry_date, str):
                raise ValueError("expiry_date is invalid")
            data["expiry_signal"] = _expiry_signal_from_date(
                expiry_date, today=datetime.now(UTC).date()
            )
        return data


class PrivateCardSummary(_PrivateModel):
    card_id: str
    offering_id: str
    lifecycle: str
    created_at: str
    updated_at: str
    masked_last4: str | None = Field(default=None, pattern=r"^•••• [0-9]{4}$")
    replacement_card_id: str | None = None
    child_records: list[PrivateChildRecordSummary] = Field(default_factory=list)

    @field_validator("card_id")
    @classmethod
    def _validate_card_id(cls, value: str) -> str:
        uuid.UUID(value)
        return value

    @model_validator(mode="after")
    def _validate_child_record_linkage(self) -> PrivateCardSummary:
        seen: set[str] = set()
        for child in self.child_records:
            if child.parent_card_id != self.card_id:
                raise ValueError("child record parent_card_id does not match its card")
            if child.child_id in seen:
                raise ValueError("duplicate child record id")
            seen.add(child.child_id)
        return self


class PrivateCardList(_PrivateModel):
    cards: list[PrivateCardSummary]
    lifecycle_counts: dict[str, int]

    @model_validator(mode="after")
    def _validate_unique_card_and_child_ids(self) -> PrivateCardList:
        """Reject collisions across the complete protected response, not only
        within one card. A future reader must not be able to alias two card or
        child records into a single browser payload."""
        card_ids: set[str] = set()
        child_ids: set[str] = set()
        for card in self.cards:
            if card.card_id in card_ids:
                raise ValueError("duplicate card id")
            card_ids.add(card.card_id)
            for child in card.child_records:
                if child.child_id in child_ids:
                    raise ValueError("duplicate child record id")
                child_ids.add(child.child_id)
        return self


class OwnedDiscoveryCard(_PrivateModel):
    """A bounded public join for benefit-first discovery."""

    local_card_ref: str
    public_offering_id: str | None = None
    public_display: str | None = None
    public_variant: str | None = None
    lifecycle: str
    catalog_match: Literal["matched", "unmatched"]
    reasons: list[str]
    rule_ids: list[str]


class OwnedDiscoveryList(_PrivateModel):
    cards: list[OwnedDiscoveryCard]


class ProtectedRequest(_PrivateModel):
    passphrase: str = Field(min_length=12, max_length=1024)


class DeviceActionRequest(_PrivateModel):
    """Optional reauthentication for actions backed by the device-held key."""

    passphrase: str | None = Field(default=None, min_length=12, max_length=1024)


class AddCardRequest(DeviceActionRequest):
    offering_id: str
    secret_fields: dict[str, str] = Field(default_factory=dict)
    lifecycle: CardLifecycle = CardLifecycle.ACTIVE


class EditCardRequest(DeviceActionRequest):
    changes: dict[str, str]


class TransitionRequest(DeviceActionRequest):
    lifecycle: CardLifecycle


class DestructiveRequest(DeviceActionRequest):
    confirmation: str


class RevealRequest(_PrivateModel):
    mode: Literal["create", "reuse"] = "reuse"
    credential_type: Literal["pin", "passphrase"] | None = None
    credential: StrictStr | None = Field(default=None, max_length=1024)
    confirm: StrictStr | None = Field(default=None, max_length=1024)
    # Kept only to reject the retired contract without reflecting its value.
    passphrase: StrictStr | None = Field(default=None, min_length=12, max_length=1024)
    field: StrictStr | None = None


class ProtectedResult(_PrivateModel):
    card_id: str | None = None
    successor_card_id: str | None = None
    erase_prompt: bool = False
    backup_warning: str | None = None
    action_authorized: bool = False


class RevealResult(_PrivateModel):
    card_number: StrictStr
    # Optional: a card may have a number stored without an expiry. When this was
    # required, such a card produced a validation error rather than a reveal,
    # and the browser saw a failure carrying no code to explain itself.
    expiry: StrictStr | None = None
    cvv: StrictStr | None = None


class ManualAggregateRequest(ProtectedRequest):
    rule_id: str
    rule_version: StrictInt
    amount: str
    currency: str
    period: str


class ClearAggregateRequest(ProtectedRequest):
    rule_id: str
    rule_version: StrictInt


class AttemptContractRequest(ProtectedRequest):
    idempotency_key: StrictStr = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    expected_private_state_revision: StrictStr = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )


class AttemptCreateRequest(AttemptContractRequest):
    rule_id: str
    rule_version: StrictInt
    outcome: AttemptOutcome
    note: str | None = None


class AttemptUpdateRequest(AttemptContractRequest):
    outcome: AttemptOutcome
    note: str | None = None


class AttemptDeleteRequest(AttemptContractRequest):
    pass


class ManualAggregateResponse(_PrivateModel):
    aggregate_id: str
    card_id: str
    rule_id: str
    rule_version: int
    amount: str
    currency: str
    period: str
    created_at: str
    updated_at: str


class PrivateAttemptResponse(_PrivateModel):
    attempt_id: str
    card_id: str
    rule_id: str
    rule_version: int
    outcome: AttemptOutcome
    note: str | None = None
    created_at: str
    updated_at: str


class PrivateAttemptMutationResponse(PrivateAttemptResponse):
    private_state_revision: StrictStr = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )


class PrivateAttemptDeleteResponse(_PrivateModel):
    deleted: StrictStr
    private_state_revision: StrictStr = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )


class PrivateStateResponse(_PrivateModel):
    aggregates: list[ManualAggregateResponse]
    attempts: list[PrivateAttemptResponse]
    private_state_revision: StrictStr = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$"
    )


_RAW_BROWSER_HEADER_NAMES = (
    "host",
    "origin",
    "sec-fetch-mode",
    "sec-fetch-site",
    "x-csrf-token",
    "content-type",
    "content-length",
    "transfer-encoding",
)
# Headers a reverse proxy adds to describe the hop it performed. They are
# ignored here, deliberately and by name, rather than rejected.
#
# Rejecting them broke every protected action reached through the owner's
# gateway. That gateway presents a genuine loopback request to this process and
# then annotates it with X-Forwarded-Host and X-Forwarded-Proto so a backend can
# still learn the external origin the standard way. Refusing the request because
# it carried that annotation meant the owner could browse their cards from their
# phone but could never open one, and the refusal surfaced as a bare string with
# no error code, so the screen could only say something had gone wrong.
#
# Ignoring them is safe because no decision in this module reads them. Host,
# Origin, the Fetch Metadata pair and the CSRF token are what admit a request,
# and all four are checked against the configured loopback listener. A page on
# another origin cannot reach these routes by adding one of these headers: doing
# so from script forces a CORS preflight this application does not answer, and
# its Sec-Fetch-Site would not be same-origin regardless. The rule that matters
# is not that these headers are absent, but that they are never consulted —
# which tests/test_protected_flow_routes.py and
# tests/test_gateway_protected_actions.py pin.
_FORWARDED_HEADER_NAMES: set[str] = set()


def _raw_browser_header_values(request: Request) -> dict[str, list[str]]:
    """Return security-sensitive headers without HTTP library normalization.

    ASGI exposes one ``(name, value)`` item for every received header.  Do not
    use ``request.headers`` for protected routes: it can conceal duplicate
    fields by choosing or joining a value before this boundary sees it.
    """
    values: dict[str, list[str]] = {name: [] for name in _RAW_BROWSER_HEADER_NAMES}
    for raw_name, raw_value in request.scope.get("headers", []):
        name = raw_name.decode("latin-1")
        lower_name = name.lower()
        if lower_name in values:
            # ASGI servers must lowercase names.  A non-conforming adapter
            # must not turn case differences into an alternate security path.
            if name != lower_name:
                raise HTTPException(status_code=403, detail="protected browser action rejected")
            values[lower_name].append(raw_value.decode("latin-1"))
        elif lower_name in _FORWARDED_HEADER_NAMES:
            raise HTTPException(status_code=403, detail="protected browser action rejected")
    return values


def _check_browser_headers(
    *,
    request: Request,
    port: int,
    require_origin: bool = True,
    require_fetch_metadata: bool = True,
) -> dict[str, list[str]]:
    """Validate browser headers before any protected action."""
    expected_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    values = _raw_browser_header_values(request)
    # Fetch Metadata is always verified when sent, and demanded only where the
    # caller can be relied on to send it. Browsers attach Sec-Fetch-* solely to
    # potentially trustworthy origins, which over plain HTTP means loopback and
    # nothing else. Reaching MyCard through the owner's gateway puts the page on
    # the machine's network address instead, so no Sec-Fetch header arrives at
    # all, and demanding one refused every protected action from their phone
    # while the same action worked on the machine itself.
    #
    # Callers that only ever run on loopback keep the stricter rule; the unlock
    # routes do, because the browser reaches them before any gateway hop and
    # they are the ones that open the vault. A duplicate is refused either way:
    # what must never happen is two conflicting values letting a caller pick
    # which one is read.
    fetch_metadata_counts = [len(values[name]) for name in ("sec-fetch-mode", "sec-fetch-site")]
    if len(values["host"]) != 1 or any(count > 1 for count in fetch_metadata_counts):
        raise HTTPException(status_code=403, detail="protected browser action rejected")
    if require_fetch_metadata and any(count != 1 for count in fetch_metadata_counts):
        raise HTTPException(status_code=403, detail="protected browser action rejected")
    if len(values["origin"]) != (1 if require_origin else min(1, len(values["origin"]))):
        raise HTTPException(status_code=403, detail="protected browser action rejected")
    if values["host"][0] not in expected_hosts:
        raise HTTPException(status_code=403, detail="protected browser action rejected")
    # When the browser did send them, they must still say same-origin. This is
    # what stops a cross-site request that happens to guess the rest.
    if values["sec-fetch-site"] and values["sec-fetch-site"][0] != "same-origin":
        raise HTTPException(status_code=403, detail="protected browser action rejected")
    if values["sec-fetch-mode"] and values["sec-fetch-mode"][0] != "cors":
        raise HTTPException(status_code=403, detail="protected browser action rejected")
    origin = values["origin"][0] if values["origin"] else None
    if origin is not None:
        try:
            parsed = urlsplit(origin)
            valid = (
                parsed.scheme == "http" and parsed.username is None and parsed.password is None
                and parsed.path in {"", "/"} and not parsed.query and not parsed.fragment
                and parsed.hostname in {"127.0.0.1", "localhost"} and parsed.port == port
            )
        except ValueError:
            valid = False
        if not valid:
            raise HTTPException(status_code=403, detail="protected browser action rejected")
    return values


def _require_exact_origin_match(values: dict[str, list[str]]) -> None:
    """Keep an explicitly supplied Origin tied to the received loopback Host."""
    origins = values["origin"]
    if origins and origins[0] != f"http://{values['host'][0]}":
        raise HTTPException(status_code=403, detail="protected browser action rejected")


def _single_csrf_token(values: dict[str, list[str]]) -> str:
    """Require exactly one raw, unjoined CSRF header value."""
    tokens = values["x-csrf-token"]
    if len(tokens) != 1 or not tokens[0] or "," in tokens[0]:
        raise HTTPException(status_code=403, detail="protected browser action rejected")
    return tokens[0]


def _validated_unlock_content_length(values: dict[str, list[str]]) -> int | None:
    """Validate exact JSON framing before a request body is received."""
    media_types = values["content-type"]
    if len(media_types) != 1 or media_types[0] != "application/json":
        raise HTTPException(status_code=415, detail="protected request rejected")
    lengths = values["content-length"]
    if len(lengths) > 1:
        raise HTTPException(status_code=413, detail="protected request rejected")
    if not lengths:
        return None
    length = lengths[0]
    if not length.isascii() or not length.isdecimal():
        raise HTTPException(status_code=413, detail="protected request rejected")
    declared = int(length)
    if declared > 4096:
        raise HTTPException(status_code=413, detail="protected request rejected")
    return declared


def _reject_ambiguous_optional_media(values: dict[str, list[str]]) -> None:
    """A bodyless protected route still rejects duplicate media framing."""
    if len(values["content-type"]) > 1 or any("," in value for value in values["content-type"]):
        raise HTTPException(status_code=415, detail="protected request rejected")
    if len(values["content-length"]) > 1:
        raise HTTPException(status_code=413, detail="protected request rejected")


def _check_request_security(
    *,
    request: Request,
    port: int,
    expected_csrf_token: str,
) -> None:
    """Enforce the configured loopback origin on every protected mutation.

    Browsers normally send Origin, and Fetch Metadata alongside it when the page
    is on a trustworthy origin. Either may legitimately be absent — reaching the
    app through the owner's gateway puts the page on a plain-HTTP network
    address, where a browser sends neither. What is never optional is the
    synchronizer token together with the exact configured loopback Host, and
    when Origin or Fetch Metadata is present it must agree with them.
    """
    values = _check_browser_headers(
        request=request, port=port, require_origin=False, require_fetch_metadata=False
    )
    _reject_ambiguous_optional_media(values)
    expected_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    host = values["host"][0]
    origin = values["origin"][0] if values["origin"] else None
    sec_fetch_mode = values["sec-fetch-mode"][0] if values["sec-fetch-mode"] else None
    sec_fetch_site = values["sec-fetch-site"][0] if values["sec-fetch-site"] else None
    csrf_token = _single_csrf_token(values)

    # Absent Fetch Metadata is accepted; contradictory Fetch Metadata is not.
    if (
        host not in expected_hosts
        or (sec_fetch_site is not None and sec_fetch_site != "same-origin")
        or (sec_fetch_mode is not None and sec_fetch_mode != "cors")
    ):
        raise HTTPException(status_code=403, detail="protected browser action rejected")

    if origin:
        try:
            parsed = urlsplit(origin)
            origin_host = parsed.hostname
            origin_port = parsed.port
        except ValueError:
            raise HTTPException(
                status_code=403, detail="protected browser action rejected"
            ) from None
        # Keep the browser path tied to the actual loopback listener.  Parsing
        # also rejects lookalike origins with credentials, paths, or a wrong
        # scheme that a string-prefix check could accidentally accept.
        if (
            parsed.scheme != "http"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or origin_host not in {"127.0.0.1", "localhost"}
            or origin_port != port
        ):
            raise HTTPException(status_code=403, detail="protected browser action rejected")
    if not secrets.compare_digest(csrf_token, expected_csrf_token):
        raise HTTPException(status_code=403, detail="protected browser action rejected")


def _open_session(
    vault_path: Path,
    passphrase: str,
    *,
    audit_log: AuditLog | None = None,
) -> VaultSession:
    try:
        return VaultStore(vault_path, audit_log=audit_log).open(passphrase)
    except VaultError:
        raise HTTPException(status_code=401, detail="reauthentication failed") from None


def _open_device_action_session(
    vault_path: Path,
    data_dir: Path,
    *,
    audit_log: AuditLog | None = None,
) -> tuple[VaultSession, str]:
    """Open a vault action with its local device-held key.

    The key remains inside this process and is used only as the existing vault
    reauthentication value. It is never returned through the HTTP boundary.
    """
    session: VaultSession | None = None
    device_key: str | None = None
    try:
        try:
            device_key = get_device_key(vault_path, data_dir, keyring_loader=load_keyring)
        except VaultError:
            # A fresh vault can still bootstrap its guarded local fallback.
            device_key = None
        session = _open_or_bootstrap_device_session(vault_path, data_dir, audit_log=audit_log)
        if device_key is None:
            try:
                device_key = get_device_key(vault_path, data_dir, keyring_loader=load_keyring)
            except (VaultError, data_location.DataLocationError):
                raise VaultUnavailable("keyring_unavailable") from None
        if device_key is None:
            raise VaultUnavailable("passphrase_only")
        return session, device_key
    except VaultUnavailable as exc:
        if session is not None:
            session.lock()
        code = _safe_diagnostic_code(exc.code)
        raise HTTPException(
            status_code=503,
            detail={"code": code, "message": VAULT_DIAGNOSTIC_MESSAGES[code]},
            headers=_NO_STORE_HEADERS,
        ) from None
    except (VaultError, OSError, data_location.DataLocationError):
        if session is not None:
            session.lock()
        raise HTTPException(
            status_code=503,
            detail={"code": "generic", "message": VAULT_DIAGNOSTIC_MESSAGES["generic"]},
            headers=_NO_STORE_HEADERS,
        ) from None


async def _read_unlock_body(request: Request, declared_length: int | None) -> bytearray:
    """Read only a small exact JSON body; parsing/validation never uses a model."""
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 4096:
            for index in range(len(body)):
                body[index] = 0
            raise HTTPException(status_code=413, detail="protected request rejected")
    if declared_length is not None and len(body) != declared_length:
        for index in range(len(body)):
            body[index] = 0
        raise HTTPException(status_code=400, detail="protected request rejected")
    return body


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _unlock_request_from_body(body: bytearray) -> tuple[str, bool]:
    try:
        parsed = json.loads(bytes(body), object_pairs_hook=_reject_duplicate_json_keys)
        if not isinstance(parsed, dict) or set(parsed) != {"passphrase", "remember"}:
            raise ValueError
        value = parsed["passphrase"]
        remember = parsed["remember"]
        if type(value) is not str or type(remember) is not bool:
            raise ValueError
        encoded = value.encode("utf-8")
        if not 12 <= len(encoded) <= 1024:
            raise ValueError
        return value, remember
    except (UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="protected request rejected") from None
    finally:
        for index in range(len(body)):
            body[index] = 0


def _remember_passphrase(vault_path: Path, data_dir: Path, passphrase: str) -> tuple[bool, str | None]:
    location_warning: str | None = None
    try:
        remember_data_dir(data_dir)
    except (OSError, TypeError, ValueError, data_location.DataLocationError):
        location_warning = _LOCATION_REMEMBER_WARNING
    try:
        keyring = load_keyring()
        set_keyring_password(keyring, keyring_account(vault_path), passphrase)
    except Exception:
        return False, _KEYRING_REMEMBER_WARNING
    return True, location_warning


def create_private_cards_router(
    data_dir: Path,
    *,
    reader: CardReader | None = None,
    demo: bool = False,
    port: int = 8777,
    catalog_dir: Path | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/private", tags=["private cards"])
    vault_path = data_location.vault_path_for_data_dir(data_dir)
    audit_log = AuditLog(vault_path.with_name("audit.jsonl"))
    reader_supplied = reader is not None
    read_cards = reader or (lambda: _read_keyring_cards(vault_path, data_dir))
    csrf_token = secrets.token_urlsafe(32)
    unlock_manager = _PassphraseUnlockManager(vault_path)

    def check_request_security(
        request: Request,
    ) -> None:
        _check_request_security(
            request=request,
            port=port,
            expected_csrf_token=csrf_token,
        )

    def active_browser_session(request: Request) -> VaultSession:
        """Require the process-local unlocked browser session for private state."""
        token = request.cookies.get("mycard_vault_session")
        session = unlock_manager.get(token)
        if session is None:
            raise HTTPException(
                status_code=401,
                # Carries a code so the interface can name what happened. As a
                # bare string this arrived at the browser with nothing to match
                # on and became "unavailable right now", which describes every
                # possible failure and therefore none of them.
                detail={
                    "code": "vault_session_required",
                    "message": "This browser session ended. Reload MyCard to continue.",
                },
                headers=_NO_STORE_HEADERS,
            )
        return session

    def protected_action_session(
        passphrase: str | None,
        request: Request,
    ) -> tuple[VaultSession, str, bool]:
        if passphrase is not None:
            return _open_session(vault_path, passphrase, audit_log=audit_log), passphrase, True
        active_session = unlock_manager.get(request.cookies.get("mycard_vault_session"))
        if active_session is not None:
            try:
                device_key = get_device_key(vault_path, data_dir, keyring_loader=load_keyring)
            except (VaultError, data_location.DataLocationError):
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": "keyring_unavailable",
                        "message": VAULT_DIAGNOSTIC_MESSAGES["keyring_unavailable"],
                    },
                    headers=_NO_STORE_HEADERS,
                ) from None
            if device_key is None:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": "passphrase_only",
                        "message": VAULT_DIAGNOSTIC_MESSAGES["passphrase_only"],
                    },
                    headers=_NO_STORE_HEADERS,
                )
            return active_session, device_key, False
        session, device_key = _open_device_action_session(
            vault_path, data_dir, audit_log=audit_log
        )
        return session, device_key, True

    @router.get("/csrf-token")
    def get_csrf_token(response: Response) -> dict[str, str]:
        response.headers.update(_NO_STORE_HEADERS)
        return {"csrf_token": csrf_token}

    @router.get("/unlock/bootstrap")
    def unlock_bootstrap(request: Request, response: Response) -> dict[str, str]:
        if demo:
            raise HTTPException(status_code=403, detail="protected request rejected", headers=_NO_STORE_HEADERS)
        values = _check_browser_headers(request=request, port=port, require_origin=False)
        _require_exact_origin_match(values)
        response.headers.update(_NO_STORE_HEADERS)
        return {"csrf_token": unlock_manager.bootstrap()}

    @router.post("/setup")
    async def setup(request: Request, response: Response) -> dict[str, object]:
        response.headers.update(_NO_STORE_HEADERS)
        if demo:
            raise HTTPException(status_code=403, detail="protected request rejected", headers=_NO_STORE_HEADERS)
        values = _check_browser_headers(request=request, port=port)
        _require_exact_origin_match(values)
        token = _single_csrf_token(values)
        declared_length = _validated_unlock_content_length(values)
        if not unlock_manager.consume_bootstrap(token):
            raise HTTPException(status_code=403, detail="protected browser action rejected", headers=_NO_STORE_HEADERS)
        if unlock_manager.rate_limited():
            raise HTTPException(status_code=429, detail="setup temporarily unavailable", headers=_NO_STORE_HEADERS)
        unlock_manager.record_attempt()
        body = await _read_unlock_body(request, declared_length)
        passphrase, remember = _unlock_request_from_body(body)
        try:
            try:
                data_location.data_location_checkpoint("before-vault-create", vault_path)
                data_location.reject_reparse(vault_path, allow_missing=True)
                session = VaultStore(vault_path, audit_log=audit_log).create(passphrase)
            except data_location.DataLocationError:
                raise HTTPException(status_code=503, detail="vault setup unavailable", headers=_NO_STORE_HEADERS) from None
            except VaultError:
                raise HTTPException(status_code=409, detail="vault setup conflict", headers=_NO_STORE_HEADERS) from None
            except OSError:
                raise HTTPException(status_code=503, detail="vault setup unavailable", headers=_NO_STORE_HEADERS) from None
            session_token = unlock_manager.create(session)
            remembered = False
            warning: str | None = None
            if remember:
                remembered, warning = _remember_passphrase(vault_path, data_dir, passphrase)
        finally:
            del passphrase
        response.set_cookie(
            "mycard_vault_session", session_token, httponly=True, samesite="strict", secure=False,
            path="/",
        )
        result: dict[str, object] = {"status": "unlocked", "remembered": remembered}
        if warning is not None:
            result["remember_warning"] = warning
        return result

    @router.post("/unlock")
    async def unlock(request: Request, response: Response) -> dict[str, object]:
        response.headers.update(_NO_STORE_HEADERS)
        if demo:
            raise HTTPException(status_code=403, detail="protected request rejected", headers=_NO_STORE_HEADERS)
        values = _check_browser_headers(request=request, port=port)
        _require_exact_origin_match(values)
        token = _single_csrf_token(values)
        declared_length = _validated_unlock_content_length(values)
        if not unlock_manager.consume_bootstrap(token):
            raise HTTPException(status_code=403, detail="protected browser action rejected", headers=_NO_STORE_HEADERS)
        if unlock_manager.rate_limited():
            raise HTTPException(status_code=429, detail="unlock temporarily unavailable", headers=_NO_STORE_HEADERS)
        unlock_manager.record_attempt()
        body = await _read_unlock_body(request, declared_length)
        passphrase, remember = _unlock_request_from_body(body)
        try:
            if not data_location.existing_regular_file(vault_path):
                raise VaultError("vault unavailable")
            data_location.data_location_checkpoint("before-vault-open", vault_path)
            data_location.reject_reparse(vault_path)
            session = VaultStore(vault_path, audit_log=audit_log).open(passphrase)
            session_token = unlock_manager.create(session)
            remembered = False
            warning: str | None = None
            if remember:
                remembered, warning = _remember_passphrase(vault_path, data_dir, passphrase)
        except (VaultError, data_location.DataLocationError):
            raise HTTPException(status_code=401, detail="unlock failed", headers=_NO_STORE_HEADERS) from None
        finally:
            # Python strings cannot be reliably zeroized; the request buffer is
            # cleared and the passphrase is never retained by this boundary.
            del passphrase
        response.set_cookie(
            "mycard_vault_session", session_token, httponly=True, samesite="strict", secure=False,
            path="/",
        )
        result: dict[str, object] = {"status": "unlocked", "remembered": remembered}
        if warning is not None:
            result["remember_warning"] = warning
        return result

    @router.post("/lock")
    def lock(request: Request, response: Response) -> dict[str, str]:
        response.headers.update(_NO_STORE_HEADERS)
        _check_request_security(request=request, port=port, expected_csrf_token=csrf_token)
        token = request.cookies.get("mycard_vault_session")
        unlock_manager.lock(token)
        response.delete_cookie("mycard_vault_session", path="/")
        return {"status": "locked"}

    @router.get("/cards", response_model=PrivateCardList)
    def list_private_cards(request: Request, response: Response) -> PrivateCardList:
        if demo:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "demo",
                    "message": VAULT_DIAGNOSTIC_MESSAGES["demo"],
                },
                headers=_NO_STORE_HEADERS,
            )
        try:
            session_cookie = request.cookies.get("mycard_vault_session")
            active_session = unlock_manager.get(session_cookie)
            if session_cookie and active_session is None and reader_supplied:
                raise VaultUnavailable("expired" if unlock_manager.expired(request.cookies.get("mycard_vault_session")) else "locked")
            if active_session is not None:
                raw = list(active_session.list_private_card_summaries())
                children = active_session.list_child_records()
                grouped: dict[str, list[dict[str, str]]] = {}
                for child in children:
                    grouped.setdefault(child["parent_card_id"], []).append(child)
                raw_cards = tuple({**card, "child_records": grouped.get(card["card_id"], [])} for card in raw)
            elif not reader_supplied:
                # The device-held key opens the browser session silently.  No
                # user credential is needed for the first private-card read;
                # reveal is the only later credential surface.
                try:
                    device_session, device_key = _open_device_action_session(
                        vault_path, data_dir, audit_log=audit_log
                    )
                except HTTPException:
                    raw_cards = read_cards()
                else:
                    session_token = unlock_manager.create(device_session)
                    del device_key
                    response.delete_cookie("mycard_vault_session", path="/")
                    response.set_cookie(
                        "mycard_vault_session",
                        session_token,
                        httponly=True,
                        samesite="strict",
                        secure=False,
                        path="/",
                    )
                    raw = list(device_session.list_private_card_summaries())
                    children = device_session.list_child_records()
                    grouped = {}
                    for child in children:
                        grouped.setdefault(child["parent_card_id"], []).append(child)
                    raw_cards = tuple(
                        {**card, "child_records": grouped.get(card["card_id"], [])}
                        for card in raw
                    )
            else:
                raw_cards = read_cards()
            cards = [PrivateCardSummary.model_validate(item) for item in raw_cards]
            cards.sort(
                key=lambda item: (item.lifecycle != "active", item.offering_id, item.created_at)
            )
            result = PrivateCardList(
                cards=cards,
                lifecycle_counts=dict(
                    sorted(Counter(item.lifecycle for item in cards).items())
                ),
            )
        except VaultUnavailable as exc:
            code = _safe_diagnostic_code(exc.code)
            raise HTTPException(
                status_code=503,
                detail={
                    "code": code,
                    "message": VAULT_DIAGNOSTIC_MESSAGES[code],
                },
                headers=_NO_STORE_HEADERS,
            ) from None
        except VaultError:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "locked",
                    "message": VAULT_DIAGNOSTIC_MESSAGES["locked"],
                },
                headers=_NO_STORE_HEADERS,
            ) from None
        except (OSError, ValueError):
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "generic",
                    "message": VAULT_DIAGNOSTIC_MESSAGES["generic"],
                },
                headers=_NO_STORE_HEADERS,
            ) from None
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        return result

    @router.get("/personal-state", response_model=PrivateStateResponse)
    def list_personal_state(request: Request, response: Response) -> PrivateStateResponse:
        """Return only the unlocked local user's progress records."""
        response.headers.update(_NO_STORE_HEADERS)
        if demo:
            raise HTTPException(
                status_code=403,
                detail="protected request rejected",
                headers=_NO_STORE_HEADERS,
            )
        _check_browser_headers(request=request, port=port)
        session = active_browser_session(request)
        try:
            return PrivateStateResponse(
                aggregates=[
                    ManualAggregateResponse.model_validate(item)
                    for item in session.list_manual_aggregates()
                ],
                attempts=[
                    PrivateAttemptResponse.model_validate(item)
                    for item in session.list_private_attempts()
                ],
                private_state_revision=session.private_state_revision_hex,
            )
        except VaultError:
            raise HTTPException(
                status_code=503,
                detail="private state unavailable",
                headers=_NO_STORE_HEADERS,
            ) from None

    @router.put(
        "/threshold-aggregates/{card_id}", response_model=ManualAggregateResponse
    )
    def upsert_manual_aggregate(
        card_id: str,
        request: ManualAggregateRequest,
        response: Response,
        http_request: Request,
    ) -> ManualAggregateResponse:
        """Save one optional private aggregate for one card/rule context."""
        response.headers.update(_NO_STORE_HEADERS)
        check_request_security(http_request)
        session = active_browser_session(http_request)
        try:
            record = session.upsert_manual_aggregate(
                card_id,
                request.rule_id,
                request.rule_version,
                request.amount,
                request.currency,
                request.period,
                passphrase=request.passphrase,
            )
            return ManualAggregateResponse.model_validate(record)
        except VaultConflictError:
            raise HTTPException(
                status_code=409,
                detail="vault changed elsewhere; reopen before saving",
                headers=_NO_STORE_HEADERS,
            ) from None
        except VaultAccessError:
            raise HTTPException(
                status_code=401,
                detail="reauthentication failed",
                headers=_NO_STORE_HEADERS,
            ) from None
        except (VaultError, ValueError):
            raise HTTPException(
                status_code=400,
                detail="protected action unavailable",
                headers=_NO_STORE_HEADERS,
            ) from None

    @router.delete("/threshold-aggregates/{card_id}")
    def clear_manual_aggregate(
        card_id: str,
        request: ClearAggregateRequest,
        response: Response,
        http_request: Request,
    ) -> dict[str, bool]:
        """Clear the current aggregate while retaining no public projection."""
        response.headers.update(_NO_STORE_HEADERS)
        check_request_security(http_request)
        session = active_browser_session(http_request)
        try:
            cleared = session.clear_manual_aggregate(
                card_id,
                request.rule_id,
                request.rule_version,
                passphrase=request.passphrase,
            )
            return {"cleared": cleared}
        except VaultConflictError:
            raise HTTPException(
                status_code=409,
                detail="vault changed elsewhere; reopen before saving",
                headers=_NO_STORE_HEADERS,
            ) from None
        except VaultAccessError:
            raise HTTPException(
                status_code=401,
                detail="reauthentication failed",
                headers=_NO_STORE_HEADERS,
            ) from None
        except (VaultError, ValueError):
            raise HTTPException(
                status_code=400,
                detail="protected action unavailable",
                headers=_NO_STORE_HEADERS,
            ) from None

    @router.post("/attempts/{card_id}", response_model=PrivateAttemptMutationResponse)
    def add_private_attempt(
        card_id: str,
        request: AttemptCreateRequest,
        response: Response,
        http_request: Request,
    ) -> PrivateAttemptMutationResponse:
        """Append a private attempt outcome; it never changes public eligibility."""
        response.headers.update(_NO_STORE_HEADERS)
        check_request_security(http_request)
        session = active_browser_session(http_request)
        try:
            record = session.add_private_attempt(
                card_id,
                request.rule_id,
                request.rule_version,
                request.outcome,
                request.note,
                passphrase=request.passphrase,
                idempotency_key=request.idempotency_key,
                expected_private_state_revision=request.expected_private_state_revision,
            )
            return PrivateAttemptMutationResponse.model_validate(record)
        except VaultConflictError:
            raise HTTPException(
                status_code=409,
                detail="vault changed elsewhere; reopen before saving",
                headers=_NO_STORE_HEADERS,
            ) from None
        except VaultAccessError:
            raise HTTPException(
                status_code=401,
                detail="reauthentication failed",
                headers=_NO_STORE_HEADERS,
            ) from None
        except (VaultError, ValueError):
            raise HTTPException(
                status_code=400,
                detail="protected action unavailable",
                headers=_NO_STORE_HEADERS,
            ) from None

    @router.put("/attempts/{attempt_id}", response_model=PrivateAttemptMutationResponse)
    def update_private_attempt(
        attempt_id: str,
        request: AttemptUpdateRequest,
        response: Response,
        http_request: Request,
    ) -> PrivateAttemptMutationResponse:
        """Edit only the private outcome/note; context identity stays bound."""
        response.headers.update(_NO_STORE_HEADERS)
        check_request_security(http_request)
        session = active_browser_session(http_request)
        try:
            record = session.update_private_attempt(
                attempt_id,
                request.outcome,
                request.note,
                passphrase=request.passphrase,
                idempotency_key=request.idempotency_key,
                expected_private_state_revision=request.expected_private_state_revision,
            )
            return PrivateAttemptMutationResponse.model_validate(record)
        except VaultConflictError:
            raise HTTPException(
                status_code=409,
                detail="vault changed elsewhere; reopen before saving",
                headers=_NO_STORE_HEADERS,
            ) from None
        except VaultAccessError:
            raise HTTPException(
                status_code=401,
                detail="reauthentication failed",
                headers=_NO_STORE_HEADERS,
            ) from None
        except (VaultError, ValueError):
            raise HTTPException(
                status_code=400,
                detail="protected action unavailable",
                headers=_NO_STORE_HEADERS,
            ) from None

    @router.delete("/attempts/{attempt_id}", response_model=PrivateAttemptDeleteResponse)
    def delete_private_attempt(
        attempt_id: str,
        request: AttemptDeleteRequest,
        response: Response,
        http_request: Request,
    ) -> PrivateAttemptDeleteResponse:
        """Delete one private attempt history entry after fresh reauthentication."""
        response.headers.update(_NO_STORE_HEADERS)
        check_request_security(http_request)
        session = active_browser_session(http_request)
        try:
            deleted = session.delete_private_attempt(
                attempt_id,
                passphrase=request.passphrase,
                idempotency_key=request.idempotency_key,
                expected_private_state_revision=request.expected_private_state_revision,
            )
            return PrivateAttemptDeleteResponse.model_validate(deleted)
        except VaultConflictError:
            raise HTTPException(
                status_code=409,
                detail="vault changed elsewhere; reopen before saving",
                headers=_NO_STORE_HEADERS,
            ) from None
        except VaultAccessError:
            raise HTTPException(
                status_code=401,
                detail="reauthentication failed",
                headers=_NO_STORE_HEADERS,
            ) from None
        except (VaultError, ValueError):
            raise HTTPException(
                status_code=400,
                detail="protected action unavailable",
                headers=_NO_STORE_HEADERS,
            ) from None

    @router.get("/discovery/cards", response_model=OwnedDiscoveryList)
    def discovery_cards(response: Response) -> OwnedDiscoveryList:
        """Join private offering IDs to public facts without exposing them."""
        if demo or catalog_dir is None:
            code = "demo" if demo else "generic"
            raise HTTPException(
                status_code=503,
                detail={"code": code, "message": VAULT_DIAGNOSTIC_MESSAGES[code]},
                headers=_NO_STORE_HEADERS,
            )
        try:
            cards = [PrivateCardSummary.model_validate(item) for item in read_cards()]
            catalog = load_catalog(catalog_dir)
            by_key = {offering.slug: offering for offering in catalog.offerings}
            by_key.update({offering.id: offering for offering in catalog.offerings})
            output: list[OwnedDiscoveryCard] = []
            for card in cards:
                offering = by_key.get(card.offering_id)
                if offering is None:
                    output.append(OwnedDiscoveryCard(
                        local_card_ref=card.card_id,
                        lifecycle=card.lifecycle,
                        catalog_match="unmatched",
                        reasons=["No canonical public catalog offering matches this record."],
                        rule_ids=[],
                    ))
                    continue
                output.append(OwnedDiscoveryCard(
                    local_card_ref=card.card_id,
                    public_offering_id=offering.id,
                    public_display=offering.display_name,
                    public_variant=offering.product_variant_id,
                    lifecycle=card.lifecycle,
                    catalog_match="matched",
                    reasons=["Canonical public catalog match; this is not proof of eligibility."],
                    rule_ids=[rule.id for rule in catalog.benefits if rule.offering_id == offering.id],
                ))
            output.sort(key=lambda item: (item.catalog_match != "matched", item.public_display or "", item.local_card_ref))
            response.headers.update(_NO_STORE_HEADERS)
            return OwnedDiscoveryList(cards=output)
        except VaultUnavailable as exc:
            code = _safe_diagnostic_code(exc.code)
            raise HTTPException(
                status_code=503,
                detail={"code": code, "message": VAULT_DIAGNOSTIC_MESSAGES[code]},
                headers=_NO_STORE_HEADERS,
            ) from None
        except (VaultError, CatalogLoadError, OSError, ValueError):
            raise HTTPException(
                status_code=503,
                detail={"code": "locked", "message": VAULT_DIAGNOSTIC_MESSAGES["locked"]},
                headers=_NO_STORE_HEADERS,
            ) from None

    @router.get("/expiry-signals")
    def expiry_signals(response: Response) -> dict[str, object]:
        if demo:
            raise HTTPException(status_code=503, detail="private cards unavailable", headers=_NO_STORE_HEADERS)
        try:
            session = _open_keyring_session(vault_path, data_dir)
            try:
                signals = session.list_expiry_signals()
            finally:
                session.lock()
        except VaultUnavailable as exc:
            code = _safe_diagnostic_code(exc.code)
            raise HTTPException(
                status_code=503,
                detail={"code": code, "message": VAULT_DIAGNOSTIC_MESSAGES[code]},
                headers=_NO_STORE_HEADERS,
            ) from None
        except VaultError:
            raise HTTPException(
                status_code=503,
                detail={"code": "locked", "message": VAULT_DIAGNOSTIC_MESSAGES["locked"]},
                headers=_NO_STORE_HEADERS,
            ) from None
        except (OSError, ValueError):
            raise HTTPException(
                status_code=503,
                detail={"code": "generic", "message": VAULT_DIAGNOSTIC_MESSAGES["generic"]},
                headers=_NO_STORE_HEADERS,
            ) from None
        response.headers.update(_NO_STORE_HEADERS)
        return {"signals": signals}

    @router.post("/cards/add")
    def add_card(request: AddCardRequest, http_request: Request) -> ProtectedResult:
        check_request_security(http_request)
        session, action_passphrase, owns_session = protected_action_session(
            request.passphrase, http_request
        )
        try:
            card_id = session.add_card(request.offering_id, request.secret_fields, lifecycle=request.lifecycle, passphrase=action_passphrase)
            return ProtectedResult(card_id=card_id)
        except VaultError:
            raise HTTPException(status_code=400, detail="protected action unavailable") from None
        finally:
            del action_passphrase
            if owns_session:
                session.lock()

    @router.post("/cards/{card_id}/edit")
    def edit_card(card_id: str, request: EditCardRequest, http_request: Request) -> ProtectedResult:
        check_request_security(http_request)
        session, action_passphrase, owns_session = protected_action_session(
            request.passphrase, http_request
        )
        try:
            session.edit_card(card_id, request.changes, passphrase=action_passphrase)
            return ProtectedResult(card_id=card_id)
        except VaultError:
            raise HTTPException(status_code=400, detail="protected action unavailable") from None
        finally:
            del action_passphrase
            if owns_session:
                session.lock()

    @router.post("/cards/{card_id}/lifecycle")
    def transition_card(card_id: str, request: TransitionRequest, http_request: Request) -> ProtectedResult:
        check_request_security(http_request)
        session, action_passphrase, owns_session = protected_action_session(
            request.passphrase, http_request
        )
        try:
            prompt = session.transition_card(card_id, request.lifecycle, passphrase=action_passphrase)
            return ProtectedResult(card_id=card_id, erase_prompt=prompt)
        except VaultError:
            raise HTTPException(status_code=400, detail="protected action unavailable") from None
        finally:
            del action_passphrase
            if owns_session:
                session.lock()

    @router.post("/cards/{card_id}/replace")
    def replace_card(card_id: str, request: AddCardRequest, http_request: Request) -> ProtectedResult:
        check_request_security(http_request)
        session, action_passphrase, owns_session = protected_action_session(
            request.passphrase, http_request
        )
        try:
            successor = session.replace_card(card_id, request.secret_fields, passphrase=action_passphrase)
            return ProtectedResult(card_id=card_id, successor_card_id=successor)
        except VaultError:
            raise HTTPException(status_code=400, detail="protected action unavailable") from None
        finally:
            del action_passphrase
            if owns_session:
                session.lock()

    @router.post("/cards/{card_id}/erase-cvv-pin")
    def erase_cvv_pin(card_id: str, request: DeviceActionRequest, http_request: Request) -> ProtectedResult:
        check_request_security(http_request)
        if request.passphrase is None:
            session = active_browser_session(http_request)
            authorization_token = http_request.cookies.get(_DETAIL_SESSION_COOKIE)
            if not authorization_token:
                raise HTTPException(
                    status_code=401,
                    detail="card-details authorization required",
                    headers=_NO_STORE_HEADERS,
                )
            try:
                session.erase_cvv_pin_with_detail_authorization(
                    card_id, authorization_token=authorization_token
                )
                return ProtectedResult(card_id=card_id)
            except VaultError:
                raise HTTPException(
                    status_code=400,
                    detail="protected action unavailable",
                    headers=_NO_STORE_HEADERS,
                ) from None
        session, action_passphrase, owns_session = protected_action_session(
            request.passphrase, http_request
        )
        try:
            session.erase_cvv_pin(card_id, passphrase=action_passphrase)
            return ProtectedResult(card_id=card_id)
        except VaultError:
            raise HTTPException(status_code=400, detail="protected action unavailable") from None
        finally:
            del action_passphrase
            if owns_session:
                session.lock()

    @router.delete("/cards/{card_id}")
    def delete_card(card_id: str, request: DestructiveRequest, http_request: Request) -> ProtectedResult:
        check_request_security(http_request)
        if request.confirmation != "DELETE CARD":
            raise HTTPException(status_code=422, detail="typed confirmation required")
        session, action_passphrase, owns_session = protected_action_session(
            request.passphrase, http_request
        )
        try:
            session.delete_card(card_id, confirmation=request.confirmation, passphrase=action_passphrase)
            return ProtectedResult(card_id=card_id, backup_warning="Encrypted backups may still contain this record.")
        except VaultError:
            raise HTTPException(status_code=400, detail="protected action unavailable") from None
        finally:
            del action_passphrase
            if owns_session:
                session.lock()

    @router.post("/cards/{card_id}/purge")
    def purge_card(card_id: str, request: DestructiveRequest, http_request: Request) -> ProtectedResult:
        check_request_security(http_request)
        if request.confirmation != "DELETE CARD":
            raise HTTPException(status_code=422, detail="typed confirmation required")
        session, action_passphrase, owns_session = protected_action_session(
            request.passphrase, http_request
        )
        try:
            session.purge_card(card_id, confirmation=request.confirmation, passphrase=action_passphrase)
            return ProtectedResult(card_id=card_id, backup_warning="Encrypted backups may still contain this record.")
        except VaultError:
            raise HTTPException(status_code=400, detail="protected action unavailable") from None
        finally:
            del action_passphrase
            if owns_session:
                session.lock()

    @router.post("/cards/{card_id}/reveal-authorize")
    def authorize_reveal(
        card_id: str,
        request: RevealRequest,
        response: Response,
        http_request: Request,
    ) -> RevealResult:
        """Create/reuse the local details code and return one browser reveal."""
        check_request_security(http_request)
        response.headers.update(_NO_STORE_HEADERS)
        if request.passphrase is not None:
            # Preserve a generic response for callers of the retired contract;
            # the live browser flow never sends a vault passphrase here.
            raise HTTPException(
                status_code=410,
                detail="plaintext reveal is disabled",
                headers=_NO_STORE_HEADERS,
            )

        session = active_browser_session(http_request)
        has_code = session.detail_credential_configured
        has_credential = request.credential is not None
        should_create = request.mode == "create" or (not has_code and has_credential)

        if should_create:
            if has_code:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "credential_exists",
                        "message": "A card-details code already exists in this vault.",
                    },
                    headers=_NO_STORE_HEADERS,
                )
            if (
                request.credential_type is None
                or request.credential is None
                or request.confirm is None
                or request.credential != request.confirm
            ):
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "credential_invalid",
                        "message": "The card-details code could not be created.",
                    },
                    headers=_NO_STORE_HEADERS,
                )
            # Creating the code and reading a card are separate failures and are
            # reported separately. Catching both together told an owner setting
            # up their PIN that card details were unavailable, which described
            # neither what they did nor what went wrong.
            try:
                authorization_token = session.create_detail_credential(
                    card_id, request.credential_type, request.credential
                )
            except VaultError:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": "credential_not_created",
                        "message": "That code could not be set up. Nothing was changed.",
                    },
                    headers=_NO_STORE_HEADERS,
                ) from None
            try:
                values = session.reveal_detail_values(
                    card_id, authorization_token=authorization_token
                )
            except VaultError:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": "card_details_unavailable",
                        "message": "Full card details are unavailable for this card.",
                    },
                    headers=_NO_STORE_HEADERS,
                ) from None
            unlock_manager.detail_success()
        elif has_credential:
            delay, retry_after = unlock_manager.detail_before_attempt()
            if retry_after:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "code": "credential_locked",
                        "message": "Card details are temporarily unavailable.",
                    },
                    headers={**_NO_STORE_HEADERS, "Retry-After": str(max(1, int(retry_after)))},
                )
            if delay:
                time.sleep(delay)
            try:
                session.verify_detail_credential(request.credential)
                authorization_token = session.detail_session_token()
                values = session.reveal_detail_values(
                    card_id, authorization_token=authorization_token
                )
            except VaultError:
                lockout = unlock_manager.detail_failure()
                if lockout:
                    raise HTTPException(
                        status_code=429,
                        detail={
                            "code": "credential_locked",
                            "message": "Card details are temporarily unavailable.",
                        },
                        headers={
                            **_NO_STORE_HEADERS,
                            "Retry-After": str(int(lockout)),
                        },
                    ) from None
                raise HTTPException(
                    status_code=401,
                    detail={
                        "code": "credential_invalid",
                        "message": "The card-details code was not accepted.",
                    },
                    headers=_NO_STORE_HEADERS,
                ) from None
            unlock_manager.detail_success()
        else:
            if not has_code:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "credential_required",
                        "message": "Create a code for card details.",
                    },
                    headers=_NO_STORE_HEADERS,
                )
            authorization_token = http_request.cookies.get(_DETAIL_SESSION_COOKIE)
            if not authorization_token:
                raise HTTPException(
                    status_code=401,
                    detail={
                        "code": "detail_session_required",
                        "message": "Card details are unavailable in this browser session.",
                    },
                    headers=_NO_STORE_HEADERS,
                )
            try:
                values = session.reveal_detail_values(
                    card_id, authorization_token=authorization_token
                )
            except VaultError:
                raise HTTPException(
                    status_code=401,
                    detail={
                        "code": "detail_session_required",
                        "message": "Card details are unavailable in this browser session.",
                    },
                    headers=_NO_STORE_HEADERS,
                ) from None

        response.set_cookie(
            _DETAIL_SESSION_COOKIE,
            session.detail_session_token(),
            httponly=True,
            samesite="strict",
            secure=False,
            path="/",
            max_age=900,
        )
        return RevealResult.model_validate(values)

    return router


def _open_keyring_session(vault_path: Path, data_dir: Path | None = None) -> VaultSession:
    data_dir = data_dir or vault_path.parent.parent
    try:
        data_location.reject_reparse(vault_path, allow_missing=True)
        passphrase = get_device_key(vault_path, data_dir, keyring_loader=load_keyring)
    except (VaultError, data_location.DataLocationError):
        raise VaultUnavailable("keyring_unavailable") from None
    try:
        exists = data_location.existing_regular_file(vault_path)
    except data_location.DataLocationError:
        raise VaultUnavailable("generic") from None
    if not exists:
        raise VaultUnavailable("vault_missing")
    if passphrase is None:
        raise VaultUnavailable("passphrase_only")
    data_location.data_location_checkpoint("before-keyring-vault-open", vault_path)
    data_location.reject_reparse(vault_path)
    return VaultStore(vault_path).open(passphrase)


def _open_or_bootstrap_device_session(
    vault_path: Path,
    data_dir: Path,
    *,
    audit_log: AuditLog | None = None,
) -> VaultSession:
    """Open a remembered device vault, creating the first empty vault silently."""

    try:
        exists = data_location.existing_regular_file(vault_path)
    except data_location.DataLocationError:
        raise VaultUnavailable("generic") from None
    try:
        passphrase = get_device_key(vault_path, data_dir, keyring_loader=load_keyring)
    except VaultError:
        if exists:
            raise VaultUnavailable("keyring_unavailable") from None
        # A missing/unusable keyring can still use the local fallback.  On a
        # genuinely fresh install, set_device_key below creates that fallback.
        passphrase = None
    if exists:
        if passphrase is None:
            raise VaultUnavailable("passphrase_only")
        try:
            data_location.data_location_checkpoint("before-keyring-vault-open", vault_path)
            data_location.reject_reparse(vault_path)
            return VaultStore(vault_path, audit_log=audit_log).open(passphrase)
        except (VaultError, data_location.DataLocationError):
            raise VaultUnavailable("locked") from None
    if passphrase is not None:
        raise VaultUnavailable("wrong_data_dir")

    generated_key = secrets.token_urlsafe(32)
    try:
        set_device_key(vault_path, data_dir, generated_key, keyring_loader=load_keyring)
        data_location.data_location_checkpoint("before-vault-create", vault_path)
        data_location.reject_reparse(vault_path, allow_missing=True)
        return VaultStore(vault_path, audit_log=audit_log).create(generated_key)
    except (VaultError, OSError, data_location.DataLocationError):
        raise VaultUnavailable("keyring_unavailable") from None
    finally:
        del generated_key


def _read_keyring_cards(
    vault_path: Path,
    data_dir: Path | None = None,
) -> tuple[dict[str, Any], ...]:
    data_dir = data_dir or vault_path.parent.parent
    try:
        session = _open_or_bootstrap_device_session(vault_path, data_dir)
    except VaultUnavailable:
        raise
    except (VaultError, OSError, data_location.DataLocationError):
        raise VaultUnavailable("generic") from None
    try:
        cards = session.list_private_card_summaries()
        child_records = session.list_child_records()
    finally:
        session.lock()
    grouped: dict[str, list[dict[str, str]]] = {}
    for child in child_records:
        grouped.setdefault(child["parent_card_id"], []).append(child)
    return tuple({**card, "child_records": grouped.get(card["card_id"], [])} for card in cards)


def _read_keyring_reminder_inputs(
    vault_path: Path,
    data_dir: Path | None = None,
) -> tuple[dict[str, Any], ...]:
    """Read only the dedicated server-side derived reminder inputs."""
    data_dir = data_dir or vault_path.parent.parent
    try:
        data_location.reject_reparse(vault_path, allow_missing=True)
        passphrase = get_device_key(vault_path, data_dir, keyring_loader=load_keyring)
    except (VaultError, data_location.DataLocationError):
        raise VaultUnavailable("keyring_unavailable") from None
    try:
        exists = data_location.existing_regular_file(vault_path)
    except data_location.DataLocationError:
        raise VaultUnavailable("generic") from None
    if not exists:
        raise VaultUnavailable("vault_missing" if passphrase is None else "wrong_data_dir")
    if passphrase is None:
        raise VaultUnavailable("passphrase_only")
    data_location.data_location_checkpoint("before-keyring-reminder-open", vault_path)
    data_location.reject_reparse(vault_path)
    session = VaultStore(vault_path).open(passphrase)
    try:
        return session.list_reminder_inputs()
    finally:
        session.lock()


def _authorize_keyring_vault(vault_path: Path, data_dir: Path | None = None) -> None:
    """Require the existing OS-keyring unlock control for local mutations."""
    _read_keyring_reminder_inputs(vault_path, data_dir)
