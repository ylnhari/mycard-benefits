"""Bounded one-time import contract for private local card manifests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .core import (
    CardLifecycle,
    ReconciliationCard,
    VaultError,
    validate_offering_id,
    validate_reconciliation_id,
    validate_reconciliation_pan,
    validate_secret_fields,
)

_MAX_MANIFEST_BYTES = 1024 * 1024
_MAX_IMPORT_CARDS = 1_000
_CARD_KEYS = frozenset({"offering_id", "lifecycle", "secret_fields"})
_ROOT_KEYS = frozenset({"schema_version", "cards"})
_RECONCILIATION_CARD_KEYS = frozenset({"source_identity", "offering_id", "lifecycle", "secret_fields"})


@dataclass(frozen=True)
class ImportCard:
    offering_id: str
    lifecycle: CardLifecycle
    secret_fields: dict[str, str]


@dataclass(frozen=True)
class CardManifest:
    cards: tuple[ImportCard, ...]


@dataclass(frozen=True)
class ReconciliationManifest:
    cards: tuple[ReconciliationCard, ...]


def load_manifest(path: Path) -> CardManifest:
    """Load a private JSON manifest without ever including field values in errors."""
    try:
        with path.open("rb") as handle:
            raw = handle.read(_MAX_MANIFEST_BYTES + 1)
    except OSError:
        raise VaultError("unable to read card manifest") from None
    if len(raw) > _MAX_MANIFEST_BYTES:
        raise VaultError("card manifest is too large")
    try:
        payload: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise VaultError("card manifest is invalid") from None
    if not isinstance(payload, dict) or set(payload) != _ROOT_KEYS:
        raise VaultError("card manifest is invalid")
    if payload.get("schema_version") != 1:
        raise VaultError("unsupported card manifest schema")
    raw_cards = payload.get("cards")
    if not isinstance(raw_cards, list) or not raw_cards or len(raw_cards) > _MAX_IMPORT_CARDS:
        raise VaultError("card manifest is invalid")

    return CardManifest(cards=tuple(_parse_card(item) for item in raw_cards))


def load_reconciliation_manifest(path: Path) -> ReconciliationManifest:
    """Load an ignored private reconciliation manifest without value-safe errors."""
    try:
        with path.open("rb") as handle:
            raw = handle.read(_MAX_MANIFEST_BYTES + 1)
    except OSError:
        raise VaultError("unable to read reconciliation manifest") from None
    if len(raw) > _MAX_MANIFEST_BYTES:
        raise VaultError("reconciliation manifest is too large")
    try:
        payload: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise VaultError("reconciliation manifest is invalid") from None
    if not isinstance(payload, dict) or set(payload) != _ROOT_KEYS or payload.get("schema_version") != 1:
        raise VaultError("reconciliation manifest is invalid")
    raw_cards = payload.get("cards")
    if not isinstance(raw_cards, list) or not raw_cards or len(raw_cards) > _MAX_IMPORT_CARDS:
        raise VaultError("reconciliation manifest is invalid")
    return ReconciliationManifest(cards=tuple(_parse_reconciliation_card(item) for item in raw_cards))


def _parse_card(value: Any) -> ImportCard:
    if not isinstance(value, dict) or set(value) != _CARD_KEYS:
        raise VaultError("card manifest is invalid")
    offering_id = value.get("offering_id")
    secret_fields = value.get("secret_fields")
    lifecycle_value = value.get("lifecycle")
    if not isinstance(offering_id, str):
        raise VaultError("card manifest is invalid")
    if not isinstance(secret_fields, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in secret_fields.items()
    ):
        raise VaultError("card manifest is invalid")
    if not isinstance(lifecycle_value, str):
        raise VaultError("card manifest is invalid")
    try:
        validate_offering_id(offering_id)
        validate_secret_fields(secret_fields)
    except VaultError:
        raise VaultError("card manifest is invalid") from None
    try:
        lifecycle = CardLifecycle(lifecycle_value)
    except (TypeError, ValueError):
        raise VaultError("card manifest is invalid") from None
    return ImportCard(
        offering_id=offering_id,
        lifecycle=lifecycle,
        secret_fields=dict(secret_fields),
    )


def _parse_reconciliation_card(value: Any) -> ReconciliationCard:
    if not isinstance(value, dict) or set(value) != _RECONCILIATION_CARD_KEYS:
        raise VaultError("reconciliation manifest is invalid")
    source_identity = value.get("source_identity")
    offering_id = value.get("offering_id")
    lifecycle_value = value.get("lifecycle")
    secret_fields = value.get("secret_fields")
    if not isinstance(source_identity, str) or not isinstance(lifecycle_value, str):
        raise VaultError("reconciliation manifest is invalid")
    if offering_id is not None and not isinstance(offering_id, str):
        raise VaultError("reconciliation manifest is invalid")
    if not isinstance(secret_fields, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in secret_fields.items()
    ):
        raise VaultError("reconciliation manifest is invalid")
    if "reconciliation_id" in secret_fields:
        raise VaultError("reconciliation manifest is invalid")
    try:
        validate_reconciliation_id(source_identity)
        if offering_id is not None:
            validate_offering_id(offering_id)
        validate_secret_fields(secret_fields)
        pan = secret_fields.get("pan")
        if pan is None:
            raise VaultError("reconciliation manifest is invalid")
        validate_reconciliation_pan(pan)
        lifecycle = CardLifecycle(lifecycle_value)
    except (TypeError, ValueError, VaultError):
        raise VaultError("reconciliation manifest is invalid") from None
    return ReconciliationCard(
        source_identity=source_identity,
        offering_id=offering_id,
        lifecycle=lifecycle,
        secret_fields=dict(secret_fields),
    )
