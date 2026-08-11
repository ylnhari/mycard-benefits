from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mycard_benefits.app import create_app
from mycard_benefits.config import Settings
from mycard_benefits.vault.core import VaultError, VaultStore
from mycard_benefits.vault.router import AddCardRequest

PASS = "SYNTHETIC-ONLY-onboarding-passphrase"
ORIGIN = "http://127.0.0.1:8777"


class SyntheticKeyring:
    def __init__(self, *, fail_set: bool = False) -> None:
        self.value: str | None = None
        self.fail_set = fail_set

    def get_password(self, service_name: str, username: str) -> str | None:
        return self.value

    def set_password(self, service_name: str, username: str, password: str) -> None:
        if self.fail_set:
            raise RuntimeError("SYNTHETIC-ONLY-keyring-write-failure")
        self.value = password


def _headers(token: str) -> dict[str, str]:
    return {
        "Origin": ORIGIN,
        "Host": "127.0.0.1:8777",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "X-CSRF-Token": token,
    }


def _client(data_dir: Path) -> TestClient:
    settings = Settings(
        data_dir=data_dir,
        catalog_dir=Path(__file__).parent / "fixtures" / "synthetic_catalog",
        port=8777,
    )
    return TestClient(create_app(settings))


def _bootstrap(client: TestClient) -> str:
    response = client.get("/api/v1/private/unlock/bootstrap", headers=_headers("unused"))
    assert response.status_code == 200
    return response.json()["csrf_token"]


def test_setup_creates_synthetic_vault_and_remembered_launch_reopens_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mycard_benefits.config as config
    import mycard_benefits.vault.router as router

    keyring = SyntheticKeyring()
    monkeypatch.setattr(router, "load_keyring", lambda: keyring)
    remembered_root = tmp_path / "application-data"
    monkeypatch.setattr(config, "user_data_root", lambda: remembered_root)
    data_dir = tmp_path / "selected-data"

    with _client(data_dir) as client:
        token = _bootstrap(client)
        response = client.post(
            "/api/v1/private/setup",
            headers={**_headers(token), "Content-Type": "application/json"},
            json={"passphrase": PASS, "remember": True},
        )
        assert response.status_code == 200
        assert response.json() == {"status": "unlocked", "remembered": True}
        assert PASS not in response.text
        assert str(data_dir) not in response.text
        assert (data_dir / "private" / "vault.json").is_file()

    # A later process has no prior browser session, but the keyring-backed
    # password and remembered location are sufficient for safe summaries.
    session = VaultStore(data_dir / "private" / "vault.json").open(PASS)
    session.add_card("synthetic-offering", {"pan": "SYNTHETIC-ONLY-PAN"}, passphrase=PASS)
    session.lock()
    later_settings = config.Settings.from_environment()
    assert later_settings.data_dir == data_dir.resolve()
    with _client(later_settings.data_dir) as client:
        cards = client.get("/api/v1/private/cards")
        assert cards.status_code == 200
        assert cards.json()["cards"][0]["offering_id"] == "synthetic-offering"
        assert "SYNTHETIC-ONLY-PAN" not in cards.text


def test_my_cards_bootstrap_creates_and_opens_a_device_held_vault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mycard_benefits.vault.router as router

    keyring = SyntheticKeyring()
    monkeypatch.setattr(router, "load_keyring", lambda: keyring)
    data_dir = tmp_path / "data"

    with _client(data_dir) as client:
        response = client.get("/api/v1/private/cards")

    assert response.status_code == 200
    assert response.json() == {"cards": [], "lifecycle_counts": {}}
    assert isinstance(keyring.value, str) and len(keyring.value) >= 32
    assert keyring.value not in response.text
    session = VaultStore(data_dir / "private" / "vault.json").open(keyring.value)
    assert session.list_cards() == ()
    session.lock()


def test_device_held_card_action_does_not_request_a_passphrase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mycard_benefits.vault.router as router

    keyring = SyntheticKeyring()
    monkeypatch.setattr(router, "load_keyring", lambda: keyring)
    data_dir = tmp_path / "data"

    with _client(data_dir) as client:
        assert client.get("/api/v1/private/cards").status_code == 200
        token = client.get("/api/v1/private/csrf-token").json()["csrf_token"]
        response = client.post(
            "/api/v1/private/cards/add",
            headers={**_headers(token), "Content-Type": "application/json"},
            json={"offering_id": "synthetic-offering", "secret_fields": {}},
        )
        assert response.status_code == 200
        cards = client.get("/api/v1/private/cards")

    assert cards.status_code == 200
    assert len(cards.json()["cards"]) == 1


