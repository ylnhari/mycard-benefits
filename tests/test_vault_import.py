from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from mycard_benefits import vault_cli
from mycard_benefits.vault import CardLifecycle, VaultError, VaultStore
from mycard_benefits.vault.importer import load_manifest


class _FakeKeyring:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service_name: str, username: str) -> str | None:
        return self.values.get((service_name, username))

    def set_password(self, service_name: str, username: str, password: str) -> None:
        self.values[(service_name, username)] = password


def _write_manifest(path: Path, cards: list[dict[str, object]]) -> None:
    path.write_text(json.dumps({"schema_version": 1, "cards": cards}), encoding="utf-8")


def _args(data_dir: Path, manifest: Path, *, create: bool) -> argparse.Namespace:
    return argparse.Namespace(
        data_dir=data_dir,
        keyring=True,
        command="import",
        manifest=manifest,
        create=create,
    )


def test_load_manifest_is_strict_and_value_safe(tmp_path: Path) -> None:
    path = tmp_path / "cards.json"
    path.write_text('{"schema_version":1,"cards":[{"unexpected":"secret-marker"}]}')
    with pytest.raises(VaultError, match="card manifest is invalid") as failure:
        load_manifest(path)
    assert "secret-marker" not in str(failure.value)


def test_batch_add_is_atomic_when_later_card_is_invalid(tmp_path: Path) -> None:
    store = VaultStore(tmp_path / "vault.json")
    session = store.create("synthetic passphrase")
    with pytest.raises(VaultError):
        session.add_cards(
            [
                ("valid-offer", {"nickname": "SYNTHETIC-ONLY-valid"}, CardLifecycle.ACTIVE),
                ("bad-offer", {"unsupported": "SYNTHETIC-ONLY-secret"}, CardLifecycle.ACTIVE),
            ]
        )
    assert session.list_cards() == ()


def test_keyring_create_import_and_verify_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = tmp_path / "cards.json"
    _write_manifest(
        manifest_path,
        [
            {
                "offering_id": "synthetic-offer-one",
                "lifecycle": "active",
                "secret_fields": {"nickname": "SYNTHETIC-ONLY-one"},
            },
            {
                "offering_id": "synthetic-offer-two",
                "lifecycle": "archived",
                "secret_fields": {"nickname": "SYNTHETIC-ONLY-two"},
            },
        ],
    )
    fake_keyring = _FakeKeyring()
    monkeypatch.setattr(vault_cli, "_load_keyring", lambda: fake_keyring)
    assert vault_cli.run(_args(tmp_path, manifest_path, create=True)) == 2
    verify_args = argparse.Namespace(data_dir=tmp_path, keyring=True, command="verify")
    assert vault_cli.run(verify_args) == 2
    assert len(fake_keyring.values) == 1


def test_invalid_manifest_fails_before_keyring_or_vault_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = tmp_path / "cards.json"
    _write_manifest(
        manifest_path,
        [
            {
                "offering_id": "synthetic-offer",
                "lifecycle": "active",
                "secret_fields": {"unsupported": "SYNTHETIC-ONLY-value"},
            }
        ],
    )
    fake_keyring = _FakeKeyring()
    monkeypatch.setattr(vault_cli, "_load_keyring", lambda: fake_keyring)
    with pytest.raises(VaultError):
        vault_cli.run(_args(tmp_path, manifest_path, create=True))
    assert not (tmp_path / "private" / "vault.json").exists()
    assert fake_keyring.values == {}


def test_failed_keyring_write_removes_new_empty_vault_and_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = tmp_path / "cards.json"
    _write_manifest(manifest_path, [_card("synthetic-one")])

    class FailingKeyring(_FakeKeyring):
        def set_password(self, service_name: str, username: str, password: str) -> None:
            raise RuntimeError("synthetic keyring failure")

    monkeypatch.setattr(vault_cli, "_load_keyring", FailingKeyring)
    with pytest.raises(VaultError, match="keyring is unavailable"):
        vault_cli.run(_args(tmp_path, manifest_path, create=True))
    vault_path = tmp_path / "private" / "vault.json"
    assert not vault_path.exists()
    assert not vault_path.with_name("vault.json.lock").exists()


