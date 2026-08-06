"""Bounded deterministic recursive diffs for already-validated public JSON."""

from __future__ import annotations

import json
from typing import Any

from .model import CandidateValidationError, DiffEntry

MAX_DIFF_ENTRIES = 1024
MAX_DIFF_DEPTH = 6


def deterministic_diff(before_json: str, after_json: str) -> tuple[DiffEntry, ...]:
    try:
        before = json.loads(before_json)
        after = json.loads(after_json)
    except (TypeError, json.JSONDecodeError) as exc:
        raise CandidateValidationError("candidate diff input is not canonical JSON") from exc
    entries: list[DiffEntry] = []
    _walk(before, after, "", 0, entries)
    return tuple(entries)


def _walk(before: Any, after: Any, path: str, depth: int, entries: list[DiffEntry]) -> None:
    if len(entries) >= MAX_DIFF_ENTRIES:
        raise CandidateValidationError("candidate diff exceeds maximum entries")
    if depth > MAX_DIFF_DEPTH:
        raise CandidateValidationError("candidate diff exceeds maximum depth")
    if type(before) is not type(after):
        _append(path, before, after, entries)
    elif isinstance(before, dict):
        for key in sorted(set(before) | set(after)):
            if key not in before:
                _append(_path(path, key), None, after[key], entries)
            elif key not in after:
                _append(_path(path, key), before[key], None, entries)
            else:
                _walk(before[key], after[key], _path(path, key), depth + 1, entries)
    elif isinstance(before, list):
        for index in range(max(len(before), len(after))):
            item_path = _path(path, str(index))
            if index >= len(before):
                _append(item_path, None, after[index], entries)
            elif index >= len(after):
                _append(item_path, before[index], None, entries)
            else:
                _walk(before[index], after[index], item_path, depth + 1, entries)
    elif before != after:
        _append(path, before, after, entries)


def _append(path: str, before: Any, after: Any, entries: list[DiffEntry]) -> None:
    if len(entries) >= MAX_DIFF_ENTRIES:
        raise CandidateValidationError("candidate diff exceeds maximum entries")
    entries.append(DiffEntry(path or "/", _dump(before), _dump(after)))


def _path(parent: str, value: str) -> str:
    escaped = value.replace("~", "~0").replace("/", "~1")
    return f"{parent}/{escaped}"


def _dump(value: Any) -> str | None:
    try:
        return None if value is None else json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise CandidateValidationError("candidate diff value is not canonical JSON") from exc
