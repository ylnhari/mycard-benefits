"""Per-installation identity and signed local health metadata."""

from __future__ import annotations

import base64
import errno
import json
import os
import re
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .config import API_VERSION, APP_ID

IDENTITY_FILENAME = "installation-identity.json"
_NONCE = re.compile(r"^[A-Za-z0-9_-]{16,256}$")


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


class _IdentityStateLock:
    """Cross-process lock for installation identity transitions."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle: Any = None

    def __enter__(self) -> _IdentityStateLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        self.handle.seek(0)
        self.handle.write(b"0")
        self.handle.flush()
        deadline = time.monotonic() + 10
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    self.handle.seek(0)
                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[attr-defined]
                return self
            except (BlockingIOError, OSError) as exc:
                if isinstance(exc, OSError) and exc.errno not in (
                    errno.EACCES,
                    errno.EAGAIN,
                    errno.EDEADLK,
                ):
                    self.handle.close()
                    raise
                if time.monotonic() >= deadline:
                    self.handle.close()
                    raise RuntimeError("installation identity is busy") from None
                time.sleep(0.01)

    def __exit__(self, *_: Any) -> None:
        if self.handle is None:
            return
        if os.name == "nt":
            import msvcrt

            self.handle.seek(0)
            msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]
        self.handle.close()


@dataclass(frozen=True)
class InstallationIdentity:
    install_id: str
    private_key: Ed25519PrivateKey

    @property
    def public_key(self) -> str:
        raw = self.private_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        return _b64url(raw)

    def _payload(self) -> dict[str, str | int]:
        private_raw = self.private_key.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        return {
            "schema_version": 3,
            "app_id": APP_ID,
            "install_id": self.install_id,
            "private_key": _b64url(private_raw),
        }

    def save(self, data_dir: Path) -> None:
        path = data_dir / IDENTITY_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._payload(), sort_keys=True), encoding="utf-8")
        with suppress(OSError):
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)

    @classmethod
    def load_or_create(cls, data_dir: Path) -> InstallationIdentity:
        data_dir.mkdir(parents=True, exist_ok=True)
        path = data_dir / IDENTITY_FILENAME
        with _IdentityStateLock(path.with_name(path.name + ".lock")):
            if path.is_file():
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                    if raw.get("schema_version") not in (1, 2, 3) or raw.get("app_id") != APP_ID:
                        raise ValueError("identity metadata mismatch")
                    install_id = str(uuid.UUID(raw["install_id"]))
                    private_key = Ed25519PrivateKey.from_private_bytes(_unb64url(raw["private_key"]))
                    identity = cls(install_id=install_id, private_key=private_key)
                    if raw.get("schema_version") != 3:
                        identity.save(data_dir)
                    return identity
                except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise RuntimeError(
                        "installation identity is corrupt; restore it from backup"
                    ) from exc

            identity = cls(install_id=str(uuid.uuid4()), private_key=Ed25519PrivateKey.generate())
            identity.save(data_dir)
            return identity

    def signed_health(self, nonce: str) -> dict[str, Any]:
        if not _NONCE.fullmatch(nonce):
            raise ValueError("nonce must be 16-256 base64url characters")
        body: dict[str, Any] = {
            "app_id": APP_ID,
            "api_version": API_VERSION,
            "install_id": self.install_id,
            "nonce": nonce,
            "public_key": self.public_key,
        }
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        body["signature"] = _b64url(self.private_key.sign(canonical))
        return body
