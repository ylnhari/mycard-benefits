from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from mycard_benefits import cli
from mycard_benefits.config import Settings


def test_cli_always_binds_loopback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}

    def fake_create_app(settings: Settings) -> object:
        captured["settings"] = settings
        return object()

    def fake_run(app: object, *, host: str, port: int) -> None:
        captured.update(app=app, host=host, port=port)

    def unexpected_timer(*args: object, **kwargs: object) -> None:
        raise AssertionError("--no-browser must not schedule a browser launch")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "mycard-benefits",
            "--port",
            "18877",
            "--data-dir",
            str(tmp_path / "data"),
            "--demo",
            "--no-browser",
        ],
    )
    monkeypatch.setattr(cli, "create_app", fake_create_app)
    monkeypatch.setattr(cli.uvicorn, "run", fake_run)
    monkeypatch.setattr(cli.threading, "Timer", unexpected_timer)

    cli.main()

    settings = captured["settings"]
    assert isinstance(settings, Settings)
    assert settings.port == 18877
    assert settings.demo is True
    assert settings.data_dir == (tmp_path / "data").resolve()
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 18877
