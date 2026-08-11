"""Explicit, safe exports of non-secret local metadata."""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

_FIELDS = ("card_id", "offering_id", "lifecycle", "created_at", "updated_at", "replacement_card_id")
_DANGEROUS = ("=", "+", "-", "@")
_SECRET_KEY = re.compile(r"(?:password|passwd|secret|token|cookie|otp|cvv|pin|pan|private[_ -]?key|credential|authorization)", re.I)
_PAN_SHAPED = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")
_REJECT = object()


def _safe_text(value: Any, pattern: re.Pattern[str]) -> Any:
    if type(value) is not str or not pattern.fullmatch(value) or _SECRET_KEY.search(value) or _PAN_SHAPED.search(value):
        return _REJECT
    return value


def _safe(value: Any) -> Any:
    if type(value) is dict:
        result = {}
        for key, pattern in {
            "card_id": _ID,
            "offering_id": _ID,
            "lifecycle": re.compile(r"^(?:active|expired|archived)$"),
            "created_at": _TIMESTAMP,
            "updated_at": _TIMESTAMP,
            "replacement_card_id": _ID,
        }.items():
            if key not in value:
                continue
            safe = None if key == "replacement_card_id" and value[key] is None else _safe_text(value[key], pattern)
            if safe is _REJECT:
                return _REJECT
            result[key] = safe
        return result
    return _REJECT


def redacted_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [safe for record in records if (safe := _safe(record)) is not _REJECT]


def export_redacted_json(records: Iterable[dict[str, Any]], destination: Path) -> None:
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(json.dumps({"records": redacted_records(records)}, sort_keys=True, indent=2), encoding="utf-8")
    temporary.replace(destination)

def export_csv(records: Iterable[dict[str, Any]], destination: Path) -> None:
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(_FIELDS), extrasaction="ignore")
    writer.writeheader()
    for record in redacted_records(records):
        row = {field: record.get(field, "") for field in _FIELDS}
        for field, value in row.items():
            if isinstance(value, str) and value.lstrip().startswith(_DANGEROUS):
                row[field] = "'" + value
        writer.writerow(row)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(buffer.getvalue(), encoding="utf-8", newline="")
    temporary.replace(destination)
