from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mycard_benefits import data_location
from mycard_benefits.app import create_app
from mycard_benefits.config import Settings
from mycard_benefits.vault.core import VaultError, VaultStore
from mycard_benefits.vault.keyring_store import keyring_account
from mycard_benefits.vault.router import _read_keyring_cards

PASS = "SYNTHETIC-ONLY-correction-passphrase"
ORIGIN = "http://127.0.0.1:8777"


def _headers(token: str) -> dict[str, str]:
    return {
        "Origin": ORIGIN,
        "Host": "127.0.0.1:8777",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "X-CSRF-Token": token,
    }


def _make_junction(link: Path, target: Path) -> None:
    if os.name != "nt":
        pytest.skip("Windows junctions are unavailable on this platform")
    target.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("Windows junction facility is unavailable in this environment")


def _make_directory_symlink(link: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("directory symlinks are unavailable in this environment")


def _make_file_symlink(link: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("SYNTHETIC-ONLY-target", encoding="utf-8")
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("file symlinks are unavailable in this environment")


def _directory_reparse(link: Path, target: Path) -> None:
    if os.name == "nt":
        _make_junction(link, target)
    else:
        _make_directory_symlink(link, target)


def _file_reparse(link: Path, target: Path) -> None:
    if os.name == "nt":
        _make_junction(link, target)
        return
    _make_file_symlink(link, target)


def _remembered_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    import mycard_benefits.config as config

    root = tmp_path / "synthetic-application-data"
    monkeypatch.setattr(config, "user_data_root", lambda: root)
    return root


@pytest.mark.parametrize("hostile_part", ["selected", "private", "vault"])
def test_load_remembered_location_rejects_reparse_components(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hostile_part: str
) -> None:
    import mycard_benefits.config as config

    app_root = _remembered_root(tmp_path, monkeypatch)
    selected = tmp_path / "selected-data"
    selected.mkdir()
    app_root.mkdir()
    pointer = app_root / "selected-data-location.json"
    pointer.write_text(
        '{"data_dir": "' + str(selected) + '", "version": 1}', encoding="utf-8"
    )
    outside = tmp_path / "outside"
    if hostile_part == "selected":
        selected_link = tmp_path / "selected-link"
        _directory_reparse(selected_link, outside)
        pointer.write_text(
            '{"data_dir": "' + str(selected_link) + '", "version": 1}', encoding="utf-8"
        )
    elif hostile_part == "private":
        _directory_reparse(selected / "private", outside)
    else:
        (selected / "private").mkdir()
        _file_reparse(selected / "private" / "vault.json", outside / "vault.json")

    assert config.load_remembered_data_dir() is None
    assert not (outside / "vault.json").is_file()


def test_load_remembered_location_rejects_hostile_pointer_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mycard_benefits.config as config

    app_root = _remembered_root(tmp_path, monkeypatch)
    app_root.mkdir()
    _file_reparse(
        app_root / "selected-data-location.json", tmp_path / "outside-pointer.json"
    )
    assert config.load_remembered_data_dir() is None


def test_remembered_write_rejects_reparse_selected_root(tmp_path: Path) -> None:
    import mycard_benefits.config as config

    selected_link = tmp_path / "selected-link"
    _directory_reparse(selected_link, tmp_path / "outside")
    with pytest.raises(data_location.DataLocationError):
        config.remember_data_dir(selected_link)


def test_remembered_write_rejects_swap_before_pointer_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mycard_benefits.config as config

    app_root = _remembered_root(tmp_path, monkeypatch)
    destination = app_root / "selected-data-location.json"
    link_target = tmp_path / "outside-pointer.json"

    def swap(phase: str, path: Path) -> None:
        if phase == "before-pointer-replace":
            app_root.mkdir(parents=True, exist_ok=True)
            _file_reparse(destination, link_target)

    monkeypatch.setattr(data_location, "data_location_checkpoint", swap)
    with pytest.raises(data_location.DataLocationError):
        config.remember_data_dir(tmp_path / "selected-data")
    assert not link_target.is_file()


def test_settings_and_router_reject_hostile_data_root_before_use(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mycard_benefits.config as config

    hostile = tmp_path / "hostile"
    _directory_reparse(hostile, tmp_path / "outside")
    monkeypatch.setattr(config, "resolve_port", lambda *args, **kwargs: 8777)
    with pytest.raises(data_location.DataLocationError):
        Settings.from_environment(explicit_data_dir=hostile)
    with pytest.raises(data_location.DataLocationError):
        create_app(
            Settings(
                data_dir=hostile,
                catalog_dir=tmp_path,
                port=8777,
            )
        )


def test_keyring_account_and_automatic_reader_reject_hostile_vault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mycard_benefits.vault.router as router

    hostile = tmp_path / "hostile-vault.json"
    _file_reparse(hostile, tmp_path / "outside-vault")
    with pytest.raises(VaultError):
        keyring_account(hostile)
    monkeypatch.setattr(router, "load_keyring", lambda: object())
    with pytest.raises(router.VaultUnavailable) as error:
        _read_keyring_cards(hostile)
    assert error.value.code == "generic"


def test_automatic_reader_distinguishes_safe_fresh_install_from_hostile_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mycard_benefits.vault.router as router

    class StubKeyring:
        def get_password(self, service_name: str, username: str) -> str | None:
            return None

    monkeypatch.setattr(router, "load_keyring", lambda: StubKeyring())
    fresh_vault = tmp_path / "fresh-install" / "private" / "vault.json"
    assert _read_keyring_cards(fresh_vault) == ()
    assert fresh_vault.is_file()
    assert fresh_vault.with_name("device-key").is_file()

    hostile_root = tmp_path / "hostile-root"
    _directory_reparse(hostile_root, tmp_path / "outside")
    with pytest.raises(router.VaultUnavailable) as hostile_error:
        _read_keyring_cards(hostile_root / "private" / "vault.json")
    assert hostile_error.value.code == "generic"


def test_setup_fails_closed_when_private_directory_swaps_before_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "selected-data"
    outside = tmp_path / "outside"
    swapped = False

    def swap(phase: str, path: Path) -> None:
        nonlocal swapped
        if phase == "before-vault-create" and not swapped:
            swapped = True
            _directory_reparse(data_dir / "private", outside)

    monkeypatch.setattr(data_location, "data_location_checkpoint", swap)
    with TestClient(
        create_app(
            Settings(
                data_dir=data_dir,
                catalog_dir=tmp_path,
                port=8777,
            )
        )
    ) as client:
        bootstrap = client.get("/api/v1/private/unlock/bootstrap", headers=_headers("unused"))
        response = client.post(
            "/api/v1/private/setup",
            headers={**_headers(bootstrap.json()["csrf_token"]), "Content-Type": "application/json"},
            json={"passphrase": PASS, "remember": False},
        )
    assert response.status_code == 503
    assert not (outside / "vault.json").exists()


def test_unlock_fails_closed_when_vault_directory_swaps_before_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "selected-data"
    vault = data_dir / "private" / "vault.json"
    session = VaultStore(vault).create(PASS)
    session.lock()
    outside = tmp_path / "outside"
    swapped = False

    def swap(phase: str, path: Path) -> None:
        nonlocal swapped
        if phase == "before-vault-open" and not swapped:
            swapped = True
            shutil.rmtree(data_dir / "private")
            _directory_reparse(data_dir / "private", outside)

    monkeypatch.setattr(data_location, "data_location_checkpoint", swap)
    with TestClient(
        create_app(
            Settings(
                data_dir=data_dir,
                catalog_dir=tmp_path,
                port=8777,
            )
        )
    ) as client:
        bootstrap = client.get("/api/v1/private/unlock/bootstrap", headers=_headers("unused"))
        response = client.post(
            "/api/v1/private/unlock",
            headers={**_headers(bootstrap.json()["csrf_token"]), "Content-Type": "application/json"},
            json={"passphrase": PASS, "remember": False},
        )
    assert response.status_code == 401
    assert not (outside / "vault.json").exists()
