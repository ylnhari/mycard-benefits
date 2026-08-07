from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mycard_benefits.app import create_app
from mycard_benefits.config import Settings
from mycard_benefits.vault.router import VaultUnavailable


def _client(tmp_path: Path, reader: object) -> TestClient:
    settings = Settings(
        data_dir=tmp_path / "data",
        catalog_dir=tmp_path / "catalog",
        port=8777,
    )
    return TestClient(create_app(settings, private_card_reader=reader))  # type: ignore[arg-type]


def test_private_cards_are_a_local_read_only_api_without_gateway_coupling(tmp_path: Path) -> None:
    called = False

    def reader() -> tuple[dict[str, str], ...]:
        nonlocal called
        called = True
        return ()

    with _client(tmp_path, reader) as client:
        response = client.get("/api/v1/private/cards")

    assert response.status_code == 200
    assert response.json() == {"cards": [], "lifecycle_counts": {}}
    assert called


def test_private_cards_return_only_envelope_metadata(tmp_path: Path) -> None:
    def reader() -> tuple[dict[str, str], ...]:
        return (
            {
                "card_id": "018f47f2-0f86-7b0a-bc7d-f00ba47c0001",
                "offering_id": "hdfc-regalia-gold-credit",
                "lifecycle": "active",
                "created_at": "2026-08-07T00:00:00Z",
                "updated_at": "2026-08-07T00:00:00Z",
            },
            {
                "card_id": "018f47f2-0f86-7b0a-bc7d-f00ba47c0002",
                "offering_id": "hdfc-tata-neu-rupay-select-credit",
                "lifecycle": "archived",
                "created_at": "2026-08-06T00:00:00Z",
                "updated_at": "2026-08-07T00:00:00Z",
                "replacement_card_id": "018f47f2-0f86-7b0a-bc7d-f00ba47c0001",
            },
        )

    with _client(tmp_path, reader) as client:
        response = client.get("/api/v1/private/cards")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    assert payload["lifecycle_counts"] == {"active": 1, "archived": 1}
    assert [card["lifecycle"] for card in payload["cards"]] == ["active", "archived"]
    assert "secret_fields" not in response.text
    for secret in ("pan", "cvv", "pin", "nickname", "expiry", "cardholder", "notes", "owner"):
        assert secret not in response.text.lower()


def test_private_cards_fail_closed_on_unexpected_reader_fields(tmp_path: Path) -> None:
    def reader() -> tuple[dict[str, str], ...]:
        return (
            {
                "card_id": "018f47f2-0f86-7b0a-bc7d-f00ba47c0001",
                "offering_id": "hdfc-regalia-gold-credit",
                "lifecycle": "active",
                "created_at": "2026-08-07T00:00:00Z",
                "updated_at": "2026-08-07T00:00:00Z",
                "nickname": "SYNTHETIC-ONLY-SHOULD-NOT-LEAK",
            },
        )

    with _client(tmp_path, reader) as client:
        response = client.get("/api/v1/private/cards")

    assert response.status_code == 503
    assert "SYNTHETIC-ONLY-SHOULD-NOT-LEAK" not in response.text


def test_private_cards_rows_carry_only_the_five_envelope_fields(tmp_path: Path) -> None:
    def reader() -> tuple[dict[str, str], ...]:
        return (
            {
                "card_id": "018f47f2-0f86-7b0a-bc7d-f00ba47c0001",
                "offering_id": "hdfc-regalia-gold-credit",
                "lifecycle": "active",
                "created_at": "2026-08-07T00:00:00Z",
                "updated_at": "2026-08-07T00:00:00Z",
                "replacement_card_id": "018f47f2-0f86-7b0a-bc7d-f00ba47c0002",
            },
        )

    with _client(tmp_path, reader) as client:
        payload = client.get("/api/v1/private/cards").json()

    assert len(payload["cards"]) == 1
    row = payload["cards"][0]
    assert row["card_id"] == "018f47f2-0f86-7b0a-bc7d-f00ba47c0001"
    assert row["offering_id"] == "hdfc-regalia-gold-credit"
    assert row["lifecycle"] == "active"
    assert row["created_at"] == "2026-08-07T00:00:00Z"
    assert row["updated_at"] == "2026-08-07T00:00:00Z"
    assert row["replacement_card_id"] == "018f47f2-0f86-7b0a-bc7d-f00ba47c0002"
    assert row["child_records"] == []
    assert set(row) == {
        "card_id",
        "offering_id",
        "lifecycle",
        "created_at",
        "updated_at",
        "replacement_card_id",
        "child_records",
    }


