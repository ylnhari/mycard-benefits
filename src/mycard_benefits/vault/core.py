"""Versioned, local encrypted vault storage.

The on-disk JSON envelope carries crypto metadata and non-sensitive card
metadata only.  Every user-supplied card value is authenticated ciphertext.
"""

from __future__ import annotations

import base64
import calendar
import contextlib
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
import uuid
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, NoReturn, Protocol, cast

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .. import data_location
from .personal_state import (
    MAX_PERSONAL_STATE_RECORDS,
    AttemptOutcome,
    ManualSpendAggregate,
    PrivateAttempt,
    aggregate_context_key,
    serialize_aggregate,
    serialize_attempt,
    validate_aggregate_record,
    validate_amount,
    validate_attempt_record,
    validate_currency,
    validate_idempotency_key,
    validate_identifier,
    validate_note,
    validate_period,
    validate_private_state_revision,
    validate_rule_version,
)

_FORMAT_VERSION: Final = 2
_DEK_BYTES: Final = 32
_DEK_AAD: Final = b"mycard-benefits/vault-dek/v1"
_RECORD_AAD_PREFIX: Final = b"mycard-benefits/vault-record/v1:"
_ENVELOPE_MAC_INFO: Final = b"mycard-benefits/vault-envelope-mac/v2"
_PRIVATE_IMPORT_ARTIFACT_INFO: Final = b"mycard-benefits/private-import-artifacts/v1"
_PRIVATE_STATE_AAD: Final = b"mycard-benefits/vault-private-state/v1"
_PRIVATE_STATE_VERSION: Final = 1
_MAX_VAULT_BYTES: Final = 5 * 1024 * 1024
_MAX_RECORDS: Final = 1_000
_MAX_CHILD_RECORDS: Final = 5_000
_BACKUP_COUNT: Final = 3
_COPY_CHUNK_BYTES: Final = 64 * 1024
_MAX_SECRET_VALUE_CHARS: Final = 4_096
_MAX_SECRET_TOTAL_CHARS: Final = 16_384
_MIN_PASSPHRASE_BYTES: Final = 12
_MAX_PASSPHRASE_BYTES: Final = 1_024
_MIN_DETAIL_PIN_CHARS: Final = 6
_MIN_DETAIL_PASSPHRASE_BYTES: Final = 12
_MAX_DETAIL_CREDENTIAL_BYTES: Final = 1_024
_DETAIL_CREDENTIAL_TYPES: Final = frozenset({"pin", "passphrase"})
_MAX_ATTEMPT_CONTRACTS: Final = 128
_ATTEMPT_CONTRACT_TTL_SECONDS: Final = 900.0
_DETAIL_CREDENTIAL_UNSET: Final = object()
_ALLOWED_SECRET_FIELDS: Final = frozenset(
    {
        "cardholder_name",
        # A private local alias for the owner may differ from the cardholder.
        # It stays encrypted and never crosses the browser envelope.
        "owner_alias",
        "pan",
        # A user may know only the final four digits.  It is encrypted with
        # the rest of the private record and is never an envelope field.
        "last_four",
        "expiry_month",
        "expiry_year",
        "cvv",
        "pin",
        "nickname",
        "notes",
        "billing_postcode",
        # A source-derived opaque handle is encrypted with the private record.
        # It is used only by the non-destructive reconciliation path and is
        # never included in the browser envelope or an error message.
        "reconciliation_id",
        # JSON-encoded, non-secret reconciliation metadata.  It remains inside
        # the authenticated record so the browser never becomes a write path.
        "reconciliation_metadata",
    }
)
_REVEALABLE_SECRET_FIELDS: Final = _ALLOWED_SECRET_FIELDS - {
    "reconciliation_id", "reconciliation_metadata", "last_four"
}
_OFFERING_ID: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_RECONCILIATION_ID: Final = re.compile(r"^[0-9a-f]{32}$")


class VaultError(Exception):
    """A non-sensitive vault failure suitable for callers to present generically."""


class VaultAccessError(VaultError):
    """A vault could not be opened or authenticated."""


class VaultConflictError(VaultError):
    """A different process changed the vault after this session opened it."""


class VaultPermissionError(VaultError):
    """Restrictive local storage permissions could not be established."""


class _PermissionHelper(Protocol):
    def secure_directory(self, path: Path) -> None: ...

    def secure_file(self, path: Path) -> None: ...


class AuditSink(Protocol):
    """Minimal value-free audit boundary used by protected vault sessions."""

    def record(
        self,
        action: Any,
        *,
        record_ref: str | None = None,
        event_id: str | None = None,
        success: bool = True,
    ) -> str: ...


class _PlatformPermissions:
    """Establish actual local-only permissions, not merely cosmetic chmod bits."""

    def secure_directory(self, path: Path) -> None:
        if os.name == "nt":
            self._secure_windows(path)
            return
        os.chmod(path, 0o700)
        if (path.stat().st_mode & 0o777) != 0o700:
            raise VaultPermissionError("private storage permissions unavailable")

    def secure_file(self, path: Path) -> None:
        if os.name == "nt":
            self._secure_windows(path)
            return
        os.chmod(path, 0o600)
        if (path.stat().st_mode & 0o777) != 0o600:
            raise VaultPermissionError("private storage permissions unavailable")

    @staticmethod
    def _secure_windows(path: Path) -> None:
        try:
            import ntsecuritycon  # type: ignore[import-untyped]
            import pywintypes  # type: ignore[import-untyped]
            import win32api  # type: ignore[import-untyped]
            import win32con  # type: ignore[import-untyped]
            import win32security  # type: ignore[import-untyped]
        except ImportError as exc:
            raise VaultPermissionError("private storage permissions unavailable") from exc
        token = None
        try:
            token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
            sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
            acl = win32security.ACL()
            acl.AddAccessAllowedAce(win32security.ACL_REVISION, ntsecuritycon.FILE_ALL_ACCESS, sid)
            descriptor = win32security.SECURITY_DESCRIPTOR()
            descriptor.SetSecurityDescriptorDacl(1, acl, 0)
            descriptor.SetSecurityDescriptorControl(
                win32security.SE_DACL_PROTECTED, win32security.SE_DACL_PROTECTED
            )
            info = win32security.DACL_SECURITY_INFORMATION | win32security.PROTECTED_DACL_SECURITY_INFORMATION
            # One atomic ACL application: never install a transient NULL/empty DACL.
            win32security.SetFileSecurity(str(path), info, descriptor)
            read_back = win32security.GetFileSecurity(str(path), info)
            control, _ = read_back.GetSecurityDescriptorControl()
            dacl = read_back.GetSecurityDescriptorDacl()
            if not (control & win32security.SE_DACL_PROTECTED) or dacl is None or dacl.GetAceCount() != 1:
                raise VaultPermissionError("private storage permissions unavailable")
            header, mask, ace_sid = dacl.GetAce(0)
            if header[0] != win32security.ACCESS_ALLOWED_ACE_TYPE or header[1] != 0 or mask != ntsecuritycon.FILE_ALL_ACCESS or ace_sid != sid:
                raise VaultPermissionError("private storage permissions unavailable")
        except pywintypes.error as exc:
            raise VaultPermissionError("private storage permissions unavailable") from exc
        finally:
            if token is not None:
                token.Close()


def secure_private_path(path: Path, *, directory: bool) -> None:
    """Apply the vault's restrictive local-storage boundary to an artifact."""
    helper = _PlatformPermissions()
    if directory:
        helper.secure_directory(path)
    else:
        helper.secure_file(path)


class CardLifecycle(StrEnum):
    APPLIED = "applied"
    PENDING = "pending"
    ACTIVE = "active"
    FROZEN = "frozen"
    EXPIRED = "expired"
    LOST = "lost"
    STOLEN = "stolen"
    RENEWED = "renewed"
    REPLACED = "replaced"
    UPGRADED = "upgraded"
    DOWNGRADED = "downgraded"
    CLOSED = "closed"
    RETIRED = "retired"
    ARCHIVED = "archived"


class ChildRecordKind(StrEnum):
    PRIORITY_PASS = "priority_pass"
    LOUNGE_CREDENTIAL = "lounge_credential"
    MEMBERSHIP = "membership"
    VOUCHER = "voucher"
    COMPANION_CREDENTIAL = "companion_credential"


