from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mycard_benefits.vault.core import CardLifecycle, VaultError, VaultStore
from mycard_benefits.vault.reconciliation import (
    ReconciliationAction,
    ReconciliationProposal,
    ReconciliationService,
)
from mycard_benefits.vault.reconciliation_router import create_reconciliation_router

PASS = "synthetic passphrase"


def _session(path: Path):
    session = VaultStore(path / "private" / "vault.json").create(PASS)
    session.add_card(
        "synthetic-offer-variant",
        {"pan": "SYNTHETIC-ONLY-PAN-ALPHA"},
        passphrase=PASS,
    )
    return session


def _proposal(card_id: str, **changes: object) -> ReconciliationProposal:
    base = ReconciliationProposal(
        card_id=card_id, owner_alias="owner-a", owner_role="primary",
        offering_id="synthetic-offer-variant", offering_dimensions={"network": "synthetic-network"},
        lifecycle=CardLifecycle.ACTIVE, expiry_signal="unknown", archived_vs_expired="unknown",
        provisional_active=True, replacement_card_id=None, ambiguities=("owner_unknown",),
    )
    return replace(base, **changes)


def test_token_binds_action_final_correction_and_record(tmp_path: Path) -> None:
    session = _session(tmp_path)
    card_id = session.list_cards()[0]["card_id"]
    service = ReconciliationService()
    proposal = _proposal(card_id)
    correction = replace(proposal, offering_id="synthetic-other-variant")
    token = service.authorize(session, proposal, ReconciliationAction.CORRECT,
                              correction=correction, passphrase=PASS)
    with pytest.raises(VaultError):
        service.apply(session, proposal, ReconciliationAction.CONFIRM, token)
    # The failed substitution did not make the vault unreadable or mutate it.
    assert VaultStore(tmp_path / "private" / "vault.json").open(PASS).list_cards()[0]["offering_id"] == "synthetic-offer-variant"


def test_unknown_ambiguity_text_is_rejected_and_preview_is_redacted(tmp_path: Path) -> None:
    session = _session(tmp_path)
    card_id = session.list_cards()[0]["card_id"]
    with pytest.raises(ValueError):
        _proposal(card_id, ambiguities=("SYNTHETIC-ONLY-EXPIRY-PRIVATE",))
    preview = ReconciliationService().preview(session, _proposal(card_id))
    assert "SYNTHETIC-ONLY-EXPIRY-PRIVATE" not in str(preview)
    assert preview["ambiguity_copy"]["owner_unknown"] == "Owner is not confirmed."


def test_invalid_lineage_and_persist_crash_leave_vault_reopenable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session = _session(tmp_path)
    card_id = session.list_cards()[0]["card_id"]
    session.add_card(
        "synthetic-offer-variant",
        {"pan": "SYNTHETIC-ONLY-PAN-BRAVO"},
        passphrase=PASS,
    )
    second = session.list_cards()[1]["card_id"]
    service = ReconciliationService()
    invalid = _proposal(card_id, replacement_card_id=second)
    token = service.authorize(session, invalid, ReconciliationAction.CONFIRM, passphrase=PASS)
    with pytest.raises(VaultError):
        service.apply(session, invalid, ReconciliationAction.CONFIRM, token)
    reopened = VaultStore(tmp_path / "private" / "vault.json").open(PASS)
    assert all(card.get("replacement_card_id") is None for card in reopened.list_cards())
    valid = _proposal(card_id)
    token = service.authorize(session, valid, ReconciliationAction.CONFIRM, passphrase=PASS)
    monkeypatch.setattr(session, "_persist", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("synthetic crash")))
    with pytest.raises(OSError):
        service.apply(session, valid, ReconciliationAction.CONFIRM, token)
    assert VaultStore(tmp_path / "private" / "vault.json").open(PASS).list_cards()[0]["offering_id"] == "synthetic-offer-variant"


def test_route_preview_authorize_apply_and_no_private_reflection(tmp_path: Path) -> None:
    session = _session(tmp_path)
    app = __import__("fastapi").FastAPI()
    app.include_router(create_reconciliation_router(tmp_path, session_provider=lambda: session))
    client = TestClient(app)
    card_id = session.list_cards()[0]["card_id"]
    proposal = _proposal(card_id).canonical()
    preview = client.post("/api/v1/private/reconciliation/preview", json=proposal)
    assert preview.status_code == 200
    auth = client.post("/api/v1/private/reconciliation/authorize",
                       json={"proposal": proposal, "action": "defer", "passphrase": PASS})
    assert auth.status_code == 200
    applied = client.post("/api/v1/private/reconciliation/apply",
                          json={"proposal": proposal, "action": "defer",
                                "authorization": auth.json()["authorization"]})
    assert applied.status_code == 200 and applied.json()["changed"] is False
    leaked = client.post("/api/v1/private/reconciliation/preview",
                         json={**proposal, "owner_alias": "SYNTHETIC-ONLY-PRIVATE-NAME"})
    assert leaked.status_code == 422
    assert "SYNTHETIC-ONLY-PRIVATE-NAME" not in leaked.text


def test_preview_resolves_ids_from_protected_state_and_does_not_echo_unchecked_id(tmp_path: Path) -> None:
    session = _session(tmp_path)
    app = __import__("fastapi").FastAPI()
    app.include_router(create_reconciliation_router(tmp_path, session_provider=lambda: session))
    client = TestClient(app)
    card_id = session.list_cards()[0]["card_id"]
    proposal = _proposal(card_id).canonical()
    unchecked = "018f47f2-0f86-7b0a-bc7d-f00ba47c0999"
    response = client.post("/api/v1/private/reconciliation/preview",
                           json={**proposal, "replacement_card_id": unchecked})
    assert response.status_code == 422
    assert unchecked not in response.text


def test_unknown_lineage_preserves_existing_replacement_until_explicit_choice(tmp_path: Path) -> None:
    session = _session(tmp_path)
    card_id = session.list_cards()[0]["card_id"]
    replacement = session.replace_card(
        card_id,
        {"pan": "SYNTHETIC-ONLY-PAN-BRAVO"},
        lifecycle=CardLifecycle.ARCHIVED,
        passphrase=PASS,
    )
    service = ReconciliationService()
    proposal = _proposal(card_id, lifecycle=CardLifecycle.ARCHIVED,
                         ambiguities=("lineage_unknown",))
    token = service.authorize(session, proposal, ReconciliationAction.CONFIRM, passphrase=PASS)
    service.apply(session, proposal, ReconciliationAction.CONFIRM, token)
    reopened = VaultStore(tmp_path / "private" / "vault.json").open(PASS)
    old = next(card for card in reopened.list_cards() if card["card_id"] == card_id)
    assert old["replacement_card_id"] == replacement
