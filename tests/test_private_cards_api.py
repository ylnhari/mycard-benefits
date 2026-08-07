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
    assert "pan" not in response.text.lower()
    assert "cvv" not in response.text.lower()


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