def test_private_cards_accept_unmatched_offerings_and_never_return_secret_values(
    tmp_path: Path,
) -> None:
    def reader() -> tuple[dict[str, object], ...]:
        return (
            {
                "card_id": "018f47f2-0f86-7b0a-bc7d-f00ba47c0003",
                "offering_id": "not-a-catalog-slug",
                "lifecycle": "expired",
                "created_at": "2026-01-02T00:00:00Z",
                "updated_at": "2026-02-03T00:00:00Z",
                "secret_fields": {
                    "nickname": "SYNTHETIC-ONLY-PRIMARY",
                    "notes": "SYNTHETIC-ONLY-NOTE",
                    "cardholder": "SYNTHETIC-ONLY-OWNER",
                    "expiry": "2030-12",
                    "pan": "SYNTHETIC-ONLY-4000",
                    "cvv": "SYNTHETIC-ONLY-123",
                    "pin": "SYNTHETIC-ONLY-4321",
                },
            },
        )

    with _client(tmp_path, reader) as client:
        response = client.get("/api/v1/private/cards")

    assert response.status_code == 503
    text = response.text
    for secret in (
        "SYNTHETIC-ONLY-PRIMARY",
        "SYNTHETIC-ONLY-NOTE",
        "SYNTHETIC-ONLY-OWNER",
        "2030-12",
        "SYNTHETIC-ONLY-4000",
        "SYNTHETIC-ONLY-123",
        "SYNTHETIC-ONLY-4321",
        "not-a-catalog-slug",
    ):
        assert secret not in text


def test_unmatched_offering_response_is_envelope_only_and_never_repeats_slug(
    tmp_path: Path,
) -> None:
    def reader() -> tuple[dict[str, str], ...]:
        return (
            {
                "card_id": "018f47f2-0f86-7b0a-bc7d-f00ba47c0003",
                "offering_id": "not-a-catalog-slug",
                "lifecycle": "expired",
                "created_at": "2026-01-02T00:00:00Z",
                "updated_at": "2026-02-03T00:00:00Z",
            },
        )

    with _client(tmp_path, reader) as client:
        response = client.get("/api/v1/private/cards")

    assert response.status_code == 200
    row = response.json()["cards"][0]
    assert row["offering_id"] == "not-a-catalog-slug"
    assert set(row) == {
        "card_id",
        "offering_id",
        "lifecycle",
        "created_at",
        "updated_at",
        "replacement_card_id",
        "child_records",
    }
    assert response.text.count("not-a-catalog-slug") == 1, (
        "the raw offering identifier must never leak into any extra field"
    )


def test_private_cards_503_when_reader_raises(tmp_path: Path) -> None:
    def reader() -> tuple[dict[str, str], ...]:
        raise OSError("vault unavailable")

    with _client(tmp_path, reader) as client:
        response = client.get("/api/v1/private/cards")

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "generic"
    assert detail["message"]
    assert (
        response.headers.get("cache-control") is None
        or response.headers["cache-control"] != "no-store"
    )
    assert "fallback" not in response.text.lower()