def test_local_device_key_fallback_supports_passphrase_free_card_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mycard_benefits.vault.router as router

    def unavailable_keyring() -> object:
        raise VaultError("keyring support is not installed")

    monkeypatch.setattr(router, "load_keyring", unavailable_keyring)
    data_dir = tmp_path / "data"

    with _client(data_dir) as client:
        assert client.get("/api/v1/private/cards").status_code == 200
        token = client.get("/api/v1/private/csrf-token").json()["csrf_token"]
        response = client.post(
            "/api/v1/private/cards/add",
            headers={**_headers(token), "Content-Type": "application/json"},
            json={"offering_id": "synthetic-offering", "secret_fields": {}},
        )
        assert response.status_code == 200

    assert (data_dir / "private" / "device-key").is_file()


def test_remembered_location_is_selected_only_without_overriding_explicit_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mycard_benefits.config as config

    monkeypatch.setattr(config, "REPO_ROOT", tmp_path / "checkout")
    monkeypatch.setattr(config, "PACKAGE_ROOT", tmp_path / "site-packages" / "mycard_benefits")
    monkeypatch.setattr(config, "resolve_port", lambda *args, **kwargs: 8777)
    app_data = tmp_path / "application-data"
    selected = tmp_path / "selected-data"
    monkeypatch.setattr(config, "user_data_root", lambda: app_data)
    config.remember_data_dir(selected)

    normal = config.Settings.from_environment()
    explicit = config.Settings.from_environment(explicit_data_dir=tmp_path / "other-data")
    demo = config.Settings.from_environment(demo=True)
    assert normal.data_dir == selected.resolve()
    assert explicit.data_dir == (tmp_path / "other-data").resolve()
    assert demo.data_dir == (tmp_path / "checkout" / "demo-data").resolve()
    assert normal.data_dir != demo.data_dir


def test_keyring_failure_keeps_created_vault_openable_and_reports_safe_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mycard_benefits.config as config
    import mycard_benefits.vault.router as router

    monkeypatch.setattr(router, "load_keyring", lambda: SyntheticKeyring(fail_set=True))
    monkeypatch.setattr(config, "user_data_root", lambda: tmp_path / "application-data")
    data_dir = tmp_path / "data"
    with _client(data_dir) as client:
        token = _bootstrap(client)
        response = client.post(
            "/api/v1/private/setup",
            headers={**_headers(token), "Content-Type": "application/json"},
            json={"passphrase": PASS, "remember": True},
        )
        assert response.status_code == 200
        assert response.json()["remembered"] is False
        assert response.json()["remember_warning"]
        assert PASS not in response.text
    session = VaultStore(data_dir / "private" / "vault.json").open(PASS)
    session.lock()


def test_product_only_card_and_optional_last_four_stay_private_and_safe(
    tmp_path: Path,
) -> None:
    """An offering alone is useful; a manually entered final four is private."""
    data_dir = tmp_path / "data"
    vault_path = data_dir / "private" / "vault.json"
    session = VaultStore(vault_path).create(PASS)
    product_only = AddCardRequest.model_validate(
        {"passphrase": PASS, "offering_id": "synthetic-offering"}
    )
    product_only_id = session.add_card(
        product_only.offering_id,
        product_only.secret_fields,
        passphrase=product_only.passphrase,
    )
    with_last_four = AddCardRequest.model_validate(
        {
            "passphrase": PASS,
            "offering_id": "synthetic-offering-with-last-four",
            "secret_fields": {"last_four": "1234"},
        }
    )
    last_four_id = session.add_card(
        with_last_four.offering_id,
        with_last_four.secret_fields,
        passphrase=with_last_four.passphrase,
    )
    summaries = {item["card_id"]: item for item in session.list_private_card_summaries()}
    assert summaries[product_only_id].get("masked_last4") is None
    assert summaries[last_four_id]["masked_last4"] == "•••• 1234"
    session.lock()

    envelope = json.loads(vault_path.read_text(encoding="utf-8"))
    assert all("last_four" not in record for record in envelope["records"])
    assert "last_four" not in vault_path.read_text(encoding="utf-8")


