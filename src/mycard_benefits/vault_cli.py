"""Private vault maintenance commands; decrypted values are never printed."""

from __future__ import annotations

import argparse
import contextlib
import getpass
import secrets
import sys
from pathlib import Path

from .config import Settings
from .vault import VaultError, VaultStore
from .vault.importer import load_manifest
from .vault.keyring_store import (
    Keyring,
    get_keyring_password,
    keyring_account,
    load_keyring,
    set_keyring_password,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MyCard Benefits private vault maintenance")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="app-owned data root; its private child receives restrictive permissions",
    )
    parser.add_argument("--keyring", action="store_true", help="use the operating-system keyring")
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser("import", help="import a validated private manifest")
    import_parser.add_argument("--manifest", type=Path, required=True)
    import_parser.add_argument("--create", action="store_true")

    subparsers.add_parser("verify", help="verify the vault and report only its record count")
    return parser


def main() -> None:
    try:
        count = run(build_parser().parse_args())
    except VaultError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
    except Exception:
        print("Vault operation failed.", file=sys.stderr)
        raise SystemExit(1) from None
    print(f"Vault operation completed. Card count: {count}.")


def run(args: argparse.Namespace) -> int:
    data_dir = Settings.from_environment(explicit_data_dir=args.data_dir).data_dir
    vault_path = (data_dir / "private" / "vault.json").resolve()
    store = VaultStore(vault_path)
    creating = bool(getattr(args, "create", False))
    if creating == vault_path.exists():
        expected = "not exist" if creating else "exist"
        raise VaultError(f"vault must {expected} for this operation")
    manifest = load_manifest(args.manifest.resolve()) if args.command == "import" else None

    keyring: Keyring | None = _load_keyring() if args.keyring else None
    account = _keyring_account(vault_path)
    if keyring is not None:
        passphrase = _get_keyring_password(keyring, account)
        if creating:
            if passphrase is not None:
                raise VaultError("a keyring entry already exists for this vault")
            passphrase = secrets.token_urlsafe(32)
        elif passphrase is None:
            raise VaultError("no keyring entry exists for this vault")
    else:
        passphrase = _prompt_passphrase(confirm=creating)

    session = store.create(passphrase) if creating else store.open(passphrase)
    if creating and keyring is not None:
        try:
            _set_keyring_password(keyring, account, passphrase)
        except BaseException:
            session.lock()
            with contextlib.suppress(OSError):
                vault_path.unlink(missing_ok=True)
                vault_path.with_name(f"{vault_path.name}.lock").unlink(missing_ok=True)
            raise
    try:
        if manifest is not None:
            session.add_cards(
                (card.offering_id, card.secret_fields, card.lifecycle)
                for card in manifest.cards
            )
        return len(session.list_cards())
    finally:
        session.lock()


def _prompt_passphrase(*, confirm: bool) -> str:
    if not sys.stdin.isatty():
        raise VaultError("interactive passphrase input requires a terminal")
    passphrase = getpass.getpass("Vault passphrase: ")
    if confirm and passphrase != getpass.getpass("Confirm vault passphrase: "):
        raise VaultError("passphrases do not match")
    return passphrase


def _load_keyring() -> Keyring:
    return load_keyring()


def _keyring_account(vault_path: Path) -> str:
    return keyring_account(vault_path)


def _get_keyring_password(keyring: Keyring, account: str) -> str | None:
    return get_keyring_password(keyring, account)


def _set_keyring_password(keyring: Keyring, account: str, passphrase: str) -> None:
    set_keyring_password(keyring, account, passphrase)


if __name__ == "__main__":
    main()