class ChildRecordLifecycle(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    ARCHIVED = "archived"


@dataclass(frozen=True)
class _KdfParameters:
    salt: bytes
    time_cost: int = 3
    memory_cost_kib: int = 65_536
    parallelism: int = 1


@dataclass(frozen=True)
class _Record:
    card_id: str
    offering_id: str
    lifecycle: CardLifecycle
    created_at: str
    updated_at: str
    ciphertext: bytes
    replacement_card_id: str | None = None


def _validate_replacement_graph(
    records: dict[str, _Record], *, error_type: type[VaultError]
) -> None:
    def invalid() -> NoReturn:
        raise error_type("replacement lineage is invalid")

    incoming: dict[str, int] = {card_id: 0 for card_id in records}
    for record in records.values():
        if not isinstance(record.created_at, str) or not isinstance(record.updated_at, str):
            invalid()
        try:
            _validate_timestamp(record.created_at)
            _validate_timestamp(record.updated_at)
        except (TypeError, VaultAccessError):
            invalid()
        if record.updated_at < record.created_at:
            invalid()
        successor_id = record.replacement_card_id
        if successor_id is None:
            continue
        successor = records.get(successor_id)
        if successor is None or successor_id == record.card_id:
            invalid()
        if record.lifecycle is CardLifecycle.ACTIVE:
            invalid()
        if successor.offering_id != record.offering_id or successor.created_at < record.created_at:
            invalid()
        incoming[successor_id] += 1
        if incoming[successor_id] > 1:
            invalid()
    for card_id in records:
        seen: set[str] = set()
        current = card_id
        while records[current].replacement_card_id is not None:
            if current in seen:
                invalid()
            seen.add(current)
            current = records[current].replacement_card_id  # type: ignore[assignment]


@dataclass(frozen=True)
class _ChildRecord:
    """Non-secret; the display label is always derived from `kind`, never free text."""

    child_id: str
    parent_card_id: str
    kind: ChildRecordKind
    lifecycle: ChildRecordLifecycle
    created_at: str
    updated_at: str
    expiry_date: str | None = None


@dataclass(frozen=True, repr=False)
class ReconciliationCard:
    """One validated private source record for non-destructive reconciliation."""

    source_identity: str
    offering_id: str | None
    lifecycle: CardLifecycle
    secret_fields: dict[str, str]


@dataclass(frozen=True)
class ReconciliationResult:
    """Count-only result for a local source reconciliation.

    The result deliberately has no source identifiers, offering identifiers,
    card IDs, or values. A caller may safely use it in a local receipt.
    """

    imported: int
    bound_existing: int
    unchanged: int


class RevealAuthorization:
    """Opaque, one-use authorization minted by a reauthenticated session."""

    __slots__ = ("_nonce",)

    def __init__(self, nonce: str) -> None:
        self._nonce = nonce


class ReconciliationAuthorization:
    """Opaque, one-use authorization for a reviewed metadata change."""

    __slots__ = ("_nonce",)

    def __init__(self, nonce: str) -> None:
        self._nonce = nonce


class ConsolidationAuthorization:
    """Opaque, one-use authorization for one exact private import plan."""

    __slots__ = ("_nonce",)

    def __init__(self, nonce: str) -> None:
        self._nonce = nonce


@dataclass
class _AttemptMutationContract:
    """Transient server-side binding for one private attempt mutation.

    The contract is deliberately not part of the encrypted vault format. Its
    payload binding is a digest, and the protected receipt is retained only in
    this bounded process-local session index; neither is logged or published.
    The vault revision precondition makes an accepted mutation replay-safe
    across a process restart even though the index itself is transient.
    """

    session_binding: str
    action: str
    card_id: str
    attempt_id: str | None
    rule_id: str
    rule_version: int
    expected_revision: bytes
    payload_digest: bytes
    expires_at: float
    receipt: dict[str, str | int | None]


class VaultStore:
    """Encrypted vault file factory and persistence boundary."""

    def __init__(
        self,
        path: Path,
        *,
        _permissions: _PermissionHelper | None = None,
        audit_log: AuditSink | None = None,
    ) -> None:
        self.path = data_location.lexical_absolute(path)
        self._permissions: _PermissionHelper = _permissions or _PlatformPermissions()
        self._audit_log = audit_log

    def create(self, passphrase: str) -> VaultSession:
        passphrase = _validate_passphrase(passphrase)
        kdf = _KdfParameters(salt=secrets.token_bytes(16))
        dek = secrets.token_bytes(_DEK_BYTES)
        envelope = _new_envelope(kdf, dek, passphrase)
        encoded = _encode_envelope(envelope)
        _validate_write_bounds(encoded, {}, {})
        data_location.reject_reparse(self.path, allow_missing=True)
        data_location.data_location_checkpoint("before-vault-lock", self.path)
        data_location.reject_reparse(self.path, allow_missing=True)
        with _exclusive_lock(self.path, self._permissions):
            data_location.reject_reparse(self.path, allow_missing=True)
            try:
                self.path.lstat()
            except FileNotFoundError:
                pass
            else:
                raise VaultError("vault already exists")
            data_location.data_location_checkpoint("before-vault-create-write", self.path)
            data_location.reject_reparse(self.path, allow_missing=True)
            _atomic_write(self.path, encoded, self._permissions, backup=False)
        return VaultSession(
            self,
            kdf,
            bytearray(dek),
            {},
            {},
            str(envelope["wrapped_dek"]),
            _digest(encoded),
            audit_log=self._audit_log,
        )

    def open(self, passphrase: str) -> VaultSession:
        try:
            raw_file = data_location.read_guarded_bytes(
                self.path, maximum=_MAX_VAULT_BYTES
            )
        except (OSError, data_location.DataLocationError):
            raise VaultAccessError("unable to unlock vault") from None
        return self.open_bytes(raw_file, passphrase)

    def open_bytes(self, raw_file: bytes, passphrase: str) -> VaultSession:
        """Open a bounded, already-held vault snapshot.

        Protected restore and migration paths use this method while retaining
        the exact file handle they authenticated. It does not widen the
        browser or provider boundary and never persists the supplied bytes.
        """
        try:
            passphrase = _validate_passphrase(passphrase)
        except VaultError:
            raise VaultAccessError("unable to unlock vault") from None
        try:
            if len(raw_file) > _MAX_VAULT_BYTES:
                raise VaultAccessError("unable to unlock vault")
            envelope = json.loads(raw_file.decode("utf-8"))
            kdf = _parse_kdf(envelope)
            dek = _unwrap_dek(envelope, kdf, passphrase)
            _verify_envelope_mac(envelope, dek)
            records = _parse_records(envelope, dek)
            child_records = _parse_child_records(envelope, records)
            events = _parse_reconciliation_events(envelope)
            manual_aggregates, attempts, detail_credential = _parse_private_state(
                envelope, dek, records
            )
        except (OSError, ValueError, KeyError, TypeError, InvalidTag, VaultError) as exc:
            if isinstance(exc, VaultAccessError):
                raise
            raise VaultAccessError("unable to unlock vault") from None
        return VaultSession(
            self,
            kdf,
            bytearray(dek),
            records,
            child_records,
            str(envelope["wrapped_dek"]),
            _digest(raw_file),
            reconciliation_events=events,
            manual_aggregates=manual_aggregates,
            attempts=attempts,
            detail_credential=detail_credential,
            audit_log=self._audit_log,
        )


class VaultSession:
    """An unlocked in-memory session which can be explicitly or automatically locked."""

    def __init__(
        self,
        store: VaultStore,
        kdf: _KdfParameters,
        dek: bytearray,
        records: dict[str, _Record],
        child_records: dict[str, _ChildRecord],
        wrapped_dek: str,
        revision: bytes,
        *,
        reconciliation_events: list[dict[str, str]] | None = None,
        manual_aggregates: dict[str, ManualSpendAggregate] | None = None,
        attempts: dict[str, PrivateAttempt] | None = None,
        detail_credential: dict[str, Any] | None = None,
        idle_timeout_seconds: float = 300.0,
        audit_log: AuditSink | None = None,
    ) -> None:
        if idle_timeout_seconds <= 0:
            raise VaultError("idle timeout must be positive")
        self._store = store
        self._kdf = kdf
        self._dek: bytearray | None = dek
        self._records = records
        self._child_records = child_records
        self._wrapped_dek = wrapped_dek
        self._revision = revision
        self._idle_timeout_seconds = idle_timeout_seconds
        self._last_activity = time.monotonic()
        self._expires_at = self._last_activity + 3600.0
        # nonce -> (record id, action, field, session binding, expiry)
        self._reveal_authorizations: dict[str, tuple[str, str, str | None, str, float]] = {}
        self._session_binding = secrets.token_urlsafe(24)
        self._reconciliation_authorizations: dict[
            str, tuple[str, str, str, str, bytes, float, dict[str, Any]]
        ] = {}
        # nonce -> (plan digest, action, vault revision, expiry).  This is kept
        # only in the freshly unlocked local session and is consumed before an
        # importer can write a batch.
        self._consolidation_authorizations: dict[str, tuple[str, str, bytes, float]] = {}
        # Idempotency contracts are process-local and bounded. They are bound
        # to this unlocked session and the vault revision, never persisted in
        # the public envelope or encrypted private-state blob.
        self._attempt_mutation_contracts: dict[str, _AttemptMutationContract] = {}
        self._reconciliation_events = list(reconciliation_events or [])
        self._manual_aggregates = dict(manual_aggregates or {})
        self._attempts = dict(attempts or {})
        self._detail_credential = (
            dict(detail_credential) if detail_credential is not None else None
        )
        self._audit_log = audit_log
        self._lock = threading.RLock()

    @property
    def locked(self) -> bool:
        with self._lock:
            self._auto_lock_if_idle()
            return self._dek is None

    @property
    def revision_hex(self) -> str:
        with self._lock:
            self._ensure_unlocked()
            return self._revision.hex()

    @property
    def private_state_revision_hex(self) -> str:
        """Return the opaque revision used by protected private-state writes."""
        return self.revision_hex

    def lock(self) -> None:
        with self._lock:
            if self._dek is not None:
                _zero(self._dek)
            self._dek = None
            self._records.clear()
            self._child_records.clear()
            self._manual_aggregates.clear()
            self._attempts.clear()
            self._detail_credential = None
            self._reveal_authorizations.clear()
            self._reconciliation_authorizations.clear()
            self._consolidation_authorizations.clear()
            self._attempt_mutation_contracts.clear()

    def list_cards(self) -> tuple[dict[str, str], ...]:
        with self._lock:
            self._ensure_unlocked()
            return tuple(
                {
                    "card_id": record.card_id,
                    "offering_id": record.offering_id,
                    "lifecycle": record.lifecycle.value,
                    "created_at": record.created_at,
                    "updated_at": record.updated_at,
                    **(
                        {"replacement_card_id": record.replacement_card_id}
                        if record.replacement_card_id
                        else {}
                    ),
                }
                for record in self._records.values()
            )

    def reconciliation_card(self, card_id: str) -> dict[str, str | None]:
        """Return only the protected envelope fields needed to bind a mutation."""
        with self._lock:
            self._ensure_unlocked()
            record = self._get_record(card_id)
            return {
                "card_id": record.card_id,
                "offering_id": record.offering_id,
                "lifecycle": record.lifecycle.value,
                "replacement_card_id": record.replacement_card_id,
                "updated_at": record.updated_at,
            }

    def list_private_card_summaries(self) -> tuple[dict[str, str], ...]:
        """Return envelope metadata plus a server-derived masked last four.

        Decryption happens only in this local process. Invalid or masked PAN
        values are represented as absent; no plaintext secret crosses this
        method's boundary.
        """
        with self._lock:
            self._ensure_unlocked()
            summaries: list[dict[str, str]] = []
            for record in self._records.values():
                summary = {
                    "card_id": record.card_id,
                    "offering_id": record.offering_id,
                    "lifecycle": record.lifecycle.value,
                    "created_at": record.created_at,
                    "updated_at": record.updated_at,
                }
                if record.replacement_card_id:
                    summary["replacement_card_id"] = record.replacement_card_id
                values = self._decrypt_record(record)
                # A full valid PAN is the authoritative local identifier.  A
                # separately entered final four is only a product-first
                # fallback when no full PAN has been stored.
                masked = _masked_last4(values.get("pan"))
                if masked is None:
                    masked = _masked_private_last4(values.get("last_four"))
                if masked is not None:
                    summary["masked_last4"] = masked
                summaries.append(summary)
            return tuple(summaries)

    @property
    def detail_credential_configured(self) -> bool:
        """Whether this vault has a user-created card-details code."""
        with self._lock:
            self._ensure_unlocked()
            return self._detail_credential is not None

    def detail_session_token(self) -> str:
        """Return the opaque, persisted local capability for this vault."""
        with self._lock:
            self._ensure_unlocked()
            if self._detail_credential is None:
                raise VaultAccessError("card-details code is not configured")
            token = self._detail_credential.get("session_token")
            if not isinstance(token, str):
                raise VaultAccessError("card-details authorization is unavailable")
            return token

    def create_detail_credential(
        self, card_id: str, credential_type: str, credential: str
    ) -> str:
        """Create the one local code used to authorize card-detail reveals.

        The code is never stored.  It wraps the existing vault DEK in the
        same Argon2id/AES-GCM envelope used by the vault's primary key.  The
        returned value is an opaque browser-session capability, not the code.
        """
        with self._lock:
            self._require_unlocked()
            if self._detail_credential is not None:
                raise VaultConflictError("card-details code already exists")
            record = self._get_record(card_id)
            values = self._decrypt_record(record)
            if not _has_revealable_card_details(values):
                raise VaultAccessError("card details are unavailable")
            _validate_detail_credential(credential_type, credential)
            detail_kdf = _KdfParameters(
                salt=secrets.token_bytes(16),
                time_cost=self._kdf.time_cost,
                memory_cost_kib=self._kdf.memory_cost_kib,
                parallelism=self._kdf.parallelism,
            )
            envelope = _new_envelope(
                detail_kdf, bytes(self._require_unlocked()), credential
            )
            stored = {
                "version": _FORMAT_VERSION,
                "credential_type": credential_type,
                "kdf": envelope["kdf"],
                "wrapped_dek": envelope["wrapped_dek"],
                "session_token": secrets.token_urlsafe(32),
            }
            self._persist(
                self._records,
                self._child_records,
                detail_credential=stored,
                audit_action="detail_credential_create",
                audit_record_ref=card_id,
            )
            return str(stored["session_token"])

    def verify_detail_credential(self, credential: str) -> None:
        """Verify a card-details code without retaining its plaintext."""
        with self._lock:
            self._require_unlocked()
            detail = self._detail_credential
            if detail is None:
                raise VaultAccessError("card-details code is not configured")
            credential_type = detail.get("credential_type")
            _validate_detail_credential(credential_type, credential)
            detail_kdf = _parse_kdf(
                {"version": _FORMAT_VERSION, "kdf": detail["kdf"]}
            )
            candidate = bytearray()
            try:
                candidate = bytearray(
                    _unwrap_dek(
                        {"wrapped_dek": detail["wrapped_dek"]}, detail_kdf, credential
                    )
                )
                if not secrets.compare_digest(candidate, self._require_unlocked()):
                    raise VaultAccessError("card-details code was not accepted")
            except (InvalidTag, KeyError, TypeError, ValueError, VaultError):
                raise VaultAccessError("card-details code was not accepted") from None
            finally:
                _zero(candidate)

    def reveal_detail_values(
        self, card_id: str, *, authorization_token: str
    ) -> dict[str, str | None]:
        """Return card-detail plaintext only after a bound local authorization."""
        with self._lock:
            self._require_unlocked()
            if not self._detail_authorization_matches(authorization_token):
                raise VaultAccessError("card details are unavailable")
            values = self._decrypt_record(self._get_record(card_id))
            if not _has_revealable_card_details(values):
                raise VaultAccessError("card details are unavailable")
            expiry_month = values["expiry_month"]
            expiry_year = values["expiry_year"]
            display_year = expiry_year[-2:] if len(expiry_year) == 4 else expiry_year
            return {
                "card_number": values["pan"],
                "expiry": f"{expiry_month} / {display_year}",
                "cvv": values.get("cvv"),
            }

    def erase_cvv_pin_with_detail_authorization(
        self, card_id: str, *, authorization_token: str
    ) -> None:
        """Erase CVV/PIN after the same card-details session proof."""
        with self._lock:
            self._require_unlocked()
            if not self._detail_authorization_matches(authorization_token):
                raise VaultAccessError("card details are unavailable")
            record = self._get_record(card_id)
            values = self._decrypt_record(record)
            changed = {
                key: value for key, value in values.items() if key not in {"cvv", "pin"}
            }
            updated = replace(record, updated_at=_timestamp())
            updated = replace(updated, ciphertext=self._encrypt_record(updated, changed))
            self._persist(
                {**self._records, card_id: updated},
                self._child_records,
                audit_action="secret_erase",
                audit_record_ref=card_id,
            )

    def _detail_authorization_matches(self, authorization_token: str) -> bool:
        with self._lock:
            detail = self._detail_credential
            if detail is None or not isinstance(authorization_token, str):
                return False
            stored = detail.get("session_token")
            return isinstance(stored, str) and secrets.compare_digest(
                stored, authorization_token
            )

    def list_reminder_inputs(self) -> tuple[dict[str, Any], ...]:
        """Return server-only reminder inputs, never a browser/API model.

        Only dates needed by the local reminder engine are selected from the
        decrypted record. Unknown fields are omitted rather than guessed.
        """
        with self._lock:
            self._ensure_unlocked()
            result: list[dict[str, Any]] = []
            for record in self._records.values():
                item: dict[str, Any] = {
                    "card_id": record.card_id,
                    "offering_id": record.offering_id,
                    "lifecycle": record.lifecycle.value,
                    "child_records": [],
                }
                values = self._decrypt_record(record)
                year, month = values.get("expiry_year"), values.get("expiry_month")
                if isinstance(year, str) and isinstance(month, str) and year.isdigit() and month.isdigit():
                    y, m = int(year), int(month)
                    if 1 <= y <= 9999 and 1 <= m <= 12:
                        item["expiry_date"] = f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"
                children: list[dict[str, Any]] = item["child_records"]
                for child in self._child_records.values():
                    if child.parent_card_id == record.card_id:
                        child_item: dict[str, Any] = {
                            "child_id": child.child_id,
                            "kind": child.kind.value,
                            "lifecycle": child.lifecycle.value,
                        }
                        if child.expiry_date is not None:
                            child_item["expiry_date"] = child.expiry_date
                        children.append(child_item)
                result.append(item)
            return tuple(result)

    def list_child_records(self, parent_card_id: str | None = None) -> tuple[dict[str, str], ...]:
        with self._lock:
            self._ensure_unlocked()
            return tuple(
                {
                    "child_id": record.child_id,
                    "parent_card_id": record.parent_card_id,
                    "kind": record.kind.value,
                    "lifecycle": record.lifecycle.value,
                    "created_at": record.created_at,
                    "updated_at": record.updated_at,
                    **({"expiry_date": record.expiry_date} if record.expiry_date else {}),
                }
                for record in self._child_records.values()
                if parent_card_id is None or record.parent_card_id == parent_card_id
            )

    def list_manual_aggregates(self) -> tuple[dict[str, str | int], ...]:
        """Return the current private aggregate snapshot for the local UI only."""
        with self._lock:
            self._ensure_unlocked()
            records = sorted(
                self._manual_aggregates.values(),
                key=lambda record: (record.created_at, record.aggregate_id),
            )
            return tuple(serialize_aggregate(record) for record in records)

    def upsert_manual_aggregate(
        self,
        card_id: str,
        rule_id: str,
        rule_version: int,
        amount: str,
        currency: str,
        period: str,
        *,
        passphrase: str,
    ) -> dict[str, str | int]:
        """Replace the one current manual aggregate for one card/rule context."""
        self._reauthenticate(passphrase)
        with self._lock:
            self._require_unlocked()
            self._get_record(card_id)
            try:
                card_id = validate_identifier(card_id, "card_id")
                rule_id = validate_identifier(rule_id, "rule_id")
                rule_version = validate_rule_version(rule_version)
                amount = validate_amount(amount)
                currency = validate_currency(currency)
                period = validate_period(period)
            except ValueError as exc:
                raise VaultError(str(exc)) from None
            key = aggregate_context_key(card_id, rule_id, rule_version)
            existing = self._manual_aggregates.get(key)
            now = _timestamp()
            record = ManualSpendAggregate(
                aggregate_id=existing.aggregate_id if existing else _uuid7(),
                card_id=card_id,
                rule_id=rule_id,
                rule_version=rule_version,
                amount=amount,
                currency=currency,
                period=period,
                created_at=existing.created_at if existing else now,
                updated_at=now,
            )
            candidate = {**self._manual_aggregates, key: record}
            self._persist(
                self._records,
                self._child_records,
                manual_aggregates=candidate,
            )
            return serialize_aggregate(record)

    def clear_manual_aggregate(
        self,
        card_id: str,
        rule_id: str,
        rule_version: int,
        *,
        passphrase: str,
    ) -> bool:
        """Clear the current aggregate without creating a public fact."""
        self._reauthenticate(passphrase)
        with self._lock:
            self._require_unlocked()
            self._get_record(card_id)
            try:
                card_id = validate_identifier(card_id, "card_id")
                rule_id = validate_identifier(rule_id, "rule_id")
                rule_version = validate_rule_version(rule_version)
            except ValueError as exc:
                raise VaultError(str(exc)) from None
            key = aggregate_context_key(card_id, rule_id, rule_version)
            cleared = key in self._manual_aggregates
            candidate = dict(self._manual_aggregates)
            candidate.pop(key, None)
            self._persist(
                self._records,
                self._child_records,
                manual_aggregates=candidate,
            )
            return cleared

    def list_private_attempts(self) -> tuple[dict[str, str | int | None], ...]:
        """Return private attempt history for the unlocked human-facing UI."""
        with self._lock:
            self._ensure_unlocked()
            records = sorted(
                self._attempts.values(),
                key=lambda record: (record.created_at, record.attempt_id),
            )
            return tuple(serialize_attempt(record) for record in records)

    def _validate_attempt_contract_inputs(
        self,
        idempotency_key: str | None,
        expected_private_state_revision: str | None,
    ) -> tuple[str, bytes] | None:
        if idempotency_key is None and expected_private_state_revision is None:
            return None
        if idempotency_key is None or expected_private_state_revision is None:
            raise VaultError("private attempt contract is invalid")
        try:
            key = validate_idempotency_key(idempotency_key)
            revision = validate_private_state_revision(expected_private_state_revision)
        except ValueError as exc:
            raise VaultError(str(exc)) from None
        return key, bytes.fromhex(revision)

    def _attempt_payload_digest(
        self,
        *,
        action: str,
        card_id: str,
        attempt_id: str | None,
        rule_id: str,
        rule_version: int,
        outcome: AttemptOutcome | None,
        note: str | None,
    ) -> bytes:
        payload = {
            "action": action,
            "attempt_id": attempt_id,
            "card_id": card_id,
            "note": note,
            "outcome": outcome.value if outcome is not None else None,
            "rule_id": rule_id,
            "rule_version": rule_version,
        }
        canonical = json.dumps(
            payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        return hashlib.sha256(canonical).digest()

    def _prune_attempt_mutation_contracts(self) -> None:
        now = time.monotonic()
        for key, contract in tuple(self._attempt_mutation_contracts.items()):
            if now > contract.expires_at:
                del self._attempt_mutation_contracts[key]

    def _replay_attempt_contract(
        self,
        contract_inputs: tuple[str, bytes] | None,
        *,
        action: str,
        card_id: str | None,
        attempt_id: str | None,
        rule_id: str | None,
        rule_version: int | None,
        outcome: AttemptOutcome | None,
        note: str | None,
    ) -> dict[str, str | int | None] | None:
        """Return an exact prior receipt or reject a substituted contract."""
        if contract_inputs is None:
            return None
        key, expected_revision = contract_inputs
        self._prune_attempt_mutation_contracts()
        contract = self._attempt_mutation_contracts.get(key)
        if contract is None:
            return None
        bound_card_id = contract.card_id if card_id is None else card_id
        bound_rule_id = contract.rule_id if rule_id is None else rule_id
        bound_rule_version = (
            contract.rule_version if rule_version is None else rule_version
        )
        if (
            contract.session_binding != self._session_binding
            or contract.action != action
            or contract.card_id != bound_card_id
            or contract.attempt_id != attempt_id
            or contract.rule_id != bound_rule_id
            or contract.rule_version != bound_rule_version
            or contract.expected_revision != expected_revision
            or not secrets.compare_digest(
                contract.payload_digest,
                self._attempt_payload_digest(
                    action=action,
                    card_id=bound_card_id,
                    attempt_id=attempt_id,
                    rule_id=bound_rule_id,
                    rule_version=bound_rule_version,
                    outcome=outcome,
                    note=note,
                ),
            )
        ):
            raise VaultConflictError("private attempt operation conflict")
        return dict(contract.receipt)

    def _prepare_new_attempt_contract(
        self, contract_inputs: tuple[str, bytes] | None
    ) -> None:
        if contract_inputs is None:
            return
        _, expected_revision = contract_inputs
        if self._revision != expected_revision:
            raise VaultConflictError("vault changed elsewhere; reopen before saving")
        self._prune_attempt_mutation_contracts()
        if len(self._attempt_mutation_contracts) >= _MAX_ATTEMPT_CONTRACTS:
            raise VaultError("private attempt contract limit exceeded")

    def _remember_attempt_contract(
        self,
        contract_inputs: tuple[str, bytes] | None,
        *,
        action: str,
        card_id: str,
        attempt_id: str | None,
        rule_id: str,
        rule_version: int,
        outcome: AttemptOutcome | None,
        note: str | None,
        receipt: dict[str, str | int | None],
    ) -> None:
        if contract_inputs is None:
            return
        key, expected_revision = contract_inputs
        self._attempt_mutation_contracts[key] = _AttemptMutationContract(
            session_binding=self._session_binding,
            action=action,
            card_id=card_id,
            attempt_id=attempt_id,
            rule_id=rule_id,
            rule_version=rule_version,
            expected_revision=expected_revision,
            payload_digest=self._attempt_payload_digest(
                action=action,
                card_id=card_id,
                attempt_id=attempt_id,
                rule_id=rule_id,
                rule_version=rule_version,
                outcome=outcome,
                note=note,
            ),
            expires_at=time.monotonic() + _ATTEMPT_CONTRACT_TTL_SECONDS,
            receipt=dict(receipt),
        )

    def add_private_attempt(
        self,
        card_id: str,
        rule_id: str,
        rule_version: int,
        outcome: AttemptOutcome | str,
        note: str | None,
        *,
        passphrase: str,
        idempotency_key: str | None = None,
        expected_private_state_revision: str | None = None,
    ) -> dict[str, str | int | None]:
        """Append one private outcome with an optional replay-safe contract."""
        self._reauthenticate(passphrase)
        with self._lock:
            self._require_unlocked()
            try:
                card_id = validate_identifier(card_id, "card_id")
                rule_id = validate_identifier(rule_id, "rule_id")
                rule_version = validate_rule_version(rule_version)
            except ValueError as exc:
                raise VaultError(str(exc)) from None
            try:
                outcome = AttemptOutcome(outcome)
            except (TypeError, ValueError):
                raise VaultError("attempt outcome is invalid") from None
            try:
                note = validate_note(note)
            except ValueError as exc:
                raise VaultError(str(exc)) from None
            contract_inputs = self._validate_attempt_contract_inputs(
                idempotency_key, expected_private_state_revision
            )
            replay = self._replay_attempt_contract(
                contract_inputs,
                action="attempt.create",
                card_id=card_id,
                attempt_id=None,
                rule_id=rule_id,
                rule_version=rule_version,
                outcome=outcome,
                note=note,
            )
            if replay is not None:
                return replay
            self._prepare_new_attempt_contract(contract_inputs)
            self._get_record(card_id)
            if len(self._attempts) >= MAX_PERSONAL_STATE_RECORDS:
                raise VaultError("private attempt limit exceeded")
            now = _timestamp()
            record = PrivateAttempt(
                attempt_id=_uuid7(),
                card_id=card_id,
                rule_id=rule_id,
                rule_version=rule_version,
                outcome=outcome,
                note=note,
                created_at=now,
                updated_at=now,
            )
            candidate = {**self._attempts, record.attempt_id: record}
            self._persist(
                self._records,
                self._child_records,
                attempts=candidate,
            )
            result = {
                **serialize_attempt(record),
                "private_state_revision": self._revision.hex(),
            }
            self._remember_attempt_contract(
                contract_inputs,
                action="attempt.create",
                card_id=card_id,
                attempt_id=None,
                rule_id=rule_id,
                rule_version=rule_version,
                outcome=outcome,
                note=note,
                receipt=result,
            )
            return result

    def update_private_attempt(
        self,
        attempt_id: str,
        outcome: AttemptOutcome | str,
        note: str | None,
        *,
        passphrase: str,
        idempotency_key: str | None = None,
        expected_private_state_revision: str | None = None,
    ) -> dict[str, str | int | None]:
        """Edit one private attempt with an optional replay-safe contract."""
        self._reauthenticate(passphrase)
        with self._lock:
            self._require_unlocked()
            try:
                attempt_id = validate_identifier(attempt_id, "attempt_id")
            except ValueError as exc:
                raise VaultError(str(exc)) from None
            contract_inputs = self._validate_attempt_contract_inputs(
                idempotency_key, expected_private_state_revision
            )
            try:
                outcome = AttemptOutcome(outcome)
            except (TypeError, ValueError):
                raise VaultError("attempt outcome is invalid") from None
            try:
                note = validate_note(note)
            except ValueError as exc:
                raise VaultError(str(exc)) from None
            replay = self._replay_attempt_contract(
                contract_inputs,
                action="attempt.update",
                card_id=None,
                attempt_id=attempt_id,
                rule_id=None,
                rule_version=None,
                outcome=outcome,
                note=note,
            )
            if replay is not None:
                return replay
            self._prepare_new_attempt_contract(contract_inputs)
            try:
                existing = self._attempts[attempt_id]
            except KeyError:
                raise VaultError("unknown private attempt") from None
            updated = PrivateAttempt(
                attempt_id=existing.attempt_id,
                card_id=existing.card_id,
                rule_id=existing.rule_id,
                rule_version=existing.rule_version,
                outcome=outcome,
                note=note,
                created_at=existing.created_at,
                updated_at=_timestamp(),
            )
            candidate = {**self._attempts, attempt_id: updated}
            self._persist(
                self._records,
                self._child_records,
                attempts=candidate,
            )
            result = {
                **serialize_attempt(updated),
                "private_state_revision": self._revision.hex(),
            }
            self._remember_attempt_contract(
                contract_inputs,
                action="attempt.update",
                card_id=existing.card_id,
                attempt_id=attempt_id,
                rule_id=existing.rule_id,
                rule_version=existing.rule_version,
                outcome=outcome,
                note=note,
                receipt=result,
            )
            return result

    def delete_private_attempt(
        self,
        attempt_id: str,
        *,
        passphrase: str,
        idempotency_key: str | None = None,
        expected_private_state_revision: str | None = None,
    ) -> dict[str, str | int | None]:
        """Delete one private history entry with an optional replay-safe contract."""
        self._reauthenticate(passphrase)
        with self._lock:
            self._require_unlocked()
            try:
                attempt_id = validate_identifier(attempt_id, "attempt_id")
            except ValueError as exc:
                raise VaultError(str(exc)) from None
            contract_inputs = self._validate_attempt_contract_inputs(
                idempotency_key, expected_private_state_revision
            )
            replay = self._replay_attempt_contract(
                contract_inputs,
                action="attempt.delete",
                card_id=None,
                attempt_id=attempt_id,
                rule_id=None,
                rule_version=None,
                outcome=None,
                note=None,
            )
            if replay is not None:
                return replay
            self._prepare_new_attempt_contract(contract_inputs)
            if attempt_id not in self._attempts:
                raise VaultError("unknown private attempt")
            existing = self._attempts[attempt_id]
            candidate = dict(self._attempts)
            del candidate[attempt_id]
            self._persist(
                self._records,
                self._child_records,
                attempts=candidate,
            )
            result: dict[str, str | int | None] = {
                "deleted": attempt_id,
                "private_state_revision": self._revision.hex(),
            }
            self._remember_attempt_contract(
                contract_inputs,
                action="attempt.delete",
                card_id=existing.card_id,
                attempt_id=attempt_id,
                rule_id=existing.rule_id,
                rule_version=existing.rule_version,
                outcome=None,
                note=None,
                receipt=result,
            )
            return result

    def add_card(
        self,
        offering_id: str,
        secret_fields: dict[str, str],
        *,
        lifecycle: CardLifecycle = CardLifecycle.ACTIVE,
        passphrase: str,
    ) -> str:
        self._reauthenticate(passphrase)
        with self._lock:
            self._require_unlocked()
            _validate_secret_fields(secret_fields, allow_empty=True)
            validate_offering_id(offering_id)
            if not isinstance(lifecycle, CardLifecycle):
                raise VaultError("invalid lifecycle")
            card_id = _uuid7()
            now = _timestamp()
            record = _Record(
                card_id=card_id,
                offering_id=offering_id,
                lifecycle=lifecycle,
                created_at=now,
                updated_at=now,
                ciphertext=b"",
            )
            record = replace(record, ciphertext=self._encrypt_record(record, secret_fields))
            candidate = {**self._records, card_id: record}
            self._persist(candidate, self._child_records)
            return card_id

    def add_child_record(
        self,
        parent_card_id: str,
        kind: ChildRecordKind,
        *,
        lifecycle: ChildRecordLifecycle = ChildRecordLifecycle.ACTIVE,
        expiry_date: str | None = None,
    ) -> str:
        """Add a non-secret child record. There is no free-text label: the display
        name is always derived from `kind`, so no secret value can be stored here."""
        with self._lock:
            self._require_unlocked()
            self._get_record(parent_card_id)
            if not isinstance(kind, ChildRecordKind):
                raise VaultError("invalid child record kind")
            if not isinstance(lifecycle, ChildRecordLifecycle):
                raise VaultError("invalid lifecycle")
            if expiry_date is not None:
                _validate_date(expiry_date)
            if len(self._child_records) >= _MAX_CHILD_RECORDS:
                raise VaultError("too many child records")
            child_id = _uuid7()
            now = _timestamp()
            record = _ChildRecord(
                child_id=child_id,
                parent_card_id=parent_card_id,
                kind=kind,
                lifecycle=lifecycle,
                created_at=now,
                updated_at=now,
                expiry_date=expiry_date,
            )
            candidate = {**self._child_records, child_id: record}
            self._persist(self._records, candidate)
            return child_id

    def add_cards(
        self,
        cards: Iterable[tuple[str, dict[str, str], CardLifecycle]],
    ) -> tuple[str, ...]:
        """Validate and persist a bounded card batch in one vault revision."""
        with self._lock:
            self._require_unlocked()
            pending: list[tuple[str, dict[str, str], CardLifecycle]] = []
            for card in cards:
                if len(pending) >= _MAX_RECORDS:
                    raise VaultError("too many cards")
                try:
                    offering_id, secret_fields, lifecycle = card
                except (TypeError, ValueError):
                    raise VaultError("invalid card import") from None
                validate_offering_id(offering_id)
                if not isinstance(lifecycle, CardLifecycle):
                    raise VaultError("invalid lifecycle")
                _validate_secret_fields(secret_fields, allow_empty=True)
                pending.append((offering_id, dict(secret_fields), lifecycle))
            if not pending:
                raise VaultError("at least one card is required")
            if len(self._records) + len(pending) > _MAX_RECORDS:
                raise VaultError("too many cards")

            candidate = dict(self._records)
            card_ids: list[str] = []
            for offering_id, secret_fields, lifecycle in pending:
                card_id = _uuid7()
                now = _timestamp()
                record = _Record(
                    card_id=card_id,
                    offering_id=offering_id,
                    lifecycle=lifecycle,
                    created_at=now,
                    updated_at=now,
                    ciphertext=b"",
                )
                record = replace(record, ciphertext=self._encrypt_record(record, secret_fields))
                candidate[card_id] = record
                card_ids.append(card_id)
            self._persist(candidate, self._child_records, audit_action="import")
            return tuple(card_ids)

    def reconcile_cards(
        self, cards: Iterable[ReconciliationCard]
    ) -> ReconciliationResult:
        """Reconcile a complete private source batch atomically and idempotently.

        A source identity is encrypted into its matched record. Existing
        records are never overwritten: a PAN match may only bind a previously
        unbound record by adding missing values and the source identity. Any
        ambiguity, mismatch, duplicate, or lifecycle conflict aborts the whole
        batch before persistence.
        """
        with self._lock:
            self._require_unlocked()
            pending: list[ReconciliationCard] = []
            seen_sources: set[str] = set()
            seen_pans: set[str] = set()
            for card in cards:
                if not isinstance(card, ReconciliationCard):
                    raise VaultError("reconciliation input is invalid")
                validate_reconciliation_id(card.source_identity)
                if card.source_identity in seen_sources:
                    raise VaultConflictError("reconciliation conflict")
                if card.offering_id is not None:
                    validate_offering_id(card.offering_id)
                if not isinstance(card.lifecycle, CardLifecycle):
                    raise VaultError("reconciliation input is invalid")
                values = dict(card.secret_fields)
                if values.get("reconciliation_id") not in (None, card.source_identity):
                    raise VaultConflictError("reconciliation conflict")
                values["reconciliation_id"] = card.source_identity
                _validate_secret_fields(values)
                pan = values.get("pan")
                if pan is None:
                    raise VaultError("reconciliation input is invalid")
                validate_reconciliation_pan(pan)
                pan_digits = _pan_digits(pan)
                assert pan_digits is not None
                if pan_digits in seen_pans:
                    raise VaultConflictError("reconciliation conflict")
                seen_sources.add(card.source_identity)
                seen_pans.add(pan_digits)
                pending.append(
                    ReconciliationCard(
                        source_identity=card.source_identity,
                        offering_id=card.offering_id,
                        lifecycle=card.lifecycle,
                        secret_fields=values,
                    )
                )
            if not pending:
                raise VaultError("reconciliation input is empty")
            decrypted: dict[str, dict[str, str]] = {}
            by_source: dict[str, _Record] = {}
            by_pan: dict[str, _Record] = {}
            for record in self._records.values():
                values = self._decrypt_record(record)
                decrypted[record.card_id] = values
                source = values.get("reconciliation_id")
                if source is not None:
                    validate_reconciliation_id(source)
                    if source in by_source:
                        raise VaultConflictError("reconciliation conflict")
                    by_source[source] = record
                pan_digits = _pan_digits(values.get("pan"))
                if pan_digits is not None:
                    if pan_digits in by_pan:
                        raise VaultConflictError("reconciliation conflict")
                    by_pan[pan_digits] = record

            candidate = dict(self._records)
            imported = bound_existing = unchanged = 0
            changed = False
            for incoming in pending:
                incoming_pan = _pan_digits(incoming.secret_fields["pan"])
                assert incoming_pan is not None
                current = by_source.get(incoming.source_identity)
                if current is not None:
                    current_values = decrypted[current.card_id]
                    if _pan_digits(current_values.get("pan")) != incoming_pan:
                        raise VaultConflictError("reconciliation conflict")
                    if current.lifecycle is not incoming.lifecycle:
                        raise VaultConflictError("reconciliation conflict")
                    if incoming.offering_id is not None and incoming.offering_id != current.offering_id:
                        raise VaultConflictError("reconciliation conflict")
                    merged = dict(current_values)
                    for key, value in incoming.secret_fields.items():
                        if key in merged and merged[key] != value:
                            raise VaultConflictError("reconciliation conflict")
                        merged.setdefault(key, value)
                    _validate_secret_fields(merged, allow_empty=True)
                    if merged != current_values:
                        now = _timestamp()
                        updated = replace(current, updated_at=now)
                        updated = replace(updated, ciphertext=self._encrypt_record(updated, merged))
                        candidate[current.card_id] = updated
                        decrypted[current.card_id] = merged
                        by_source[incoming.source_identity] = updated
                        changed = True
                        bound_existing += 1
                    else:
                        unchanged += 1
                    continue

                current = by_pan.get(incoming_pan)
                if current is not None:
                    current_values = decrypted[current.card_id]
                    if current_values.get("reconciliation_id") is not None:
                        raise VaultConflictError("reconciliation conflict")
                    if incoming.offering_id is not None and incoming.offering_id != current.offering_id:
                        raise VaultConflictError("reconciliation conflict")
                    if current.lifecycle is not incoming.lifecycle:
                        raise VaultConflictError("reconciliation conflict")
                    merged = dict(current_values)
                    for key, value in incoming.secret_fields.items():
                        if key in merged and merged[key] != value:
                            raise VaultConflictError("reconciliation conflict")
                        merged.setdefault(key, value)
                    _validate_secret_fields(merged, allow_empty=True)
                    now = _timestamp()
                    updated = replace(current, updated_at=now)
                    updated = replace(updated, ciphertext=self._encrypt_record(updated, merged))
                    candidate[current.card_id] = updated
                    decrypted[current.card_id] = merged
                    by_source[incoming.source_identity] = updated
                    changed = True
                    bound_existing += 1
                    continue

                offering_id = incoming.offering_id or f"unmatched-{incoming.source_identity}"
                if len(candidate) >= _MAX_RECORDS:
                    raise VaultError("too many cards")
                now = _timestamp()
                card_id = _uuid7()
                record = _Record(
                    card_id=card_id,
                    offering_id=offering_id,
                    lifecycle=incoming.lifecycle,
                    created_at=now,
                    updated_at=now,
                    ciphertext=b"",
                )
                record = replace(record, ciphertext=self._encrypt_record(record, incoming.secret_fields))
                candidate[card_id] = record
                decrypted[card_id] = dict(incoming.secret_fields)
                by_source[incoming.source_identity] = record
                by_pan[incoming_pan] = record
                imported += 1
                changed = True
            if changed:
                self._persist(candidate, self._child_records, audit_action="import")
            return ReconciliationResult(imported, bound_existing, unchanged)

    def replace_card(
        self,
        card_id: str,
        secret_fields: dict[str, str],
        *,
        lifecycle: CardLifecycle = CardLifecycle.CLOSED,
        passphrase: str,
    ) -> str:
        self._reauthenticate(passphrase)
        with self._lock:
            self._require_unlocked()
            if not isinstance(lifecycle, CardLifecycle):
                raise VaultError("invalid lifecycle")
            if lifecycle not in {
                CardLifecycle.EXPIRED,
                CardLifecycle.LOST,
                CardLifecycle.STOLEN,
                CardLifecycle.CLOSED,
                CardLifecycle.RETIRED,
                CardLifecycle.ARCHIVED,
            }:
                raise VaultError("replacement requires a non-active lifecycle")
            old = self._get_record(card_id)
            if old.replacement_card_id is not None:
                raise VaultError("card already has a replacement")
            _validate_secret_fields(secret_fields, allow_empty=True)
            new_id = _uuid7()
            now = _timestamp()
            new_record = _Record(
                card_id=new_id,
                offering_id=old.offering_id,
                lifecycle=CardLifecycle.ACTIVE,
                created_at=now,
                updated_at=now,
                ciphertext=b"",
            )
            new_record = replace(new_record, ciphertext=self._encrypt_record(new_record, secret_fields))
            old_values = self._decrypt_record(old)
            updated_old = replace(old, lifecycle=lifecycle, replacement_card_id=new_id, updated_at=now)
            updated_old = replace(updated_old, ciphertext=self._encrypt_record(updated_old, old_values))
            candidate = {**self._records, old.card_id: updated_old, new_id: new_record}
            self._persist(
                candidate,
                self._child_records,
                audit_action="replace",
                audit_record_ref=f"{old.card_id}:{new_id}",
            )
            return new_id

    def _reauthenticate(self, passphrase: str) -> None:
        """Verify the current vault key for one protected action."""
        with self._lock:
            self._require_unlocked()
            try:
                candidate = bytearray(
                    _unwrap_dek({"wrapped_dek": self._wrapped_dek}, self._kdf,
                                _validate_passphrase(passphrase))
                )
                current = self._require_unlocked()
                if not secrets.compare_digest(candidate, current):
                    raise VaultAccessError("reauthentication failed")
            except (InvalidTag, ValueError, VaultError):
                raise VaultAccessError("reauthentication failed") from None
            finally:
                if "candidate" in locals():
                    _zero(candidate)

    def edit_card(self, card_id: str, changes: dict[str, str], *, passphrase: str) -> None:
        self._reauthenticate(passphrase)
        with self._lock:
            record = self._get_record(card_id)
            values = self._decrypt_record(record)
            _validate_secret_fields(changes)
            values.update(changes)
            _validate_secret_fields(values, allow_empty=True)
            updated = replace(record, updated_at=_timestamp())
            updated = replace(updated, ciphertext=self._encrypt_record(updated, values))
            self._persist(
                {**self._records, card_id: updated},
                self._child_records,
                audit_action="edit",
                audit_record_ref=card_id,
            )

    def transition_card(self, card_id: str, lifecycle: CardLifecycle, *, passphrase: str) -> bool:
        self._reauthenticate(passphrase)
        with self._lock:
            if not isinstance(lifecycle, CardLifecycle):
                raise VaultError("invalid lifecycle")
            record = self._get_record(card_id)
            values = self._decrypt_record(record)
            updated = replace(record, lifecycle=lifecycle, updated_at=_timestamp())
            updated = replace(updated, ciphertext=self._encrypt_record(updated, values))
            self._persist(
                {**self._records, card_id: updated},
                self._child_records,
                audit_action="lifecycle",
                audit_record_ref=card_id,
            )
            return lifecycle in {CardLifecycle.EXPIRED, CardLifecycle.LOST,
                                 CardLifecycle.STOLEN, CardLifecycle.CLOSED,
                                 CardLifecycle.RETIRED}

    def erase_cvv_pin(self, card_id: str, *, passphrase: str) -> None:
        self._reauthenticate(passphrase)
        with self._lock:
            record = self._get_record(card_id)
            values = self._decrypt_record(record)
            changed = {key: value for key, value in values.items() if key not in {"cvv", "pin"}}
            updated = replace(record, updated_at=_timestamp())
            updated = replace(updated, ciphertext=self._encrypt_record(updated, changed))
            self._persist(
                {**self._records, card_id: updated},
                self._child_records,
                audit_action="secret_erase",
                audit_record_ref=card_id,
            )

    def delete_card(self, card_id: str, *, confirmation: str, passphrase: str) -> None:
        self._reauthenticate(passphrase)
        if confirmation != "DELETE CARD":
            raise VaultError("typed confirmation required")
        with self._lock:
            self._get_record(card_id)
            candidate = dict(self._records)
            del candidate[card_id]
            children = {key: value for key, value in self._child_records.items()
                        if value.parent_card_id != card_id}
            aggregates = {
                key: value
                for key, value in self._manual_aggregates.items()
                if value.card_id != card_id
            }
            attempts = {
                key: value
                for key, value in self._attempts.items()
                if value.card_id != card_id
            }
            self._persist(
                candidate,
                children,
                manual_aggregates=aggregates,
                attempts=attempts,
                audit_action="delete",
                audit_record_ref=card_id,
            )

    def purge_card(self, card_id: str, *, confirmation: str, passphrase: str) -> None:
        self._reauthenticate(passphrase)
        if confirmation != "DELETE CARD":
            raise VaultError("typed confirmation required")
        with self._lock:
            self._get_record(card_id)
            candidate = dict(self._records)
            del candidate[card_id]
            children = {
                key: value
                for key, value in self._child_records.items()
                if value.parent_card_id != card_id
            }
            self._persist(
                candidate,
                children,
                audit_action="purge",
                audit_record_ref=card_id,
            )

    def authorize_action(
        self, card_id: str, action: str, *, passphrase: str,
        field: str | None = None, ttl_seconds: float = 15.0,
    ) -> RevealAuthorization:
        """Mint a single-use token bound to action, record, and this session."""
        if action not in {"reveal", "copy"} or ttl_seconds <= 0 or ttl_seconds > 30:
            raise VaultError("protected action unavailable")
        if field not in _REVEALABLE_SECRET_FIELDS:
            raise VaultAccessError("protected action unavailable")
        self._reauthenticate(passphrase)
        with self._lock:
            record = self._get_record(card_id)
            if field not in self._decrypt_record(record):
                raise VaultAccessError("protected action unavailable")
            nonce = secrets.token_urlsafe(24)
            self._reveal_authorizations[nonce] = (
                card_id, action, field, self._session_binding, time.monotonic() + ttl_seconds
            )
            return RevealAuthorization(nonce)

    def consume_action(self, authorization: RevealAuthorization, *, action: str) -> str:
        """Consume a token for exactly the action it was minted for."""
        if action not in {"reveal", "copy"}:
            raise VaultAccessError("protected action unavailable")
        with self._lock:
            if not isinstance(authorization, RevealAuthorization):
                raise VaultAccessError("protected action unavailable")
            details = self._reveal_authorizations.pop(authorization._nonce, None)
            if details is None:
                raise VaultAccessError("protected action unavailable")
            card_id, bound_action, field, session_binding, expires_at = details
            if bound_action != action or session_binding != self._session_binding or field is None:
                raise VaultAccessError("protected action unavailable")
            if time.monotonic() > expires_at:
                raise VaultAccessError("protected action unavailable")
            value = self._decrypt_record(self._get_record(card_id)).get(field)
            if not isinstance(value, str):
                raise VaultAccessError("protected action unavailable")
            if self._audit_log is not None:
                try:
                    self._audit_log.record(action, record_ref=card_id)
                except Exception as exc:
                    raise VaultError("protected audit unavailable") from exc
            return value

    def list_expiry_signals(self, *, today: date | None = None) -> tuple[dict[str, str], ...]:
        """Return bounded card expiry buckets; never return month or year."""
        from datetime import date as date_type

        current = today or date_type.today()
        with self._lock:
            self._ensure_unlocked()
            result: list[dict[str, str]] = []
            for record in self._records.values():
                values = self._decrypt_record(record)
                month, year = values.get("expiry_month"), values.get("expiry_year")
                if not (month and year and month.isdigit() and year.isdigit()):
                    continue
                try:
                    expiry = date_type(int(year), int(month), 1)
                except ValueError:
                    continue
                signal = "expired" if expiry < date_type(current.year, current.month, 1) else (
                    "expiring_soon" if (expiry.year * 12 + expiry.month) -
                    (current.year * 12 + current.month) <= 1 else "active"
                )
                result.append({"card_id": record.card_id, "signal": signal})
            return tuple(result)

    def authorize_reveal(
        self,
        card_id: str,
        field: str,
        *,
        passphrase: str,
        ttl_seconds: float = 15.0,
    ) -> RevealAuthorization:
        """Reauthenticate and mint a one-use authorization for a UI reveal.

        Authorization transiently decrypts the selected record only to confirm
        the requested field exists. Plaintext is returned only by consume_reveal.
        """
        with self._lock:
            self._require_unlocked()
            if ttl_seconds <= 0 or ttl_seconds > 30:
                raise VaultError("reveal ttl must be between 0 and 30 seconds")
            record = self._get_record(card_id)
            if field not in _REVEALABLE_SECRET_FIELDS:
                raise VaultAccessError("reveal is unavailable")
            try:
                passphrase = _validate_passphrase(passphrase)
                candidate_dek = bytearray(
                    _unwrap_dek({"wrapped_dek": self._wrapped_dek}, self._kdf, passphrase)
                )
            except (InvalidTag, ValueError, VaultError):
                raise VaultAccessError("reauthentication failed") from None
            try:
                current_dek = self._require_unlocked()
                if not secrets.compare_digest(candidate_dek, current_dek):
                    raise VaultAccessError("reauthentication failed")
                if field not in self._decrypt_record(record):
                    raise VaultAccessError("reveal is unavailable")
                nonce = secrets.token_urlsafe(24)
                self._reveal_authorizations[nonce] = (
                    card_id, "reveal", field, self._session_binding,
                    time.monotonic() + ttl_seconds
                )
                return RevealAuthorization(nonce)
            finally:
                _zero(candidate_dek)

    def consume_reveal(self, authorization: RevealAuthorization) -> str:
        """Consume an authorization and return plaintext only for this UI action."""
        with self._lock:
            if not isinstance(authorization, RevealAuthorization):
                raise VaultAccessError("reveal is unavailable")
            details = self._reveal_authorizations.pop(authorization._nonce, None)
            if details is None:
                raise VaultAccessError("reveal is unavailable")
            card_id, action, field, session_binding, expires_at = details
            if action != "reveal" or session_binding != self._session_binding or field is None:
                raise VaultAccessError("reveal is unavailable")
            if time.monotonic() > expires_at:
                raise VaultAccessError("reveal is unavailable")
            values = self._decrypt_record(self._get_record(card_id))
            value = values.get(field)
            if not isinstance(value, str):
                raise VaultAccessError("reveal is unavailable")
            if self._audit_log is not None:
                try:
                    self._audit_log.record("reveal", record_ref=card_id)
                except Exception as exc:
                    raise VaultError("protected audit unavailable") from exc
            return value

    def authorize_reconciliation(
        self,
        card_id: str,
        proposal_digest: str,
        action: str,
        intent_digest: str,
        mutation: dict[str, Any],
        *,
        passphrase: str,
        ttl_seconds: float = 30.0,
    ) -> ReconciliationAuthorization:
        """Reauthenticate for exactly one proposed reconciliation mutation.

        The proposal digest is opaque to the vault.  The caller must present
        the same digest when applying the change, preventing token reuse for a
        different record or edited proposal.
        """
        with self._lock:
            self._require_unlocked()
            if (not isinstance(proposal_digest, str) or len(proposal_digest) != 64
                    or not isinstance(intent_digest, str) or len(intent_digest) != 64
                    or not isinstance(action, str) or action not in {"confirm", "defer", "reject", "correct"}):
                raise VaultError("proposal digest is invalid")
            if ttl_seconds <= 0 or ttl_seconds > 60:
                raise VaultError("reconciliation ttl must be between 0 and 60 seconds")
            current = self._get_record(card_id)
            normalized = _normalize_reconciliation_mutation(mutation)
            if (normalized["record"] != card_id or normalized["action"] != action
                    or normalized["expected_old"] != {
                        "offering_id": current.offering_id,
                        "lifecycle": current.lifecycle.value,
                        "replacement_card_id": current.replacement_card_id,
                        "updated_at": current.updated_at,
                    }
                    or normalized["expected_revision"] != self._revision.hex()):
                raise VaultConflictError("reconciliation state changed")
            try:
                candidate_dek = bytearray(_unwrap_dek(
                    {"wrapped_dek": self._wrapped_dek}, self._kdf, _validate_passphrase(passphrase)
                ))
            except (InvalidTag, ValueError, VaultError):
                raise VaultAccessError("reauthentication failed") from None
            try:
                if not secrets.compare_digest(candidate_dek, self._require_unlocked()):
                    raise VaultAccessError("reauthentication failed")
                nonce = secrets.token_urlsafe(24)
                self._reconciliation_authorizations[nonce] = (
                    card_id, proposal_digest, action, intent_digest, self._revision,
                    time.monotonic() + ttl_seconds, normalized
                )
                return ReconciliationAuthorization(nonce)
            finally:
                _zero(candidate_dek)

    def authorize_consolidation(
        self, plan_digest: str, action: str, *, passphrase: str, ttl_seconds: float = 30.0
    ) -> ConsolidationAuthorization:
        """Freshly authorize exactly one local import plan.

        The importer owns the canonical plan construction.  The vault binds
        the approved digest to its current revision and consumes the nonce
        before the atomic reconciliation write, so an unlocked/keyring-opened
        session alone cannot apply a plan.
        """
        with self._lock:
            self._require_unlocked()
            if (
                not isinstance(plan_digest, str)
                or len(plan_digest) != 64
                or not isinstance(action, str)
                or action not in {"consolidate_apply", "consolidate_recover"}
                or ttl_seconds <= 0
                or ttl_seconds > 60
            ):
                raise VaultError("consolidation authorization is invalid")
            self._reauthenticate(passphrase)
            nonce = secrets.token_urlsafe(24)
            self._consolidation_authorizations[nonce] = (
                plan_digest,
                action,
                self._revision,
                time.monotonic() + ttl_seconds,
            )
            return ConsolidationAuthorization(nonce)

    def consume_consolidation(
        self, authorization: ConsolidationAuthorization, plan_digest: str, action: str
    ) -> None:
        """Consume an exact-plan authorization immediately before import."""
        with self._lock:
            if not isinstance(authorization, ConsolidationAuthorization):
                raise VaultAccessError("consolidation authorization is invalid")
            details = self._consolidation_authorizations.pop(authorization._nonce, None)
            if details is None:
                raise VaultAccessError("consolidation authorization is invalid")
            expected_digest, expected_action, expected_revision, expires_at = details
            if (
                time.monotonic() > expires_at
                or not secrets.compare_digest(expected_digest, plan_digest)
                or expected_action != action
                or self._revision != expected_revision
            ):
                raise VaultConflictError("vault changed elsewhere; reopen before saving")

    def derive_private_import_artifact_key(self) -> bytearray:
        """Derive a process-local key for encrypted import recovery artifacts.

        The vault data-encryption key never crosses this boundary.  The caller
        owns and zeroizes the returned short-lived derived key after passing it
        to the local consolidator; it must never be serialized or returned by
        an HTTP route.
        """
        with self._lock:
            dek = self._require_unlocked()
            return bytearray(
                HKDF(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=None,
                    info=_PRIVATE_IMPORT_ARTIFACT_INFO,
                ).derive(dek)
            )

    def apply_reconciliation_metadata(
        self,
        authorization: ReconciliationAuthorization,
        *,
        mutation: dict[str, Any],
    ) -> None:
        """Atomically apply only a previously authorized metadata proposal."""
        with self._lock:
            if not isinstance(authorization, ReconciliationAuthorization):
                raise VaultAccessError("reconciliation authorization is invalid")
            details = self._reconciliation_authorizations.pop(authorization._nonce, None)
            if details is None:
                raise VaultAccessError("reconciliation authorization is invalid")
            card_id, expected_digest, expected_action, expected_intent, expected_revision, expires_at, expected_mutation = details
            normalized = _normalize_reconciliation_mutation(mutation)
            if (time.monotonic() > expires_at or normalized != expected_mutation
                    or expected_digest != normalized["proposal_digest"]
                    or expected_action != normalized["action"]
                    or expected_intent != normalized["intent_digest"]):
                raise VaultAccessError("reconciliation authorization is invalid")
            if self._revision != expected_revision:
                raise VaultConflictError("vault changed elsewhere; reopen before saving")
            metadata = normalized["metadata"]
            action = normalized["action"]
            if action in {"defer", "reject"}:
                self._record_reconciliation_event(card_id, action, normalized["proposal_digest"], normalized["intent_digest"])
                return
            new_values = normalized["new"]
            lifecycle = CardLifecycle(new_values["lifecycle"])
            offering_id = new_values["offering_id"]
            replacement_card_id = new_values["replacement_card_id"]
            candidate = dict(self._records)
            current = self._get_record(card_id)
            updated_at = current.updated_at if replacement_card_id == current.replacement_card_id else _timestamp()
            updated = replace(current, offering_id=offering_id, lifecycle=lifecycle,
                              replacement_card_id=replacement_card_id, updated_at=updated_at)
            candidate[card_id] = updated
            self._validate_replacement_graph(candidate)
            values = self._decrypt_record(current)
            values["reconciliation_metadata"] = metadata
            updated = replace(updated, ciphertext=self._encrypt_record(updated, values))
            candidate[card_id] = updated
            self._persist(candidate, self._child_records)

    def _record_reconciliation_event(self, card_id: str, action: str, proposal_digest: str,
                                     intent_digest: str) -> None:
        event = {"record": card_id, "action": action, "proposal_digest": proposal_digest,
                 "intent_digest": intent_digest, "at": _timestamp()}
        events = [*self._reconciliation_events, event]
        if len(events) > 1000:
            raise VaultError("reconciliation event limit exceeded")
        self._persist(self._records, self._child_records, reconciliation_events=events)

    @staticmethod
    def _validate_replacement_graph(records: dict[str, _Record]) -> None:
        _validate_replacement_graph(records, error_type=VaultError)

    def export_rewrapped(self, destination: Path, new_passphrase: str) -> None:
        """Write a self-contained encrypted copy under a new passphrase.

        The protected recovery service retains record ciphertext and only
        regenerates the envelope wrapping and MAC; plaintext remains inside
        this unlocked local session.
        """
        with self._lock:
            dek = bytes(self._require_unlocked())
            new_passphrase = _validate_passphrase(new_passphrase)
            kdf = _KdfParameters(salt=secrets.token_bytes(16))
            envelope = _new_envelope(kdf, dek, new_passphrase)
            encoded = _encode_envelope(
                _serialize_envelope(
                    kdf,
                    str(envelope["wrapped_dek"]),
                    self._records,
                    self._child_records,
                    dek,
                    reconciliation_events=self._reconciliation_events,
                    manual_aggregates=self._manual_aggregates,
                    attempts=self._attempts,
                    detail_credential=self._detail_credential,
                )
            )
            _validate_write_bounds(
                encoded,
                self._records,
                self._child_records,
                self._manual_aggregates,
                self._attempts,
            )
            with _exclusive_lock(destination, self._store._permissions):
                if destination.exists():
                    raise VaultError("export already exists")
                _atomic_write(destination, encoded, self._store._permissions, backup=False)
            if self._audit_log is not None:
                try:
                    self._audit_log.record("export", record_ref=f"export:{self._revision.hex()}")
                except Exception as exc:
                    with contextlib.suppress(OSError):
                        destination.unlink()
                    raise VaultError("protected audit unavailable") from exc

    def _get_record(self, card_id: str) -> _Record:
        with self._lock:
            try:
                uuid.UUID(card_id)
                return self._records[card_id]
            except (KeyError, ValueError, AttributeError) as exc:
                raise VaultError("unknown card") from exc

    def _encrypt_record(self, record: _Record, values: dict[str, str]) -> bytes:
        with self._lock:
            dek = self._require_unlocked()
            nonce = secrets.token_bytes(12)
            plaintext = json.dumps(values, separators=(",", ":"), sort_keys=True).encode("utf-8")
            return nonce + AESGCM(dek).encrypt(nonce, plaintext, _record_aad(record))

    def _decrypt_record(self, record: _Record) -> dict[str, str]:
        with self._lock:
            dek = self._require_unlocked()
            try:
                nonce, ciphertext = record.ciphertext[:12], record.ciphertext[12:]
                raw = AESGCM(dek).decrypt(nonce, ciphertext, _record_aad(record))
                values: Any = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError, InvalidTag, json.JSONDecodeError):
                raise VaultAccessError("encrypted record is invalid") from None
            if not isinstance(values, dict) or not all(
                isinstance(key, str) and isinstance(value, str) for key, value in values.items()
            ):
                raise VaultAccessError("encrypted record is invalid")
            return values

    def _persist(
        self, cards: dict[str, _Record], child_records: dict[str, _ChildRecord],
        *, reconciliation_events: list[dict[str, str]] | None = None,
        manual_aggregates: dict[str, ManualSpendAggregate] | None = None,
        attempts: dict[str, PrivateAttempt] | None = None,
        detail_credential: dict[str, Any] | None | object = _DETAIL_CREDENTIAL_UNSET,
        audit_action: str | None = None,
        audit_record_ref: str | None = None,
    ) -> None:
        with self._lock:
            dek = self._require_unlocked()
            next_aggregates = (
                self._manual_aggregates if manual_aggregates is None else manual_aggregates
            )
            next_attempts = self._attempts if attempts is None else attempts
            next_detail_credential = (
                self._detail_credential
                if detail_credential is _DETAIL_CREDENTIAL_UNSET
                else cast(dict[str, Any] | None, detail_credential)
            )
            encoded = _encode_envelope(
                _serialize_envelope(self._kdf, self._wrapped_dek, cards, child_records, dek,
                                    reconciliation_events=reconciliation_events
                                    if reconciliation_events is not None else self._reconciliation_events,
                                    manual_aggregates=next_aggregates,
                                    attempts=next_attempts,
                                    detail_credential=next_detail_credential)
            )
            _validate_write_bounds(
                encoded, cards, child_records, next_aggregates, next_attempts
            )
            with _exclusive_lock(self._store.path, self._store._permissions):
                try:
                    current_revision = _bounded_file_digest(self._store.path)
                    previous = (
                        self._store.path.read_bytes()
                        if audit_action is not None and self._audit_log is not None
                        else None
                    )
                except (OSError, VaultError):
                    raise VaultConflictError("vault changed elsewhere; reopen before saving") from None
                if current_revision != self._revision:
                    raise VaultConflictError("vault changed elsewhere; reopen before saving")
                _atomic_write(self._store.path, encoded, self._store._permissions, backup=True)
                if audit_action is not None and self._audit_log is not None:
                    try:
                        record_ref = audit_record_ref or (
                            f"{audit_action}:{_digest(encoded).hex()}"
                        )
                        self._audit_log.record(audit_action, record_ref=record_ref)
                    except Exception as exc:
                        if previous is None:
                            raise VaultError("protected audit unavailable") from exc
                        try:
                            _atomic_write(
                                self._store.path,
                                previous,
                                self._store._permissions,
                                backup=False,
                            )
                        except Exception as rollback_error:
                            raise VaultError("protected audit unavailable") from rollback_error
                        raise VaultError("protected audit unavailable") from None
            self._revision = _digest(encoded)
            self._records = cards
            self._child_records = child_records
            self._manual_aggregates = dict(next_aggregates)
            self._attempts = dict(next_attempts)
            self._detail_credential = (
                dict(next_detail_credential) if next_detail_credential is not None else None
            )
            if reconciliation_events is not None:
                self._reconciliation_events = list(reconciliation_events)

    def _auto_lock_if_idle(self) -> None:
        with self._lock:
            if self._dek is not None and (
                time.monotonic() - self._last_activity > self._idle_timeout_seconds
                or time.monotonic() > self._expires_at
            ):
                self.lock()

    def _ensure_unlocked(self) -> bytearray:
        with self._lock:
            self._auto_lock_if_idle()
            if self._dek is None:
                raise VaultAccessError("vault is locked")
            return self._dek

    def _require_unlocked(self) -> bytearray:
        with self._lock:
            dek = self._ensure_unlocked()
            self._last_activity = time.monotonic()
            return dek


def _new_envelope(kdf: _KdfParameters, dek: bytes, passphrase: str) -> dict[str, Any]:
    kek = bytearray(_derive_kek(passphrase, kdf))
    try:
        nonce = secrets.token_bytes(12)
        wrapped = AESGCM(kek).encrypt(nonce, dek, _DEK_AAD)
    finally:
        _zero(kek)
    envelope = {
        "version": _FORMAT_VERSION,
        "kdf": _serialize_kdf(kdf),
        "wrapped_dek": _b64(nonce + wrapped),
        "records": [],
        "child_records": [],
        "private_state": _encrypt_private_state({}, {}, dek),
    }
    envelope["mac"] = _envelope_mac(envelope, dek)
    return envelope


def _encrypt_private_state(
    manual_aggregates: dict[str, ManualSpendAggregate],
    attempts: dict[str, PrivateAttempt],
    dek: bytes | bytearray,
    detail_credential: dict[str, Any] | None = None,
) -> str:
    payload = {
        "version": _PRIVATE_STATE_VERSION,
        "manual_aggregates": [
            serialize_aggregate(record)
            for record in sorted(manual_aggregates.values(), key=lambda item: item.aggregate_id)
        ],
        "attempts": [
            serialize_attempt(record)
            for record in sorted(attempts.values(), key=lambda item: item.attempt_id)
        ],
    }
    if detail_credential is not None:
        payload["detail_credential"] = detail_credential
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(dek).encrypt(nonce, _encode_envelope(payload), _PRIVATE_STATE_AAD)
    return _b64(nonce + ciphertext)


def _parse_private_state(
    envelope: dict[str, Any], dek: bytes, records: dict[str, _Record]
) -> tuple[dict[str, ManualSpendAggregate], dict[str, PrivateAttempt], dict[str, Any] | None]:
    raw_blob = envelope.get("private_state")
    if raw_blob is None:
        # Vault format v2 predates this optional encrypted section.
        return {}, {}, None
    try:
        blob = _unb64(raw_blob)
        if len(blob) < 12 + 16:
            raise ValueError
        payload = json.loads(
            AESGCM(dek).decrypt(blob[:12], blob[12:], _PRIVATE_STATE_AAD).decode("utf-8")
        )
        if not isinstance(payload, dict) or not {
            "version", "manual_aggregates", "attempts"
        }.issubset(payload) or set(payload) - {
            "version", "manual_aggregates", "attempts", "detail_credential"
        } or payload["version"] != _PRIVATE_STATE_VERSION:
            raise ValueError
        raw_aggregates = payload["manual_aggregates"]
        raw_attempts = payload["attempts"]
        if (
            not isinstance(raw_aggregates, list)
            or not isinstance(raw_attempts, list)
            or len(raw_aggregates) + len(raw_attempts) > MAX_PERSONAL_STATE_RECORDS
        ):
            raise ValueError
        card_ids = set(records)
        aggregates: dict[str, ManualSpendAggregate] = {}
        aggregate_ids: set[str] = set()
        for raw in raw_aggregates:
            aggregate_record = validate_aggregate_record(raw, card_ids=card_ids)
            key = aggregate_context_key(
                aggregate_record.card_id,
                aggregate_record.rule_id,
                aggregate_record.rule_version,
            )
            if key in aggregates or aggregate_record.aggregate_id in aggregate_ids:
                raise ValueError
            aggregates[key] = aggregate_record
            aggregate_ids.add(aggregate_record.aggregate_id)
        attempts: dict[str, PrivateAttempt] = {}
        for raw in raw_attempts:
            attempt_record = validate_attempt_record(raw, card_ids=card_ids)
            if attempt_record.attempt_id in attempts:
                raise ValueError
            attempts[attempt_record.attempt_id] = attempt_record
        raw_detail_credential = payload.get("detail_credential")
        detail_credential = (
            _validate_detail_credential_envelope(raw_detail_credential)
            if raw_detail_credential is not None
            else None
        )
        return aggregates, attempts, detail_credential
    except (InvalidTag, KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise VaultAccessError("encrypted private state is invalid") from None


def _serialize_envelope(
    kdf: _KdfParameters,
    wrapped_dek: str,
    cards: dict[str, _Record],
    child_records: dict[str, _ChildRecord],
    dek: bytes | bytearray,
    *,
    reconciliation_events: list[dict[str, str]] | None = None,
    manual_aggregates: dict[str, ManualSpendAggregate] | None = None,
    attempts: dict[str, PrivateAttempt] | None = None,
    detail_credential: dict[str, Any] | None = None,
) -> dict[str, Any]:
    envelope = {
        "version": _FORMAT_VERSION,
        "kdf": _serialize_kdf(kdf),
        "wrapped_dek": wrapped_dek,
        "records": [
            {
                "card_id": record.card_id,
                "offering_id": record.offering_id,
                "lifecycle": record.lifecycle.value,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
                "ciphertext": _b64(record.ciphertext),
                **(
                    {"replacement_card_id": record.replacement_card_id}
                    if record.replacement_card_id
                    else {}
                ),
            }
            for record in cards.values()
        ],
        "child_records": [
            {
                "child_id": record.child_id,
                "parent_card_id": record.parent_card_id,
                "kind": record.kind.value,
                "lifecycle": record.lifecycle.value,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
                **({"expiry_date": record.expiry_date} if record.expiry_date else {}),
            }
            for record in child_records.values()
        ],
        "reconciliation_events": list(reconciliation_events or []),
        "private_state": _encrypt_private_state(
            manual_aggregates or {}, attempts or {}, dek, detail_credential
        ),
    }
    envelope["mac"] = _envelope_mac(envelope, dek)
    return envelope


def _serialize_kdf(kdf: _KdfParameters) -> dict[str, Any]:
    return {
        "algorithm": "argon2id",
        "salt": _b64(kdf.salt),
        "time_cost": kdf.time_cost,
        "memory_cost_kib": kdf.memory_cost_kib,
        "parallelism": kdf.parallelism,
    }


def _parse_kdf(envelope: dict[str, Any]) -> _KdfParameters:
    if envelope.get("version") != _FORMAT_VERSION:
        raise VaultAccessError("unsupported vault format")
    raw = envelope["kdf"]
    if not isinstance(raw, dict) or raw.get("algorithm") != "argon2id":
        raise VaultAccessError("unsupported vault format")
    values = (raw.get("time_cost"), raw.get("memory_cost_kib"), raw.get("parallelism"))
    if any(type(value) is not int for value in values):
        raise VaultAccessError("unsupported vault format")
    time_cost, memory_cost_kib, parallelism = cast(tuple[int, int, int], values)
    kdf = _KdfParameters(
        salt=_unb64(raw["salt"]),
        time_cost=time_cost,
        memory_cost_kib=memory_cost_kib,
        parallelism=parallelism,
    )
    if not (
        16 <= len(kdf.salt) <= 64
        and 2 <= kdf.time_cost <= 5
        and 32_768 <= kdf.memory_cost_kib <= 131_072
        and 1 <= kdf.parallelism <= 2
    ):
        raise VaultAccessError("unsupported vault format")
    return kdf


def _envelope_mac(envelope: dict[str, Any], dek: bytes | bytearray) -> str:
    """MAC the complete ordered envelope; rollback needs an external anchor."""
    key = bytearray(
        HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_ENVELOPE_MAC_INFO).derive(
            dek
        )
    )
    try:
        canonical = _encode_envelope({name: value for name, value in envelope.items() if name != "mac"})
        return _b64(hmac.digest(key, canonical, "sha256"))
    finally:
        _zero(key)


def _verify_envelope_mac(envelope: dict[str, Any], dek: bytes | bytearray) -> None:
    mac = envelope.get("mac")
    if not isinstance(mac, str) or not hmac.compare_digest(mac, _envelope_mac(envelope, dek)):
        raise VaultAccessError("encrypted vault is invalid")


def _validate_detail_credential(credential_type: object, credential: object) -> str:
    if type(credential_type) is not str or credential_type not in _DETAIL_CREDENTIAL_TYPES:
        raise VaultError("card-details code type is invalid")
    if type(credential) is not str:
        raise VaultError("card-details code is invalid")
    try:
        byte_length = len(credential.encode("utf-8"))
    except UnicodeEncodeError:
        raise VaultError("card-details code is invalid") from None
    if byte_length > _MAX_DETAIL_CREDENTIAL_BYTES:
        raise VaultError("card-details code is invalid")
    if credential_type == "pin":
        if len(credential) < _MIN_DETAIL_PIN_CHARS or not re.fullmatch(r"[0-9]+", credential):
            raise VaultError("card-details PIN is invalid")
    elif byte_length < _MIN_DETAIL_PASSPHRASE_BYTES:
        raise VaultError("card-details passphrase is invalid")
    return credential


def _has_revealable_card_details(values: dict[str, str]) -> bool:
    return all(
        isinstance(values.get(key), str) and bool(values[key])
        for key in ("pan", "expiry_month", "expiry_year")
    )


def _validate_detail_credential_envelope(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != {
        "version", "credential_type", "kdf", "wrapped_dek", "session_token"
    }:
        raise ValueError
    if raw.get("version") != _FORMAT_VERSION:
        raise ValueError
    credential_type = raw.get("credential_type")
    if type(credential_type) is not str or credential_type not in _DETAIL_CREDENTIAL_TYPES:
        raise ValueError
    if not isinstance(raw.get("kdf"), dict) or not isinstance(raw.get("wrapped_dek"), str):
        raise ValueError
    _parse_kdf({"version": _FORMAT_VERSION, "kdf": raw["kdf"]})
    wrapped = _unb64(raw["wrapped_dek"])
    if len(wrapped) < 12 + 16:
        raise ValueError
    session_token = raw.get("session_token")
    if not isinstance(session_token, str) or not 32 <= len(session_token) <= 128:
        raise ValueError
    return {
        "version": _FORMAT_VERSION,
        "credential_type": credential_type,
        "kdf": dict(raw["kdf"]),
        "wrapped_dek": raw["wrapped_dek"],
        "session_token": session_token,
    }


def _unwrap_dek(envelope: dict[str, Any], kdf: _KdfParameters, passphrase: str) -> bytes:
    wrapped = _unb64(envelope["wrapped_dek"])
    if len(wrapped) < 12 + 16:
        raise VaultAccessError("unable to unlock vault")
    kek = bytearray(_derive_kek(passphrase, kdf))
    try:
        dek = AESGCM(kek).decrypt(wrapped[:12], wrapped[12:], _DEK_AAD)
        if len(dek) != _DEK_BYTES:
            raise VaultAccessError("unable to unlock vault")
        return dek
    finally:
        _zero(kek)


def _parse_records(envelope: dict[str, Any], dek: bytes) -> dict[str, _Record]:
    raw_records = envelope["records"]
    if not isinstance(raw_records, list) or len(raw_records) > _MAX_RECORDS:
        raise VaultAccessError("encrypted record is invalid")
    records: dict[str, _Record] = {}
    for raw in raw_records:
        if not isinstance(raw, dict):
            raise VaultAccessError("encrypted record is invalid")
        required = ("card_id", "offering_id", "lifecycle", "created_at", "updated_at", "ciphertext")
        if any(not isinstance(raw.get(name), str) for name in required):
            raise VaultAccessError("encrypted record is invalid")
        card_id = raw["card_id"]
        uuid.UUID(card_id)
        replacement = raw.get("replacement_card_id")
        if replacement is not None:
            if not isinstance(replacement, str):
                raise VaultAccessError("encrypted record is invalid")
            uuid.UUID(replacement)
            if replacement == card_id:
                raise VaultAccessError("encrypted record is invalid")
        record = _Record(
            card_id=card_id,
            offering_id=raw["offering_id"],
            lifecycle=CardLifecycle(raw["lifecycle"]),
            created_at=raw["created_at"],
            updated_at=raw["updated_at"],
            ciphertext=_unb64(raw["ciphertext"]),
            replacement_card_id=replacement,
        )
        try:
            validate_offering_id(record.offering_id)
        except VaultError:
            raise VaultAccessError("encrypted record is invalid") from None
        if len(record.ciphertext) < 12 + 16 or card_id in records:
            raise VaultAccessError("encrypted record is invalid")
        _validate_timestamp(record.created_at)
        _validate_timestamp(record.updated_at)
        if record.updated_at < record.created_at:
            raise VaultAccessError("encrypted record is invalid")
        # Authenticate and validate all ciphertext at unlock, so tampering or
        # a forbidden persisted field fails before any reveal.
        nonce, ciphertext = record.ciphertext[:12], record.ciphertext[12:]
        raw_values: Any = json.loads(
            AESGCM(dek).decrypt(nonce, ciphertext, _record_aad(record)).decode("utf-8")
        )
        if not isinstance(raw_values, dict):
            raise VaultAccessError("encrypted record is invalid")
        _validate_secret_fields(raw_values, allow_empty=True)
        records[card_id] = record
    _validate_replacement_graph(records, error_type=VaultAccessError)
    return records


def _parse_child_records(
    envelope: dict[str, Any], cards: dict[str, _Record]
) -> dict[str, _ChildRecord]:
    """Parse the additive, non-secret child-record list; absent means none yet."""
    raw_child_records = envelope.get("child_records", [])
    if not isinstance(raw_child_records, list) or len(raw_child_records) > _MAX_CHILD_RECORDS:
        raise VaultAccessError("encrypted record is invalid")
    child_records: dict[str, _ChildRecord] = {}
    for raw in raw_child_records:
        if not isinstance(raw, dict):
            raise VaultAccessError("encrypted record is invalid")
        required = (
            "child_id",
            "parent_card_id",
            "kind",
            "lifecycle",
            "created_at",
            "updated_at",
        )
        allowed = {*required, "expiry_date"}
        if set(raw) - allowed:
            raise VaultAccessError("encrypted record is invalid")
        if any(not isinstance(raw.get(name), str) for name in required):
            raise VaultAccessError("encrypted record is invalid")
        child_id = raw["child_id"]
        parent_card_id = raw["parent_card_id"]
        expiry_date = raw.get("expiry_date")
        if expiry_date is not None and not isinstance(expiry_date, str):
            raise VaultAccessError("encrypted record is invalid")
        uuid.UUID(child_id)
        uuid.UUID(parent_card_id)
        if parent_card_id not in cards or child_id in child_records:
            raise VaultAccessError("encrypted record is invalid")
        try:
            kind = ChildRecordKind(raw["kind"])
            lifecycle = ChildRecordLifecycle(raw["lifecycle"])
            if expiry_date is not None:
                _validate_date(expiry_date)
        except (ValueError, VaultError):
            raise VaultAccessError("encrypted record is invalid") from None
        record = _ChildRecord(
            child_id=child_id,
            parent_card_id=parent_card_id,
            kind=kind,
            lifecycle=lifecycle,
            created_at=raw["created_at"],
            updated_at=raw["updated_at"],
            expiry_date=expiry_date,
        )
        _validate_timestamp(record.created_at)
        _validate_timestamp(record.updated_at)
        if record.updated_at < record.created_at:
            raise VaultAccessError("encrypted record is invalid")
        child_records[child_id] = record
    return child_records


def _parse_reconciliation_events(envelope: dict[str, Any]) -> list[dict[str, str]]:
    """Parse bounded, non-private workflow events from the authenticated envelope."""
    raw_events = envelope.get("reconciliation_events", [])
    if not isinstance(raw_events, list) or len(raw_events) > 1_000:
        raise VaultAccessError("encrypted record is invalid")
    events: list[dict[str, str]] = []
    for event in raw_events:
        if not isinstance(event, dict) or set(event) != {"record", "action", "proposal_digest", "intent_digest", "at"}:
            raise VaultAccessError("encrypted record is invalid")
        if (not all(isinstance(value, str) for value in event.values())
                or event["action"] not in {"defer", "reject"}
                or len(event["proposal_digest"]) != 64 or len(event["intent_digest"]) != 64):
            raise VaultAccessError("encrypted record is invalid")
        try:
            uuid.UUID(event["record"])
        except (ValueError, AttributeError):
            raise VaultAccessError("encrypted record is invalid") from None
        events.append(dict(event))
    return events


def _derive_kek(passphrase: str, kdf: _KdfParameters) -> bytes:
    return hash_secret_raw(
        secret=passphrase.encode("utf-8"),
        salt=kdf.salt,
        time_cost=kdf.time_cost,
        memory_cost=kdf.memory_cost_kib,
        parallelism=kdf.parallelism,
        hash_len=32,
        type=Type.ID,
    )


def _validate_passphrase(passphrase: object) -> str:
    if type(passphrase) is not str:
        raise VaultError("passphrase is invalid")
    try:
        byte_length = len(passphrase.encode("utf-8"))
    except UnicodeEncodeError:
        raise VaultError("passphrase is invalid") from None
    if not _MIN_PASSPHRASE_BYTES <= byte_length <= _MAX_PASSPHRASE_BYTES:
        raise VaultError("passphrase is invalid")
    return passphrase


def _validate_secret_fields(values: dict[str, str], *, allow_empty: bool = False) -> None:
    if not isinstance(values, dict) or (not values and not allow_empty):
        raise VaultError("secret fields must be a non-empty string map")
    if set(values) - _ALLOWED_SECRET_FIELDS:
        raise VaultError("secret field is not permitted")
    total_characters = 0
    for value in values.values():
        if not isinstance(value, str) or not value or len(value) > _MAX_SECRET_VALUE_CHARS:
            raise VaultError("secret field value is invalid")
        total_characters += len(value)
    if total_characters > _MAX_SECRET_TOTAL_CHARS:
        raise VaultError("secret field values are too large")
    if "reconciliation_id" in values:
        validate_reconciliation_id(values["reconciliation_id"])
    if "last_four" in values:
        validate_last_four(values["last_four"])
    if "pan" in values and "last_four" in values:
        pan_last_four = _last_four_from_pan(values["pan"])
        if pan_last_four is not None and not secrets.compare_digest(
            pan_last_four, values["last_four"]
        ):
            # Reject rather than silently accepting contradictory local card
            # identifiers.  The route maps this to a generic protected error.
            raise VaultError("last four does not match pan")


def validate_secret_fields(values: dict[str, str]) -> None:
    """Validate a prospective record without persisting or exposing its values."""
    _validate_secret_fields(values)


def validate_reconciliation_id(value: str) -> None:
    if not isinstance(value, str) or _RECONCILIATION_ID.fullmatch(value) is None:
        raise VaultError("reconciliation id is invalid")


def validate_reconciliation_pan(value: str) -> None:
    if _pan_digits(value) is None:
        raise VaultError("reconciliation input is invalid")


def validate_last_four(value: str) -> None:
    """Accept exactly four ASCII digits for the encrypted last-four fallback."""
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{4}", value) is None:
        raise VaultError("last four is invalid")


def validate_offering_id(value: str) -> None:
    """Protect the cleartext envelope field from receiving arbitrary private text."""
    if not isinstance(value, str) or _OFFERING_ID.fullmatch(value) is None:
        raise VaultError("offering_id is invalid")


def _pan_digits(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    digits = "".join(character for character in value if "0" <= character <= "9")
    return digits if 12 <= len(digits) <= 19 else None


def _masked_last4(value: str | None) -> str | None:
    last_four = _last_four_from_pan(value)
    return _masked_private_last4(last_four)


def _last_four_from_pan(value: str | None) -> str | None:
    digits = _pan_digits(value)
    return digits[-4:] if digits is not None else None


def _masked_private_last4(value: str | None) -> str | None:
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{4}", value) is None:
        return None
    return f"•••• {value}"


def _validate_date(value: str) -> None:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise VaultError("date is invalid") from None


def _atomic_write(path: Path, encoded: bytes, permissions: _PermissionHelper, *, backup: bool) -> None:
    data_location.reject_reparse(path.parent, allow_missing=True)
    data_location.data_location_checkpoint("before-atomic-directory-create", path.parent)
    path.parent.mkdir(parents=True, exist_ok=True)
    data_location.reject_reparse(path.parent)
    permissions.secure_directory(path.parent)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(12)}.tmp")
    data_location.reject_reparse(temporary, allow_missing=True)
    data_location.data_location_checkpoint("before-atomic-temp-create", temporary)
    data_location.reject_reparse(temporary, allow_missing=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(temporary, flags, 0o600)
    try:
        permissions.secure_file(temporary)
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        if backup:
            data_location.reject_reparse(path, allow_missing=True)
            try:
                path.lstat()
            except FileNotFoundError:
                pass
            else:
                _rotate_backups(path, permissions)
        data_location.data_location_checkpoint("before-atomic-replace", path)
        data_location.reject_reparse(path, allow_missing=True)
        os.replace(temporary, path)
        permissions.secure_file(path)
        _fsync_directory(path.parent)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def _rotate_backups(path: Path, permissions: _PermissionHelper) -> None:
    staged = path.with_name(f".{path.name}.{secrets.token_hex(12)}.backup.tmp")
    rollback_paths: dict[int, Path] = {}
    try:
        _copy_bounded_file(path, staged, permissions)
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            staged.unlink()
        raise

    try:
        for index in range(1, _BACKUP_COUNT + 1):
            original = _backup_path(path, index)
            if original.exists():
                rollback = original.with_name(
                    f".{original.name}.{secrets.token_hex(12)}.rollback.tmp"
                )
                os.replace(original, rollback)
                rollback_paths[index] = rollback
    except Exception:
        for index, rollback in rollback_paths.items():
            with contextlib.suppress(FileNotFoundError):
                os.replace(rollback, _backup_path(path, index))
        with contextlib.suppress(FileNotFoundError):
            staged.unlink()
        raise

    original_locations = dict(rollback_paths)
    try:
        for index in range(2, _BACKUP_COUNT + 1):
            previous = index - 1
            if previous in original_locations:
                os.replace(original_locations[previous], _backup_path(path, index))
                original_locations[previous] = _backup_path(path, index)
                permissions.secure_file(_backup_path(path, index))
        first = _backup_path(path, 1)
        os.replace(staged, first)
        permissions.secure_file(first)
        _fsync_directory(path.parent)
    except Exception:
        recovery_paths: dict[int, Path] = {}
        for index, location in original_locations.items():
            if location.exists():
                recovery = _backup_path(path, index).with_name(
                    f".{_backup_path(path, index).name}.{secrets.token_hex(12)}.recovery.tmp"
                )
                os.replace(location, recovery)
                recovery_paths[index] = recovery
        for index in range(1, _BACKUP_COUNT + 1):
            with contextlib.suppress(FileNotFoundError):
                _backup_path(path, index).unlink()
        for index, recovery in recovery_paths.items():
            with contextlib.suppress(FileNotFoundError):
                os.replace(recovery, _backup_path(path, index))
        raise
    finally:
        with contextlib.suppress(FileNotFoundError):
            staged.unlink()
        for rollback in rollback_paths.values():
            with contextlib.suppress(FileNotFoundError):
                rollback.unlink()


def _copy_bounded_file(source: Path, target: Path, permissions: _PermissionHelper) -> None:
    total = 0
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        permissions.secure_file(target)
        with source.open("rb") as reader, os.fdopen(fd, "wb") as writer:
            fd = -1
            while chunk := reader.read(_COPY_CHUNK_BYTES):
                total += len(chunk)
                if total > _MAX_VAULT_BYTES:
                    raise VaultError("vault size limit exceeded")
                writer.write(chunk)
            writer.flush()
            os.fsync(writer.fileno())
    except Exception:
        if fd >= 0:
            os.close(fd)
            fd = -1
        with contextlib.suppress(FileNotFoundError):
            target.unlink()
        raise
    finally:
        if fd >= 0:
            os.close(fd)


def _bounded_file_digest(path: Path) -> bytes:
    total = 0
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_COPY_CHUNK_BYTES):
            total += len(chunk)
            if total > _MAX_VAULT_BYTES:
                raise VaultError("vault size limit exceeded")
            digest.update(chunk)
    return digest.digest()


def _backup_path(path: Path, index: int) -> Path:
    return path.with_name(f"{path.name}.bak.{index}")


@contextmanager
def _exclusive_lock(path: Path, permissions: _PermissionHelper) -> Iterator[None]:
    lock_path = path.with_name(f"{path.name}.lock")
    data_location.reject_reparse(lock_path.parent, allow_missing=True)
    data_location.data_location_checkpoint("before-lock-directory-create", lock_path.parent)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    data_location.reject_reparse(lock_path.parent)
    permissions.secure_directory(lock_path.parent)
    data_location.reject_reparse(lock_path, allow_missing=True)
    data_location.data_location_checkpoint("before-lock-open", lock_path)
    data_location.reject_reparse(lock_path, allow_missing=True)
    flags = os.O_RDWR | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(lock_path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "a+b") as handle:
            descriptor = -1
            permissions.secure_file(lock_path)
            _lock_file(handle)
            try:
                yield
            finally:
                _unlock_file(handle)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _lock_file(handle: Any) -> None:
    if os.name == "nt":
        import msvcrt

        if handle.seek(0, os.SEEK_END) == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        _retry_lock(lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1))
    else:
        import fcntl

        fcntl_module = cast(Any, fcntl)
        _retry_lock(
            lambda: fcntl_module.flock(
                handle.fileno(),
                fcntl_module.LOCK_EX | fcntl_module.LOCK_NB,
            )
        )


def _retry_lock(acquire: Callable[[], None]) -> None:
    deadline = time.monotonic() + 5
    while True:
        try:
            acquire()
            return
        except OSError:
            if time.monotonic() >= deadline:
                raise VaultConflictError("vault is busy; retry") from None
            time.sleep(0.02)


def _unlock_file(handle: Any) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        with contextlib.suppress(OSError):
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _encode_envelope(envelope: dict[str, Any]) -> bytes:
    return json.dumps(envelope, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _validate_write_bounds(
    encoded: bytes,
    cards: dict[str, _Record],
    child_records: dict[str, _ChildRecord],
    manual_aggregates: dict[str, ManualSpendAggregate] | None = None,
    attempts: dict[str, PrivateAttempt] | None = None,
) -> None:
    if (
        len(cards) > _MAX_RECORDS
        or len(child_records) > _MAX_CHILD_RECORDS
        or len(manual_aggregates or {}) + len(attempts or {}) > MAX_PERSONAL_STATE_RECORDS
        or len(encoded) > _MAX_VAULT_BYTES
    ):
        raise VaultError("vault size limit exceeded")


def _digest(value: bytes) -> bytes:
    return hashlib.sha256(value).digest()


def _zero(value: bytearray) -> None:
    for index in range(len(value)):
        value[index] = 0


def _record_aad(record: _Record) -> bytes:
    metadata = {
        "card_id": record.card_id,
        "created_at": record.created_at,
        "lifecycle": record.lifecycle.value,
        "offering_id": record.offering_id,
        "replacement_card_id": record.replacement_card_id,
        "updated_at": record.updated_at,
    }
    return _RECORD_AAD_PREFIX + json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _normalize_reconciliation_mutation(mutation: dict[str, Any]) -> dict[str, Any]:
    """Validate and canonicalize every field covered by a vault authorization."""
    if not isinstance(mutation, dict) or set(mutation) != {
        "record", "action", "proposal_digest", "intent_digest", "expected_revision",
        "expected_old", "new", "metadata",
    }:
        raise VaultError("reconciliation mutation is invalid")
    old = mutation["expected_old"]
    new = mutation["new"]
    if (not isinstance(mutation["record"], str) or not isinstance(mutation["action"], str)
            or mutation["action"] not in {"confirm", "defer", "reject", "correct"}
            or not isinstance(mutation["proposal_digest"], str) or len(mutation["proposal_digest"]) != 64
            or not isinstance(mutation["intent_digest"], str) or len(mutation["intent_digest"]) != 64
            or not isinstance(mutation["expected_revision"], str) or len(mutation["expected_revision"]) != 64
            or not isinstance(old, dict) or set(old) != {"offering_id", "lifecycle", "replacement_card_id", "updated_at"}
            or not isinstance(new, dict) or set(new) != {"offering_id", "lifecycle", "replacement_card_id"}
            or not isinstance(mutation["metadata"], str) or len(mutation["metadata"]) > 8_192):
        raise VaultError("reconciliation mutation is invalid")
    validate_offering_id(old["offering_id"])
    if old["lifecycle"] not in {item.value for item in CardLifecycle}:
        raise VaultError("reconciliation mutation is invalid")
    if old["replacement_card_id"] is not None:
        uuid.UUID(old["replacement_card_id"])
    validate_offering_id(new["offering_id"])
    if new["lifecycle"] not in {item.value for item in CardLifecycle}:
        raise VaultError("reconciliation mutation is invalid")
    if new["replacement_card_id"] is not None:
        uuid.UUID(new["replacement_card_id"])
    try:
        decoded = json.loads(mutation["metadata"])
    except (TypeError, ValueError):
        raise VaultError("reconciliation mutation is invalid") from None
    if not isinstance(decoded, dict):
        raise VaultError("reconciliation mutation is invalid")
    return cast(dict[str, Any], json.loads(json.dumps(mutation, sort_keys=True, separators=(",", ":"))))


def _timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _unb64(value: Any) -> bytes:
    if not isinstance(value, str):
        raise ValueError("invalid encoding")
    return base64.b64decode(value.encode("ascii"), validate=True)


def _validate_timestamp(value: str) -> None:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        raise VaultAccessError("encrypted record is invalid") from None
    if parsed.year < 2000:
        raise VaultAccessError("encrypted record is invalid")


def _uuid7() -> str:
    milliseconds = int(time.time_ns() // 1_000_000)
    random_a = secrets.randbits(12)
    random_b = secrets.randbits(62)
    value = (milliseconds << 80) | (0x7 << 76) | (random_a << 64) | (0b10 << 62) | random_b
    return str(uuid.UUID(int=value))