def test_unavailable_codes_map_to_distinct_structured_details(tmp_path: Path) -> None:
    for code in (
        "demo",
        "vault_missing",
        "passphrase_only",
        "wrong_data_dir",
        "locked",
        "keyring_unavailable",
        "generic",
    ):

        def reader(_code: str = code) -> tuple[dict[str, str], ...]:
            raise VaultUnavailable(_code)

        with _client(tmp_path, reader) as client:
            response = client.get("/api/v1/private/cards")

        assert response.status_code == 503
        detail = response.json()["detail"]
        assert detail["code"] == code, code
        assert detail["message"], code
        assert str(tmp_path) not in response.text, code


def test_real_reader_reports_vault_missing_when_no_vault_and_no_keyring_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class StubKeyring:
        def get_password(self, service_name: str, username: str) -> str | None:
            return None

    import mycard_benefits.vault.router as router_module

    monkeypatch.setattr(router_module, "load_keyring", lambda: StubKeyring())

    with _client(tmp_path, None) as client:  # type: ignore[arg-type]
        response = client.get("/api/v1/private/cards")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "vault_missing"


def test_real_reader_reports_wrong_data_dir_when_keyring_knows_this_vault_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class StubKeyring:
        def get_password(self, service_name: str, username: str) -> str | None:
            return "SYNTHETIC-ONLY-passphrase"

    import mycard_benefits.vault.router as router_module

    monkeypatch.setattr(router_module, "load_keyring", lambda: StubKeyring())

    with _client(tmp_path, None) as client:  # type: ignore[arg-type]
        response = client.get("/api/v1/private/cards")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "wrong_data_dir"
    assert "SYNTHETIC-ONLY-passphrase" not in response.text


def test_real_reader_reports_passphrase_only_when_vault_exists_without_keyring_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "data" / "private" / "vault.json"
    vault.parent.mkdir(parents=True)
    vault.write_bytes(b"")

    class StubKeyring:
        def get_password(self, service_name: str, username: str) -> str | None:
            return None

    import mycard_benefits.vault.router as router_module

    monkeypatch.setattr(router_module, "load_keyring", lambda: StubKeyring())

    with _client(tmp_path, None) as client:  # type: ignore[arg-type]
        response = client.get("/api/v1/private/cards")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "passphrase_only"


def test_real_reader_reports_locked_when_vault_exists_with_stored_passphrase_but_open_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "data" / "private" / "vault.json"
    vault.parent.mkdir(parents=True)
    vault.write_bytes(b"not a vault")

    class StubKeyring:
        def get_password(self, service_name: str, username: str) -> str | None:
            return "SYNTHETIC-ONLY-passphrase"

    import mycard_benefits.vault.router as router_module

    monkeypatch.setattr(router_module, "load_keyring", lambda: StubKeyring())

    with _client(tmp_path, None) as client:  # type: ignore[arg-type]
        response = client.get("/api/v1/private/cards")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "locked"


def _child_record(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "child_id": "018f47f2-0f86-7b0a-bc7d-f00ba47c0010",
        "parent_card_id": "018f47f2-0f86-7b0a-bc7d-f00ba47c0001",
        "kind": "priority_pass",
        "lifecycle": "active",
        "created_at": "2026-08-07T00:00:00Z",
        "updated_at": "2026-08-07T00:00:00Z",
    }
    base.update(overrides)
    return base


def _card_with_children(*children: dict[str, object]) -> dict[str, object]:
    return {
        "card_id": "018f47f2-0f86-7b0a-bc7d-f00ba47c0001",
        "offering_id": "hdfc-regalia-gold-credit",
        "lifecycle": "active",
        "created_at": "2026-08-07T00:00:00Z",
        "updated_at": "2026-08-07T00:00:00Z",
        "child_records": list(children),
    }


