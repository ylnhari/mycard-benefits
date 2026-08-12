from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mycard_benefits.app import create_app
from mycard_benefits.config import Settings
from mycard_benefits.vault.core import VaultError, VaultStore

PASS = "synthetic protected passphrase"
ORIGIN = "http://127.0.0.1:8777"
CARD = "hdfc-regalia-gold-credit"


def _origin_headers(**extra: str) -> dict[str, str]:
    return {"Origin": ORIGIN, "Host": "127.0.0.1:8777", **extra}


def _protected_headers(client: TestClient, **extra: str) -> dict[str, str]:
    token = client.get("/api/v1/private/csrf-token").json()["csrf_token"]
    return _origin_headers(
        **{"Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "same-origin", "X-CSRF-Token": token, **extra}
    )


def _setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, str]:
    data_dir = tmp_path / "data"
    vault_path = data_dir / "private" / "vault.json"
    session = VaultStore(vault_path).create(PASS)
    card_id = session.add_card(CARD, {"pan": "SYNTHETIC-ONLY-PAN"}, passphrase=PASS)
    session.lock()

    class StubKeyring:
        def get_password(self, service_name: str, username: str) -> str:
            return PASS

    import mycard_benefits.vault.router as router

    monkeypatch.setattr(router, "load_keyring", lambda: StubKeyring())
    settings = Settings(data_dir=data_dir, catalog_dir=tmp_path / "catalog", port=8777)
    return TestClient(create_app(settings)), card_id


def test_csrf_token_is_no_store_and_actual_loopback_origin_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _setup(tmp_path, monkeypatch)
    token = client.get("/api/v1/private/csrf-token")
    assert token.status_code == 200
    assert token.headers["cache-control"] == "no-store"

    response = client.post(
        "/api/v1/private/cards/add",
        headers=_protected_headers(client),
        json={"passphrase": PASS, "offering_id": CARD, "secret_fields": {"nickname": "Synthetic"}},
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


def test_missing_origin_requires_token_host_and_fetch_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _setup(tmp_path, monkeypatch)
    token = client.get("/api/v1/private/csrf-token").json()["csrf_token"]
    body = {"passphrase": PASS, "offering_id": CARD, "secret_fields": {"nickname": "Synthetic"}}

    rejected = client.post("/api/v1/private/cards/add", json=body)
    assert rejected.status_code == 403
    accepted = client.post(
        "/api/v1/private/cards/add",
        headers={
            "Host": "127.0.0.1:8777",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "X-CSRF-Token": token,
        },
        json=body,
    )
    assert accepted.status_code == 200


@pytest.mark.parametrize(
    "change",
    [
        {"X-CSRF-Token": ""},
        {"X-CSRF-Token": "SYNTHETIC-ONLY-WRONG-CSRF"},
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "Same-Origin"},
        {"Sec-Fetch-Site": "same-origin, same-origin"},
        {"Sec-Fetch-Site": ""},
        {"Sec-Fetch-Mode": "no-cors"},
        {"Sec-Fetch-Mode": "CORS"},
        {"Sec-Fetch-Mode": "cors, cors"},
        {"Sec-Fetch-Mode": ""},
        {"Host": "127.0.0.1:8777, 127.0.0.1:8777"},
        {"Origin": f"{ORIGIN}, {ORIGIN}"},
    ],
)
def test_origin_present_requires_each_csrf_and_fetch_metadata_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: dict[str, str]
) -> None:
    client, _ = _setup(tmp_path, monkeypatch)
    body = {"passphrase": PASS, "offering_id": CARD, "secret_fields": {"nickname": "Synthetic"}}
    headers = _protected_headers(client)
    headers.update(change)
    response = client.post("/api/v1/private/cards/add", headers=headers, json=body)
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "duplicate",
    [
        ("Origin", ORIGIN),
        ("Host", "127.0.0.1:8777"),
        ("Sec-Fetch-Site", "same-origin"),
        ("Sec-Fetch-Mode", "cors"),
        ("X-CSRF-Token", "SYNTHETIC-ONLY-DUPLICATE"),
    ],
)
def test_protected_route_rejects_duplicate_security_headers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, duplicate: tuple[str, str]
) -> None:
    client, _ = _setup(tmp_path, monkeypatch)
    headers = _protected_headers(client)
    raw_headers = [*headers.items(), duplicate]
    response = client.post(
        "/api/v1/private/cards/add",
        headers=raw_headers,
        json={"passphrase": PASS, "offering_id": CARD, "secret_fields": {"nickname": "Synthetic"}},
    )
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("forwarded_name", ["Forwarded", "X-Forwarded-Host", "X-Forwarded-Proto"])
def test_a_forwarded_header_cannot_change_a_protected_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, forwarded_name: str
) -> None:
    """A spoofed forwarded header decides nothing here, either way.

    This once asserted that the presence of such a header was itself fatal.
    That could not stay: the owner's gateway annotates every request it
    forwards with X-Forwarded-Host and X-Forwarded-Proto, so the rule refused
    every protected action from their phone. What matters is not that these
    headers are absent but that they are never consulted, so the check is that
    a hostile value changes nothing about the result.
    """
    client, _ = _setup(tmp_path, monkeypatch)
    body = {"passphrase": PASS, "offering_id": CARD}

    without = client.post("/api/v1/private/cards/add", headers=_protected_headers(client), json=body)
    hostile = _protected_headers(client)
    hostile[forwarded_name] = "evil.invalid"
    with_header = client.post("/api/v1/private/cards/add", headers=hostile, json=body)

    assert with_header.status_code == without.status_code
    assert with_header.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("forwarded_name", ["Forwarded", "X-Forwarded-Host", "X-Forwarded-Proto"])
