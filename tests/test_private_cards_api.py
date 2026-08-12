from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mycard_benefits.app import create_app
from mycard_benefits.config import Settings
from mycard_benefits.vault.core import VaultError, VaultStore
from mycard_benefits.vault.router import VaultUnavailable

SYNTHETIC_CATALOG = Path(__file__).parent / "fixtures" / "synthetic_catalog"


def _client(tmp_path: Path, reader: object) -> TestClient:
    settings = Settings(
        data_dir=tmp_path / "data",
        catalog_dir=tmp_path / "catalog",
        port=8777,
    )
    return TestClient(create_app(settings, private_card_reader=reader))  # type: ignore[arg-type]


def _copy_discovery_catalog(tmp_path: Path) -> None:
    for relative in (
        "schema/release.json",
        "offerings/synthetic-example-in.json",
        "benefits/synthetic-example-reward.json",
        "benefits/synthetic-example-movie.json",
    ):
        target = tmp_path / "catalog" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((SYNTHETIC_CATALOG / relative).read_text(encoding="utf-8"), encoding="utf-8")


def test_owned_discovery_joins_canonical_public_offering_and_redacts_unmatched_id(tmp_path: Path) -> None:
    _copy_discovery_catalog(tmp_path)

    def reader() -> tuple[dict[str, object], ...]:
        return (
            {"card_id": "018f47f2-0f86-7b0a-bc7d-f00ba47c0001", "offering_id": "synthetic-example-in-visa", "lifecycle": "active", "created_at": "2026-08-07T00:00:00Z", "updated_at": "2026-08-07T00:00:00Z"},
            {"card_id": "018f47f2-0f86-7b0a-bc7d-f00ba47c0002", "offering_id": "SYNTHETIC-ONLY-UNMATCHED-RAW", "lifecycle": "archived", "created_at": "2026-08-07T00:00:00Z", "updated_at": "2026-08-07T00:00:00Z"},
        )

    with _client(tmp_path, reader) as client:
        response = client.get("/api/v1/private/discovery/cards")

    assert response.status_code == 200
    payload = response.json()
    assert payload["cards"][0]["catalog_match"] == "matched"
    assert payload["cards"][0]["public_display"] == "Synthetic Example India Visa"
    assert payload["cards"][0]["rule_ids"] == [
        "33333333-3333-4333-8333-333333333334",
        "33333333-3333-4333-8333-333333333333",
    ]
    assert payload["cards"][1]["catalog_match"] == "unmatched"
    assert "SYNTHETIC-ONLY-UNMATCHED-RAW" not in response.text
    assert "owner" not in response.text.lower()
    assert response.headers["cache-control"] == "no-store"


def test_discovery_owned_order_is_server_side_and_cursor_is_state_bound(tmp_path: Path) -> None:
    _copy_discovery_catalog(tmp_path)

    def reader() -> tuple[dict[str, object], ...]:
        return (
            {"card_id": "018f47f2-0f86-7b0a-bc7d-f00ba47c0001", "offering_id": "synthetic-example-in-visa", "lifecycle": "active", "created_at": "2026-08-07T00:00:00Z", "updated_at": "2026-08-07T00:00:00Z"},
        )

    with _client(tmp_path, reader) as client:
        first = client.get("/api/v1/catalog/discovery", params={"page_size": 1})
        assert first.status_code == 200
        assert first.json()[0]["owned_match"] is True
        next_cursor = first.headers["x-discovery-next-cursor"]
        assert next_cursor and next_cursor != "1"

        second = client.get(
            "/api/v1/catalog/discovery", params={"page_size": 1, "cursor": next_cursor}
        )
        assert second.status_code == 200
        assert second.json()[0]["owned_match"] is True
        assert second.headers.get("x-discovery-next-cursor", "") == ""

        owned = client.get(
            "/api/v1/catalog/discovery",
            params={"page_size": 1, "owned_only": "true"},
        )
        assert owned.status_code == 200
        assert all(item["owned_match"] for item in owned.json())
        owned_cursor = owned.headers["x-discovery-next-cursor"]
        owned_page_two = client.get(
            "/api/v1/catalog/discovery",
            params={"page_size": 1, "owned_only": "true", "cursor": owned_cursor},
        )
        assert owned_page_two.status_code == 200
        assert all(item["owned_match"] for item in owned_page_two.json())
        assert owned_page_two.headers.get("x-discovery-next-cursor", "") == ""

        mismatched = client.get(
            "/api/v1/catalog/discovery",
            params={"page_size": 1, "cursor": next_cursor, "q": "movie"},
        )
        assert mismatched.status_code == 409


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
        "masked_last4",
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
        "masked_last4",
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
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert "fallback" not in response.text.lower()


def test_private_cards_reject_cross_site_unsafe_methods_without_reading_the_vault(
    tmp_path: Path,
) -> None:
    """The protected browser surface is read-only, so it has no CSRF write path."""
    called = False

    def reader() -> tuple[dict[str, str], ...]:
        nonlocal called
        called = True
        raise AssertionError("an unsafe method must not call the vault reader")

    with _client(tmp_path, reader) as client:
        for method in ("post", "put", "patch", "delete"):
            response = client.request(
                method,
                "/api/v1/private/cards",
                headers={"Origin": "https://attacker.invalid"},
                json={"marker": "SYNTHETIC-ONLY-CSRF-MARKER"},
            )
            assert response.status_code == 405
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["pragma"] == "no-cache"
            assert "SYNTHETIC-ONLY-CSRF-MARKER" not in response.text
            assert "access-control-allow-origin" not in response.headers
    assert not called


def test_private_cards_unknown_unavailable_code_is_redacted_from_api_and_logs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    marker = "SYNTHETIC-ONLY-PRIVATE-ERROR-MARKER"

    def reader() -> tuple[dict[str, str], ...]:
        raise VaultUnavailable(marker)

    with _client(tmp_path, reader) as client:
        response = client.get("/api/v1/private/cards")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "generic"
    assert marker not in response.text
    assert marker not in caplog.text


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
        assert response.headers["cache-control"] == "no-store", code
        assert response.headers["pragma"] == "no-cache", code
        assert str(tmp_path) not in response.text, code


def test_real_reader_bootstraps_vault_when_no_vault_and_no_keyring_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class StubKeyring:
        def get_password(self, service_name: str, username: str) -> str | None:
            return None

        def set_password(self, service_name: str, username: str, password: str) -> None:
            raise RuntimeError("SYNTHETIC-ONLY-keyring-write-unavailable")

    import mycard_benefits.vault.router as router_module

    monkeypatch.setattr(router_module, "load_keyring", lambda: StubKeyring())

    with _client(tmp_path, None) as client:  # type: ignore[arg-type]
        response = client.get("/api/v1/private/cards")

    assert response.status_code == 200
    assert response.json()["cards"] == []
    assert (tmp_path / "data" / "private" / "vault.json").is_file()
    assert (tmp_path / "data" / "private" / "device-key").is_file()


def test_real_reader_bootstraps_vault_when_keyring_is_unavailable_and_vault_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable_keyring() -> object:
        raise VaultError("SYNTHETIC-ONLY-keyring-unavailable")

    import mycard_benefits.vault.router as router_module

    monkeypatch.setattr(router_module, "load_keyring", unavailable_keyring)

    with _client(tmp_path, None) as client:  # type: ignore[arg-type]
        response = client.get("/api/v1/private/cards")

    assert response.status_code == 200
    assert response.json()["cards"] == []
    assert (tmp_path / "data" / "private" / "vault.json").is_file()
    assert (tmp_path / "data" / "private" / "device-key").is_file()
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert "SYNTHETIC-ONLY-keyring-unavailable" not in response.text


def test_real_reader_keeps_keyring_unavailable_for_present_vault_manual_unlock_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    passphrase = "SYNTHETIC-ONLY-manual-unlock-passphrase"
    vault = tmp_path / "data" / "private" / "vault.json"
    session = VaultStore(vault).create(passphrase)
    session.add_card(
        "synthetic-example-in-visa",
        {"pan": "SYNTHETIC-ONLY-PAN"},
        passphrase=passphrase,
    )
    session.lock()

    def unavailable_keyring() -> object:
        raise VaultError("SYNTHETIC-ONLY-keyring-unavailable")

    import mycard_benefits.vault.router as router_module

    monkeypatch.setattr(router_module, "load_keyring", unavailable_keyring)

    with _client(tmp_path, None) as client:  # type: ignore[arg-type]
        response = client.get("/api/v1/private/cards")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "keyring_unavailable"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert passphrase not in response.text
    assert "SYNTHETIC-ONLY-PAN" not in response.text


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
        # Far in the past for the same reason as the envelope timestamps below:
        # a date near today collides with the relative expiry dates one test
        # builds, and turns a leak assertion into a calendar-dependent failure.
        "created_at": "2000-01-01T00:00:00Z",
        "updated_at": "2000-01-01T00:00:00Z",
    }
    base.update(overrides)
    return base


def _card_with_children(*children: dict[str, object]) -> dict[str, object]:
    # The envelope timestamps are deliberately far in the past. A test here
    # asserts that no child's exact expiry date appears anywhere in the
    # response, and it builds those dates relative to today. With a timestamp
    # near the present, one of them eventually lands on the same day and the
    # assertion fails against these timestamps rather than any leaked value —
    # a failure that appears on one calendar day and cannot be reproduced on
    # any other. A date no relative offset can reach removes the collision.
    return {
        "card_id": "018f47f2-0f86-7b0a-bc7d-f00ba47c0001",
        "offering_id": "hdfc-regalia-gold-credit",
        "lifecycle": "active",
        "created_at": "2000-01-01T00:00:00Z",
        "updated_at": "2000-01-01T00:00:00Z",
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
    card_id = session.add_card("hdfc-regalia-gold-credit", {"pan": "SYNTHETIC-ONLY-PAN"}, passphrase="synthetic passphrase for child records")
    other_card_id = session.add_card("hdfc-tata-neu-rupay-select-credit", {"pan": "SYNTHETIC-ONLY-PAN-2"}, passphrase="synthetic passphrase for child records")
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


def test_production_reminder_reader_returns_only_derived_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mycard_benefits.vault import ChildRecordKind
    from mycard_benefits.vault.core import VaultStore
    from mycard_benefits.vault.router import _read_keyring_reminder_inputs

    vault_path = tmp_path / "data" / "private" / "vault.json"
    session = VaultStore(vault_path).create("synthetic reminder passphrase")
    card_id = session.add_card(
        "hdfc-regalia-gold-credit",
        {"pan": "SYNTHETIC-ONLY-PAN", "expiry_month": "08", "expiry_year": "2026"},
        passphrase="synthetic reminder passphrase",
    )
    session.add_child_record(card_id, ChildRecordKind.VOUCHER, expiry_date="2026-08-10")
    session.lock()

    class StubKeyring:
        def get_password(self, service_name: str, username: str) -> str | None:
            return "synthetic reminder passphrase"

    import mycard_benefits.vault.router as router_module
    monkeypatch.setattr(router_module, "load_keyring", lambda: StubKeyring())
    inputs = _read_keyring_reminder_inputs(vault_path)
    assert inputs[0]["expiry_date"] == "2026-08-31"
    assert "pan" not in inputs[0]
    assert inputs[0]["child_records"][0]["expiry_date"] == "2026-08-10"
