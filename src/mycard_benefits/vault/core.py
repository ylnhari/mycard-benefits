"""Versioned, local encrypted vault storage.

The on-disk JSON envelope carries crypto metadata and non-sensitive card
metadata only.  Every user-supplied card value is authenticated ciphertext.
"""

from __future__ import annotations

import base64
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
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, Protocol, cast

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_FORMAT_VERSION: Final = 2
_DEK_BYTES: Final = 32
_DEK_AAD: Final = b"mycard-benefits/vault-dek/v1"
_RECORD_AAD_PREFIX: Final = b"mycard-benefits/vault-record/v1:"
_ENVELOPE_MAC_INFO: Final = b"mycard-benefits/vault-envelope-mac/v2"
_MAX_VAULT_BYTES: Final = 5 * 1024 * 1024
_MAX_RECORDS: Final = 1_000
_MAX_CHILD_RECORDS: Final = 5_000
_MAX_LABEL_CHARS: Final = 160
_BACKUP_COUNT: Final = 3
_COPY_CHUNK_BYTES: Final = 64 * 1024
_MAX_SECRET_VALUE_CHARS: Final = 4_096
_MAX_SECRET_TOTAL_CHARS: Final = 16_384
_MIN_PASSPHRASE_BYTES: Final = 12
_MAX_PASSPHRASE_BYTES: Final = 1_024
_ALLOWED_SECRET_FIELDS: Final = frozenset(
    {
        "cardholder_name",
        "pan",
        "expiry_month",
        "expiry_year",
        "cvv",
        "pin",
        "nickname",
        "notes",
        "billing_postcode",
    }
)
_OFFERING_ID: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")


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


