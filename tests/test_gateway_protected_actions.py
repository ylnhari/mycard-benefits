"""Protected actions must work when the app is reached through the gateway.

The owner reported four times that card details failed from their phone while
working on the machine itself. Two independent checks refused every protected
request that had crossed the gateway, and both refusals surfaced as a bare
string with no error code, so the screen could only say something had gone
wrong without saying what.

1. The gateway annotates the hop with ``X-Forwarded-Host`` and
   ``X-Forwarded-Proto``. Their mere presence was treated as an attack.
2. Browsers send Fetch Metadata only to potentially trustworthy origins, which
   over plain HTTP means loopback alone. On the machine's network address a
   browser sends no ``Sec-Fetch-*`` header at all, and the check required one.

Neither refusal reflected anything about the request's legitimacy: the same
person, on the same vault, was refused for having taken a different route. What
still admits a request is the CSRF token with the exact loopback Host, and an
Origin or Fetch Metadata value that agrees with them when present.

These tests send the header shapes a browser and the gateway actually produce.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_protected_flow_routes import _setup

PORT = 8777
LOOPBACK_ORIGIN = f"http://127.0.0.1:{PORT}"


def _csrf(client: TestClient) -> str:
    return client.get("/api/v1/private/csrf-token").json()["csrf_token"]


def _on_the_machine(client: TestClient) -> dict[str, str]:
    """What a browser sends on 127.0.0.1: Origin plus Fetch Metadata."""
    return {
        "Host": f"127.0.0.1:{PORT}",
        "Origin": LOOPBACK_ORIGIN,
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "X-CSRF-Token": _csrf(client),
        "Content-Type": "application/json",
    }


def _through_the_gateway(client: TestClient) -> dict[str, str]:
    """What arrives from a phone: no Origin, no Fetch Metadata, forwarded pair.

    The gateway rewrites Host to the loopback target and strips Origin; the
    browser omits Sec-Fetch-* because the page is not on a trustworthy origin.
    """
    return {
        "Host": f"127.0.0.1:{PORT}",
        "X-Forwarded-Host": "100.90.58.116:55038",
        "X-Forwarded-Proto": "http",
        "X-CSRF-Token": _csrf(client),
        "Content-Type": "application/json",
    }


def _reveal(client: TestClient, card_id: str, headers: dict[str, str]):
    return client.post(
        f"/api/v1/private/cards/{card_id}/reveal-authorize",
        headers=headers,
        json={"mode": "reuse"},
    )


def test_a_gateway_request_is_not_refused_for_being_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The phone gets the same answer as the machine, not a rejection."""
    client, card_id = _setup(tmp_path, monkeypatch)

    direct = _reveal(client, card_id, _on_the_machine(client))
    gateway = _reveal(client, card_id, _through_the_gateway(client))

    assert gateway.status_code == direct.status_code
    assert "protected browser action rejected" not in gateway.text
    # The reply must carry a code the interface can explain. A bare string is
    # what produced "unavailable right now", which told the owner nothing.
    assert isinstance(gateway.json()["detail"], dict)


def test_forwarded_headers_alone_do_not_reject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A proxy describing its own hop is not evidence of an attack."""
    client, card_id = _setup(tmp_path, monkeypatch)
    headers = _on_the_machine(client) | {
        "X-Forwarded-Host": "100.90.58.116:55038",
        "X-Forwarded-Proto": "http",
        "Forwarded": "host=100.90.58.116:55038;proto=http",
    }

    assert "protected browser action rejected" not in _reveal(client, card_id, headers).text


def test_absent_fetch_metadata_alone_does_not_reject(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No browser sends Sec-Fetch-* over plain HTTP off loopback."""
    client, card_id = _setup(tmp_path, monkeypatch)
    headers = {
        "Host": f"127.0.0.1:{PORT}",
        "X-CSRF-Token": _csrf(client),
        "Content-Type": "application/json",
    }

    assert "protected browser action rejected" not in _reveal(client, card_id, headers).text


def test_a_forwarded_header_cannot_stand_in_for_the_real_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ignoring these headers must not mean trusting them.

    The gateway always rewrites Host to the loopback target. A request whose
    Host is something else did not come that way, and no X-Forwarded-Host can
    make it look as though it did.
    """
    client, card_id = _setup(tmp_path, monkeypatch)
    headers = _through_the_gateway(client) | {"Host": "attacker.example:8777"}

    assert _reveal(client, card_id, headers).status_code == 403


@pytest.mark.parametrize(
    "hostile",
    [
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
        {"Sec-Fetch-Mode": "navigate"},
        {"Origin": "http://evil.example"},
    ],
)
def test_contradictory_metadata_is_still_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hostile: dict[str, str]
) -> None:
    """Absent is accepted; contradictory is not. That distinction is the fix."""
    client, card_id = _setup(tmp_path, monkeypatch)
    headers = _through_the_gateway(client) | hostile

    assert _reveal(client, card_id, headers).status_code == 403


def test_a_duplicated_fetch_metadata_header_is_still_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two conflicting values must never let a caller choose which is read."""
    client, card_id = _setup(tmp_path, monkeypatch)
    token = _csrf(client)
    response = client.post(
        f"/api/v1/private/cards/{card_id}/reveal-authorize",
        headers=[
            ("host", f"127.0.0.1:{PORT}"),
            ("sec-fetch-site", "same-origin"),
            ("sec-fetch-site", "cross-site"),
            ("x-csrf-token", token),
            ("content-type", "application/json"),
        ],
        json={"mode": "reuse"},
    )

    assert response.status_code == 403


def test_the_csrf_token_is_still_required_without_fetch_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With Fetch Metadata optional, the token carries the weight. It must hold."""
    client, card_id = _setup(tmp_path, monkeypatch)
    headers = {"Host": f"127.0.0.1:{PORT}", "Content-Type": "application/json"}

    assert _reveal(client, card_id, headers).status_code == 403

    wrong = headers | {"X-CSRF-Token": "not-the-token"}
    assert _reveal(client, card_id, wrong).status_code == 403
