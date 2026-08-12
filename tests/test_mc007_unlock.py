from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mycard_benefits.app import create_app
from mycard_benefits.config import Settings
from mycard_benefits.vault.core import VaultError, VaultStore

PASS = "synthetic mc007 passphrase"
ORIGIN = "http://127.0.0.1:8777"


def _setup(tmp_path: Path, *, demo: bool = False) -> TestClient:
    vault = tmp_path / "data" / "private" / "vault.json"
    session = VaultStore(vault).create(PASS)
    session.add_card("synthetic-offering", {"pan": "SYNTHETIC-ONLY-PAN"}, passphrase=PASS)
    session.lock()
    settings = Settings(data_dir=tmp_path / "data", catalog_dir=Path(__file__).parent / "fixtures" / "synthetic_catalog", port=8777, demo=demo)
    return TestClient(create_app(settings))


def _headers(client: TestClient, token: str, **extra: str) -> dict[str, str]:
    return {
        "Origin": ORIGIN, "Host": "127.0.0.1:8777", "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin", "X-CSRF-Token": token, **extra,
    }


def _no_origin_headers(**extra: str) -> dict[str, str]:
    return {
        "Host": "127.0.0.1:8777", "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin", **extra,
    }


def _raw_headers(token: str, *, cookie: str | None = None) -> list[tuple[bytes, bytes]]:
    headers = [
        (b"origin", ORIGIN.encode("ascii")),
        (b"host", b"127.0.0.1:8777"),
        (b"sec-fetch-mode", b"cors"),
        (b"sec-fetch-site", b"same-origin"),
        (b"x-csrf-token", token.encode("ascii")),
        (b"content-type", b"application/json"),
    ]
    if cookie is not None:
        headers.append((b"cookie", cookie.encode("ascii")))
    return headers


def _raw_request(
    app: Any, *, path: str, headers: list[tuple[bytes, bytes]], body: bytes,
    method: str = "POST",
) -> tuple[int, dict[str, str], int]:
    """Call the ASGI app without an HTTP client normalizing duplicate headers."""
    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "root_path": "",
        "headers": headers,
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 8777),
    }
    received = 0
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        nonlocal received
        received += 1
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    start = next(message for message in sent if message["type"] == "http.response.start")
    response_headers = {
        name.decode("latin-1").lower(): value.decode("latin-1")
        for name, value in start["headers"]
    }
    return start["status"], response_headers, received


def _raw_get_headers() -> list[tuple[bytes, bytes]]:
    return [
        (b"host", b"127.0.0.1:8777"),
        (b"sec-fetch-mode", b"cors"),
        (b"sec-fetch-site", b"same-origin"),
    ]


def _hostile_unlock_headers(kind: str, token: str) -> tuple[list[tuple[bytes, bytes]], int]:
    headers = _raw_headers(token)
    if kind == "csrf-equal-duplicate":
        headers.append((b"x-csrf-token", token.encode("ascii")))
        return headers, 403
    if kind == "csrf-conflicting-duplicate":
        headers.append((b"x-csrf-token", b"SYNTHETIC-ONLY-CONFLICT"))
        return headers, 403
    if kind == "csrf-comma-joined":
        headers[4] = (b"x-csrf-token", f"{token},{token}".encode("ascii"))
        return headers, 403
    if kind == "csrf-case-variant":
        headers[4] = (b"X-CSRF-Token", token.encode("ascii"))
        return headers, 403
    if kind == "media-equal-duplicate":
        headers.append((b"content-type", b"application/json"))
        return headers, 415
    if kind == "media-conflicting-duplicate":
        headers.append((b"content-type", b"text/plain"))
        return headers, 415
    if kind == "media-comma-joined":
        headers[5] = (b"content-type", b"application/json, text/plain")
        return headers, 415
    if kind == "media-case-variant":
        headers[5] = (b"Content-Type", b"application/json")
        return headers, 403
    if kind == "length-equal-duplicate":
        headers.extend(((b"content-length", b"2"), (b"content-length", b"2")))
        return headers, 413
    raise AssertionError(kind)