def test_private_cards_nest_child_records_with_only_envelope_fields(tmp_path: Path) -> None:
    def reader() -> tuple[dict[str, object], ...]:
        return (
            _card_with_children(
                _child_record(expiry_date="2027-01-01"),
                _child_record(
                    child_id="018f47f2-0f86-7b0a-bc7d-f00ba47c0011",
                    kind="voucher",
                    lifecycle="expired",
                    created_at="2026-08-06T00:00:00Z",
                    updated_at="2026-08-06T00:00:00Z",
                ),
            ),
        )

    with _client(tmp_path, reader) as client:
        response = client.get("/api/v1/private/cards")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    children = response.json()["cards"][0]["child_records"]
    assert len(children) == 2
    assert children[0]["kind"] == "priority_pass"
    assert children[0]["expiry_signal"] == "active"
    assert set(children[0]) == {
        "child_id",
        "parent_card_id",
        "kind",
        "lifecycle",
        "created_at",
        "updated_at",
        "expiry_signal",
    }
    assert children[1]["kind"] == "voucher"
    assert children[1]["lifecycle"] == "expired"
    assert children[1]["expiry_signal"] is None
    assert "2027-01-01" not in response.text
    assert "label" not in response.text


def test_private_cards_never_send_the_exact_child_expiry_date(tmp_path: Path) -> None:
    """Only a bounded signal crosses the boundary; the raw date never does."""
    today = datetime.now(UTC).date()
    expired_date = (today - timedelta(days=5)).isoformat()
    soon_date = (today + timedelta(days=5)).isoformat()
    later_date = (today + timedelta(days=400)).isoformat()

    def reader() -> tuple[dict[str, object], ...]:
        return (
            _card_with_children(
                _child_record(expiry_date=expired_date),
                _child_record(child_id="018f47f2-0f86-7b0a-bc7d-f00ba47c0011", expiry_date=soon_date),
                _child_record(child_id="018f47f2-0f86-7b0a-bc7d-f00ba47c0012", expiry_date=later_date),
            ),
        )

    with _client(tmp_path, reader) as client:
        response = client.get("/api/v1/private/cards")

    assert response.status_code == 200
    children = response.json()["cards"][0]["child_records"]
    assert [child["expiry_signal"] for child in children] == ["expired", "expiring_soon", "active"]
    for exact_date in (expired_date, soon_date, later_date):
        assert exact_date not in response.text
    assert "expiry_date" not in response.text


def test_private_cards_fail_closed_on_unexpected_child_record_fields(tmp_path: Path) -> None:
    def reader() -> tuple[dict[str, object], ...]:
        return (
            _card_with_children(
                _child_record(membership_number="SYNTHETIC-ONLY-SHOULD-NOT-LEAK"),
            ),
        )

    with _client(tmp_path, reader) as client:
        response = client.get("/api/v1/private/cards")

    assert response.status_code == 503
    assert "SYNTHETIC-ONLY-SHOULD-NOT-LEAK" not in response.text
    for secret in ("membership_number", "barcode", "credential_secret", "pan", "cvv", "pin"):
        assert secret not in response.text.lower()


def test_private_cards_fail_closed_on_free_text_child_label(tmp_path: Path) -> None:
    """There is no display-label field at all; any attempt to supply one is rejected."""

    def reader() -> tuple[dict[str, object], ...]:
        return (
            _card_with_children(
                _child_record(label="SYNTHETIC-ONLY-secret-membership-number-ALPHA-NOT-A-REAL-PAN"),
            ),
        )

    with _client(tmp_path, reader) as client:
        response = client.get("/api/v1/private/cards")

    assert response.status_code == 503
    assert "SYNTHETIC-ONLY-secret-membership-number" not in response.text
    assert "NOT-A-REAL-PAN" not in response.text


def test_private_cards_fail_closed_on_unknown_child_kind_or_lifecycle(tmp_path: Path) -> None:
    def reader_with_kind() -> tuple[dict[str, object], ...]:
        return (_card_with_children(_child_record(kind="not-a-real-kind")),)

    def reader_with_lifecycle() -> tuple[dict[str, object], ...]:
        return (_card_with_children(_child_record(lifecycle="not-a-real-lifecycle")),)

    for reader in (reader_with_kind, reader_with_lifecycle):
        with _client(tmp_path, reader) as client:
            response = client.get("/api/v1/private/cards")
        assert response.status_code == 503


