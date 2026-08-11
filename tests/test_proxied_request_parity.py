"""Behaviour parity for a request that arrived through the Rover gateway.

The owner reaches this application two ways: directly on the machine running
it, and from a phone through Rover, which starts local programs and exposes
them behind one authenticated URL. It is the same person either way, so the
application must answer identically either way.

That is not automatic. Rover's ``transparentRewrite`` presents a genuine
loopback request to the backend: it rewrites ``Host`` to ``127.0.0.1:<port>``
and drops ``Origin`` along with every client-supplied forwarding header. So a
proxied request differs from a direct one only in the absence of ``Origin`` —
and any check that quietly depends on ``Origin`` being present would refuse
the phone while accepting the laptop, splitting behaviour by device.

These tests pin the parity so a future header check cannot reintroduce that
split without failing here.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_protected_flow_routes import _setup

PORT = 8777


def _headers(client: TestClient, *, proxied: bool) -> dict[str, str]:
    """Build the two header shapes that reach the application.

    Both carry a freshly issued CSRF token, so the only difference between
    them is what Rover rewrites. A stale token produces the same 403 as a
    rejected origin, which would make any comparison here meaningless.
    """
    token = client.get("/api/v1/private/csrf-token").json()["csrf_token"]
    headers = {
        "Host": f"127.0.0.1:{PORT}",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "X-CSRF-Token": token,
        "Content-Type": "application/json",
    }
    if not proxied:
        headers["Origin"] = f"http://127.0.0.1:{PORT}"
    return headers


def test_reveal_answers_a_proxied_request_exactly_as_a_direct_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The phone and the laptop get the same answer from the reveal endpoint."""
    client, card_id = _setup(tmp_path, monkeypatch)
    path = f"/api/v1/private/cards/{card_id}/reveal-authorize"
    body = {"mode": "reuse"}

    direct = client.post(path, headers=_headers(client, proxied=False), json=body)
    proxied = client.post(path, headers=_headers(client, proxied=True), json=body)

    assert proxied.status_code == direct.status_code
    # A direct caller that is merely refused for an unrelated reason would make
    # the equality above pass vacuously, so require the shared outcome to be a
    # real one rather than the generic origin rejection.
    assert direct.status_code != 403 or "protected browser action rejected" not in direct.text


def test_private_cards_are_listed_for_a_proxied_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reaching the app through Rover is not itself a reason to withhold data."""
    client, _ = _setup(tmp_path, monkeypatch)
    direct = client.get("/api/v1/private/cards", headers=_headers(client, proxied=False))
    proxied = client.get("/api/v1/private/cards", headers=_headers(client, proxied=True))

    assert proxied.status_code == direct.status_code == 200


def test_a_non_loopback_host_is_still_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Parity is for what Rover actually sends, not for anything claiming to be it.

    Rover always rewrites Host to the loopback target. A request whose Host is
    something else did not come through that path, so the existing check must
    keep refusing it — accepting one would open the app to DNS rebinding.
    """
    client, card_id = _setup(tmp_path, monkeypatch)
    headers = _headers(client, proxied=True) | {"Host": "attacker.example:8777"}
    response = client.post(
        f"/api/v1/private/cards/{card_id}/reveal-authorize", headers=headers, json={"mode": "reuse"}
    )
    assert response.status_code == 403
