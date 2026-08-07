"""Verification for Rover's signed browser-session cookie."""

from __future__ import annotations

import hashlib
import hmac
import re
import time

_TOKEN_TTL_SECONDS = 24 * 60 * 60
_FUTURE_TOLERANCE_SECONDS = 60
_NONCE = re.compile(r"^[0-9a-f]{32}$")
_SIGNATURE = re.compile(r"^[0-9a-f]{64}$")


def verify_rover_token(secret: str | None, token: str | None, *, now: float | None = None) -> bool:
    """Return True only for a current token issued by Rover with ``secret``."""
    if not secret or not token or len(token) > 256:
        return False
    parts = token.split(".", 2)
    if len(parts) != 3:
        return False
    timestamp, nonce, signature = parts
    if not timestamp.isascii() or not timestamp.isdecimal():
        return False
    if not _NONCE.fullmatch(nonce) or not _SIGNATURE.fullmatch(signature):
        return False
    issued_at = int(timestamp)
    age = (time.time() if now is None else now) - issued_at
    if age > _TOKEN_TTL_SECONDS or age < -_FUTURE_TOLERANCE_SECONDS:
        return False
    expected = hmac.new(
        secret.encode("utf-8"),
        f"{timestamp}:{nonce}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
