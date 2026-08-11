"""Local protected-operation services.

This module deliberately has no web integration.  Its local audit seam stores
only opaque identifiers and bounded metadata, and uses the vault's passphrase
as a user-held cryptographic boundary.
"""
from __future__ import annotations

import base64
import binascii
import contextlib
import hashlib
import json
import os
import secrets
import stat
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import BinaryIO, Final, cast

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from .core import VaultError, VaultSession, VaultStore, _exclusive_lock, _PlatformPermissions

_VERSION: Final = 1
_MAX_ATTACHMENT_BYTES: Final = 10 * 1024 * 1024
_MAX_AUDIT_BYTES: Final = 20 * 1024 * 1024
_MAX_AUDIT_REF_INPUT: Final = 256
_AUDIT_REF_PREFIX: Final = b"mycard-benefits/audit-reference/v1:"
_AUDIT_EVENT_KEYS: Final = frozenset(
    {"event_id", "occurred_at", "action", "record_ref", "success"}
)
_PURPOSES: Final = frozenset({"boarding_pass", "voucher", "enrollment_confirmation", "membership_document"})
_BACKUP_LABELS: Final = frozenset({"scheduled", "manual"})
_MAX_PROTECTED_BYTES: Final = 20 * 1024 * 1024
_ATTACHMENT_METADATA_KEYS: Final = frozenset(
    {
        "attachment_id", "owner_record_ref", "purpose", "expiry", "retention_days",
        "size", "created_at", "media_schema", "metadata_schema", "version",
        "ciphertext_sha256",
    }
)


def _reject_reparse(path: Path, *, allow_missing: bool = False) -> None:
    """Reject links/reparse points in every existing path component."""
    current = Path(path.anchor) if path.anchor else Path()
    for part in path.parts[1:] if path.anchor else path.parts:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            if allow_missing and current == path:
                continue
            raise ProtectedError("protected path is unavailable") from None
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ProtectedError("protected path is unavailable")


def _read_held(path: Path, *, limit: int = _MAX_PROTECTED_BYTES) -> bytes:
    _reject_reparse(path)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as handle:
            fd = -1
            data = handle.read(limit + 1)
    except (OSError, ValueError):
        raise ProtectedError("protected file is unavailable") from None
    finally:
        if "fd" in locals() and fd >= 0:
            os.close(fd)
    if len(data) > limit:
        raise ProtectedError("protected file is too large")
    return data


def _safe_destination(path: Path) -> None:
    parent = path.parent
    while not parent.exists():
        if parent == parent.parent:
            break
        parent = parent.parent
    _reject_reparse(parent)
    if path.exists() and (path.is_symlink() or not path.is_file()):
        raise ProtectedError("protected destination is invalid")


def _open_read_no_replace(path: Path) -> int:
    """Open a destination while denying Windows write/delete sharing."""
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if os.name != "nt":
        return os.open(path, flags)
    # ``os.open`` uses the CRT's permissive sharing defaults on Windows.  Use
    # CreateFileW directly so an attacker cannot rename/delete/replace the
    # destination while its final identity is being verified.
    import ctypes
    import msvcrt

    invalid_handle = ctypes.c_void_p(-1).value
    handle = ctypes.windll.kernel32.CreateFileW(
        str(path), 0x80000000, 0x00000001, None, 3, 0x00000080, None
    )
    if handle == invalid_handle:
        raise OSError("unable to hold restore destination")
    try:
        return msvcrt.open_osfhandle(handle, flags)
    except BaseException:
        ctypes.windll.kernel32.CloseHandle(handle)
        raise


class ProtectedError(VaultError):
    """A protected local operation failed without exposing sensitive detail."""


def _opaque_audit_ref(value: str | None) -> str:
    """Return a bounded, non-reversible reference for an audit operation."""
    value = value if value is not None else uuid.uuid4().hex
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= _MAX_AUDIT_REF_INPUT
        or not value.isascii()
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
    ):
        raise ProtectedError("audit record reference is invalid")
    return hashlib.sha256(_AUDIT_REF_PREFIX + value.encode("ascii")).hexdigest()


