"""Per-installation signing identity used to reject wrong-port launch requests."""

from __future__ import annotations

import base64
import json
import os
import re
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

    @classmethod
    def load_or_create(cls, data_dir: Path) -> InstallationIdentity:
        data_dir.mkdir(parents=True, exist_ok=True)
        path = data_dir / IDENTITY_FILENAME
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if raw.get("schema_version") != 1 or raw.get("app_id") != APP_ID:
                    raise ValueError("identity metadata mismatch")
                install_id = str(uuid.UUID(raw["install_id"]))
                private_key = Ed25519PrivateKey.from_private_bytes(
                    _unb64url(raw["private_key"])
                )
                return cls(install_id=install_id, private_key=private_key)
            except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise RuntimeError("installation identity is corrupt; restore it from backup") from exc

        identity = cls(install_id=str(uuid.uuid4()), private_key=Ed25519PrivateKey.generate())
        private_raw = identity.private_key.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        payload = {
            "schema_version": 1,
            "app_id": APP_ID,
            "install_id": identity.install_id,
            "private_key": _b64url(private_raw),
        }
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        with suppress(OSError):
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)
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