def test_a_forwarded_header_cannot_rescue_a_rejected_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, forwarded_name: str
) -> None:
    """Ignoring these headers must not shade into trusting them."""
    client, _ = _setup(tmp_path, monkeypatch)
    headers = _protected_headers(client)
    headers["Host"] = "evil.invalid:8777"
    headers[forwarded_name] = f"127.0.0.1:{8777}"

    response = client.post(
        "/api/v1/private/cards/add",
        headers=headers,
        json={"passphrase": PASS, "offering_id": CARD},
    )

    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"


def test_protected_route_succeeds_only_when_all_security_checks_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _setup(tmp_path, monkeypatch)
    response = client.post(
        "/api/v1/private/cards/add",
        headers=_protected_headers(client),
        json={"passphrase": PASS, "offering_id": CARD, "secret_fields": {"nickname": "Synthetic"}},
    )
    assert response.status_code == 200


@pytest.mark.parametrize(
    ("path_kind", "method"),
    [
        ("edit", "post"),
        ("lifecycle", "post"),
        ("replace", "post"),
        ("erase-cvv-pin", "post"),
        ("delete", "delete"),
        ("purge", "post"),
    ],
)
def test_every_protected_mutation_has_a_success_route_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    path_kind: str,
    method: str,
) -> None:
    client, card_id = _setup(tmp_path, monkeypatch)
    payload: dict[str, object] = {"passphrase": PASS}
    if path_kind == "edit":
        payload["changes"] = {"nickname": "Synthetic edit"}
    elif path_kind == "lifecycle":
        payload["lifecycle"] = "closed"
    elif path_kind == "replace":
        payload.update(
            offering_id=CARD,
            lifecycle="closed",
            secret_fields={"nickname": "Synthetic replacement"},
        )
    elif path_kind == "delete" or path_kind == "purge":
        payload["confirmation"] = "DELETE CARD"
    elif path_kind == "erase-cvv-pin":
        pass
    else:  # pragma: no cover - protects the test table itself
        raise AssertionError(path_kind)
    path = f"/api/v1/private/cards/{card_id}"
    if path_kind not in {"delete"}:
        path += f"/{path_kind}"
    response = client.request(method.upper(), path, headers=_protected_headers(client), json=payload)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    ("path", "method"),
    [
        ("/api/v1/private/cards/{card_id}/edit", "post"),
        ("/api/v1/private/cards/{card_id}/lifecycle", "post"),
        ("/api/v1/private/cards/{card_id}/replace", "post"),
        ("/api/v1/private/cards/{card_id}/erase-cvv-pin", "post"),
        ("/api/v1/private/cards/{card_id}", "delete"),
        ("/api/v1/private/cards/{card_id}/purge", "post"),
        ("/api/v1/private/cards/{card_id}/reveal-authorize", "post"),
    ],
)
def test_protected_routes_reject_wrong_origin_host_and_fetch_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    method: str,
) -> None:
    client, card_id = _setup(tmp_path, monkeypatch)
    rendered = path.format(card_id=card_id)
    if path.endswith("/edit"):
        hostile_body = {"passphrase": PASS, "changes": {"nickname": "Synthetic"}}
    elif path.endswith("/lifecycle"):
        hostile_body = {"passphrase": PASS, "lifecycle": "closed"}
    elif path.endswith("/replace"):
        hostile_body = {"passphrase": PASS, "offering_id": CARD, "lifecycle": "closed", "secret_fields": {"nickname": "Synthetic"}}
    elif path.endswith("/erase-cvv-pin"):
        hostile_body = {"passphrase": PASS}
    elif path.endswith("/reveal-authorize"):
        hostile_body = {"passphrase": PASS, "field": "pan"}
    else:
        hostile_body = {"passphrase": PASS, "confirmation": "DELETE CARD"}
    response = client.request(
        method.upper(),
        rendered,
        headers={"Origin": "http://127.0.0.1:8777", "Host": "evil.invalid"},
        json=hostile_body,
    )
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"
    response = client.request(
        method.upper(),
        rendered,
        headers={"Origin": "http://127.0.0.1:8777", "Sec-Fetch-Site": "cross-site"},
        json=hostile_body,
    )
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"