def _is_opaque_audit_ref(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == hashlib.sha256().digest_size * 2
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
    )


class AuditAction(StrEnum):
    REVEAL = "reveal"
    COPY = "copy"
    DETAIL_CREDENTIAL_CREATE = "detail_credential_create"
    EDIT = "edit"
    LIFECYCLE = "lifecycle"
    REPLACE = "replace"
    DELETE = "delete"
    SECRET_ERASE = "secret_erase"
    IMPORT = "import"
    EXPORT = "export"
    MIGRATION = "migration"
    PURGE = "purge"


class VerifiedRestoreLease:
    """One-use capability for a verified restored vault.

    A restore is not a bare success: the lease owns both the destination lock
    and the exact, no-delete (on Windows) read handle that was authenticated.
    The caller must consume it once; reopening ``path`` outside this lease
    cannot inherit the restore verification claim.
    """

    def __init__(
        self,
        path: Path,
        expected: bytes,
        passphrase: str,
        *,
        validate: Callable[[bytes], None],
        destination_lock: contextlib.AbstractContextManager[None],
    ) -> None:
        self.path = path
        self._expected = expected
        self._passphrase = passphrase
        self._validate = validate
        self._destination_lock = destination_lock
        self._handle: BinaryIO | None = None
        self._identity: tuple[int, int] | None = None
        self._consumed = False
        self._closed = False
        try:
            _reject_reparse(path)
            fd = _open_read_no_replace(path)
            self._handle = os.fdopen(fd, "rb")
            identity = os.fstat(self._handle.fileno())
            self._identity = (identity.st_dev, identity.st_ino)
            # This first verification is the final byte/authentication check.
            self.verify()
            self._validate(self._read_exact())
            # Revalidate after authentication before the capability can leave
            # the restore routine.
            self.verify()
        except (OSError, ValueError):
            self._close_handle_only()
            raise ProtectedError("restore destination is unavailable") from None
        except BaseException:
            self._close_handle_only()
            raise

    def _close_handle_only(self) -> None:
        """Clean construction failure without releasing the caller-owned lock."""
        self._closed = True
        if self._handle is not None:
            self._handle.close()
        self._handle = None

    def _read_exact(self) -> bytes:
        if self._handle is None:
            raise ProtectedError("restore capability is closed")
        self._handle.seek(0)
        actual = self._handle.read(len(self._expected) + 1)
        if actual != self._expected:
            raise ProtectedError("restore destination changed")
        return actual

    def verify(self) -> None:
        """Reject replacement before handoff, return, or first consumption."""
        if self._closed or self._handle is None or self._identity is None:
            raise ProtectedError("restore capability is closed")
        self._read_exact()
        _reject_reparse(self.path)
        current = self.path.stat()
        if (current.st_dev, current.st_ino) != self._identity:
            raise ProtectedError("restore destination changed")

    def consume(self) -> VaultSession:
        """Activate the exact authenticated bytes once while protection is held."""
        if self._consumed:
            raise ProtectedError("restore capability was already consumed")
        # The recheck is deliberately immediately before and after activation:
        # a same-path reopen outside this held capability is never trusted.
        self.verify()
        session = VaultStore(self.path).open_bytes(self._read_exact(), self._passphrase)
        try:
            self.verify()
        except BaseException:
            session.lock()
            raise
        self._consumed = True
        return session

    def close(self) -> None:
        """Release the exact handle and destination lock after trusted use."""
        if self._closed:
            return
        self._closed = True
        try:
            if self._handle is not None:
                self._handle.close()
        finally:
            self._handle = None
            self._destination_lock.__exit__(None, None, None)

    def __enter__(self) -> VerifiedRestoreLease:
        if self._closed:
            raise ProtectedError("restore capability is closed")
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


