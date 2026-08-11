from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from mycard_benefits.vault.core import (
    CardLifecycle,
    VaultAccessError,
    VaultConflictError,
    VaultError,
    VaultStore,
)
from mycard_benefits.vault.reconciliation import (
    ReconciliationAction,
    ReconciliationProposal,
    ReconciliationService,
)

PASS = "synthetic passphrase"


def _session(tmp_path: Path):
    store = VaultStore(tmp_path / "private" / "vault.json")
    session = store.create(PASS)
    session.add_card(
        "synthetic-offer-variant",
        {"pan": "SYNTHETIC-ONLY-PAN-ALPHA"},
        passphrase=PASS,
    )
    return session


def _proposal(card_id: str) -> ReconciliationProposal:
    return ReconciliationProposal(
        card_id=card_id, owner_alias="owner-a", owner_role="primary",
        offering_id="synthetic-offer-variant", offering_dimensions={"network": "synthetic-network", "tier": "standard"},
        lifecycle=CardLifecycle.ACTIVE, expiry_signal="unknown", archived_vs_expired="unknown",
        provisional_active=True, replacement_card_id=None, ambiguities=("owner_unknown",),
    )


def test_preview_preserves_ambiguity_and_supports_all_actions(tmp_path: Path) -> None:
    session = _session(tmp_path)
    card_id = session.list_cards()[0]["card_id"]
    preview = ReconciliationService().preview(session, _proposal(card_id))
    assert preview["status"] == "pending"
    assert preview["proposal"]["ambiguities"] == ["owner_unknown"]
    assert preview["allowed_actions"] == ["confirm", "correct", "defer", "reject"]
    assert preview["ui_write_handoff"] == "protected-local-service"


@pytest.mark.parametrize("action", list(ReconciliationAction))
def test_fresh_authorization_applies_each_human_disposition(tmp_path: Path, action: ReconciliationAction) -> None:
    session = _session(tmp_path)
    card_id = session.list_cards()[0]["card_id"]
    service = ReconciliationService()
    proposal = _proposal(card_id)
    correction = _proposal(card_id) if action is ReconciliationAction.CORRECT else None
    token = service.authorize(session, proposal, action, passphrase=PASS, correction=correction)
    result = service.apply(session, proposal, action, token, correction=correction)
    assert result.action is action
    assert result.changed is (action in {ReconciliationAction.CONFIRM, ReconciliationAction.CORRECT})
    assert result.audit == {"record": card_id, "action": action.value}
    assert VaultStore(tmp_path / "private" / "vault.json").open(PASS).list_cards()[0]["card_id"] == card_id


def test_correct_requires_explicit_values_and_wrong_record_is_rejected(tmp_path: Path) -> None:
    session = _session(tmp_path)
    card_id = session.list_cards()[0]["card_id"]
    service = ReconciliationService()
    proposal = _proposal(card_id)
    with pytest.raises(ValueError, match="correction is required"):
        service.authorize(session, proposal, ReconciliationAction.CORRECT, passphrase=PASS)

    wrong = replace(proposal, card_id="018f47f2-0f86-7b0a-bc7d-f00ba47c0099")
    token = service.authorize(session, proposal, ReconciliationAction.CORRECT,
                              passphrase=PASS, correction=proposal)
    with pytest.raises(ValueError, match="wrong record"):
        service.apply(session, proposal, ReconciliationAction.CORRECT, token, correction=wrong)


def test_replay_tamper_and_concurrent_change_fail_closed(tmp_path: Path) -> None:
    session = _session(tmp_path)
    card_id = session.list_cards()[0]["card_id"]
    service = ReconciliationService()
    proposal = _proposal(card_id)
    token = service.authorize(session, proposal, ReconciliationAction.CONFIRM, passphrase=PASS)
    with pytest.raises(VaultAccessError):
        service.apply(session, replace(proposal, expiry_signal="expired"), ReconciliationAction.CONFIRM, token)
    token = service.authorize(session, proposal, ReconciliationAction.DEFER, passphrase=PASS)
    service.apply(session, proposal, ReconciliationAction.DEFER, token)
    with pytest.raises(VaultAccessError):
        service.apply(session, proposal, ReconciliationAction.DEFER, token)

    session = _session(tmp_path / "concurrent")
    card_id = session.list_cards()[0]["card_id"]
    proposal = _proposal(card_id)
    token = service.authorize(session, proposal, ReconciliationAction.CONFIRM, passphrase=PASS)
    other = VaultStore(tmp_path / "concurrent" / "private" / "vault.json").open(PASS)
    other.add_card("synthetic-second", {"pan": "SYNTHETIC-ONLY-PAN-BRAVO"}, passphrase=PASS)
    with pytest.raises(VaultConflictError):
        service.apply(session, proposal, ReconciliationAction.CONFIRM, token)


@pytest.mark.parametrize("action", [ReconciliationAction.CONFIRM, ReconciliationAction.CORRECT])
def test_successful_state_mutation_reopens_in_a_fresh_process(tmp_path: Path, action: ReconciliationAction) -> None:
    session = _session(tmp_path)
    card_id = session.list_cards()[0]["card_id"]
    service = ReconciliationService()
    proposal = _proposal(card_id)
    token = service.authorize(session, proposal, action, passphrase=PASS,
                              correction=proposal if action is ReconciliationAction.CORRECT else None)
    service.apply(session, proposal, action, token,
                  correction=proposal if action is ReconciliationAction.CORRECT else None)
    reopened = VaultStore(tmp_path / "private" / "vault.json").open(PASS)
    assert reopened.list_cards()[0]["offering_id"] == "synthetic-offer-variant"


def test_authorization_binds_every_mutation_field_and_rejects_stale_revision(tmp_path: Path) -> None:
    session = _session(tmp_path)
    card_id = session.list_cards()[0]["card_id"]
    service = ReconciliationService()
    proposal = _proposal(card_id)
    token = service.authorize(session, proposal, ReconciliationAction.CONFIRM, passphrase=PASS)
    with pytest.raises(VaultAccessError):
        service.apply(session, replace(proposal, offering_id="synthetic-substituted"),
                      ReconciliationAction.CONFIRM, token)
    token = service.authorize(session, proposal, ReconciliationAction.CONFIRM, passphrase=PASS)
    session.add_card("synthetic-second", {"pan": "SYNTHETIC-ONLY-PAN-BRAVO"}, passphrase=PASS)
    with pytest.raises(VaultAccessError):
        service.apply(session, proposal, ReconciliationAction.CONFIRM, token)
    assert VaultStore(tmp_path / "private" / "vault.json").open(PASS).list_cards()[0]["offering_id"] == "synthetic-offer-variant"


def test_vault_rejects_omitted_mutation_fields(tmp_path: Path) -> None:
    session = _session(tmp_path)
    card_id = session.list_cards()[0]["card_id"]
    service = ReconciliationService()
    proposal = _proposal(card_id)
    mutation = service._mutation(session, proposal, proposal, ReconciliationAction.CONFIRM)
    token = session.authorize_reconciliation(card_id, proposal.digest(), "confirm",
                                             proposal.intent_digest(ReconciliationAction.CONFIRM),
                                             mutation, passphrase=PASS)
    del mutation["metadata"]
    with pytest.raises(VaultError):
        session.apply_reconciliation_metadata(token, mutation=mutation)
