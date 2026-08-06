from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from mycard_benefits.app import create_app
from mycard_benefits.config import Settings


def _client(tmp_path: Path) -> TestClient:
    settings = Settings(data_dir=tmp_path / "data", catalog_dir=tmp_path / "catalog", port=8777)
    return TestClient(create_app(settings))


def test_blank_dashboard_and_unsigned_health(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "Do not enter real card data" in page.text
        health = client.get("/api/v1/health").json()
        assert health["status"] == "ok"
        assert health["app_id"] == "mycard-benefits"
        assert "data" not in health


def test_signed_health_and_invalid_nonce(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/api/v1/health", params={"nonce": "0123456789abcdef"})
        assert response.status_code == 200
        assert response.json()["nonce"] == "0123456789abcdef"
        assert response.json()["signature"]
        assert client.get("/api/v1/health", params={"nonce": "bad"}).status_code == 400


def test_catalog_router_is_registered_and_fails_closed(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/api/v1/catalog/offerings")

    assert response.status_code == 503
    assert response.json() == {"detail": "Catalog unavailable"}
    assert str(tmp_path) not in response.text