def test_existing_vault_accepts_an_additional_atomic_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    _write_manifest(first, [_card("synthetic-one")])
    _write_manifest(second, [_card("synthetic-two")])
    fake_keyring = _FakeKeyring()
    monkeypatch.setattr(vault_cli, "_load_keyring", lambda: fake_keyring)

    assert vault_cli.run(_args(tmp_path, first, create=True)) == 1
    assert vault_cli.run(_args(tmp_path, second, create=False)) == 2


def test_concurrent_keyring_create_keeps_the_winning_passphrase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = tmp_path / "cards.json"
    _write_manifest(manifest_path, [_card("synthetic-one")])
    fake_keyring = _FakeKeyring()
    monkeypatch.setattr(vault_cli, "_load_keyring", lambda: fake_keyring)

    def create() -> int | type[Exception]:
        try:
            return vault_cli.run(_args(tmp_path, manifest_path, create=True))
        except Exception as exc:
            return type(exc)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(lambda _: create(), range(2)))
    assert results.count(1) == 1
    assert len(fake_keyring.values) == 1
    verify_args = argparse.Namespace(data_dir=tmp_path, keyring=True, command="verify")
    assert vault_cli.run(verify_args) == 1


def test_keyring_is_retained_after_post_import_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = tmp_path / "cards.json"
    _write_manifest(manifest_path, [_card("synthetic-one")])
    fake_keyring = _FakeKeyring()
    monkeypatch.setattr(vault_cli, "_load_keyring", lambda: fake_keyring)

    class Session:
        def add_cards(self, cards: object) -> tuple[str, ...]:
            tuple(cards)  # type: ignore[arg-type]
            return ("synthetic-id",)

        def list_cards(self) -> tuple[dict[str, str], ...]:
            raise OSError("synthetic post-import failure")

        def lock(self) -> None:
            pass

    class Store:
        def __init__(self, path: Path) -> None:
            self.path = path

        def create(self, passphrase: str) -> Session:
            return Session()

        def open(self, passphrase: str) -> Session:
            raise AssertionError("not used")

    monkeypatch.setattr(vault_cli, "VaultStore", Store)
    with pytest.raises(OSError):
        vault_cli.run(_args(tmp_path, manifest_path, create=True))
    assert len(fake_keyring.values) == 1


def test_interactive_prompt_requires_tty_and_matching_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(vault_cli.sys.stdin, "isatty", lambda: False)
    with pytest.raises(VaultError, match="requires a terminal"):
        vault_cli._prompt_passphrase(confirm=False)

    monkeypatch.setattr(vault_cli.sys.stdin, "isatty", lambda: True)
    answers = iter(["synthetic passphrase", "different synthetic passphrase"])
    monkeypatch.setattr(vault_cli.getpass, "getpass", lambda _: next(answers))
    with pytest.raises(VaultError, match="passphrases do not match"):
        vault_cli._prompt_passphrase(confirm=True)


def test_manifest_rejects_bounds_and_plaintext_offering_ids(tmp_path: Path) -> None:
    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b"x" * (1024 * 1024 + 1))
    with pytest.raises(VaultError, match="too large"):
        load_manifest(oversized)

    too_many = tmp_path / "too-many.json"
    _write_manifest(too_many, [_card("synthetic-offer") for _ in range(1001)])
    with pytest.raises(VaultError, match="invalid"):
        load_manifest(too_many)

    unsafe_id = tmp_path / "unsafe-id.json"
    _write_manifest(unsafe_id, [_card("SYNTHETIC owner name")])
    with pytest.raises(VaultError, match="invalid"):
        load_manifest(unsafe_id)


def test_core_rejects_plaintext_in_offering_id(tmp_path: Path) -> None:
    session = VaultStore(tmp_path / "vault.json").create("synthetic passphrase")
    with pytest.raises(VaultError, match="offering_id is invalid"):
        session.add_card(
            "SYNTHETIC owner name",
            {"nickname": "SYNTHETIC-ONLY-card"},
        )


def test_committed_example_manifest_is_valid_and_synthetic() -> None:
    path = Path(__file__).parents[1] / "samples" / "card-import.example.json"
    manifest = load_manifest(path)
    assert len(manifest.cards) == 2
    assert all(
        value.startswith("SYNTHETIC-ONLY-")
        for card in manifest.cards
        for value in card.secret_fields.values()
    )


def _card(offering_id: str) -> dict[str, object]:
    return {
        "offering_id": offering_id,
        "lifecycle": "active",
        "secret_fields": {"nickname": "SYNTHETIC-ONLY-card"},
    }