def test_unlock_returns_only_cookie_and_cards_are_ephemeral(tmp_path: Path) -> None:
    with _setup(tmp_path / "rate-limit") as client:
        bootstrap = client.get("/api/v1/private/unlock/bootstrap", headers=_headers(client, "unused"))
        token = bootstrap.json()["csrf_token"]
        unlocked = client.post("/api/v1/private/unlock", headers=_headers(client, token), json={"passphrase": PASS, "remember": False})
        assert unlocked.status_code == 200
        assert "passphrase" not in unlocked.text
        assert "mycard_vault_session" in unlocked.headers["set-cookie"]
        cards = client.get("/api/v1/private/cards")
        assert cards.status_code == 200
        assert cards.json()["cards"][0]["masked_last4"] is None
        assert "SYNTHETIC-ONLY-PAN" not in cards.text
        assert cards.headers["cache-control"] == "no-store"
        csrf = client.get("/api/v1/private/csrf-token").json()["csrf_token"]
        locked = client.post("/api/v1/private/lock", headers=_headers(client, csrf))
        assert locked.status_code == 200
        assert client.get("/api/v1/private/cards").json()["detail"]["code"] in {"passphrase_only", "keyring_unavailable"}


def test_unlock_bootstrap_is_one_use_and_wrong_passphrase_is_generic(tmp_path: Path) -> None:
    with _setup(tmp_path) as client:
        token = client.get("/api/v1/private/unlock/bootstrap", headers=_headers(client, "unused")).json()["csrf_token"]
        wrong = client.post("/api/v1/private/unlock", headers=_headers(client, token), json={"passphrase": "synthetic wrong passphrase", "remember": False})
        assert wrong.status_code == 401
        assert "synthetic wrong passphrase" not in wrong.text
        replay = client.post("/api/v1/private/unlock", headers=_headers(client, token), json={"passphrase": PASS, "remember": False})
        assert replay.status_code == 403


def test_no_origin_same_origin_unlock_bootstrap_authorizes_one_post_and_replay_is_rejected(
    tmp_path: Path,
) -> None:
    with _setup(tmp_path) as client:
        bootstrap = client.get(
            "/api/v1/private/unlock/bootstrap", headers=_no_origin_headers()
        )
        assert bootstrap.status_code == 200
        assert set(bootstrap.json()) == {"csrf_token"}
        assert bootstrap.headers["cache-control"] == "no-store"
        assert bootstrap.headers["pragma"] == "no-cache"
        token = bootstrap.json()["csrf_token"]

        substituted = client.post(
            "/api/v1/private/unlock",
            headers=_headers(client, "SYNTHETIC-ONLY-wrong-csrf"),
            json={"passphrase": PASS, "remember": False},
        )
        assert substituted.status_code == 403
        assert substituted.headers["cache-control"] == "no-store"
        assert substituted.headers["pragma"] == "no-cache"

        unlocked = client.post(
            "/api/v1/private/unlock",
            headers=_headers(client, token),
            json={"passphrase": PASS, "remember": False},
        )
        assert unlocked.status_code == 200
        assert PASS not in unlocked.text
        replay = client.post(
            "/api/v1/private/unlock",
            headers=_headers(client, token),
            json={"passphrase": PASS, "remember": False},
        )
        assert replay.status_code == 403
        assert replay.headers["cache-control"] == "no-store"
        assert replay.headers["pragma"] == "no-cache"


@pytest.mark.parametrize(
    ("header", "value"),
    [
        ("Origin", "https://attacker.invalid"),
        ("Origin", "http://127.0.0.1:8777/path"),
        ("Origin", ""),
        ("Host", "attacker.invalid:8777"),
        ("Sec-Fetch-Site", None),
        ("Sec-Fetch-Site", "cross-site"),
        ("Sec-Fetch-Site", "none"),
        ("Sec-Fetch-Mode", None),
        ("Sec-Fetch-Mode", "no-cors"),
    ],
)
def test_unlock_bootstrap_rejects_hostile_or_malformed_browser_metadata_without_private_state_change(
    tmp_path: Path, header: str, value: str | None
) -> None:
    with _setup(tmp_path) as client:
        headers = _no_origin_headers()
        if value is None:
            headers.pop(header)
        else:
            headers[header] = value
        rejected = client.get("/api/v1/private/unlock/bootstrap", headers=headers)
        assert rejected.status_code == 403
        assert rejected.headers["cache-control"] == "no-store"
        assert rejected.headers["pragma"] == "no-cache"
        locked = client.get("/api/v1/private/cards")
        assert locked.status_code != 200
        assert "SYNTHETIC-ONLY-PAN" not in locked.text

        valid = client.get(
            "/api/v1/private/unlock/bootstrap", headers=_no_origin_headers()
        )
        token = valid.json()["csrf_token"]
        unlocked = client.post(
            "/api/v1/private/unlock", headers=_headers(client, token), json={"passphrase": PASS, "remember": False}
        )
        assert unlocked.status_code == 200