def test_private_cards_fail_closed_on_child_parent_mismatch(tmp_path: Path) -> None:
    def reader() -> tuple[dict[str, object], ...]:
        return (
            _card_with_children(
                _child_record(parent_card_id="018f47f2-0f86-7b0a-bc7d-f00ba47c0099"),
            ),
        )

    with _client(tmp_path, reader) as client:
        response = client.get("/api/v1/private/cards")

    assert response.status_code == 503


def test_private_cards_fail_closed_on_duplicate_child_record_ids(tmp_path: Path) -> None:
    def reader() -> tuple[dict[str, object], ...]:
        return (_card_with_children(_child_record(), _child_record()),)

    with _client(tmp_path, reader) as client:
        response = client.get("/api/v1/private/cards")

    assert response.status_code == 503


def test_private_cards_fail_closed_on_duplicate_ids_across_cards(tmp_path: Path) -> None:
    first = _card_with_children(_child_record())
    second = _card_with_children(
        _child_record(parent_card_id="018f47f2-0f86-7b0a-bc7d-f00ba47c0002")
    )
    second["card_id"] = "018f47f2-0f86-7b0a-bc7d-f00ba47c0002"

    def duplicate_child_reader() -> tuple[dict[str, object], ...]:
        return first, second

    with _client(tmp_path, duplicate_child_reader) as client:
        response = client.get("/api/v1/private/cards")

    assert response.status_code == 503

    duplicate_card = _card_with_children()

    def duplicate_card_reader() -> tuple[dict[str, object], ...]:
        return first, duplicate_card

    with _client(tmp_path, duplicate_card_reader) as client:
        response = client.get("/api/v1/private/cards")

    assert response.status_code == 503


def test_private_cards_fail_closed_on_invalid_child_identifiers(tmp_path: Path) -> None:
    def reader() -> tuple[dict[str, object], ...]:
        return (_card_with_children(_child_record(child_id="not-a-uuid")),)

    with _client(tmp_path, reader) as client:
        response = client.get("/api/v1/private/cards")

    assert response.status_code == 503


def test_real_reader_groups_child_records_under_their_parent_card(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mycard_benefits.vault import ChildRecordKind
    from mycard_benefits.vault.core import VaultStore
    from mycard_benefits.vault.keyring_store import keyring_account

    vault_path = tmp_path / "data" / "private" / "vault.json"
    session = VaultStore(vault_path).create("synthetic passphrase for child records")
    card_id = session.add_card("hdfc-regalia-gold-credit", {"pan": "SYNTHETIC-ONLY-PAN"})
    other_card_id = session.add_card("hdfc-tata-neu-rupay-select-credit", {"pan": "SYNTHETIC-ONLY-PAN-2"})
    session.add_child_record(card_id, ChildRecordKind.LOUNGE_CREDENTIAL)
    session.add_child_record(other_card_id, ChildRecordKind.MEMBERSHIP)
    session.lock()

    class StubKeyring:
        def get_password(self, service_name: str, username: str) -> str | None:
            return "synthetic passphrase for child records"

    import mycard_benefits.vault.router as router_module

    monkeypatch.setattr(router_module, "load_keyring", lambda: StubKeyring())
    assert keyring_account(vault_path)  # exercised implicitly by the real reader below

    with _client(tmp_path, None) as client:  # type: ignore[arg-type]
        response = client.get("/api/v1/private/cards")

    assert response.status_code == 200
    payload = response.json()
    by_card = {card["card_id"]: card for card in payload["cards"]}
    assert len(by_card[card_id]["child_records"]) == 1
    assert by_card[card_id]["child_records"][0]["kind"] == "lounge_credential"
    assert len(by_card[other_card_id]["child_records"]) == 1
    assert by_card[other_card_id]["child_records"][0]["kind"] == "membership"
    assert "SYNTHETIC-ONLY-PAN" not in response.text
    for secret in ("pan", "cvv", "pin"):
        assert secret not in response.text.lower()
