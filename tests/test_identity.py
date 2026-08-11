from __future__ import annotations

import base64
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from mycard_benefits.identity import InstallationIdentity


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def test_identity_is_stable_and_health_signature_verifies(tmp_path: Path) -> None:
    first = InstallationIdentity.load_or_create(tmp_path)
    second = InstallationIdentity.load_or_create(tmp_path)
    assert first.install_id == second.install_id
    assert first.public_key == second.public_key

    signed = first.signed_health("0123456789abcdef")
    signature = _decode(str(signed.pop("signature")))
    canonical = json.dumps(signed, sort_keys=True, separators=(",", ":")).encode()
    Ed25519PublicKey.from_public_bytes(_decode(first.public_key)).verify(signature, canonical)


def test_identity_rejects_invalid_nonce_and_tampering(tmp_path: Path) -> None:
    identity = InstallationIdentity.load_or_create(tmp_path)
    with pytest.raises(ValueError, match="nonce"):
        identity.signed_health("short")
    signed = identity.signed_health("0123456789abcdef")
    signature = _decode(str(signed.pop("signature")))
    signed["app_id"] = "wrong-app"
    canonical = json.dumps(signed, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(InvalidSignature):
        Ed25519PublicKey.from_public_bytes(_decode(identity.public_key)).verify(signature, canonical)


def test_identity_creation_is_stable_under_concurrency(tmp_path: Path) -> None:
    def load() -> str:
        return InstallationIdentity.load_or_create(tmp_path).install_id

    with ThreadPoolExecutor(max_workers=4) as executor:
        install_ids = list(executor.map(lambda _: load(), range(4)))
    assert len(set(install_ids)) == 1