@pytest.mark.parametrize("forwarded_name", ["Forwarded", "X-Forwarded-Host", "X-Forwarded-Proto"])
def test_unlock_ignores_forwarded_annotations_but_never_trusts_them(
    tmp_path: Path, forwarded_name: str
) -> None:
    """Proxy annotations are inert, not an alternate Host or Origin.

    The old contract rejected the mere presence of a forwarded header. Rover
    adds those headers to every request it forwards, so that mechanism made an
    otherwise valid phone request impossible. The security property is that
    their values cannot change a valid decision or rescue an invalid real
    Host/Origin value.
    """
    with _setup(tmp_path / "baseline") as baseline:
        token = baseline.get(
            "/api/v1/private/unlock/bootstrap", headers=_no_origin_headers()
        ).json()["csrf_token"]
        plain = baseline.post(
            "/api/v1/private/unlock",
            headers=_headers(baseline, token),
            json={"passphrase": PASS, "remember": False},
        )
        assert plain.status_code == 200

    with _setup(tmp_path / "forwarded") as client:
        annotation = {forwarded_name: "attacker.invalid"}
        bootstrap = client.get(
            "/api/v1/private/unlock/bootstrap",
            headers=_no_origin_headers(**annotation),
        )
        assert bootstrap.status_code == 200
        token = bootstrap.json()["csrf_token"]
        annotated = client.post(
            "/api/v1/private/unlock",
            headers=_headers(client, token, **annotation),
            json={"passphrase": PASS, "remember": False},
        )
        assert annotated.status_code == plain.status_code

        fake_host = client.get(
            "/api/v1/private/unlock/bootstrap",
            headers=_no_origin_headers(
                Host="attacker.invalid:8777", **{forwarded_name: "127.0.0.1:8777"}
            ),
        )
        assert fake_host.status_code == 403
        fake_origin = client.get(
            "/api/v1/private/unlock/bootstrap",
            headers=_headers(
                client,
                "unused",
                Origin="http://attacker.invalid:8777",
                **{forwarded_name: "127.0.0.1:8777"},
            ),
        )
        assert fake_origin.status_code == 403


@pytest.mark.parametrize("duplicate", ["origin", "host"])
def test_unlock_bootstrap_rejects_duplicate_origin_or_host_without_private_state_change(
    tmp_path: Path, duplicate: str
) -> None:
    with _setup(tmp_path) as client:
        headers = _raw_get_headers()
        if duplicate == "origin":
            headers.extend(
                [(b"origin", ORIGIN.encode("ascii")), (b"origin", ORIGIN.encode("ascii"))]
            )
        else:
            headers.append((b"host", b"127.0.0.1:8777"))
        status, response_headers, received = _raw_request(
            client.app, path="/api/v1/private/unlock/bootstrap", headers=headers,
            body=b"", method="GET",
        )
        assert status == 403
        assert response_headers["cache-control"] == "no-store"
        assert response_headers["pragma"] == "no-cache"
        assert received == 0
        assert client.get("/api/v1/private/cards").status_code != 200

        valid = client.get(
            "/api/v1/private/unlock/bootstrap", headers=_no_origin_headers()
        )
        unlocked = client.post(
            "/api/v1/private/unlock",
            headers=_headers(client, valid.json()["csrf_token"]),
            json={"passphrase": PASS, "remember": False},
        )
        assert unlocked.status_code == 200


