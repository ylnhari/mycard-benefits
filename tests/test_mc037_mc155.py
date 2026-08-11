from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mycard_benefits.app import create_app
from mycard_benefits.config import Settings
from mycard_benefits.vault import AuditLog, CardLifecycle, VaultAccessError, VaultError, VaultStore
from mycard_benefits.vault import core as vault_core

ROOT = Path(__file__).parents[1]
PASS = "SYNTHETIC-ONLY-passphrase"
NEXT_PASS = "SYNTHETIC-ONLY-recovery-passphrase"
WRONG_PASS = "SYNTHETIC-ONLY-wrong-passphrase"
CARD = "hdfc-regalia-gold-credit"


def _events(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _protected_headers(client: TestClient) -> dict[str, str]:
    token = client.get("/api/v1/private/csrf-token").json()["csrf_token"]
    return {
        "Origin": "http://127.0.0.1:8777",
        "Host": "127.0.0.1:8777",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "X-CSRF-Token": token,
    }


def _api_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[TestClient, Path, str]:
    data_dir = tmp_path / "data"
    vault_path = data_dir / "private" / "vault.json"
    session = VaultStore(vault_path).create(PASS)
    card_id = session.add_card(
        CARD,
        {
            "pan": "SYNTHETIC-ONLY-PAN",
            "cvv": "SYNTHETIC-ONLY-CVV",
            "pin": "SYNTHETIC-ONLY-PIN",
            "owner_alias": "SYNTHETIC-ONLY-owner",
            "expiry_month": "SYNTHETIC-ONLY-month",
            "expiry_year": "SYNTHETIC-ONLY-year",
        },
        passphrase=PASS,
    )
    session.lock()

    class StubKeyring:
        def get_password(self, service_name: str, username: str) -> str:
            return PASS

    import mycard_benefits.vault.router as router

    monkeypatch.setattr(router, "load_keyring", lambda: StubKeyring())
    settings = Settings(data_dir=data_dir, catalog_dir=ROOT / "catalog", port=8777)
    return TestClient(create_app(settings)), vault_path, card_id


def test_required_operations_emit_value_free_events_and_preserve_lineage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    timestamp_counter = 0

    def synthetic_timestamp() -> str:
        nonlocal timestamp_counter
        timestamp_counter += 1
        minutes, seconds = divmod(timestamp_counter, 60)
        return f"2026-08-10T00:{minutes:02d}:{seconds:02d}Z"

    monkeypatch.setattr(vault_core, "_timestamp", synthetic_timestamp)
    vault_path = tmp_path / "vault.json"
    audit_path = tmp_path / "audit.jsonl"
    audit = AuditLog(audit_path)
    session = VaultStore(vault_path, audit_log=audit).create(PASS)
    original_id = session.add_card(
        CARD,
        {
            "pan": "SYNTHETIC-ONLY-ORIGINAL-PAN",
            "cvv": "SYNTHETIC-ONLY-ORIGINAL-CVV",
            "pin": "SYNTHETIC-ONLY-ORIGINAL-PIN",
            "nickname": "SYNTHETIC-ONLY-original",
        },
        passphrase=PASS,
    )

    imported_id = session.add_cards(
        [
            (
                CARD,
                {"pan": "SYNTHETIC-ONLY-IMPORT-PAN"},
                CardLifecycle.ACTIVE,
            )
        ]
    )[0]
    session.edit_card(
        original_id,
        {"nickname": "SYNTHETIC-ONLY-edited"},
        passphrase=PASS,
    )
    assert session.transition_card(original_id, CardLifecycle.LOST, passphrase=PASS)
    successor_id = session.replace_card(
        original_id,
        {
            "pan": "SYNTHETIC-ONLY-REPLACEMENT-PAN",
            "cvv": "SYNTHETIC-ONLY-REPLACEMENT-CVV",
        },
        passphrase=PASS,
    )
    session.erase_cvv_pin(original_id, passphrase=PASS)
    export_path = tmp_path / "recovery.json"
    session.export_rewrapped(export_path, NEXT_PASS)
    session.delete_card(imported_id, confirmation="DELETE CARD", passphrase=PASS)
    purged_id = session.add_card(
        CARD,
        {"pan": "SYNTHETIC-ONLY-PURGED-PAN"},
        passphrase=PASS,
    )
    session.purge_card(purged_id, confirmation="DELETE CARD", passphrase=PASS)

    cards = {item["card_id"]: item for item in session.list_cards()}
    assert cards[original_id]["lifecycle"] == CardLifecycle.CLOSED.value
    assert cards[original_id]["replacement_card_id"] == successor_id
    assert successor_id in cards
    assert cards[original_id]["updated_at"] > cards[original_id]["created_at"]
    assert cards[original_id]["updated_at"] > cards[successor_id]["created_at"]
    session.lock()

    reopened = VaultStore(vault_path).open(PASS)
    reopened_cards = {item["card_id"]: item for item in reopened.list_cards()}
    assert set(reopened_cards) == {original_id, successor_id}
    assert reopened_cards[original_id]["updated_at"] == cards[original_id]["updated_at"]
    assert reopened_cards[original_id]["updated_at"] > reopened_cards[successor_id]["created_at"]
    with pytest.raises(VaultAccessError):
        reopened.authorize_reveal(original_id, "cvv", passphrase=PASS)
    with pytest.raises(VaultAccessError):
        reopened.authorize_reveal(original_id, "pin", passphrase=PASS)
    reopened.lock()

    events = _events(audit_path)
    assert [event["action"] for event in events] == [
        "import",
        "edit",
        "lifecycle",
        "replace",
        "secret_erase",
        "export",
        "delete",
        "purge",
    ]
    assert all(
        set(event) == {"event_id", "occurred_at", "action", "record_ref", "success"}
        for event in events
    )
    assert all(event["success"] is True for event in events)
    assert all(isinstance(event["event_id"], str) and event["event_id"] for event in events)
    assert all(
        isinstance(event["record_ref"], str)
        and len(event["record_ref"]) == 64
        and event["record_ref"] == event["record_ref"].lower()
        and all(character in "0123456789abcdef" for character in event["record_ref"])
        for event in events
    )
    # Repeated operations on one card may intentionally share the same opaque
    # record binding; the action field distinguishes those committed events.
    assert len({event["record_ref"] for event in events}) >= 4
    audit_bytes = audit_path.read_bytes()
    for marker in (
        PASS,
        NEXT_PASS,
        "SYNTHETIC-ONLY-ORIGINAL-PAN",
        "SYNTHETIC-ONLY-ORIGINAL-CVV",
        "SYNTHETIC-ONLY-ORIGINAL-PIN",
        "SYNTHETIC-ONLY-owner",
    ):
        assert marker.encode() not in audit_bytes
    assert export_path.is_file()


class _FailingAudit:
    def record(
        self, action: object, *, record_ref: str | None = None, success: bool = True
    ) -> str:
        raise RuntimeError("SYNTHETIC-ONLY-audit-failure")


def test_audit_failure_rolls_back_mutation_and_export_without_success_claim(
    tmp_path: Path,
) -> None:
    vault_path = tmp_path / "vault.json"
    session = VaultStore(vault_path).create(PASS)
    card_id = session.add_card(
        CARD,
        {"pan": "SYNTHETIC-ONLY-PAN", "nickname": "SYNTHETIC-ONLY-old"},
        passphrase=PASS,
    )
    session.lock()
    before = vault_path.read_bytes()

    failing = VaultStore(vault_path, audit_log=_FailingAudit()).open(PASS)
    with pytest.raises(VaultError, match="protected audit unavailable"):
        failing.edit_card(card_id, {"nickname": "SYNTHETIC-ONLY-new"}, passphrase=PASS)
    assert vault_path.read_bytes() == before
    check = VaultStore(vault_path).open(PASS)
    authorization = check.authorize_reveal(card_id, "nickname", passphrase=PASS)
    assert check.consume_reveal(authorization) == "SYNTHETIC-ONLY-old"
    check.lock()

    destination = tmp_path / "failed-export.json"
    with pytest.raises(VaultError, match="protected audit unavailable"):
        failing.export_rewrapped(destination, NEXT_PASS)
    assert not destination.exists()
    failing.lock()


@pytest.mark.parametrize("lifecycle", ["expired", "lost", "closed"])
def test_lifecycle_prompt_and_secret_erase_are_fresh_private_and_preserve_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lifecycle: str
) -> None:
    client, vault_path, card_id = _api_setup(tmp_path, monkeypatch)
    with client:
        response = client.post(
            f"/api/v1/private/cards/{card_id}/lifecycle",
            headers=_protected_headers(client),
            json={"passphrase": PASS, "lifecycle": lifecycle},
        )
        assert response.status_code == 200
        assert response.json() == {"card_id": card_id, "successor_card_id": None, "erase_prompt": True, "backup_warning": None, "action_authorized": False}
        assert response.headers["cache-control"] == "no-store"
        assert "SYNTHETIC-ONLY-CVV" not in response.text
        assert "SYNTHETIC-ONLY-PIN" not in response.text

        rejected = client.post(
            f"/api/v1/private/cards/{card_id}/erase-cvv-pin",
            headers=_protected_headers(client),
            json={"passphrase": WRONG_PASS},
        )
        assert rejected.status_code == 401
        assert rejected.headers["cache-control"] == "no-store"
        assert "SYNTHETIC-ONLY" not in rejected.text
        assert [event["action"] for event in _events(vault_path.with_name("audit.jsonl"))] == ["lifecycle"]

        erased = client.post(
            f"/api/v1/private/cards/{card_id}/erase-cvv-pin",
            headers=_protected_headers(client),
            json={"passphrase": PASS},
        )
        assert erased.status_code == 200
        assert erased.headers["cache-control"] == "no-store"
        assert "SYNTHETIC-ONLY" not in erased.text

    reopened = VaultStore(vault_path).open(PASS)
    assert reopened.list_cards() == (
        {
            "card_id": card_id,
            "offering_id": CARD,
            "lifecycle": lifecycle,
            "created_at": reopened.list_cards()[0]["created_at"],
            "updated_at": reopened.list_cards()[0]["updated_at"],
        },
    )
    with pytest.raises(VaultAccessError):
        reopened.authorize_reveal(card_id, "cvv", passphrase=PASS)
    with pytest.raises(VaultAccessError):
        reopened.authorize_reveal(card_id, "pin", passphrase=PASS)
    reopened.lock()

    events = _events(vault_path.with_name("audit.jsonl"))
    assert [event["action"] for event in events] == ["lifecycle", "secret_erase"]
    assert all(event["success"] is True for event in events)
    assert all(isinstance(event["record_ref"], str) for event in events)
    assert b"SYNTHETIC-ONLY-CVV" not in vault_path.with_name("audit.jsonl").read_bytes()


def test_ui_exposes_a_separate_keep_by_default_erase_prompt_without_plaintext() -> None:
    script = (ROOT / "src" / "mycard_benefits" / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    template = (ROOT / "src" / "mycard_benefits" / "templates" / "index.html").read_text(
        encoding="utf-8"
    )

    for fragment in (
        'id="secretErasePrompt"',
        'id="secretEraseForm"',
        'id="secretEraseKeepButton"',
        'Keep stored CVV/PIN',
        'Erase stored CVV/PIN',
        'hidden role="alertdialog"',
        'autocomplete="current-password"',
    ):
        assert fragment in template
    for fragment in (
        "function showSecretErasePrompt",
        "function keepSecretErasePrompt",
        "function submitSecretErase",
        "result?.erase_prompt === true",
        "encodeURIComponent(cardId)",
        "/erase-cvv-pin",
        "keeping them is the default",
        "clearSecretErasePrompt",
        "form.reset()",
    ):
        assert fragment in script
    assert "card.secret_fields" not in script
    assert "clipboard" not in script.lower()
