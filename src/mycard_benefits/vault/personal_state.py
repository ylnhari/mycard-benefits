"""Validated private progress records kept inside the encrypted vault.

This module contains no web, catalog, agent, or logging integration.  Rule
identities are public references, while amounts and notes are private values
that the vault encrypts before persistence.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Final

MAX_PERSONAL_STATE_RECORDS: Final = 1_000
MAX_MANUAL_AMOUNT: Final = Decimal("1000000000")
MAX_AMOUNT_SCALE: Final = 6
MAX_NOTE_CHARS: Final = 512
MAX_PERIOD_CHARS: Final = 64
MAX_CURRENCY_CHARS: Final = 3
MAX_RULE_VERSION: Final = 100_000
MIN_IDEMPOTENCY_KEY_CHARS: Final = 16
MAX_IDEMPOTENCY_KEY_CHARS: Final = 128
PRIVATE_STATE_REVISION_CHARS: Final = 64

_UUID_RE: Final = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
_AMOUNT_RE: Final = re.compile(r"^(?:0|[0-9]+(?:\.[0-9]{1,6})?)$")
_PERIOD_RE: Final = re.compile(
    rf"^[A-Za-z0-9][A-Za-z0-9._:/-]{{0,{MAX_PERIOD_CHARS - 1}}}$"
)
_IDEMPOTENCY_KEY_RE: Final = re.compile(
    rf"^[A-Za-z0-9_-]{{{MIN_IDEMPOTENCY_KEY_CHARS},{MAX_IDEMPOTENCY_KEY_CHARS}}}$"
)
_PRIVATE_STATE_REVISION_RE: Final = re.compile(
    rf"^[0-9a-f]{{{PRIVATE_STATE_REVISION_CHARS}}}$"
)


class AttemptOutcome(StrEnum):
    SUCCESSFUL = "successful"
    FAILED = "failed"
    REJECTED = "rejected"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class ManualSpendAggregate:
    aggregate_id: str
    card_id: str
    rule_id: str
    rule_version: int
    amount: str
    currency: str
    period: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class PrivateAttempt:
    attempt_id: str
    card_id: str
    rule_id: str
    rule_version: int
    outcome: AttemptOutcome
    note: str | None
    created_at: str
    updated_at: str


def validate_identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or _UUID_RE.fullmatch(value) is None:
        raise ValueError(f"{field} is invalid")
    try:
        uuid.UUID(value)
    except ValueError:
        raise ValueError(f"{field} is invalid") from None
    return value


def validate_rule_version(value: object) -> int:
    if type(value) is not int or not 1 <= value <= MAX_RULE_VERSION:
        raise ValueError("rule_version is invalid")
    return value


def validate_idempotency_key(value: object) -> str:
    if not isinstance(value, str) or _IDEMPOTENCY_KEY_RE.fullmatch(value) is None:
        raise ValueError("idempotency key is invalid")
    return value


def validate_private_state_revision(value: object) -> str:
    if not isinstance(value, str) or _PRIVATE_STATE_REVISION_RE.fullmatch(value) is None:
        raise ValueError("private state revision is invalid")
    return value


def validate_amount(value: object) -> str:
    if not isinstance(value, str) or _AMOUNT_RE.fullmatch(value) is None:
        raise ValueError("manual aggregate amount is invalid")
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        raise ValueError("manual aggregate amount is invalid") from None
    if not parsed.is_finite() or parsed < 0 or parsed > MAX_MANUAL_AMOUNT:
        raise ValueError("manual aggregate amount is invalid")
    exponent = parsed.as_tuple().exponent
    if not isinstance(exponent, int) or -exponent > MAX_AMOUNT_SCALE:
        raise ValueError("manual aggregate amount is invalid")
    return format(parsed, "f")


def validate_currency(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != MAX_CURRENCY_CHARS
        or not value.isascii()
        or not value.isalpha()
        or value != value.upper()
    ):
        raise ValueError("currency is invalid")
    return value


def validate_period(value: object) -> str:
    if not isinstance(value, str) or _PERIOD_RE.fullmatch(value) is None:
        raise ValueError("period is invalid")
    return value


def validate_note(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > MAX_NOTE_CHARS:
        raise ValueError("attempt note is invalid")
    if any(ord(character) < 32 and character not in "\r\n\t" for character in value):
        raise ValueError("attempt note is invalid")
    return value or None


def validate_timestamp(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("timestamp is invalid")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        raise ValueError("timestamp is invalid") from None
    if parsed.year < 2000:
        raise ValueError("timestamp is invalid")
    return value


def aggregate_context_key(card_id: str, rule_id: str, rule_version: int) -> str:
    return f"{card_id}|{rule_id}|{rule_version}"


def validate_aggregate_record(
    raw: object, *, card_ids: set[str] | frozenset[str]
) -> ManualSpendAggregate:
    required = {
        "aggregate_id", "card_id", "rule_id", "rule_version", "amount", "currency",
        "period", "created_at", "updated_at",
    }
    if not isinstance(raw, dict) or set(raw) != required:
        raise ValueError("private aggregate is invalid")
    aggregate_id = validate_identifier(raw.get("aggregate_id"), "aggregate_id")
    card_id = validate_identifier(raw.get("card_id"), "card_id")
    if card_id not in card_ids:
        raise ValueError("private aggregate is invalid")
    rule_id = validate_identifier(raw.get("rule_id"), "rule_id")
    rule_version = validate_rule_version(raw.get("rule_version"))
    amount = validate_amount(raw.get("amount"))
    currency = validate_currency(raw.get("currency"))
    period = validate_period(raw.get("period"))
    created_at = validate_timestamp(raw.get("created_at"))
    updated_at = validate_timestamp(raw.get("updated_at"))
    if updated_at < created_at:
        raise ValueError("private aggregate is invalid")
    return ManualSpendAggregate(
        aggregate_id, card_id, rule_id, rule_version, amount, currency, period,
        created_at, updated_at,
    )


def validate_attempt_record(
    raw: object, *, card_ids: set[str] | frozenset[str]
) -> PrivateAttempt:
    required = {
        "attempt_id", "card_id", "rule_id", "rule_version", "outcome", "note",
        "created_at", "updated_at",
    }
    if not isinstance(raw, dict) or set(raw) != required:
        raise ValueError("private attempt is invalid")
    attempt_id = validate_identifier(raw.get("attempt_id"), "attempt_id")
    card_id = validate_identifier(raw.get("card_id"), "card_id")
    if card_id not in card_ids:
        raise ValueError("private attempt is invalid")
    rule_id = validate_identifier(raw.get("rule_id"), "rule_id")
    rule_version = validate_rule_version(raw.get("rule_version"))
    outcome_value = raw.get("outcome")
    if not isinstance(outcome_value, str):
        raise ValueError("private attempt is invalid")
    try:
        outcome = AttemptOutcome(outcome_value)
    except (TypeError, ValueError):
        raise ValueError("private attempt is invalid") from None
    note = validate_note(raw.get("note"))
    created_at = validate_timestamp(raw.get("created_at"))
    updated_at = validate_timestamp(raw.get("updated_at"))
    if updated_at < created_at:
        raise ValueError("private attempt is invalid")
    return PrivateAttempt(
        attempt_id, card_id, rule_id, rule_version, outcome, note, created_at, updated_at,
    )


def serialize_aggregate(record: ManualSpendAggregate) -> dict[str, str | int]:
    return {
        "aggregate_id": record.aggregate_id,
        "card_id": record.card_id,
        "rule_id": record.rule_id,
        "rule_version": record.rule_version,
        "amount": record.amount,
        "currency": record.currency,
        "period": record.period,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def serialize_attempt(record: PrivateAttempt) -> dict[str, str | int | None]:
    return {
        "attempt_id": record.attempt_id,
        "card_id": record.card_id,
        "rule_id": record.rule_id,
        "rule_version": record.rule_version,
        "outcome": record.outcome.value,
        "note": record.note,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }
