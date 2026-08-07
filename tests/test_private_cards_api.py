from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from mycard_benefits.app import create_app
from mycard_benefits.config import Settings


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
    assert set(row) == {
        "card_id",
        "offering_id",
        "lifecycle",
        "created_at",
        "updated_at",
        "replacement_card_id",
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
    assert (
        response.headers.get("cache-control") is None
        or response.headers["cache-control"] != "no-store"
    )
    assert "fallback" not in response.text.lower()