def test_manual_unlock_fallback_opens_present_vault_without_keyring_and_lock_restores_safe_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    passphrase = "SYNTHETIC-ONLY-manual-unlock-passphrase"
    vault = tmp_path / "data" / "private" / "vault.json"
    session = VaultStore(vault).create(passphrase)
    card_id = session.add_card(
        "synthetic-example-in-visa",
        {"pan": "SYNTHETIC-ONLY-PAN"},
        passphrase=passphrase,
    )
    session.lock()

    import mycard_benefits.vault.router as router

    def unavailable_keyring() -> object:
        raise VaultError("SYNTHETIC-ONLY-keyring-unavailable")

    monkeypatch.setattr(router, "load_keyring", unavailable_keyring)
    settings = Settings(
        data_dir=tmp_path / "data",
        catalog_dir=Path(__file__).parent / "fixtures" / "synthetic_catalog",
        port=8777,
    )

    with TestClient(create_app(settings)) as client:
        unavailable = client.get("/api/v1/private/cards")
        assert unavailable.status_code == 503
        assert unavailable.json()["detail"]["code"] == "keyring_unavailable"
        assert unavailable.headers["cache-control"] == "no-store"

        wrong_token = client.get(
            "/api/v1/private/unlock/bootstrap", headers=_headers(client, "unused")
        ).json()["csrf_token"]
        wrong = client.post(
            "/api/v1/private/unlock",
            headers=_headers(client, wrong_token),
            json={"passphrase": "SYNTHETIC-ONLY-wrong-passphrase", "remember": False},
        )
        assert wrong.status_code == 401
        assert wrong.headers["cache-control"] == "no-store"
        assert wrong.headers["pragma"] == "no-cache"
        assert "SYNTHETIC-ONLY-wrong-passphrase" not in wrong.text

        unlock_token = client.get(
            "/api/v1/private/unlock/bootstrap", headers=_headers(client, "unused")
        ).json()["csrf_token"]
        unlocked = client.post(
            "/api/v1/private/unlock",
            headers=_headers(client, unlock_token),
            json={"passphrase": passphrase, "remember": False},
        )
        assert unlocked.status_code == 200
        assert unlocked.headers["cache-control"] == "no-store"
        assert passphrase not in unlocked.text

        cards = client.get("/api/v1/private/cards")
        assert cards.status_code == 200
        assert cards.headers["cache-control"] == "no-store"
        assert cards.json()["cards"][0]["card_id"] == card_id
        assert cards.json()["cards"][0]["offering_id"] == "synthetic-example-in-visa"
        assert passphrase not in cards.text
        assert "SYNTHETIC-ONLY-PAN" not in cards.text

        csrf = client.get("/api/v1/private/csrf-token").json()["csrf_token"]
        locked = client.post("/api/v1/private/lock", headers=_headers(client, csrf))
        assert locked.status_code == 200
        assert locked.headers["cache-control"] == "no-store"
        after_lock = client.get("/api/v1/private/cards")
        assert after_lock.status_code == 503
        assert after_lock.json()["detail"]["code"] == "keyring_unavailable"
        assert "SYNTHETIC-ONLY-PAN" not in after_lock.text


def test_unlock_ignores_forwarded_annotation_but_rejects_bad_media_and_oversized_body(
    tmp_path: Path,
) -> None:
    """Changing the proxy annotation does not weaken body framing checks."""
    with _setup(tmp_path) as client:
        token = client.get("/api/v1/private/unlock/bootstrap", headers=_headers(client, "unused")).json()["csrf_token"]
        hostile = _headers(client, token, **{"X-Forwarded-Host": "evil.invalid"})
        accepted = client.post("/api/v1/private/unlock", headers=hostile, json={"passphrase": PASS, "remember": False})
        assert accepted.status_code == 200
        assert PASS not in accepted.text
        token = client.get("/api/v1/private/unlock/bootstrap", headers=_headers(client, "unused")).json()["csrf_token"]
        bad_media = _headers(client, token, **{"Content-Type": "application/json; charset=utf-8"})
        assert client.post("/api/v1/private/unlock", headers=bad_media, content=b'{"passphrase":"SYNTHETIC-ONLY-SECRET"}').status_code == 415
        token = client.get("/api/v1/private/unlock/bootstrap", headers=_headers(client, "unused")).json()["csrf_token"]
        large = _headers(client, token, **{"Content-Type": "application/json", "Content-Length": "4097"})
        assert client.post("/api/v1/private/unlock", headers=large, content=b"x" * 4097).status_code == 413


