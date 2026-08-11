"""Protected loopback adapter for the human reconciliation handoff."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from .. import data_location
from .core import CardLifecycle, ReconciliationAuthorization, VaultError, VaultSession, VaultStore
from .keyring_store import get_keyring_password, keyring_account, load_keyring
from .reconciliation import ReconciliationAction, ReconciliationProposal, ReconciliationService


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProposalModel(_Model):
    card_id: str
    owner_alias: str | None = None
    owner_role: str | None = None
    offering_id: str | None = None
    offering_dimensions: dict[str, str] = Field(default_factory=dict)
    lifecycle: CardLifecycle | None = None
    expiry_signal: str = "unknown"
    archived_vs_expired: str = "unknown"
    provisional_active: bool = False
    replacement_card_id: str | None = None
    ambiguities: tuple[str, ...] = ()

    def to_domain(self) -> ReconciliationProposal:
        return ReconciliationProposal(**self.model_dump())


class AuthorizeModel(_Model):
    proposal: ProposalModel
    action: ReconciliationAction
    correction: ProposalModel | None = None
    passphrase: str = Field(min_length=12, max_length=1024)


class ApplyModel(_Model):
    proposal: ProposalModel
    action: ReconciliationAction
    authorization: str = Field(min_length=20, max_length=256)
    correction: ProposalModel | None = None


def _default_session(data_dir: Path) -> VaultSession:
    try:
        vault_path = data_location.vault_path_for_data_dir(data_dir)
    except data_location.DataLocationError:
        raise HTTPException(status_code=503, detail={"code": "unavailable", "message": "Protected local vault unavailable"}) from None
    try:
        keyring = load_keyring()
        passphrase = get_keyring_password(keyring, keyring_account(vault_path))
    except VaultError:
        raise HTTPException(status_code=503, detail={"code": "unavailable", "message": "Protected local vault unavailable"}) from None
    if passphrase is None:
        raise HTTPException(status_code=503, detail={"code": "reauthentication_required", "message": "Human reauthentication is required"})
    try:
        data_location.data_location_checkpoint("before-reconciliation-vault-open", vault_path)
        data_location.reject_reparse(vault_path)
        return VaultStore(vault_path).open(passphrase)
    except (VaultError, data_location.DataLocationError):
        raise HTTPException(status_code=503, detail={"code": "unavailable", "message": "Protected local vault unavailable"}) from None


def create_reconciliation_router(
    data_dir: Path, *, session_provider: Callable[[], VaultSession] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/private/reconciliation", tags=["private reconciliation"])
    service = ReconciliationService()
    cached_session: VaultSession | None = None

    def provider() -> VaultSession:
        nonlocal cached_session
        if session_provider is not None:
            return session_provider()
        if cached_session is None or cached_session.locked:
            cached_session = _default_session(data_dir)
        return cached_session

    @router.post("/preview")
    def preview(payload: ProposalModel) -> dict[str, Any]:
        try:
            return service.preview(provider(), payload.to_domain())
        except ValueError:
            raise HTTPException(status_code=422, detail={"code": "invalid_proposal", "message": "Proposal is invalid"}) from None

    @router.post("/authorize")
    def authorize(payload: AuthorizeModel) -> dict[str, str]:
        session = provider()
        try:
            token = service.authorize(session, payload.proposal.to_domain(), payload.action,
                                      correction=payload.correction.to_domain() if payload.correction else None,
                                      passphrase=payload.passphrase)
            return {"authorization": token._nonce, "status": "authorized"}
        except (VaultError, ValueError):
            raise HTTPException(status_code=403, detail={"code": "authorization_failed", "message": "Human authorization failed"}) from None

    @router.post("/apply")
    def apply(payload: ApplyModel, response: Response) -> dict[str, Any]:
        session = provider()
        try:
            result = service.apply(session, payload.proposal.to_domain(), payload.action,
                                   ReconciliationAuthorization(payload.authorization),
                                   correction=payload.correction.to_domain() if payload.correction else None)
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
            return {"status": result.status, "action": result.action.value, "changed": result.changed,
                    "proposal_digest": result.proposal_digest, "audit": result.audit}
        except (VaultError, ValueError):
            raise HTTPException(status_code=409, detail={"code": "not_applied", "message": "Reconciliation was not applied"}) from None

    return router