def _json(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode()


def _atomic(path: Path, data: bytes) -> None:
    _safe_destination(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _PlatformPermissions().secure_directory(path.parent)
    temp = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    try:
        with temp.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        _PlatformPermissions().secure_file(temp)
        os.replace(temp, path)
        _PlatformPermissions().secure_file(path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temp.unlink()


def _restore_lease(
    destination: Path,
    raw: bytes,
    passphrase: str,
) -> VerifiedRestoreLease:
    """Atomically install and hand off a still-verified destination capability."""
    destination_lock = _exclusive_lock(destination, _PlatformPermissions())
    destination_lock.__enter__()
    lease: VerifiedRestoreLease | None = None
    try:
        _atomic(destination, raw)
        lease = VerifiedRestoreLease(
            destination,
            raw,
            passphrase,
            validate=lambda written: VaultStore(destination).open_bytes(written, passphrase).lock(),
            destination_lock=destination_lock,
        )
        # The lock and no-replace handle remain owned by ``lease``. Reject an
        # alternate inserted during construction before handing it to callers.
        lease.verify()
        return lease
    except BaseException:
        if lease is not None:
            lease.close()
        else:
            destination_lock.__exit__(None, None, None)
        raise


def _key(passphrase: str, salt: bytes) -> bytearray:
    if not isinstance(passphrase, str) or len(passphrase.encode()) < 12:
        raise ProtectedError("protected key is invalid")
    return bytearray(Scrypt(salt=salt, length=32, n=2**14, r=8, p=1).derive(passphrase.encode()))


def _seal(payload: bytes, passphrase: str, kind: str, *, aad: bytes | None = None) -> bytes:
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    key = _key(passphrase, salt)
    try:
        ciphertext = AESGCM(key).encrypt(nonce, payload, aad if aad is not None else kind.encode())
    finally:
        for i in range(len(key)):
            key[i] = 0
    return _json({"version": _VERSION, "kind": kind, "salt": base64.b64encode(salt).decode(), "nonce": base64.b64encode(nonce).decode(), "ciphertext": base64.b64encode(ciphertext).decode()})


def _open(blob: bytes, passphrase: str, kind: str, *, aad: bytes | None = None) -> bytes:
    try:
        item = json.loads(blob)
        if item.get("version") != _VERSION or item.get("kind") != kind:
            raise ProtectedError("protected file version is unsupported")
        salt, nonce = base64.b64decode(item["salt"], validate=True), base64.b64decode(item["nonce"], validate=True)
        ciphertext = base64.b64decode(item["ciphertext"], validate=True)
        if len(salt) != 16 or len(nonce) != 12 or len(ciphertext) < 16:
            raise ProtectedError("protected file is invalid")
        key = _key(passphrase, salt)
        try:
            return AESGCM(key).decrypt(nonce, ciphertext, aad if aad is not None else kind.encode())
        finally:
            for i in range(len(key)):
                key[i] = 0
    except (KeyError, TypeError, ValueError, binascii.Error, json.JSONDecodeError, InvalidTag):
        raise ProtectedError("protected file is invalid") from None


class AuditLog:
    """Append-only, value-free local audit events with bounded retention."""

    def __init__(self, path: Path, *, retention_days: int = 365) -> None:
        if not 1 <= retention_days <= 3650:
            raise ProtectedError("audit retention is invalid")
        self.path, self.retention_days = path, retention_days

    @staticmethod
    def opaque_record_ref(value: str) -> str:
        """Derive the persisted opaque reference for a bounded local identity."""
        return _opaque_audit_ref(value)

    @staticmethod
    def _existing_event(raw: bytes, event_id: str) -> dict[str, object] | None:
        for line in raw.splitlines():
            try:
                item = json.loads(line)
            except (TypeError, ValueError, json.JSONDecodeError):
                raise ProtectedError("audit log is invalid") from None
            if not isinstance(item, dict):
                raise ProtectedError("audit log is invalid")
            if item.get("event_id") == event_id:
                return cast(dict[str, object], item)
        return None

    def _has_event(
        self,
        event_id: str,
        action: AuditAction | str,
        *,
        record_ref: str,
        success: bool = True,
    ) -> bool:
        try:
            action = AuditAction(action)
        except ValueError:
            raise ProtectedError("audit action is invalid") from None
        expected_ref = _opaque_audit_ref(record_ref)
        with _exclusive_lock(self.path, _PlatformPermissions()):
            if not self.path.exists():
                return False
            _reject_reparse(self.path)
            item = self._existing_event(_read_held(self.path, limit=_MAX_AUDIT_BYTES), event_id)
            if item is None:
                return False
            if (
                set(item) != _AUDIT_EVENT_KEYS
                or item.get("action") != action.value
                or item.get("record_ref") != expected_ref
                or item.get("success") is not success
            ):
                raise ProtectedError("audit event conflict")
            return True

    @contextlib.contextmanager
    def _transaction(
        self,
        action: AuditAction | str,
        *,
        record_ref: str | None = None,
        event_id: str | None = None,
        success: bool = True,
    ) -> Iterator[str]:
        try:
            action = AuditAction(action)
        except ValueError:
            raise ProtectedError("audit action is invalid") from None
        if event_id is None:
            event_id = str(uuid.uuid4())
        else:
            try:
                parsed_event_id = uuid.UUID(event_id)
            except (ValueError, AttributeError, TypeError):
                raise ProtectedError("audit event identity is invalid") from None
            if str(parsed_event_id) != event_id:
                raise ProtectedError("audit event identity is invalid")
        event = {
            "event_id": event_id,
            "occurred_at": datetime.now(UTC).isoformat(),
            "action": action.value,
            "record_ref": _opaque_audit_ref(record_ref),
            "success": bool(success),
        }
        encoded = _json(event) + b"\n"
        with _exclusive_lock(self.path, _PlatformPermissions()):
            _reject_reparse(self.path, allow_missing=True)
            existed = self.path.exists()
            previous = _read_held(self.path, limit=_MAX_AUDIT_BYTES) if existed else b""
            try:
                existing_event = self._existing_event(previous, event_id)
                if existing_event is not None:
                    if (
                        set(existing_event) != _AUDIT_EVENT_KEYS
                        or any(
                            existing_event.get(key) != event[key]
                            for key in ("event_id", "action", "record_ref", "success")
                        )
                    ):
                        raise ProtectedError("audit event conflict")
                    yield event_id
                    return
                existing = len(previous)
                if existing + len(encoded) > _MAX_AUDIT_BYTES:
                    raise ProtectedError("audit log is full")
                with self.path.open("ab") as handle:
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
                yield event_id
            except BaseException:
                try:
                    if existed:
                        _atomic(self.path, previous)
                    else:
                        _reject_reparse(self.path, allow_missing=True)
                        with contextlib.suppress(FileNotFoundError):
                            self.path.unlink()
                except BaseException as rollback_error:
                    raise ProtectedError("audit log unavailable") from rollback_error
                raise

    def record(
        self,
        action: AuditAction | str,
        *,
        record_ref: str | None = None,
        event_id: str | None = None,
        success: bool = True,
    ) -> str:
        with self._transaction(
            action,
            record_ref=record_ref,
            event_id=event_id,
            success=success,
        ) as persisted_event_id:
            return persisted_event_id

    def purge(
        self,
        *,
        authorizer: Callable[[], bool],
        now: datetime | None = None,
    ) -> int:
        if not callable(authorizer) or not authorizer():
            raise ProtectedError("audit purge is unauthorized")
        now = now or datetime.now(UTC)
        cutoff = now - timedelta(days=self.retention_days)
        kept: list[bytes] = []
        removed = 0
        with _exclusive_lock(self.path, _PlatformPermissions()):
            if self.path.exists():
                _reject_reparse(self.path)
                for line in _read_held(self.path, limit=_MAX_AUDIT_BYTES).splitlines():
                    try:
                        item = json.loads(line)
                        if not isinstance(item, dict):
                            raise ValueError
                        if set(item) != _AUDIT_EVENT_KEYS:
                            # Rewrite valid events into the strict schema; unknown
                            # injected fields are never retained.
                            item = {
                                key: item[key]
                                for key in (
                                    "event_id",
                                    "occurred_at",
                                    "action",
                                    "record_ref",
                                    "success",
                                )
                                if key in item
                            }
                        event_id = item["event_id"]
                        occurred_at = item["occurred_at"]
                        action = AuditAction(item["action"])
                        record_ref = item.get("record_ref")
                        success = item["success"]
                        if (
                            not isinstance(event_id, str) or uuid.UUID(event_id) is None
                            or not isinstance(occurred_at, str) or not isinstance(success, bool)
                        ):
                            raise ValueError
                        if record_ref is None:
                            record_ref = _opaque_audit_ref(event_id)
                        if not _is_opaque_audit_ref(record_ref):
                            raise ValueError
                        timestamp = datetime.fromisoformat(occurred_at)
                        if timestamp.tzinfo is None:
                            raise ValueError
                        normalized = {
                            "event_id": event_id,
                            "occurred_at": occurred_at,
                            "action": action.value,
                            "record_ref": record_ref,
                            "success": success,
                        }
                        if timestamp >= cutoff:
                            kept.append(_json(normalized))
                        else:
                            removed += 1
                    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                        raise ProtectedError("audit log is invalid") from None
                _atomic(self.path, b"\n".join(kept) + (b"\n" if kept else b""))
        if removed:
            self.record(AuditAction.PURGE, record_ref="audit-log")
        return removed


class RecoveryManager:
    """Create and restore a self-contained export keyed by a user-held key."""

    @staticmethod
    def create(session: VaultSession, destination: Path) -> str:
        recovery_key = "recovery-" + secrets.token_urlsafe(24)
        session.export_rewrapped(destination, recovery_key)
        return recovery_key

    @staticmethod
    def restore(source: Path, destination: Path, recovery_key: str) -> VerifiedRestoreLease:
        _safe_destination(destination)
        with _exclusive_lock(source, _PlatformPermissions()):
            raw = _read_held(source)
            VaultStore(source).open_bytes(raw, recovery_key).lock()
            lease = _restore_lease(destination, raw, recovery_key)
        try:
            # This is the final outer-return boundary. The caller receives a
            # capability, never a detached path-success claim.
            lease.verify()
            return lease
        except BaseException:
            lease.close()
            raise


class BackupManager:
    def __init__(self, directory: Path, *, keep: int = 3) -> None:
        if not 1 <= keep <= 20:
            raise ProtectedError("backup rotation is invalid")
        self.directory, self.keep = directory, keep

    def create(self, vault: Path, passphrase: str, *, label: str = "scheduled") -> Path:
        if label not in _BACKUP_LABELS:
            raise ProtectedError("backup label is invalid")
        _reject_reparse(vault.parent)
        if not vault.is_file() or vault.is_symlink():
            raise ProtectedError("backup source is invalid")
        self.directory.mkdir(parents=True, exist_ok=True)
        _reject_reparse(self.directory)
        with _exclusive_lock(self.directory / ".rotation", _PlatformPermissions()):
            with _exclusive_lock(vault, _PlatformPermissions()):
                snapshot = _read_held(vault)
            payload = _json({"source_sha256": hashlib.sha256(snapshot).hexdigest(), "vault": base64.b64encode(snapshot).decode()})
            destination = self.directory / f"backup-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}.mcb"
            _atomic(destination, _seal(payload, passphrase, "mycard-backup-v1"))
            backups = sorted(self.directory.glob("backup-*.mcb"), key=lambda p: p.stat().st_mtime, reverse=True)
            for old in backups[self.keep:]:
                if old.is_file() and not old.is_symlink():
                    old.unlink()
        return destination

    @staticmethod
    def restore(
        source: Path, destination: Path, passphrase: str, *, label: str = "scheduled"
    ) -> VerifiedRestoreLease:
        if label not in _BACKUP_LABELS:
            raise ProtectedError("backup label is invalid")
        _safe_destination(destination)
        with _exclusive_lock(source, _PlatformPermissions()):
            raw = _read_held(source)
            item = json.loads(_open(raw, passphrase, "mycard-backup-v1"))
            vault = base64.b64decode(item["vault"], validate=True)
            if hashlib.sha256(vault).hexdigest() != item["source_sha256"]:
                raise ProtectedError("backup integrity check failed")
            lease = _restore_lease(destination, vault, passphrase)
        try:
            lease.verify()
            return lease
        except BaseException:
            lease.close()
            raise


class AttachmentStore:
    """Encrypted opaque files; agents can receive only ``metadata``."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def add(
        self, content: bytes, *, purpose: str, expiry: str | None,
        retention_days: int, passphrase: str, owner_record_ref: str = "local-owner",
    ) -> dict[str, object]:
        if purpose not in _PURPOSES or not isinstance(content, bytes) or not content or len(content) > _MAX_ATTACHMENT_BYTES:
            raise ProtectedError("attachment is invalid")
        if not 1 <= retention_days <= 3650:
            raise ProtectedError("attachment retention is invalid")
        if not isinstance(owner_record_ref, str) or not 1 <= len(owner_record_ref) <= 128:
            raise ProtectedError("attachment owner reference is invalid")
        expiry_value: str | None = expiry
        if expiry_value is not None:
            try:
                parsed_expiry = datetime.fromisoformat(expiry_value)
                if parsed_expiry.tzinfo is None:
                    raise ValueError
                expiry_value = parsed_expiry.astimezone(UTC).isoformat()
            except (TypeError, ValueError):
                raise ProtectedError("attachment expiry is invalid") from None
        attachment_id = str(uuid.uuid4())
        created_at = datetime.now(UTC).isoformat()
        metadata: dict[str, object] = {
            "attachment_id": attachment_id,
            "owner_record_ref": owner_record_ref,
            "purpose": purpose,
            "expiry": expiry_value,
            "retention_days": retention_days,
            "size": len(content),
            "created_at": created_at,
            "media_schema": "attachment-media-v1",
            "metadata_schema": "attachment-metadata-v1",
            "version": _VERSION,
        }
        self.directory.mkdir(parents=True, exist_ok=True)
        _reject_reparse(self.directory)
        path = self.directory / f"attachment-{attachment_id}.mca"
        metadata_path = self._metadata_path(attachment_id)
        try:
            with _exclusive_lock(self.directory / ".attachments", _PlatformPermissions()):
                aad = self._content_aad(metadata)
                ciphertext = _seal(content, passphrase, "mycard-attachment-v1", aad=aad)
                metadata["ciphertext_sha256"] = hashlib.sha256(ciphertext).hexdigest()
                _atomic(path, ciphertext)
                _atomic(metadata_path, _seal(_json(metadata), passphrase, "mycard-attachment-metadata-v1"))
        except Exception:
            with contextlib.suppress(OSError):
                path.unlink()
            with contextlib.suppress(OSError):
                metadata_path.unlink()
            raise
        return metadata

    @staticmethod
    def read_metadata(metadata: dict[str, object]) -> dict[str, object]:
        if set(metadata) != _ATTACHMENT_METADATA_KEYS:
            raise ProtectedError("attachment metadata is invalid")
        attachment_id = metadata.get("attachment_id")
        owner_record_ref = metadata.get("owner_record_ref")
        purpose = metadata.get("purpose")
        expiry = metadata.get("expiry")
        retention = metadata.get("retention_days")
        size = metadata.get("size")
        created = metadata.get("created_at")
        if (
            not isinstance(attachment_id, str) or not isinstance(owner_record_ref, str)
            or not 1 <= len(owner_record_ref) <= 128
            or not isinstance(purpose, str) or purpose not in _PURPOSES
        ):
            raise ProtectedError("attachment metadata is invalid")
        try:
            uuid.UUID(attachment_id)
            created_at = datetime.fromisoformat(created) if isinstance(created, str) else None
            expiry_at = datetime.fromisoformat(expiry) if isinstance(expiry, str) else None
        except (ValueError, TypeError):
            raise ProtectedError("attachment metadata is invalid") from None
        if created_at is None or created_at.tzinfo is None or (expiry is not None and (expiry_at is None or expiry_at.tzinfo is None)):
            raise ProtectedError("attachment metadata is invalid")
        if not isinstance(retention, int) or isinstance(retention, bool) or not 1 <= retention <= 3650:
            raise ProtectedError("attachment metadata is invalid")
        if not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= _MAX_ATTACHMENT_BYTES:
            raise ProtectedError("attachment metadata is invalid")
        if metadata.get("media_schema") != "attachment-media-v1" or metadata.get("metadata_schema") != "attachment-metadata-v1" or metadata.get("version") != _VERSION:
            raise ProtectedError("attachment metadata is invalid")
        digest = metadata.get("ciphertext_sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ProtectedError("attachment metadata is invalid")
        try:
            int(digest, 16)
        except ValueError:
            raise ProtectedError("attachment metadata is invalid") from None
        return dict(metadata)

    @staticmethod
    def _content_aad(metadata: dict[str, object]) -> bytes:
        fields = {
            key: metadata[key]
            for key in (
                "attachment_id", "owner_record_ref", "purpose", "expiry", "retention_days",
                "size", "created_at", "media_schema", "metadata_schema", "version",
            )
        }
        return b"mycard-attachment-content-v1:" + _json(fields)

    def _metadata_path(self, attachment_id: str) -> Path:
        return self.directory / f"attachment-{attachment_id}.meta"

    def _trusted_metadata(self, attachment_id: str, passphrase: str) -> dict[str, object]:
        try:
            uuid.UUID(attachment_id)
        except ValueError:
            raise ProtectedError("attachment is invalid") from None
        _reject_reparse(self.directory)
        raw = _read_held(self._metadata_path(attachment_id), limit=4096)
        try:
            metadata = json.loads(_open(raw, passphrase, "mycard-attachment-metadata-v1"))
        except (json.JSONDecodeError, TypeError, ValueError):
            raise ProtectedError("attachment metadata is invalid") from None
        if not isinstance(metadata, dict):
            raise ProtectedError("attachment metadata is invalid")
        trusted = self.read_metadata(metadata)
        if trusted["attachment_id"] != attachment_id:
            raise ProtectedError("attachment identity is invalid")
        return trusted

    def read(self, attachment_id: str, passphrase: str) -> bytes:
        with _exclusive_lock(self.directory / ".attachments", _PlatformPermissions()):
            metadata = self._trusted_metadata(attachment_id, passphrase)
            now = datetime.now(UTC)
            expiry = metadata["expiry"]
            created = datetime.fromisoformat(str(metadata["created_at"]))
            if (isinstance(expiry, str) and datetime.fromisoformat(expiry) <= now) or created + timedelta(days=cast(int, metadata["retention_days"])) <= now:
                raise ProtectedError("attachment has expired")
            path = self.directory / f"attachment-{attachment_id}.mca"
            if path.is_symlink() or not path.is_file():
                raise ProtectedError("attachment is unavailable")
            ciphertext = _read_held(path, limit=_MAX_ATTACHMENT_BYTES)
            if hashlib.sha256(ciphertext).hexdigest() != metadata["ciphertext_sha256"]:
                raise ProtectedError("attachment integrity check failed")
            content = _open(ciphertext, passphrase, "mycard-attachment-v1", aad=self._content_aad(metadata))
            if len(content) != metadata["size"]:
                raise ProtectedError("attachment integrity check failed")
            return content

    def purge(self, attachment_id: str, passphrase: str, *, now: datetime | None = None) -> bool:
        with _exclusive_lock(self.directory / ".attachments", _PlatformPermissions()):
            metadata = self._trusted_metadata(attachment_id, passphrase)
            created = datetime.fromisoformat(str(metadata["created_at"]))
            expiry = metadata["expiry"]
            check_time = now or datetime.now(UTC)
            expired = created + timedelta(days=cast(int, metadata["retention_days"])) <= check_time
            if isinstance(expiry, str) and datetime.fromisoformat(expiry) <= check_time:
                expired = True
            if expired:
                path = self.directory / f"attachment-{attachment_id}.mca"
                metadata_path = self._metadata_path(attachment_id)
                _reject_reparse(path)
                _reject_reparse(metadata_path)
                path.unlink(missing_ok=True)
                metadata_path.unlink(missing_ok=True)
                return True
            return False