@pytest.mark.parametrize(
    "kind",
    [
        "csrf-equal-duplicate",
        "csrf-conflicting-duplicate",
        "csrf-comma-joined",
        "csrf-case-variant",
        "media-equal-duplicate",
        "media-conflicting-duplicate",
        "media-comma-joined",
        "media-case-variant",
        "length-equal-duplicate",
    ],
)
def test_raw_asgi_unlock_header_matrix_rejects_before_body_parser_or_vault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    import mycard_benefits.vault.router as vault_router

    parser_calls = 0
    vault_open_calls = 0
    original_parser = vault_router._unlock_request_from_body
    original_open = vault_router.VaultStore.open

    def parser_spy(body: bytearray) -> tuple[str, bool]:
        nonlocal parser_calls
        parser_calls += 1
        return original_parser(body)

    def vault_open_spy(self: VaultStore, passphrase: str) -> Any:
        nonlocal vault_open_calls
        vault_open_calls += 1
        return original_open(self, passphrase)

    monkeypatch.setattr(vault_router, "_unlock_request_from_body", parser_spy)
    monkeypatch.setattr(vault_router.VaultStore, "open", vault_open_spy)
    with _setup(tmp_path) as client:
        token = client.get("/api/v1/private/unlock/bootstrap", headers=_headers(client, "unused")).json()["csrf_token"]
        headers, expected_status = _hostile_unlock_headers(kind, token)
        status, response_headers, received = _raw_request(
            client.app,
            path="/api/v1/private/unlock",
            headers=headers,
            body=b"{}",
        )

    assert status == expected_status
    assert response_headers["cache-control"] == "no-store"
    assert response_headers["pragma"] == "no-cache"
    assert received == parser_calls == vault_open_calls == 0


def test_raw_asgi_unlock_header_rejections_do_not_consume_tokens_or_rate_state(
    tmp_path: Path,
) -> None:
    with _setup(tmp_path) as client:
        token = client.get("/api/v1/private/unlock/bootstrap", headers=_headers(client, "unused")).json()["csrf_token"]
        for _ in range(5):
            headers, _ = _hostile_unlock_headers("media-conflicting-duplicate", token)
            status, _response_headers, received = _raw_request(
                client.app,
                path="/api/v1/private/unlock",
                headers=headers,
                body=b"{}",
            )
            assert status == 415
            assert received == 0
        response = client.post(
            "/api/v1/private/unlock",
            headers=_headers(client, token),
            json={"passphrase": "synthetic wrong passphrase", "remember": False},
        )
    assert response.status_code == 401


@pytest.mark.parametrize(
    ("kind", "expected_status"),
    [
        ("csrf-equal-duplicate", 403),
        ("csrf-comma-joined", 403),
        ("csrf-case-variant", 403),
        ("media-conflicting-duplicate", 415),
        ("media-comma-joined", 415),
        ("length-equal-duplicate", 413),
    ],
)
def test_raw_asgi_lock_rejects_ambiguous_headers_without_receiving_a_body(
    tmp_path: Path, kind: str, expected_status: int
) -> None:
    with _setup(tmp_path) as client:
        bootstrap = client.get("/api/v1/private/unlock/bootstrap", headers=_headers(client, "unused"))
        unlock_token = bootstrap.json()["csrf_token"]
        assert client.post(
            "/api/v1/private/unlock", headers=_headers(client, unlock_token), json={"passphrase": PASS, "remember": False}
        ).status_code == 200
        csrf = client.get("/api/v1/private/csrf-token").json()["csrf_token"]
        cookie = client.cookies.get("mycard_vault_session")
        assert cookie is not None
        headers, _ignored_status = _hostile_unlock_headers(kind, csrf)
        headers.append((b"cookie", f"mycard_vault_session={cookie}".encode("ascii")))
        status, response_headers, received = _raw_request(
            client.app,
            path="/api/v1/private/lock",
            headers=headers,
            body=b"{}",
        )
        assert client.get("/api/v1/private/cards").status_code == 200

    assert status == expected_status
    assert response_headers["cache-control"] == "no-store"
    assert response_headers["pragma"] == "no-cache"
    assert received == 0


def test_unlock_disabled_in_demo_and_rate_limit_is_generic(tmp_path: Path) -> None:
    with _setup(tmp_path, demo=True) as client:
        assert client.get("/api/v1/private/unlock/bootstrap", headers=_headers(client, "unused")).status_code == 403
    with _setup(tmp_path / "rate-limit") as client:
        for _ in range(5):
            token = client.get("/api/v1/private/unlock/bootstrap", headers=_headers(client, "unused")).json()["csrf_token"]
            assert client.post("/api/v1/private/unlock", headers=_headers(client, token), json={"passphrase": "synthetic wrong passphrase", "remember": False}).status_code == 401
        token = client.get("/api/v1/private/unlock/bootstrap", headers=_headers(client, "unused")).json()["csrf_token"]
        limited = client.post("/api/v1/private/unlock", headers=_headers(client, token), json={"passphrase": PASS, "remember": False})
        assert limited.status_code == 429
        assert PASS not in limited.text
