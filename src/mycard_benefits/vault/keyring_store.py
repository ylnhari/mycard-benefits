"""Small operating-system keyring boundary shared by vault entry points."""

from __future__ import annotations

import contextlib
import hashlib
import os
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast

from .. import data_location
from .core import VaultError, secure_private_path

KEYRING_SERVICE = "mycard-benefits"
_KEYRING_SUPPORT_MISSING = "keyring support is not installed"
_DEVICE_KEY_MAX_BYTES = 1_024
_DEVICE_KEY_MIN_BYTES = 12


class Keyring(Protocol):
    def get_password(self, service_name: str, username: str) -> str | None: ...

    def set_password(self, service_name: str, username: str, password: str) -> None: ...


def load_keyring() -> Keyring:
    try:
        import keyring
    except ImportError as exc:
        raise VaultError("keyring support is not installed") from exc
    return cast(Keyring, keyring)


def keyring_account(vault_path: Path) -> str:
    try:
        guarded = data_location.reject_reparse(vault_path, allow_missing=True)
        data_location.data_location_checkpoint("before-keyring-account", guarded)
        guarded = data_location.reject_reparse(guarded, allow_missing=True)
    except data_location.DataLocationError:
        raise VaultError("vault path unavailable") from None
    digest = hashlib.sha256(os.path.normcase(str(guarded)).encode("utf-8")).hexdigest()
    return f"vault-{digest}"


def get_keyring_password(keyring: Keyring, account: str) -> str | None:
    try:
        return keyring.get_password(KEYRING_SERVICE, account)
    except Exception:
        raise VaultError("operating-system keyring is unavailable") from None


def set_keyring_password(keyring: Keyring, account: str, passphrase: str) -> None:
    try:
        keyring.set_password(KEYRING_SERVICE, account, passphrase)
    except Exception:
        raise VaultError("operating-system keyring is unavailable") from None


def _read_local_device_key(data_dir: Path) -> str | None:
    try:
        path = data_location.device_key_path_for_data_dir(data_dir)
        if not data_location.existing_regular_file(path):
            return None
        raw = data_location.read_guarded_bytes(path, maximum=_DEVICE_KEY_MAX_BYTES)
    except (OSError, data_location.DataLocationError):
        raise VaultError("device key is unavailable") from None
    if not _DEVICE_KEY_MIN_BYTES <= len(raw) <= _DEVICE_KEY_MAX_BYTES:
        raise VaultError("device key is unavailable")
    try:
        value = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise VaultError("device key is unavailable") from None
    if value.strip() != value or len(value.encode("utf-8")) != len(raw):
        raise VaultError("device key is unavailable")
    return value


def _write_local_device_key(data_dir: Path, passphrase: str) -> None:
    encoded = passphrase.encode("utf-8")
    if not _DEVICE_KEY_MIN_BYTES <= len(encoded) <= _DEVICE_KEY_MAX_BYTES:
        raise VaultError("device key is unavailable")
    try:
        path = data_location.device_key_path_for_data_dir(data_dir)
        parent = path.parent
        data_location.reject_reparse(parent, allow_missing=True)
        parent.mkdir(parents=True, exist_ok=True)
        data_location.reject_reparse(parent)
        secure_private_path(parent, directory=True)
        data_location.reject_reparse(path, allow_missing=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError:
        existing = _read_local_device_key(data_dir)
        if existing != passphrase:
            raise VaultError("device key already exists") from None
        return
    except (OSError, data_location.DataLocationError, VaultError):
        raise VaultError("device key is unavailable") from None
    committed = False
    try:
        secure_private_path(path, directory=False)
        os.chmod(path, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        committed = True
    except (OSError, VaultError):
        raise VaultError("device key is unavailable") from None
    finally:
        if descriptor >= 0:
            with contextlib.suppress(OSError):
                os.close(descriptor)
        if not committed:
            with contextlib.suppress(OSError):
                path.unlink()


def get_device_key(
    vault_path: Path,
    data_dir: Path,
    *,
    keyring_loader: Callable[[], Keyring] = load_keyring,
) -> str | None:
    """Read the device key from the OS keyring, then the guarded local fallback."""

    account = keyring_account(vault_path)
    try:
        keyring = keyring_loader()
        passphrase = get_keyring_password(keyring, account)
    except VaultError as exc:
        local = _read_local_device_key(data_dir)
        if local is not None:
            return local
        if str(exc) == _KEYRING_SUPPORT_MISSING:
            return None
        raise
    if passphrase is not None:
        return passphrase
    return _read_local_device_key(data_dir)


def set_device_key(
    vault_path: Path,
    data_dir: Path,
    passphrase: str,
    *,
    keyring_loader: Callable[[], Keyring] = load_keyring,
) -> None:
    """Store a generated device key in the OS keyring or local 0600 fallback."""

    account = keyring_account(vault_path)
    try:
        keyring = keyring_loader()
        set_keyring_password(keyring, account, passphrase)
        return
    except VaultError:
        # A backend without an installed/usable OS keyring must remain usable
        # locally.  The fallback is still guarded by the application data-root
        # and restrictive file permissions.
        _write_local_device_key(data_dir, passphrase)