class CardLifecycle(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    LOST = "lost"
    STOLEN = "stolen"
    CLOSED = "closed"
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


@dataclass(frozen=True)
class _ChildRecord:
    child_id: str
    parent_card_id: str
    kind: ChildRecordKind
    label: str
    lifecycle: ChildRecordLifecycle
    created_at: str
    updated_at: str
    expiry_date: str | None = None


class RevealAuthorization:
    """Opaque, one-use authorization minted by a reauthenticated session."""

    __slots__ = ("_nonce",)

    def __init__(self, nonce: str) -> None:
        self._nonce = nonce


class VaultStore:
    """Encrypted vault file factory and persistence boundary."""

    def __init__(self, path: Path, *, _permissions: _PermissionHelper | None = None) -> None:
        self.path = path
        self._permissions: _PermissionHelper = _permissions or _PlatformPermissions()

    def create(self, passphrase: str) -> VaultSession:
        passphrase = _validate_passphrase(passphrase)
        kdf = _KdfParameters(salt=secrets.token_bytes(16))
        dek = secrets.token_bytes(_DEK_BYTES)
        envelope = _new_envelope(kdf, dek, passphrase)
        encoded = _encode_envelope(envelope)
        _validate_write_bounds(encoded, {}, {})
        with _exclusive_lock(self.path, self._permissions):
            if self.path.exists():
                raise VaultError("vault already exists")
            _atomic_write(self.path, encoded, self._permissions, backup=False)
        return VaultSession(
            self, kdf, bytearray(dek), {}, {}, str(envelope["wrapped_dek"]), _digest(encoded)
        )

    def open(self, passphrase: str) -> VaultSession:
        try:
            passphrase = _validate_passphrase(passphrase)
        except VaultError:
            raise VaultAccessError("unable to unlock vault") from None
        try:
            with self.path.open("rb") as handle:
                raw_file = handle.read(_MAX_VAULT_BYTES + 1)
            if len(raw_file) > _MAX_VAULT_BYTES:
                raise VaultAccessError("unable to unlock vault")
            envelope = json.loads(raw_file.decode("utf-8"))
            kdf = _parse_kdf(envelope)
            dek = _unwrap_dek(envelope, kdf, passphrase)
            _verify_envelope_mac(envelope, dek)
            records = _parse_records(envelope, dek)
            child_records = _parse_child_records(envelope, records)
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
        idle_timeout_seconds: float = 300.0,
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
        self._reveal_authorizations: dict[str, tuple[str, str, float]] = {}
        self._lock = threading.RLock()

    @property
    def locked(self) -> bool:
        with self._lock:
            self._auto_lock_if_idle()
            return self._dek is None

    def lock(self) -> None:
        with self._lock:
            if self._dek is not None:
                _zero(self._dek)
            self._dek = None
            self._records.clear()
            self._child_records.clear()
            self._reveal_authorizations.clear()

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

    def list_child_records(self, parent_card_id: str | None = None) -> tuple[dict[str, str], ...]:
        with self._lock:
            self._ensure_unlocked()
            return tuple(
                {
                    "child_id": record.child_id,
                    "parent_card_id": record.parent_card_id,
                    "kind": record.kind.value,
                    "label": record.label,
                    "lifecycle": record.lifecycle.value,
                    "created_at": record.created_at,
                    "updated_at": record.updated_at,
                    **({"expiry_date": record.expiry_date} if record.expiry_date else {}),
                }
                for record in self._child_records.values()
                if parent_card_id is None or record.parent_card_id == parent_card_id
            )

    def add_card(
        self,
        offering_id: str,
        secret_fields: dict[str, str],
        *,
        lifecycle: CardLifecycle = CardLifecycle.ACTIVE,
    ) -> str:
        with self._lock:
            self._require_unlocked()
            _validate_secret_fields(secret_fields)
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
        label: str,
        *,
        lifecycle: ChildRecordLifecycle = ChildRecordLifecycle.ACTIVE,
        expiry_date: str | None = None,
    ) -> str:
        with self._lock:
            self._require_unlocked()
            self._get_record(parent_card_id)
            if not isinstance(kind, ChildRecordKind):
                raise VaultError("invalid child record kind")
            if not isinstance(lifecycle, ChildRecordLifecycle):
                raise VaultError("invalid lifecycle")
            label = _validate_label(label)
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
                label=label,
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
                _validate_secret_fields(secret_fields)
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
            self._persist(candidate, self._child_records)
            return tuple(card_ids)

    def replace_card(
        self,
        card_id: str,
        secret_fields: dict[str, str],
        *,
        lifecycle: CardLifecycle = CardLifecycle.CLOSED,
    ) -> str:
        with self._lock:
            self._require_unlocked()
            if not isinstance(lifecycle, CardLifecycle):
                raise VaultError("invalid lifecycle")
            if lifecycle not in {
                CardLifecycle.EXPIRED,
                CardLifecycle.LOST,
                CardLifecycle.STOLEN,
                CardLifecycle.CLOSED,
                CardLifecycle.ARCHIVED,
            }:
                raise VaultError("replacement requires a non-active lifecycle")
            old = self._get_record(card_id)
            if old.replacement_card_id is not None:
                raise VaultError("card already has a replacement")
            _validate_secret_fields(secret_fields)
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
            self._persist(candidate, self._child_records)
            return new_id

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
            if field not in _ALLOWED_SECRET_FIELDS:
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
                self._reveal_authorizations[nonce] = (card_id, field, time.monotonic() + ttl_seconds)
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
            card_id, field, expires_at = details
            if time.monotonic() > expires_at:
                raise VaultAccessError("reveal is unavailable")
            values = self._decrypt_record(self._get_record(card_id))
            value = values.get(field)
            if not isinstance(value, str):
                raise VaultAccessError("reveal is unavailable")
            return value

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
        self, cards: dict[str, _Record], child_records: dict[str, _ChildRecord]
    ) -> None:
        with self._lock:
            dek = self._require_unlocked()
            encoded = _encode_envelope(
                _serialize_envelope(self._kdf, self._wrapped_dek, cards, child_records, dek)
            )
            _validate_write_bounds(encoded, cards, child_records)
            with _exclusive_lock(self._store.path, self._store._permissions):
                try:
                    current_revision = _bounded_file_digest(self._store.path)
                except (OSError, VaultError):
                    raise VaultConflictError("vault changed elsewhere; reopen before saving") from None
                if current_revision != self._revision:
                    raise VaultConflictError("vault changed elsewhere; reopen before saving")
                _atomic_write(self._store.path, encoded, self._store._permissions, backup=True)
            self._revision = _digest(encoded)
            self._records = cards
            self._child_records = child_records

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
    }
    envelope["mac"] = _envelope_mac(envelope, dek)
    return envelope


