"""Regression tests for hostile browser/API input at public boundaries."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from mycard_benefits.app import create_app
from mycard_benefits.config import Settings

ROOT = Path(__file__).parents[1]
MARKER = "SYNTHETIC-ONLY-HOSTILE-INPUT-MARKER"


def _client(tmp_path: Path) -> TestClient:
    settings = Settings(
        data_dir=tmp_path / "data",
        catalog_dir=ROOT / "tests" / "fixtures" / "synthetic_catalog",
        port=8777,
    )
    return TestClient(create_app(settings))


def test_static_mount_rejects_path_traversal(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/static/%2e%2e/pyproject.toml")

    assert response.status_code in {403, 404}
    assert "build-system" not in response.text
    assert "hatchling" not in response.text


def test_browser_renderer_uses_text_nodes_and_safe_links_for_external_content() -> None:
    script = (ROOT / "src" / "mycard_benefits" / "static" / "app.js").read_text(encoding="utf-8")
    assert "innerHTML" not in script and "insertAdjacentHTML" not in script
    assert "element.textContent = text" in script
    assert 'return ["http:", "https:"].includes(url.protocol)' in script
