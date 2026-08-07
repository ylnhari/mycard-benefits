"""Loopback-local, read-only private card envelope API."""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .core import ChildRecordKind, ChildRecordLifecycle, VaultError, VaultStore
from .keyring_store import get_keyring_password, keyring_account, load_keyring

CardReader = Callable[[], tuple[dict[str, Any], ...]]

_EXPIRING_SOON_WINDOW_DAYS = 30


class VaultUnavailable(Exception):
    """A classified, non-sensitive reason the private card list is unavailable."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


VAULT_DIAGNOSTIC_MESSAGES: dict[str, str] = {
    "demo": "Private card list is switched off in demo mode",
    "vault_missing": "No vault exists in this app's data folder yet",
    "passphrase_only": "The vault exists but was created without the operating-system keyring",
    "wrong_data_dir": "A keyring passphrase is stored for this data folder but no vault file is here",
    "locked": "The vault file exists but could not be opened",
    "keyring_unavailable": "The operating-system keyring could not be read",
    "generic": "Private card list unavailable",
}


def _expiry_signal_from_date(expiry_date: str, *, today: date) -> str:
    """Bucket a private expiry date into a coarse signal; the exact date never
    crosses this boundary. `today` is a `datetime.date`."""
    try:
        parsed = datetime.strptime(expiry_date, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("expiry_date is invalid") from None
    if parsed < today:
        return "expired"
    if parsed <= today + timedelta(days=_EXPIRING_SOON_WINDOW_DAYS):
        return "expiring_soon"
    return "active"


class _PrivateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PrivateChildRecordSummary(_PrivateModel):
    child_id: str
    parent_card_id: str
    kind: ChildRecordKind
    lifecycle: ChildRecordLifecycle
    created_at: str
    updated_at: str
    expiry_signal: Literal["expired", "expiring_soon", "active"] | None = None

    @field_validator("child_id", "parent_card_id")
    @classmethod
    def _validate_identifier(cls, value: str) -> str:
        uuid.UUID(value)
        return value

    @model_validator(mode="before")
    @classmethod
    def _derive_expiry_signal(cls, data: Any) -> Any:
        """Replace any incoming `expiry_date` with a bounded signal before this
        model's own field/extra-field validation runs, so an exact date can
        never reach a validated instance, let alone the HTTP response."""
        if not isinstance(data, dict) or "expiry_date" not in data:
            return data
        data = dict(data)
        expiry_date = data.pop("expiry_date")
        if expiry_date is not None:
            if not isinstance(expiry_date, str):
                raise ValueError("expiry_date is invalid")
            data["expiry_signal"] = _expiry_signal_from_date(
                expiry_date, today=datetime.now(UTC).date()
            )
        return data


class PrivateCardSummary(_PrivateModel):
    card_id: str
    offering_id: str
    lifecycle: str
    created_at: str
    updated_at: str
    replacement_card_id: str | None = None
    child_records: list[PrivateChildRecordSummary] = Field(default_factory=list)

    @field_validator("card_id")
    @classmethod
    def _validate_card_id(cls, value: str) -> str:
        uuid.UUID(value)
        return value

    @model_validator(mode="after")
    def _validate_child_record_linkage(self) -> PrivateCardSummary:
        seen: set[str] = set()
        for child in self.child_records:
            if child.parent_card_id != self.card_id:
                raise ValueError("child record parent_card_id does not match its card")
            if child.child_id in seen:
                raise ValueError("duplicate child record id")
            seen.add(child.child_id)
        return self


class PrivateCardList(_PrivateModel):
    cards: list[PrivateCardSummary]
    lifecycle_counts: dict[str, int]

    @model_validator(mode="after")
    def _validate_unique_card_and_child_ids(self) -> PrivateCardList:
        """Reject collisions across the complete protected response, not only
        within one card. A future reader must not be able to alias two card or
        child records into a single browser payload."""
        card_ids: set[str] = set()
        child_ids: set[str] = set()
        for card in self.cards:
            if card.card_id in card_ids:
                raise ValueError("duplicate card id")
            card_ids.add(card.card_id)
            for child in card.child_records:
                if child.child_id in child_ids:
                    raise ValueError("duplicate child record id")
                child_ids.add(child.child_id)
        return self


def create_private_cards_router(
    data_dir: Path,
    *,
    reader: CardReader | None = None,
    demo: bool = False,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/private", tags=["private cards"])
    vault_path = (data_dir / "private" / "vault.json").resolve()
    read_cards = reader or (lambda: _read_keyring_cards(vault_path))

    @router.get("/cards", response_model=PrivateCardList)
    def list_private_cards(response: Response) -> PrivateCardList:
        if demo:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "demo",
                    "message": VAULT_DIAGNOSTIC_MESSAGES["demo"],
                },
            )
        try:
            raw_cards = read_cards()
            cards = [PrivateCardSummary.model_validate(item) for item in raw_cards]
            cards.sort(
                key=lambda item: (item.lifecycle != "active", item.offering_id, item.created_at)
            )
            result = PrivateCardList(
                cards=cards,
                lifecycle_counts=dict(
                    sorted(Counter(item.lifecycle for item in cards).items())
                ),
            )
        except VaultUnavailable as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": exc.code,
                    "message": VAULT_DIAGNOSTIC_MESSAGES.get(
                        exc.code, VAULT_DIAGNOSTIC_MESSAGES["generic"]
                    ),
                },
            ) from None
        except VaultError:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "locked",
                    "message": VAULT_DIAGNOSTIC_MESSAGES["locked"],
                },
            ) from None
        except (OSError, ValueError):
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "generic",
                    "message": VAULT_DIAGNOSTIC_MESSAGES["generic"],
                },
            ) from None
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        return result

    return router


def _read_keyring_cards(vault_path: Path) -> tuple[dict[str, Any], ...]:
    try:
        keyring = load_keyring()
        passphrase = get_keyring_password(keyring, keyring_account(vault_path))
    except VaultError:
        raise VaultUnavailable("keyring_unavailable") from None
    if not vault_path.is_file():
        if passphrase is not None:
            raise VaultUnavailable("wrong_data_dir")
        raise VaultUnavailable("vault_missing")
    if passphrase is None:
        raise VaultUnavailable("passphrase_only")
    session = VaultStore(vault_path).open(passphrase)
    try:
        cards = session.list_cards()
        child_records = session.list_child_records()
    finally:
        session.lock()
    grouped: dict[str, list[dict[str, str]]] = {}
    for child in child_records:
        grouped.setdefault(child["parent_card_id"], []).append(child)
    return tuple({**card, "child_records": grouped.get(card["card_id"], [])} for card in cards)