def _serialize_envelope(
    kdf: _KdfParameters,
    wrapped_dek: str,
    cards: dict[str, _Record],
    child_records: dict[str, _ChildRecord],
    dek: bytes | bytearray,
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
                "label": record.label,
                "lifecycle": record.lifecycle.value,
                "created_at": record.created_at,
                "updated_at": record.updated_at,
                **({"expiry_date": record.expiry_date} if record.expiry_date else {}),
            }
            for record in child_records.values()
        ],
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
        _validate_secret_fields(raw_values)
        records[card_id] = record
    for record in records.values():
        if record.replacement_card_id and record.replacement_card_id not in records:
            raise VaultAccessError("encrypted record is invalid")
        if record.replacement_card_id and record.lifecycle is CardLifecycle.ACTIVE:
            raise VaultAccessError("encrypted record is invalid")
        if record.replacement_card_id:
            successor = records[record.replacement_card_id]
            if successor.offering_id != record.offering_id or successor.created_at < record.updated_at:
                raise VaultAccessError("encrypted record is invalid")
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
            "label",
            "lifecycle",
            "created_at",
            "updated_at",
        )
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
            label = _validate_label(raw["label"])
            if expiry_date is not None:
                _validate_date(expiry_date)
        except (ValueError, VaultError):
            raise VaultAccessError("encrypted record is invalid") from None
        record = _ChildRecord(
            child_id=child_id,
            parent_card_id=parent_card_id,
            kind=kind,
            label=label,
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


def _validate_secret_fields(values: dict[str, str]) -> None:
    if not values or not isinstance(values, dict):
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


def validate_secret_fields(values: dict[str, str]) -> None:
    """Validate a prospective record without persisting or exposing its values."""
    _validate_secret_fields(values)


def validate_offering_id(value: str) -> None:
    """Protect the cleartext envelope field from receiving arbitrary private text."""
    if not isinstance(value, str) or _OFFERING_ID.fullmatch(value) is None:
        raise VaultError("offering_id is invalid")


def _validate_label(value: str) -> str:
    """Bound a non-secret child-record display label; never a place for secrets."""
    if not isinstance(value, str):
        raise VaultError("label is invalid")
    stripped = value.strip()
    if not stripped or len(stripped) > _MAX_LABEL_CHARS or not stripped.isprintable():
        raise VaultError("label is invalid")
    return stripped


def _validate_date(value: str) -> None:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise VaultError("date is invalid") from None


def _atomic_write(path: Path, encoded: bytes, permissions: _PermissionHelper, *, backup: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    permissions.secure_directory(path.parent)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(12)}.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        permissions.secure_file(temporary)
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        if backup and path.exists():
            _rotate_backups(path, permissions)
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
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    permissions.secure_directory(lock_path.parent)
    with lock_path.open("a+b") as handle:
        permissions.secure_file(lock_path)
        _lock_file(handle)
        try:
            yield
        finally:
            _unlock_file(handle)


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
    encoded: bytes, cards: dict[str, _Record], child_records: dict[str, _ChildRecord]
) -> None:
    if (
        len(cards) > _MAX_RECORDS
        or len(child_records) > _MAX_CHILD_RECORDS
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
