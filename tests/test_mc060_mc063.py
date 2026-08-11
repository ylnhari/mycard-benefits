"""Focused synthetic coverage for MC-060 and MC-063 private state."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mycard_benefits.app import create_app
from mycard_benefits.config import Settings
from mycard_benefits.vault import (
    AttemptOutcome,
    VaultConflictError,
    VaultError,
    VaultStore,
)
from mycard_benefits.vault import core as vault_core

ROOT = Path(__file__).parents[1]
PASS = "SYNTHETIC-ONLY-PASSPHRASE"
CARD_OFFERING = "synthetic-only-card"
RULE_ID = "33333333-3333-4333-8333-333333333333"
OTHER_RULE_ID = "44444444-4444-4444-8444-444444444444"
ORIGIN = "http://127.0.0.1:8777"


class _TestPermissions:
    def secure_directory(self, path: Path) -> None:
        return None

    def secure_file(self, path: Path) -> None:
        return None


def _store(tmp_path: Path) -> VaultStore:
    return VaultStore(tmp_path / "private" / "vault.json", _permissions=_TestPermissions())


def _card(session) -> str:  # type: ignore[no-untyped-def]
    return session.add_card(
        CARD_OFFERING,
        {"pan": "SYNTHETIC-ONLY-NON-NUMERIC-PAN"},
        passphrase=PASS,
    )


def test_private_state_core_is_encrypted_bounded_and_crud_safe(tmp_path: Path) -> None:
    store = _store(tmp_path)
    session = store.create(PASS)
    card_id = _card(session)
    amount = "987654321.123456"
    note = "SYNTHETIC-ONLY-private-attempt-note"

    aggregate = session.upsert_manual_aggregate(
        card_id, RULE_ID, 1, amount, "INR", "2026-Q1", passphrase=PASS
    )
    assert aggregate["amount"] == amount
    assert len(session.list_manual_aggregates()) == 1
    updated = session.upsert_manual_aggregate(
        card_id, RULE_ID, 1, "12.50", "USD", "2026-Q2", passphrase=PASS
    )
    assert updated["aggregate_id"] == aggregate["aggregate_id"]
    assert updated["created_at"] == aggregate["created_at"]
    assert updated["amount"] == "12.50"

    first_attempt = session.add_private_attempt(
        card_id, RULE_ID, 1, AttemptOutcome.SUCCESSFUL, note, passphrase=PASS
    )
    second_attempt = session.add_private_attempt(
        card_id, RULE_ID, 1, AttemptOutcome.SKIPPED, None, passphrase=PASS
    )
    assert [item["attempt_id"] for item in session.list_private_attempts()] == [
        first_attempt["attempt_id"], second_attempt["attempt_id"]
    ]
    edited = session.update_private_attempt(
        str(first_attempt["attempt_id"]), AttemptOutcome.FAILED,
        "SYNTHETIC-ONLY-edited-note", passphrase=PASS,
    )
    assert edited["outcome"] == "failed"
    assert edited["created_at"] == first_attempt["created_at"]
    session.delete_private_attempt(str(second_attempt["attempt_id"]), passphrase=PASS)
    assert len(session.list_private_attempts()) == 1

    raw = store.path.read_text(encoding="utf-8")
    assert note not in raw
    assert amount not in raw
    assert "manual_aggregates" not in json.loads(raw)["private_state"]

    reopened = store.open(PASS)
    assert reopened.list_manual_aggregates()[0]["amount"] == "12.50"
    assert reopened.list_private_attempts()[0]["outcome"] == "failed"
    assert reopened.list_private_attempts()[0]["note"] == "SYNTHETIC-ONLY-edited-note"

    assert reopened.clear_manual_aggregate(card_id, RULE_ID, 1, passphrase=PASS)
    assert reopened.list_manual_aggregates() == ()
    reopened.delete_card(card_id, confirmation="DELETE CARD", passphrase=PASS)
    assert reopened.list_private_attempts() == ()


@pytest.mark.parametrize(
    ("amount", "currency", "period", "rule_version"),
    [
        ("-1", "INR", "2026-Q1", 1),
        ("NaN", "INR", "2026-Q1", 1),
        ("1000000000.0000001", "INR", "2026-Q1", 1),
        ("1.1234567", "INR", "2026-Q1", 1),
        ("1", "inr", "2026-Q1", 1),
        ("1", "INR", "", 1),
        ("1", "INR", "2026-Q1", 0),
    ],
)
def test_private_state_validation_fails_closed(
    tmp_path: Path,
    amount: str,
    currency: str,
    period: str,
    rule_version: int,
) -> None:
    session = _store(tmp_path).create(PASS)
    card_id = _card(session)
    with pytest.raises((VaultError, ValueError)):
        session.upsert_manual_aggregate(
            card_id, RULE_ID, rule_version, amount, currency, period, passphrase=PASS
        )
    assert session.list_manual_aggregates() == ()
    with pytest.raises((VaultError, ValueError)):
        session.add_private_attempt(
            card_id, RULE_ID, 1, AttemptOutcome.SUCCESSFUL,
            "SYNTHETIC-ONLY-\x00-invalid", passphrase=PASS,
        )
    assert session.list_private_attempts() == ()


def test_private_state_stale_revision_and_failed_write_leave_state_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _store(tmp_path)
    session = store.create(PASS)
    card_id = _card(session)
    other = VaultStore(store.path, _permissions=_TestPermissions()).open(PASS)

    def fail_write(*args: object, **kwargs: object) -> None:
        raise VaultError("SYNTHETIC-ONLY-write-failure")

    monkeypatch.setattr(vault_core, "_atomic_write", fail_write)
    with pytest.raises(VaultError):
        session.upsert_manual_aggregate(
            card_id, RULE_ID, 1, "10", "INR", "2026-Q1", passphrase=PASS
        )
    assert session.list_manual_aggregates() == ()
    monkeypatch.undo()

    session.upsert_manual_aggregate(
        card_id, RULE_ID, 1, "10", "INR", "2026-Q1", passphrase=PASS
    )
    with pytest.raises(VaultConflictError):
        other.upsert_manual_aggregate(
            card_id, RULE_ID, 1, "11", "INR", "2026-Q1", passphrase=PASS
        )
    other.lock()


def test_private_attempt_contract_is_atomic_across_concurrent_core_requests(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path / "same-contract")
    session = store.create(PASS)
    card_id = _card(session)
    revision = session.private_state_revision_hex

    def create_with_key(key: str) -> tuple[str, dict[str, str | int | None] | None]:
        try:
            return (
                "ok",
                session.add_private_attempt(
                    card_id,
                    RULE_ID,
                    1,
                    AttemptOutcome.SUCCESSFUL,
                    "SYNTHETIC-ONLY-concurrent-note",
                    passphrase=PASS,
                    idempotency_key=key,
                    expected_private_state_revision=revision,
                ),
            )
        except VaultConflictError:
            return ("conflict", None)

    with ThreadPoolExecutor(max_workers=2) as executor:
        same_results = list(
            executor.map(
                create_with_key,
                ["SYNTHETIC-ONLY-concurrent-same-key"] * 2,
            )
        )
    assert [status for status, _ in same_results] == ["ok", "ok"]
    same_ids = {
        str(result["attempt_id"])
        for _, result in same_results
        if result is not None
    }
    assert len(same_ids) == 1
    assert len(session.list_private_attempts()) == 1

    distinct_store = _store(tmp_path / "distinct-contract")
    distinct = distinct_store.create(PASS)
    distinct_card_id = _card(distinct)
    distinct_revision = distinct.private_state_revision_hex

    def create_distinct(key: str) -> tuple[str, dict[str, str | int | None] | None]:
        try:
            return (
                "ok",
                distinct.add_private_attempt(
                    distinct_card_id,
                    RULE_ID,
                    1,
                    AttemptOutcome.SUCCESSFUL,
                    "SYNTHETIC-ONLY-distinct-note",
                    passphrase=PASS,
                    idempotency_key=key,
                    expected_private_state_revision=distinct_revision,
                ),
            )
        except VaultConflictError:
            return ("conflict", None)

    with ThreadPoolExecutor(max_workers=2) as executor:
        distinct_results = list(
            executor.map(
                create_distinct,
                [
                    "SYNTHETIC-ONLY-concurrent-key-a",
                    "SYNTHETIC-ONLY-concurrent-key-b",
                ],
            )
        )
    assert sorted(status for status, _ in distinct_results) == ["conflict", "ok"]
    assert len(distinct.list_private_attempts()) == 1


class _StubKeyring:
    def __init__(self, passphrase: str) -> None:
        self.passphrase = passphrase

    def get_password(self, service_name: str, username: str) -> str:
        return self.passphrase


def _browser_headers(**extra: str) -> dict[str, str]:
    return {
        "Origin": ORIGIN,
        "Host": "127.0.0.1:8777",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        **extra,
    }


def _csrf_headers(client: TestClient, **extra: str) -> dict[str, str]:
    token = client.get("/api/v1/private/csrf-token").json()["csrf_token"]
    return _browser_headers(**{"X-CSRF-Token": token, **extra})


def _private_state(client: TestClient) -> dict[str, object]:
    response = client.get("/api/v1/private/personal-state", headers=_browser_headers())
    assert response.status_code == 200, response.text
    return response.json()


def _attempt_contract(client: TestClient, key: str) -> dict[str, str]:
    revision = _private_state(client)["private_state_revision"]
    assert isinstance(revision, str)
    return {
        "idempotency_key": key,
        "expected_private_state_revision": revision,
    }


def _setup_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, Path, str]:
    data_dir = tmp_path / "data"
    vault_path = data_dir / "private" / "vault.json"
    session = VaultStore(vault_path, _permissions=_TestPermissions()).create(PASS)
    card_id = _card(session)
    session.lock()
    import mycard_benefits.vault.router as router

    monkeypatch.setattr(router, "load_keyring", lambda: _StubKeyring(PASS))
    settings = Settings(data_dir=data_dir, catalog_dir=ROOT / "catalog", port=8777)
    return TestClient(create_app(settings)), vault_path, card_id


def _unlock(client: TestClient) -> None:
    bootstrap = client.get(
        "/api/v1/private/unlock/bootstrap", headers=_browser_headers()
    )
    assert bootstrap.status_code == 200, bootstrap.text
    unlocked = client.post(
        "/api/v1/private/unlock",
        headers=_browser_headers(
            **{"Content-Type": "application/json", "X-CSRF-Token": bootstrap.json()["csrf_token"]}
        ),
        json={"passphrase": PASS, "remember": False},
    )
    assert unlocked.status_code == 200, unlocked.text


def test_protected_api_requires_unlocked_session_and_keeps_private_state_local(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, vault_path, card_id = _setup_api(tmp_path, monkeypatch)
    with client:
        locked = client.get("/api/v1/private/personal-state", headers=_browser_headers())
        assert locked.status_code == 401
        assert locked.headers["cache-control"] == "no-store"
        _unlock(client)

        empty = client.get("/api/v1/private/personal-state", headers=_browser_headers())
        assert empty.status_code == 200
        assert empty.json()["aggregates"] == []
        assert empty.json()["attempts"] == []
        assert isinstance(empty.json()["private_state_revision"], str)

        body = {
            "passphrase": PASS,
            "rule_id": RULE_ID,
            "rule_version": 1,
            "amount": "987654321.123456",
            "currency": "INR",
            "period": "2026-Q1",
        }
        wrong_csrf = _csrf_headers(client)
        wrong_csrf["X-CSRF-Token"] = "SYNTHETIC-ONLY-WRONG-CSRF"
        rejected = client.put(
            f"/api/v1/private/threshold-aggregates/{card_id}",
            headers=wrong_csrf,
            json=body,
        )
        assert rejected.status_code == 403
        assert rejected.headers["cache-control"] == "no-store"

        wrong_passphrase = dict(body, passphrase="SYNTHETIC-ONLY-WRONG-PASSPHRASE")
        failed = client.put(
            f"/api/v1/private/threshold-aggregates/{card_id}",
            headers=_csrf_headers(client),
            json=wrong_passphrase,
        )
        assert failed.status_code == 401
        assert failed.headers["cache-control"] == "no-store"
        assert "WRONG-PASSPHRASE" not in failed.text

        saved = client.put(
            f"/api/v1/private/threshold-aggregates/{card_id}",
            headers=_csrf_headers(client),
            json=body,
        )
        assert saved.status_code == 200, saved.text
        aggregate = saved.json()
        assert aggregate["amount"] == body["amount"]
        replay = client.put(
            f"/api/v1/private/threshold-aggregates/{card_id}",
            headers=_csrf_headers(client),
            json=dict(body, amount="12.50"),
        )
        assert replay.status_code == 200
        assert replay.json()["aggregate_id"] == aggregate["aggregate_id"]

        attempt = client.post(
            f"/api/v1/private/attempts/{card_id}",
            headers=_csrf_headers(client),
            json={
                **_attempt_contract(client, "SYNTHETIC-ONLY-attempt-create-1"),
                "passphrase": PASS,
                "rule_id": RULE_ID,
                "rule_version": 1,
                "outcome": "successful",
                "note": "SYNTHETIC-ONLY-api-note",
            },
        )
        assert attempt.status_code == 200, attempt.text
        attempt_id = attempt.json()["attempt_id"]
        assert attempt.json()["note"] == "SYNTHETIC-ONLY-api-note"

        listed = client.get("/api/v1/private/personal-state", headers=_browser_headers())
        assert listed.json()["aggregates"][0]["amount"] == "12.50"
        assert listed.json()["attempts"][0]["note"] == "SYNTHETIC-ONLY-api-note"

        card_response = client.get("/api/v1/private/cards")
        assert "SYNTHETIC-ONLY-api-note" not in card_response.text
        assert "12.50" not in card_response.text
        public_response = client.get("/api/v1/catalog/benefits")
        assert "SYNTHETIC-ONLY-api-note" not in public_response.text
        assert "12.50" not in public_response.text
        raw = vault_path.read_text(encoding="utf-8")
        assert "SYNTHETIC-ONLY-api-note" not in raw
        assert "987654321.123456" not in raw

        edited = client.put(
            f"/api/v1/private/attempts/{attempt_id}",
            headers=_csrf_headers(client),
            json={
                **_attempt_contract(client, "SYNTHETIC-ONLY-attempt-update-1"),
                "passphrase": PASS,
                "outcome": "failed",
                "note": "SYNTHETIC-ONLY-edited-api-note",
            },
        )
        assert edited.status_code == 200
        assert edited.json()["outcome"] == "failed"
        deleted = client.request(
            "DELETE",
            f"/api/v1/private/attempts/{attempt_id}",
            headers=_csrf_headers(client),
            json={
                **_attempt_contract(client, "SYNTHETIC-ONLY-attempt-delete-1"),
                "passphrase": PASS,
            },
        )
        assert deleted.status_code == 200
        cleared = client.request(
            "DELETE",
            f"/api/v1/private/threshold-aggregates/{card_id}",
            headers=_csrf_headers(client),
            json={"passphrase": PASS, "rule_id": RULE_ID, "rule_version": 1},
        )
        assert cleared.status_code == 200
        assert cleared.json() == {"cleared": True}
        assert client.get("/api/v1/private/personal-state", headers=_browser_headers()).json() == {
            "aggregates": [], "attempts": [],
            "private_state_revision": _private_state(client)["private_state_revision"],
        }

        _csrf_headers(client)
        locked = client.post("/api/v1/private/lock", headers=_csrf_headers(client))
        assert locked.status_code == 200
        after_lock = client.get("/api/v1/private/personal-state", headers=_browser_headers())
        assert after_lock.status_code == 401
        assert after_lock.headers["cache-control"] == "no-store"


def test_private_attempt_api_contract_replay_new_operation_stale_substitution_and_no_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _vault_path, card_id = _setup_api(tmp_path, monkeypatch)
    with client:
        _unlock(client)
        first_body = {
            **_attempt_contract(client, "SYNTHETIC-ONLY-api-create-replay"),
            "passphrase": PASS,
            "rule_id": RULE_ID,
            "rule_version": 1,
            "outcome": "successful",
            "note": "SYNTHETIC-ONLY-exact-replay-note",
        }
        first = client.post(
            f"/api/v1/private/attempts/{card_id}",
            headers=_csrf_headers(client),
            json=first_body,
        )
        assert first.status_code == 200, first.text
        replay = client.post(
            f"/api/v1/private/attempts/{card_id}",
            headers=_csrf_headers(client),
            json=first_body,
        )
        assert replay.status_code == 200, replay.text
        assert replay.json() == first.json()
        state_after_replay = _private_state(client)
        assert len(state_after_replay["attempts"]) == 1

        second = client.post(
            f"/api/v1/private/attempts/{card_id}",
            headers=_csrf_headers(client),
            json={
                **_attempt_contract(client, "SYNTHETIC-ONLY-api-create-new"),
                "passphrase": PASS,
                "rule_id": OTHER_RULE_ID,
                "rule_version": 2,
                "outcome": "failed",
                "note": "SYNTHETIC-ONLY-new-operation-note",
            },
        )
        assert second.status_code == 200, second.text
        state_after_new = _private_state(client)
        assert len(state_after_new["attempts"]) == 2
        assert second.json()["attempt_id"] != first.json()["attempt_id"]

        substituted = client.post(
            f"/api/v1/private/attempts/{card_id}",
            headers=_csrf_headers(client),
            json={**first_body, "note": "SYNTHETIC-ONLY-substituted-note"},
        )
        assert substituted.status_code == 409
        assert substituted.headers["cache-control"] == "no-store"
        assert "substituted-note" not in substituted.text
        assert len(_private_state(client)["attempts"]) == 2

        stale = client.post(
            f"/api/v1/private/attempts/{card_id}",
            headers=_csrf_headers(client),
            json={
                **_attempt_contract(client, "SYNTHETIC-ONLY-api-stale-revision"),
                "expected_private_state_revision": first_body[
                    "expected_private_state_revision"
                ],
                "passphrase": PASS,
                "rule_id": RULE_ID,
                "rule_version": 1,
                "outcome": "rejected",
                "note": "SYNTHETIC-ONLY-stale-note",
            },
        )
        assert stale.status_code == 409
        assert stale.headers["cache-control"] == "no-store"
        assert len(_private_state(client)["attempts"]) == 2

        invalid = client.post(
            f"/api/v1/private/attempts/{card_id}",
            headers=_csrf_headers(client),
            json={
                "idempotency_key": "too-short",
                "expected_private_state_revision": state_after_new[
                    "private_state_revision"
                ],
                "passphrase": PASS,
                "rule_id": RULE_ID,
                "rule_version": 1,
                "outcome": "successful",
                "note": "SYNTHETIC-ONLY-validation-marker",
            },
        )
        assert invalid.status_code == 422
        assert invalid.headers["cache-control"] == "no-store"
        assert "validation-marker" not in invalid.text
        assert len(_private_state(client)["attempts"]) == 2


def test_private_attempt_api_update_delete_exact_replay_is_one_use(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _vault_path, card_id = _setup_api(tmp_path, monkeypatch)
    with client:
        _unlock(client)
        created = client.post(
            f"/api/v1/private/attempts/{card_id}",
            headers=_csrf_headers(client),
            json={
                **_attempt_contract(client, "SYNTHETIC-ONLY-update-delete-create"),
                "passphrase": PASS,
                "rule_id": RULE_ID,
                "rule_version": 1,
                "outcome": "successful",
                "note": "SYNTHETIC-ONLY-update-delete-note",
            },
        )
        assert created.status_code == 200, created.text
        attempt_id = created.json()["attempt_id"]

        update_body = {
            **_attempt_contract(client, "SYNTHETIC-ONLY-update-replay"),
            "passphrase": PASS,
            "outcome": "failed",
            "note": "SYNTHETIC-ONLY-update-note",
        }
        updated = client.put(
            f"/api/v1/private/attempts/{attempt_id}",
            headers=_csrf_headers(client),
            json=update_body,
        )
        assert updated.status_code == 200, updated.text
        update_replay = client.put(
            f"/api/v1/private/attempts/{attempt_id}",
            headers=_csrf_headers(client),
            json=update_body,
        )
        assert update_replay.status_code == 200
        assert update_replay.json() == updated.json()
        assert len(_private_state(client)["attempts"]) == 1

        delete_body = {
            **_attempt_contract(client, "SYNTHETIC-ONLY-delete-replay"),
            "passphrase": PASS,
        }
        deleted = client.request(
            "DELETE",
            f"/api/v1/private/attempts/{attempt_id}",
            headers=_csrf_headers(client),
            json=delete_body,
        )
        assert deleted.status_code == 200, deleted.text
        delete_replay = client.request(
            "DELETE",
            f"/api/v1/private/attempts/{attempt_id}",
            headers=_csrf_headers(client),
            json=delete_body,
        )
        assert delete_replay.status_code == 200
        assert delete_replay.json() == deleted.json()
        assert _private_state(client)["attempts"] == []


def test_private_attempt_api_restart_rejects_old_contract_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, vault_path, card_id = _setup_api(tmp_path, monkeypatch)
    body: dict[str, object]
    with client:
        _unlock(client)
        body = {
            **_attempt_contract(client, "SYNTHETIC-ONLY-restart-replay"),
            "passphrase": PASS,
            "rule_id": RULE_ID,
            "rule_version": 1,
            "outcome": "successful",
            "note": "SYNTHETIC-ONLY-restart-note",
        }
        first = client.post(
            f"/api/v1/private/attempts/{card_id}",
            headers=_csrf_headers(client),
            json=body,
        )
        assert first.status_code == 200, first.text

    settings = Settings(
        data_dir=vault_path.parents[1], catalog_dir=ROOT / "catalog", port=8777
    )
    restarted = TestClient(create_app(settings))
    with restarted:
        _unlock(restarted)
        replay = restarted.post(
            f"/api/v1/private/attempts/{card_id}",
            headers=_csrf_headers(restarted),
            json=body,
        )
        assert replay.status_code == 409
        assert replay.headers["cache-control"] == "no-store"
        state = _private_state(restarted)
        assert len(state["attempts"]) == 1


def test_protected_api_rejects_stale_browser_revision_and_bad_body_without_leakage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, vault_path, card_id = _setup_api(tmp_path, monkeypatch)
    with client:
        _unlock(client)
        other = VaultStore(vault_path, _permissions=_TestPermissions()).open(PASS)
        changed_elsewhere = other.upsert_manual_aggregate(
            card_id, RULE_ID, 1, "11", "INR", "2026-Q1", passphrase=PASS
        )
        assert changed_elsewhere["amount"] == "11"
        other.lock()
        stale = client.put(
            f"/api/v1/private/threshold-aggregates/{card_id}",
            headers=_csrf_headers(client),
            json={
                "passphrase": PASS,
                "rule_id": RULE_ID,
                "rule_version": 1,
                "amount": "12",
                "currency": "INR",
                "period": "2026-Q1",
            },
        )
        assert stale.status_code == 409
        assert stale.headers["cache-control"] == "no-store"

        marker = "SYNTHETIC-ONLY-validation-marker"
        invalid = client.put(
            f"/api/v1/private/threshold-aggregates/{card_id}",
            headers=_csrf_headers(client),
            json={"passphrase": PASS, "amount": marker},
        )
        assert invalid.status_code == 422
        assert invalid.headers["cache-control"] == "no-store"
        assert marker not in invalid.text


def test_removed_private_state_surface_is_not_exposed_in_the_consumer_ui() -> None:
    template = (ROOT / "src" / "mycard_benefits" / "templates" / "index.html").read_text(
        encoding="utf-8"
    )
    script = (ROOT / "src" / "mycard_benefits" / "static" / "app.js").read_text(
        encoding="utf-8"
    )
    for fragment in (
        'id="manualAggregateForm"',
        'id="manualAggregateClearForm"',
        'id="privateAttemptForm"',
        'id="privateAttemptDeleteForm"',
        'id="personalStateList"',
    ):
        assert fragment not in template
    for fragment in (
        'id="cardAddForm"',
        'id="manageCardsDetails"',
        "function secretFieldsFrom",
        'fetch("/api/v1/private/cards"',
        'cache: "no-store"',
    ):
        assert fragment in template or fragment in script
    assert "innerHTML" not in script
    assert "localStorage.setItem(\"private" not in script
