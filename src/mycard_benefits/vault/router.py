"""Rover-authenticated, read-only private card envelope API."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict

from ..rover_auth import verify_rover_token
from .core import VaultError, VaultStore
from .keyring_store import get_keyring_password, keyring_account, load_keyring

CardReader = Callable[[], tuple[dict[str, str], ...]]


class _PrivateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PrivateCardSummary(_PrivateModel):
    card_id: str
    offering_id: str
    lifecycle: str
    created_at: str
    updated_at: str
    replacement_card_id: str | None = None


class PrivateCardList(_PrivateModel):
    cards: list[PrivateCardSummary]
    lifecycle_counts: dict[str, int]


def create_private_cards_router(
    data_dir: Path,
    *,
    rover_secret: str | None,
    reader: CardReader | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/private", tags=["private cards"])
    vault_path = (data_dir / "private" / "vault.json").resolve()
    read_cards = reader or (lambda: _read_keyring_cards(vault_path))

    @router.get("/cards", response_model=PrivateCardList)
    def list_private_cards(request: Request, response: Response) -> PrivateCardList:
        token = request.cookies.get("rover_proxy")
        if not verify_rover_token(rover_secret, token):
            raise HTTPException(status_code=401, detail="Authenticated companion session required")
        try:
            raw_cards = read_cards()
            cards = [PrivateCardSummary.model_validate(item) for item in raw_cards]
        except (OSError, VaultError, ValueError):
            raise HTTPException(status_code=503, detail="Private card list unavailable") from None
        cards.sort(key=lambda item: (item.lifecycle != "active", item.offering_id, item.created_at))
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        return PrivateCardList(
            cards=cards,
            lifecycle_counts=dict(sorted(Counter(item.lifecycle for item in cards).items())),
        )

    return router


def _read_keyring_cards(vault_path: Path) -> tuple[dict[str, str], ...]:
    if not vault_path.is_file():
        raise VaultError("vault is unavailable")
    keyring = load_keyring()
    passphrase = get_keyring_password(keyring, keyring_account(vault_path))
    if passphrase is None:
        raise VaultError("vault key is unavailable")
    session = VaultStore(vault_path).open(passphrase)
    try:
        return session.list_cards()
    finally:
        session.lock()