def test_pan_last_four_mismatch_is_rejected_and_pan_wins_when_consistent(
    tmp_path: Path,
) -> None:
    vault_path = tmp_path / "private" / "vault.json"
    session = VaultStore(vault_path).create(PASS)
    # This synthetic string is deliberately not a numeric PAN. Its digit
    # fragment only exercises the legacy masking path and is not Luhn-valid.
    synthetic_pan = "SYNTHETIC-ONLY-PAN-000000000001"
    card_id = session.add_card(
        "synthetic-offering",
        {"pan": synthetic_pan, "last_four": "0001"},
        passphrase=PASS,
    )
    assert session.list_private_card_summaries()[0]["masked_last4"] == "•••• 0001"
    before = vault_path.read_bytes()
    with pytest.raises(VaultError) as exc_info:
        session.add_card(
            "synthetic-offering-mismatch",
            {"pan": synthetic_pan, "last_four": "9999"},
            passphrase=PASS,
        )
    assert "9999" not in str(exc_info.value)
    assert vault_path.read_bytes() == before
    assert session.list_private_card_summaries()[0]["card_id"] == card_id
    with pytest.raises(VaultError):
        session.edit_card(card_id, {"last_four": "9999"}, passphrase=PASS)
    assert vault_path.read_bytes() == before
    session.lock()


@pytest.mark.parametrize("last_four", ["123", "12345", "12４", "12a4", " 123"])
def test_last_four_requires_exact_ascii_digits_and_is_redacted(
    tmp_path: Path, last_four: str
) -> None:
    data_dir = tmp_path / "data"
    vault_path = data_dir / "private" / "vault.json"
    session = VaultStore(vault_path).create(PASS)
    request = AddCardRequest.model_validate(
        {
            "passphrase": PASS,
            "offering_id": "synthetic-offering",
            "secret_fields": {"last_four": last_four},
        }
    )
    with pytest.raises(VaultError) as exc_info:
        session.add_card(
            request.offering_id,
            request.secret_fields,
            passphrase=request.passphrase,
        )
    assert last_four not in str(exc_info.value)
    assert session.list_cards() == ()
    session.lock()


@pytest.mark.parametrize(
    "payload",
    [
        {"passphrase": PASS},
        {"passphrase": PASS, "remember": 1},
        {"passphrase": True, "remember": False},
        {"passphrase": PASS, "remember": False, "extra": "SYNTHETIC-ONLY"},
    ],
)
def test_setup_requires_exact_strict_body_before_mutation(
    tmp_path: Path, payload: dict[str, Any]
) -> None:
    data_dir = tmp_path / "data"
    with _client(data_dir) as client:
        token = _bootstrap(client)
        response = client.post(
            "/api/v1/private/setup",
            headers={**_headers(token), "Content-Type": "application/json"},
            json=payload,
        )
        assert response.status_code == 400
        assert response.headers["cache-control"] == "no-store"
        assert not (data_dir / "private" / "vault.json").exists()


def test_setup_rejects_existing_vault_without_overwriting_it(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    vault = data_dir / "private" / "vault.json"
    session = VaultStore(vault).create(PASS)
    session.lock()
    original = vault.read_bytes()
    with _client(data_dir) as client:
        token = _bootstrap(client)
        response = client.post(
            "/api/v1/private/setup",
            headers={**_headers(token), "Content-Type": "application/json"},
            json={"passphrase": PASS, "remember": False},
        )
    assert response.status_code == 409
    assert response.headers["cache-control"] == "no-store"
    assert vault.read_bytes() == original


def test_unlock_accepts_remember_contract_and_does_not_mutate_keyring_when_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mycard_benefits.vault.router as router

    keyring = SyntheticKeyring()
    monkeypatch.setattr(router, "load_keyring", lambda: keyring)
    data_dir = tmp_path / "data"
    session = VaultStore(data_dir / "private" / "vault.json").create(PASS)
    session.lock()
    with _client(data_dir) as client:
        token = _bootstrap(client)
        response = client.post(
            "/api/v1/private/unlock",
            headers={**_headers(token), "Content-Type": "application/json"},
            json={"passphrase": PASS, "remember": False},
        )
    assert response.status_code == 200
    assert response.json() == {"status": "unlocked", "remembered": False}
    assert keyring.value is None