def test_origin_parser_rejects_lookalikes_but_accepts_configured_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _setup(tmp_path, monkeypatch)
    body = {"passphrase": PASS, "offering_id": CARD, "secret_fields": {"nickname": "Synthetic"}}
    for origin in (
        "http://127.0.0.1:8776",
        "http://127.0.0.1:8777.evil.invalid",
        "http://user@127.0.0.1:8777",
        "https://127.0.0.1:8777",
    ):
        response = client.post("/api/v1/private/cards/add", headers={"Origin": origin}, json=body)
        assert response.status_code == 403
        assert response.headers["cache-control"] == "no-store"


def test_replace_route_requires_and_uses_fresh_core_reauthentication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, card_id = _setup(tmp_path, monkeypatch)
    response = client.post(
        f"/api/v1/private/cards/{card_id}/replace",
        headers=_protected_headers(client),
        json={
            "passphrase": PASS,
            "offering_id": CARD,
            "lifecycle": "closed",
            "secret_fields": {"nickname": "Replacement"},
        },
    )
    assert response.status_code == 200
    assert response.json()["successor_card_id"]


def test_core_add_and_replace_reject_wrong_fresh_proof(
    tmp_path: Path,
) -> None:
    from mycard_benefits.vault import VaultAccessError

    store = VaultStore(tmp_path / "vault.json")
    session = store.create(PASS)
    with pytest.raises(VaultAccessError):
        session.add_card(CARD, {"nickname": "Synthetic"}, passphrase="wrong synthetic passphrase")
    card_id = session.add_card(CARD, {"nickname": "Synthetic"}, passphrase=PASS)
    with pytest.raises(VaultAccessError):
        session.replace_card(
            card_id,
            {"nickname": "Replacement"},
            passphrase="wrong synthetic passphrase",
        )


def test_wrong_auth_and_unknown_fields_are_redacted_and_uncached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _setup(tmp_path, monkeypatch)
    marker = "SYNTHETIC-ONLY-DO-NOT-ECHO"
    response = client.post(
        "/api/v1/private/cards/add",
        headers=_protected_headers(client),
        json={
            "passphrase": "wrong synthetic passphrase",
            "offering_id": CARD,
            "secret_fields": {},
            "unknown": marker,
        },
    )
    assert response.status_code == 422
    assert marker not in response.text
    assert response.headers["cache-control"] == "no-store"

    response = client.post(
        "/api/v1/private/cards/add",
        headers=_protected_headers(client),
        json={"passphrase": "wrong synthetic passphrase", "offering_id": CARD},
    )
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert "wrong synthetic passphrase" not in response.text


def test_expiry_signals_keyring_failure_is_classified_and_no_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mycard_benefits.vault import router

    monkeypatch.setattr(router, "load_keyring", lambda: (_ for _ in ()).throw(VaultError("marker")))
    settings = Settings(data_dir=tmp_path / "data", catalog_dir=tmp_path / "catalog", port=8777)
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/private/expiry-signals")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "keyring_unavailable"
    assert response.headers["cache-control"] == "no-store"
    assert "marker" not in response.text


def test_reveal_authorize_is_disabled_without_issuing_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, card_id = _setup(tmp_path, monkeypatch)
    response = client.post(
        f"/api/v1/private/cards/{card_id}/reveal-authorize",
        headers=_protected_headers(client),
        json={"passphrase": PASS, "field": "pan"},
    )
    assert response.status_code == 410
    assert response.json()["detail"] == "plaintext reveal is disabled"
    assert "action_authorized" not in response.text
    assert response.headers["cache-control"] == "no-store"
