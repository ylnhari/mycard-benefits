"""Opt-in, local, redacted diagnostics. This module never discovers files or sends telemetry."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ALLOWED_KEYS = frozenset({"app_version", "platform", "demo", "diagnostic_code", "catalog_release"})
_SAFE_TEXT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
_SECRET_WORDS = re.compile(r"(?:password|passwd|secret|token|cookie|otp|cvv|pin|pan|private[_ -]?key|credential|authorization)", re.I)
_PAN_SHAPED = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")


def _safe_value(key: str, value: Any) -> Any:
    if key == "demo":
        return value if type(value) is bool else None
    if type(value) is str and _SAFE_TEXT.fullmatch(value) and not _SECRET_WORDS.search(value) and not _PAN_SHAPED.search(value):
        return value
    return None


def build_diagnostics(values: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for key in sorted(ALLOWED_KEYS):
        if key not in values:
            continue
        safe = _safe_value(key, values[key])
        if safe is not None:
            result[key] = safe
    return result


def export_diagnostics(values: dict[str, Any], destination: Path) -> None:
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(json.dumps(build_diagnostics(values), sort_keys=True, indent=2), encoding="utf-8")
    temporary.replace(destination)
