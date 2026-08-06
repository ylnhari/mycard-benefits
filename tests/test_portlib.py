from __future__ import annotations

import json
from pathlib import Path

import pytest

from mycard_benefits.portlib import PortError, registry_port, resolve_port


def test_resolution_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    registry = tmp_path / "ports.json"
    registry.write_text(
        json.dumps({"registry": {"mycard-benefits": {"port": 7001}}, "next_available": 9999}),
        encoding="utf-8",
    )
    monkeypatch.setenv("TEST_CARD_PORT", "7002")
    assert resolve_port("mycard-benefits", explicit=7003, env_var="TEST_CARD_PORT", registry=registry, default=7000) == 7003
    assert resolve_port("mycard-benefits", env_var="TEST_CARD_PORT", registry=registry, default=7000) == 7002
    monkeypatch.delenv("TEST_CARD_PORT")
    assert resolve_port("mycard-benefits", env_var="TEST_CARD_PORT", registry=registry, default=7000) == 7001
    assert resolve_port("missing", registry=registry, default=7000) == 7000


def test_registry_never_reads_next_available(tmp_path: Path) -> None:
    registry = tmp_path / "ports.json"
    registry.write_text(json.dumps({"registry": {}, "next_available": 8123}), encoding="utf-8")
    assert registry_port("mycard-benefits", registry=registry) is None
    with pytest.raises(PortError):
        resolve_port("mycard-benefits", registry=registry)


@pytest.mark.parametrize("value", [0, -1, 65536, True, 1.5, "not-a-port"])
def test_invalid_ports_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: object
) -> None:
    with pytest.raises(PortError):
        resolve_port("mycard-benefits", explicit=value)  # type: ignore[arg-type]

    registry = tmp_path / "ports.json"
    registry.write_text(
        json.dumps({"registry": {"mycard-benefits": {"port": value}}}),
        encoding="utf-8",
    )
    with pytest.raises(PortError):
        resolve_port("mycard-benefits", registry=registry, default=8777)

    monkeypatch.setenv("TEST_CARD_PORT", str(value))
    with pytest.raises(PortError):
        resolve_port("mycard-benefits", env_var="TEST_CARD_PORT", default=8777)


@pytest.mark.parametrize("value", [1, 8777, 65535, "8777"])
def test_valid_port_boundaries(value: int | str) -> None:
    assert resolve_port("mycard-benefits", explicit=value) == int(value)  # type: ignore[arg-type]
