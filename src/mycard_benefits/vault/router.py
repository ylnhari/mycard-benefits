"""Loopback-local, read-only private card envelope API."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from .core import VaultError, VaultStore
from .keyring_store import get_keyring_password, keyring_account, load_keyring

CardReader = Callable[[], tuple[dict[str, Any], ...]]


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


class _PrivateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PrivateChildRecordSummary(_PrivateModel):
    child_id: str
    parent_card_id: str
    kind: str
    label: str
    lifecycle: str
    created_at: str
    updated_at: str
    expiry_date: str | None = None


class PrivateCardSummary(_PrivateModel):
    card_id: str
    offering_id: str
    lifecycle: str
    created_at: str
    updated_at: str
    replacement_card_id: str | None = None
    child_records: list[PrivateChildRecordSummary] = Field(default_factory=list)


class PrivateCardList(_PrivateModel):
    cards: list[PrivateCardSummary]
    lifecycle_counts: dict[str, int]


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
        cards.sort(key=lambda item: (item.lifecycle != "active", item.offering_id, item.created_at))
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        return PrivateCardList(
            cards=cards,
            lifecycle_counts=dict(sorted(Counter(item.lifecycle for item in cards).items())),
        )

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
