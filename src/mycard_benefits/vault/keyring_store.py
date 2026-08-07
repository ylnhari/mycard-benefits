"""Small operating-system keyring boundary shared by vault entry points."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Protocol, cast

from .core import VaultError

KEYRING_SERVICE = "mycard-benefits"


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
    digest = hashlib.sha256(os.path.normcase(str(vault_path)).encode("utf-8")).hexdigest()
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
