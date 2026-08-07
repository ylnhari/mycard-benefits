from __future__ import annotations

import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from mycard_benefits.vault import (
    CardLifecycle,
    ChildRecordKind,
    ChildRecordLifecycle,
    VaultAccessError,
    VaultError,
    VaultStore,
)
from mycard_benefits.vault import core as vault_core


class _TestPermissions:
    def secure_directory(self, path: Path) -> None:
        return None

    def secure_file(self, path: Path) -> None:
        return None


def _store(tmp_path: Path) -> VaultStore:
    return VaultStore(tmp_path / "private" / "vault.json", _permissions=_TestPermissions())


def test_round_trip_uses_encrypted_payload_and_stable_nonsensitive_metadata(tmp_path: Path) -> None:
    store = _store(tmp_path)
    session = store.create("synthetic passphrase")
    marker = "SYNTHETIC-SECRET-MARKER-ONLY"
    card_id = session.add_card("offering-test", {"pan": marker, "cvv": "999"})

    payload = store.path.read_text(encoding="utf-8")
    assert marker not in payload
    envelope = json.loads(payload)
    assert envelope["version"] == 2
    assert isinstance(envelope["mac"], str)
    assert envelope["records"][0]["card_id"] == card_id
    assert envelope["records"][0]["offering_id"] == "offering-test"
    assert "ciphertext" in envelope["records"][0]
    assert "pan" not in envelope["records"][0]

    reopened = store.open("synthetic passphrase")
    assert reopened.list_cards()[0]["card_id"] == card_id
    authorization = reopened.authorize_reveal(card_id, "pan", passphrase="synthetic passphrase")
    assert reopened.consume_reveal(authorization) == marker


def test_wrong_passphrase_and_tampered_or_corrupt_files_fail_closed(tmp_path: Path) -> None:
    store = _store(tmp_path)
    session = store.create("correct synthetic passphrase")
    session.add_card("offer", {"pan": "SYNTHETIC-ONLY-PAN-ALPHA"})
    with pytest.raises(VaultAccessError):
        store.open("wrong synthetic passphrase")

    raw = bytearray(store.path.read_bytes())
    raw[-5] ^= 1
    store.path.write_bytes(raw)
    with pytest.raises(VaultAccessError):
        store.open("correct synthetic passphrase")


@pytest.mark.parametrize(
    "field,replacement",
    [
        ("offering_id", "other-offering"),
        ("lifecycle", "lost"),
        ("created_at", "2026-08-05T00:00:00Z"),
        ("updated_at", "2026-08-07T00:00:00Z"),
        ("replacement_card_id", "01987d35-0000-7000-8000-000000000001"),
    ],
)
def test_all_unencrypted_record_metadata_is_authenticated(
    tmp_path: Path, field: str, replacement: str
) -> None:
    store = _store(tmp_path)
    session = store.create("synthetic passphrase")
    session.add_card("offer", {"pan": "SYNTHETIC-ONLY-PAN-ALPHA"})
    envelope = json.loads(store.path.read_text(encoding="utf-8"))
    envelope["records"][0][field] = replacement
    store.path.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(VaultAccessError):
        store.open("synthetic passphrase")


def test_hostile_kdf_file_size_and_record_count_fail_before_unlock(tmp_path: Path) -> None:
    store = _store(tmp_path)
    session = store.create("synthetic passphrase")
    session.add_card("offer", {"pan": "SYNTHETIC-ONLY-PAN-ALPHA"})
    envelope = json.loads(store.path.read_text(encoding="utf-8"))
    envelope["kdf"]["memory_cost_kib"] = 999_999_999
    store.path.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(VaultAccessError):
        store.open("synthetic passphrase")

    count_store = VaultStore(tmp_path / "private" / "count-vault.json", _permissions=_TestPermissions())
    session = count_store.create("other synthetic passphrase")
    session.add_card("offer", {"pan": "SYNTHETIC-ONLY-PAN-BRAVO"})
    envelope = json.loads(count_store.path.read_text(encoding="utf-8"))
    envelope["records"] *= 1_001
    count_store.path.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(VaultAccessError):
        count_store.open("other synthetic passphrase")

    store.path.write_bytes(b"x" * (5 * 1024 * 1024 + 1))
    with pytest.raises(VaultAccessError):
        store.open("synthetic passphrase")

    store.path.write_bytes(b"{")
    with pytest.raises(VaultAccessError):
        store.open("correct synthetic passphrase")


def test_replacement_lifecycle_and_exact_secret_field_allowlist(tmp_path: Path) -> None:
    session = _store(tmp_path).create("synthetic passphrase")
    old_id = session.add_card("offer", {"pan": "SYNTHETIC-ONLY-PAN-BRAVO"})
    replacement_id = session.replace_card(
        old_id,
        {"pan": "SYNTHETIC-ONLY-PAN-CHARLIE"},
        lifecycle=CardLifecycle.LOST,
    )
    cards = {card["card_id"]: card for card in session.list_cards()}
    assert cards[old_id]["lifecycle"] == "lost"
    assert cards[old_id]["replacement_card_id"] == replacement_id
    assert cards[replacement_id]["lifecycle"] == "active"
    with pytest.raises(VaultError):
        session.replace_card(old_id, {"pan": "SYNTHETIC-ONLY-PAN-CHARLIE"})
    with pytest.raises(VaultError):
        session.replace_card(replacement_id, {"pan": "SYNTHETIC-ONLY-PAN-DELTA"}, lifecycle=CardLifecycle.ACTIVE)
    allowed = {
        "cardholder_name": "Synthetic Holder",
        "pan": "SYNTHETIC-ONLY-PAN-ECHO",
        "expiry_month": "12",
        "expiry_year": "2030",
        "cvv": "999",
        "pin": "9999",
        "nickname": "Synthetic",
        "notes": "Synthetic notes only",
        "billing_postcode": "000000",
    }
    assert session.add_card("offer", allowed)
    for forbidden in (
        "otp",
        "Bank-User Name",
        "one.time.password",
        "LOGIN_token",
        "session_cookie",
        "issuer_customer_id",
        "account_access",
    ):
        with pytest.raises(VaultError):
            session.add_card("offer", {forbidden: "synthetic"})


def test_secret_field_bounds_and_persisted_unknown_fields_fail_closed(tmp_path: Path) -> None:
    store = _store(tmp_path)
    session = store.create("synthetic passphrase")
    for values in (
        {"notes": "x" * (vault_core._MAX_SECRET_VALUE_CHARS + 1)},
        {"notes": "x" * vault_core._MAX_SECRET_VALUE_CHARS, "nickname": "y" * vault_core._MAX_SECRET_VALUE_CHARS, "cardholder_name": "z" * vault_core._MAX_SECRET_VALUE_CHARS, "pan": ("SYNTHETIC-ONLY-" + "p" * vault_core._MAX_SECRET_VALUE_CHARS)[:vault_core._MAX_SECRET_VALUE_CHARS], "cvv": "c"},
        {"notes": ""},
    ):
        with pytest.raises(VaultError):
            session.add_card("offer", values)

    card_id = session.add_card("offer", {"pan": "SYNTHETIC-ONLY-PAN-BRAVO"})
    record = session._records[card_id]
    values = session._decrypt_record(record)
    values["issuer_customer_id"] = "SYNTHETIC-ONLY"
    tampered = vault_core.replace(record, ciphertext=session._encrypt_record(record, values))
    envelope = vault_core._serialize_envelope(
        session._kdf,
        session._wrapped_dek,
        {card_id: tampered},
        {},
        session._dek or bytearray(),
    )
    store.path.write_bytes(vault_core._encode_envelope(envelope))
    with pytest.raises(VaultAccessError):
        store.open("synthetic passphrase")


def test_reveal_requires_reauthentication_is_one_use_and_session_bound(tmp_path: Path) -> None:
    store = _store(tmp_path)
    session = store.create("synthetic passphrase")
    card_id = session.add_card("offer", {"pin": "9999"})
    with pytest.raises(VaultAccessError):
        session.authorize_reveal(card_id, "pin", passphrase="wrong synthetic passphrase")
    reveal = session.authorize_reveal(card_id, "pin", passphrase="synthetic passphrase", ttl_seconds=1)
    assert session.consume_reveal(reveal) == "9999"
    with pytest.raises(VaultAccessError):
        session.consume_reveal(reveal)
    expired = session.authorize_reveal(card_id, "pin", passphrase="synthetic passphrase", ttl_seconds=0.01)
    time.sleep(0.02)
    with pytest.raises(VaultAccessError):
        session.consume_reveal(expired)

    locked_authorization = session.authorize_reveal(card_id, "pin", passphrase="synthetic passphrase")
    session.lock()
    assert session.locked
    with pytest.raises(VaultAccessError):
        session.list_cards()
    with pytest.raises(VaultAccessError):
        session.consume_reveal(locked_authorization)
    assert not store.open("synthetic passphrase").locked


def test_uuid7_ids_and_failed_write_leave_memory_and_disk_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = _store(tmp_path)
    session = store.create("synthetic passphrase")
    before_disk = store.path.read_bytes()
    with monkeypatch.context() as context:
        context.setattr(
            vault_core,
            "_atomic_write",
            lambda path, encoded, permissions, backup: (_ for _ in ()).throw(OSError("synthetic")),
        )
        with pytest.raises(OSError):
            session.add_card("offer", {"pan": "SYNTHETIC-ONLY-PAN-BRAVO"})
    assert session.list_cards() == ()
    assert store.path.read_bytes() == before_disk

    card_id = session.add_card("offer", {"pan": "SYNTHETIC-ONLY-PAN-BRAVO"})
    assert card_id[14] == "7"
    assert card_id[19] in {"8", "9", "a", "b"}


def test_stale_session_conflicts_without_overwriting_newer_disk_state(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = store.create("synthetic passphrase")
    stale = store.open("synthetic passphrase")
    first.add_card("offer", {"pan": "SYNTHETIC-ONLY-PAN-BRAVO"})
    current = store.path.read_bytes()
    with pytest.raises(vault_core.VaultConflictError):
        stale.add_card("offer", {"pan": "SYNTHETIC-ONLY-PAN-CHARLIE"})
    assert store.path.read_bytes() == current


def test_encrypted_backup_rotation_preserves_prior_envelopes(tmp_path: Path) -> None:
    store = _store(tmp_path)
    session = store.create("synthetic passphrase")
    session.add_card("offer", {"pan": "SYNTHETIC-ONLY-PAN-BRAVO"})
    first = store.path.read_bytes()
    session.add_card("offer", {"pan": "SYNTHETIC-ONLY-PAN-CHARLIE"})
    second = store.path.read_bytes()
    session.add_card("offer", {"pan": "SYNTHETIC-ONLY-PAN-DELTA"})
    assert store.path.with_name("vault.json.bak.1").read_bytes() == second
    assert store.path.with_name("vault.json.bak.2").read_bytes() == first


def test_lock_zeroes_owned_dek_buffer(tmp_path: Path) -> None:
    session = _store(tmp_path).create("synthetic passphrase")
    dek = session._dek
    assert dek is not None and any(dek)
    session.lock()
    assert not any(dek)


def test_same_session_concurrent_adds_do_not_lose_updates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _store(tmp_path).create("synthetic passphrase")
    original_persist = session._persist
    first_entered = threading.Event()
    release_first = threading.Event()
    call_count = 0
    count_lock = threading.Lock()

    def delayed_persist(
        cards: dict[str, vault_core._Record],
        child_records: dict[str, vault_core._ChildRecord],
    ) -> None:
        nonlocal call_count
        with count_lock:
            call_count += 1
            is_first = call_count == 1
        if is_first:
            first_entered.set()
            assert release_first.wait(timeout=2)
        original_persist(cards, child_records)

    monkeypatch.setattr(session, "_persist", delayed_persist)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(session.add_card, "offer", {"pan": "SYNTHETIC-ONLY-A"})
        assert first_entered.wait(timeout=2)
        second = executor.submit(session.add_card, "offer", {"pan": "SYNTHETIC-ONLY-B"})
        release_first.set()
        identifiers = {first.result(timeout=2), second.result(timeout=2)}

    assert len(identifiers) == 2
    assert {card["card_id"] for card in session.list_cards()} == identifiers


def test_reveal_authorization_is_consumed_once_across_threads(tmp_path: Path) -> None:
    session = _store(tmp_path).create("synthetic passphrase")
    card_id = session.add_card("offer", {"pin": "9999"})
    authorization = session.authorize_reveal(card_id, "pin", passphrase="synthetic passphrase")
    barrier = threading.Barrier(2)

    def consume() -> str | type[Exception]:
        barrier.wait()
        try:
            return session.consume_reveal(authorization)
        except VaultAccessError as exc:
            return type(exc)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: consume(), range(2)))

    assert sorted(str(result) for result in results) == ["9999", "<class 'mycard_benefits.vault.core.VaultAccessError'>"]


def test_oversized_external_vault_conflicts_without_loading_it(tmp_path: Path) -> None:
    store = _store(tmp_path)
    session = store.create("synthetic passphrase")
    store.path.write_bytes(b"x" * (vault_core._MAX_VAULT_BYTES + 1))

    with pytest.raises(vault_core.VaultConflictError):
        session.add_card("offer", {"pan": "SYNTHETIC-ONLY-PAN"})


def test_oversized_backup_source_preserves_existing_backups(tmp_path: Path) -> None:
    source = tmp_path / "vault.json"
    source.write_bytes(b"x" * (vault_core._MAX_VAULT_BYTES + 1))
    first_backup = vault_core._backup_path(source, 1)
    second_backup = vault_core._backup_path(source, 2)
    first_backup.write_bytes(b"first-backup")
    second_backup.write_bytes(b"second-backup")

    with pytest.raises(VaultError):
        vault_core._rotate_backups(source, _TestPermissions())

    assert first_backup.read_bytes() == b"first-backup"
    assert second_backup.read_bytes() == b"second-backup"
    assert not list(tmp_path.glob(".vault.json.*.backup.tmp"))


def test_posix_nonblocking_lock_retries_and_normalizes_contention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []
    clock_values = iter((0.0, 0.0, 5.0))
    fake_fcntl = SimpleNamespace(LOCK_EX=2, LOCK_NB=4, LOCK_UN=8)

    def fail_lock(fd: int, flags: int) -> None:
        calls.append(flags)
        raise OSError("busy")

    fake_fcntl.flock = fail_lock
    monkeypatch.setattr(vault_core.os, "name", "posix")
    monkeypatch.setitem(sys.modules, "fcntl", fake_fcntl)
    monkeypatch.setattr(vault_core.time, "monotonic", lambda: next(clock_values))
    monkeypatch.setattr(vault_core.time, "sleep", lambda _: None)

    with pytest.raises(vault_core.VaultConflictError):
        vault_core._lock_file(SimpleNamespace(fileno=lambda: 7))

    assert calls == [fake_fcntl.LOCK_EX | fake_fcntl.LOCK_NB] * 2


def test_windows_lock_and_unlock_target_the_same_first_byte(monkeypatch: pytest.MonkeyPatch) -> None:
    positions: list[int] = []

    class Handle:
        def __init__(self) -> None:
            self.position = 0

        def seek(self, offset: int, whence: int = 0) -> int:
            self.position = 0 if whence == 2 else offset
            return self.position

        def write(self, value: bytes) -> None:
            return None

        def flush(self) -> None:
            return None

        def fileno(self) -> int:
            return 9

    handle = Handle()
    fake_msvcrt = SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2)
    fake_msvcrt.locking = lambda fd, mode, size: positions.append(handle.position)
    monkeypatch.setattr(vault_core.os, "name", "nt")
    monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)

    vault_core._lock_file(handle)
    vault_core._unlock_file(handle)

    assert positions == [0, 0]


def test_backup_final_install_failure_restores_prior_generations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "vault.json"
    source.write_bytes(b"current")
    backups = {index: vault_core._backup_path(source, index) for index in range(1, 4)}
    backups[1].write_bytes(b"one")
    backups[2].write_bytes(b"two")
    backups[3].write_bytes(b"three")
    real_replace = vault_core.os.replace

    def fail_final_install(source_path: str | Path, target_path: str | Path) -> None:
        if Path(target_path) == backups[1] and Path(source_path).name.endswith(".backup.tmp"):
            raise OSError("synthetic install failure")
        real_replace(source_path, target_path)

    monkeypatch.setattr(vault_core.os, "replace", fail_final_install)

    with pytest.raises(OSError):
        vault_core._rotate_backups(source, _TestPermissions())

    assert {index: path.read_bytes() for index, path in backups.items()} == {
        1: b"one",
        2: b"two",
        3: b"three",
    }
    assert not list(tmp_path.glob(".*.rollback.tmp"))


def test_idle_and_absolute_session_expiry_lock_using_monotonic_time(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    idle = _store(tmp_path / "idle").create("synthetic passphrase")
    idle._idle_timeout_seconds = 1
    idle._last_activity = 10.0
    idle._expires_at = 100.0
    monkeypatch.setattr(vault_core.time, "monotonic", lambda: 11.1)
    assert idle.locked

    absolute = _store(tmp_path / "absolute").create("synthetic passphrase")
    absolute._idle_timeout_seconds = 100.0
    absolute._last_activity = 10.0
    absolute._expires_at = 11.0
    monkeypatch.setattr(vault_core.time, "monotonic", lambda: 11.1)
    assert absolute.locked


def test_reveal_rejects_missing_or_noncanonical_fields_without_minting(tmp_path: Path) -> None:
    session = _store(tmp_path).create("synthetic passphrase")
    card_id = session.add_card("offer", {"pan": "SYNTHETIC-ONLY-PAN-BRAVO"})

    for field in ("cvv", "issuer_customer_id"):
        with pytest.raises(VaultAccessError):
            session.authorize_reveal(card_id, field, passphrase="synthetic passphrase")
    assert session._reveal_authorizations == {}


def test_reveal_ttl_and_locked_operations_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _store(tmp_path).create("synthetic passphrase")
    card_id = session.add_card("offer", {"pin": "9999"})
    clock = [10.0]
    monkeypatch.setattr(vault_core.time, "monotonic", lambda: clock[0])
    authorization = session.authorize_reveal(card_id, "pin", passphrase="synthetic passphrase", ttl_seconds=1)
    clock[0] = 11.1
    with pytest.raises(VaultAccessError):
        session.consume_reveal(authorization)

    session.lock()
    with pytest.raises(VaultAccessError):
        session.add_card("offer", {"pan": "SYNTHETIC-ONLY-PAN"})
    with pytest.raises(VaultAccessError):
        session.replace_card(card_id, {"pan": "SYNTHETIC-ONLY-PAN"})
    with pytest.raises(VaultAccessError):
        session.authorize_reveal(card_id, "pin", passphrase="synthetic passphrase")


@pytest.mark.parametrize(
    "field,value",
    [
        ("time_cost", 1),
        ("time_cost", 6),
        ("memory_cost_kib", 131_073),
        ("parallelism", 3),
        ("salt", "AA=="),
    ],
)
def test_kdf_bounds_fail_closed(tmp_path: Path, field: str, value: object) -> None:
    store = _store(tmp_path)
    store.create("synthetic passphrase")
    envelope = json.loads(store.path.read_text(encoding="utf-8"))
    envelope["kdf"][field] = value
    store.path.write_text(json.dumps(envelope), encoding="utf-8")

    with pytest.raises(VaultAccessError):
        store.open("synthetic passphrase")


def test_unwrapped_dek_must_be_256_bits() -> None:
    kdf = vault_core._KdfParameters(
        salt=b"SYNTHETIC-SALT!!",
        time_cost=2,
        memory_cost_kib=32_768,
        parallelism=1,
    )
    kek = bytearray(vault_core._derive_kek("synthetic passphrase", kdf))
    nonce = b"SYNTH-NONCE!"
    try:
        wrapped = vault_core.AESGCM(kek).encrypt(
            nonce,
            b"SYNTHETIC-16BYTE",
            vault_core._DEK_AAD,
        )
    finally:
        vault_core._zero(kek)

    with pytest.raises(VaultAccessError, match="unable to unlock vault"):
        vault_core._unwrap_dek(
            {"wrapped_dek": vault_core._b64(nonce + wrapped)},
            kdf,
            "synthetic passphrase",
        )


def test_record_aad_rejects_metadata_tampering_after_mac_recomputation(tmp_path: Path) -> None:
    store = _store(tmp_path)
    session = store.create("synthetic passphrase")
    session.add_card("offer", {"pan": "SYNTHETIC-ONLY-PAN-BRAVO"})
    envelope = json.loads(store.path.read_text(encoding="utf-8"))
    envelope["records"][0]["offering_id"] = "different-offer"
    dek = session._dek
    assert dek is not None
    envelope["mac"] = vault_core._envelope_mac(envelope, dek)
    store.path.write_bytes(vault_core._encode_envelope(envelope))

    with pytest.raises(VaultAccessError):
        store.open("synthetic passphrase")


def test_envelope_key_reordering_remains_valid_under_canonical_mac(tmp_path: Path) -> None:
    store = _store(tmp_path)
    session = store.create("synthetic passphrase")
    card_id = session.add_card("offer", {"pan": "SYNTHETIC-ONLY-PAN-BRAVO"})
    envelope = json.loads(store.path.read_text(encoding="utf-8"))
    reordered = {key: envelope[key] for key in reversed(tuple(envelope))}
    store.path.write_text(json.dumps(reordered, separators=(",", ":")), encoding="utf-8")

    assert store.open("synthetic passphrase").list_cards()[0]["card_id"] == card_id


def test_replacement_chain_tampering_fails_after_mac_recomputation(tmp_path: Path) -> None:
    store = _store(tmp_path)
    session = store.create("synthetic passphrase")
    old_id = session.add_card("offer", {"pan": "SYNTHETIC-ONLY-PAN-BRAVO"})
    new_id = session.replace_card(
        old_id,
        {"pan": "SYNTHETIC-ONLY-PAN-CHARLIE"},
        lifecycle=CardLifecycle.LOST,
    )
    old = session._records[old_id]
    successor = session._records[new_id]
    bad_successor = vault_core.replace(successor, offering_id="different-offer", ciphertext=b"")
    bad_successor = vault_core.replace(
        bad_successor,
        ciphertext=session._encrypt_record(bad_successor, session._decrypt_record(successor)),
    )
    dek = session._dek
    assert dek is not None
    envelope = vault_core._serialize_envelope(
        session._kdf,
        session._wrapped_dek,
        {old_id: old, new_id: bad_successor},
        {},
        dek,
    )
    store.path.write_bytes(vault_core._encode_envelope(envelope))

    with pytest.raises(VaultAccessError):
        store.open("synthetic passphrase")


def test_permission_failure_is_fail_closed(tmp_path: Path) -> None:
    class BrokenPermissions:
        def secure_directory(self, path: Path) -> None:
            raise vault_core.VaultPermissionError("unavailable")

        def secure_file(self, path: Path) -> None:
            raise vault_core.VaultPermissionError("unavailable")

    store = VaultStore(tmp_path / "private" / "vault.json", _permissions=BrokenPermissions())
    with pytest.raises(vault_core.VaultPermissionError):
        store.create("synthetic passphrase")


@pytest.mark.skipif(vault_core.os.name != "nt", reason="Windows ACL only")
def test_windows_acl_descriptor_is_protected_and_single_current_user_ace(tmp_path: Path) -> None:
    import ntsecuritycon
    import win32api
    import win32con
    import win32security

    target = tmp_path / "acl.bin"
    target.write_bytes(b"x")
    vault_core._PlatformPermissions().secure_file(target)
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    finally:
        token.Close()
    descriptor = win32security.GetFileSecurity(str(target), win32security.DACL_SECURITY_INFORMATION)
    control, _ = descriptor.GetSecurityDescriptorControl()
    dacl = descriptor.GetSecurityDescriptorDacl()
    assert control & win32security.SE_DACL_PROTECTED
    assert dacl is not None and dacl.GetAceCount() == 1
    header, mask, ace_sid = dacl.GetAce(0)
    assert header == (win32security.ACCESS_ALLOWED_ACE_TYPE, 0)
    assert mask == ntsecuritycon.FILE_ALL_ACCESS
    assert ace_sid == sid


@pytest.mark.skipif(vault_core.os.name != "nt", reason="Windows ACL only")
def test_windows_acl_api_error_is_normalized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import pywintypes
    import win32security

    target = tmp_path / "acl-error.bin"
    target.write_bytes(b"x")
    monkeypatch.setattr(
        win32security,
        "SetFileSecurity",
        lambda path, info, descriptor: (_ for _ in ()).throw(pywintypes.error(5, "SetFileSecurity", "denied")),
    )
    with pytest.raises(vault_core.VaultPermissionError):
        vault_core._PlatformPermissions().secure_file(target)


def test_backup_permission_failure_cleans_partial_file(tmp_path: Path) -> None:
    class BackupFailure(_TestPermissions):
        def secure_file(self, path: Path) -> None:
            if path.name.endswith(".bak.1"):
                raise vault_core.VaultPermissionError("unavailable")

    store = VaultStore(tmp_path / "vault.json", _permissions=BackupFailure())
    session = store.create("synthetic passphrase")
    with pytest.raises(vault_core.VaultPermissionError):
        session.add_card("offer", {"pan": "SYNTHETIC-ONLY-PAN-BRAVO"})
    assert not store.path.with_name("vault.json.bak.1").exists()


def _two_record_envelope(tmp_path: Path) -> tuple[VaultStore, dict[str, object]]:
    store = _store(tmp_path)
    session = store.create("synthetic passphrase")
    session.add_card("offer", {"pan": "SYNTHETIC-ONLY-PAN-BRAVO"})
    session.add_card("offer", {"pan": "SYNTHETIC-ONLY-PAN-CHARLIE"})
    return store, json.loads(store.path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("change", ["delete", "reorder", "metadata"])
def test_v2_envelope_mac_rejects_record_collection_and_metadata_mutation(
    tmp_path: Path, change: str
) -> None:
    store, envelope = _two_record_envelope(tmp_path)
    records = envelope["records"]
    assert isinstance(records, list)
    if change == "delete":
        records.pop()
    elif change == "reorder":
        records.reverse()
    else:
        wrapped_dek = str(envelope["wrapped_dek"])
        replacement = "B" if wrapped_dek.startswith("A") else "A"
        envelope["wrapped_dek"] = replacement + wrapped_dek[1:]
    store.path.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(VaultAccessError):
        store.open("synthetic passphrase")


def test_v2_envelope_mac_rejects_cross_vault_record_splice(tmp_path: Path) -> None:
    first, first_envelope = _two_record_envelope(tmp_path / "one")
    second, second_envelope = _two_record_envelope(tmp_path / "two")
    first_records = first_envelope["records"]
    second_records = second_envelope["records"]
    assert isinstance(first_records, list) and isinstance(second_records, list)
    first_records[0] = second_records[0]
    first.path.write_text(json.dumps(first_envelope), encoding="utf-8")
    with pytest.raises(VaultAccessError):
        first.open("synthetic passphrase")


def test_v1_vault_is_rejected_fail_closed(tmp_path: Path) -> None:
    store = _store(tmp_path)
    session = store.create("synthetic passphrase")
    session.add_card("offer", {"pan": "SYNTHETIC-ONLY-PAN-BRAVO"})
    envelope = json.loads(store.path.read_text(encoding="utf-8"))
    envelope["version"] = 1
    envelope.pop("mac")
    store.path.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(VaultAccessError):
        store.open("synthetic passphrase")


def test_backup_intermediate_shift_failure_restores_primary_and_generations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "vault.json"
    source.write_bytes(b"primary")
    backups = {index: vault_core._backup_path(source, index) for index in range(1, 4)}
    backups[1].write_bytes(b"one")
    backups[2].write_bytes(b"two")
    backups[3].write_bytes(b"three")
    real_replace = vault_core.os.replace

    def fail_first_shift(source_path: str | Path, target_path: str | Path) -> None:
        if Path(target_path) == backups[2] and Path(source_path).name.endswith(".rollback.tmp"):
            raise OSError("synthetic shift failure")
        real_replace(source_path, target_path)

    monkeypatch.setattr(vault_core.os, "replace", fail_first_shift)

    with pytest.raises(OSError):
        vault_core._rotate_backups(source, _TestPermissions())

    assert source.read_bytes() == b"primary"
    assert {index: path.read_bytes() for index, path in backups.items()} == {
        1: b"one",
        2: b"two",
        3: b"three",
    }
    assert not list(tmp_path.glob(".*.rollback.tmp"))
    assert not list(tmp_path.glob(".*.recovery.tmp"))
    assert not list(tmp_path.glob(".*.backup.tmp"))


@pytest.mark.parametrize("invalid", ["", "short", 1234, "x" * 1_025])
def test_passphrase_validation_is_strict_and_open_reauth_fail_generically(
    tmp_path: Path,
    invalid: object,
) -> None:
    store = _store(tmp_path)
    with pytest.raises(VaultError):
        store.create(invalid)  # type: ignore[arg-type]

    session = store.create("synthetic passphrase")
    card_id = session.add_card("offer", {"pin": "9999"})
    with pytest.raises(VaultAccessError):
        store.open(invalid)  # type: ignore[arg-type]
    with pytest.raises(VaultAccessError):
        session.authorize_reveal(card_id, "pin", passphrase=invalid)  # type: ignore[arg-type]


def test_unicode_passphrase_is_validated_by_utf8_byte_length(tmp_path: Path) -> None:
    passphrase = "pässphrase12"
    store = _store(tmp_path)
    session = store.create(passphrase)

    assert not session.locked
    assert not store.open(passphrase).locked


def test_child_record_round_trip_is_non_secret_and_survives_reopen(tmp_path: Path) -> None:
    store = _store(tmp_path)
    session = store.create("synthetic passphrase")
    card_id = session.add_card("offer", {"pan": "SYNTHETIC-ONLY-PAN-BRAVO"})
    child_id = session.add_child_record(
        card_id,
        ChildRecordKind.PRIORITY_PASS,
        expiry_date="2027-01-01",
    )

    payload = store.path.read_text(encoding="utf-8")
    envelope = json.loads(payload)
    assert envelope["child_records"][0]["child_id"] == child_id
    assert envelope["child_records"][0]["parent_card_id"] == card_id
    assert envelope["child_records"][0]["kind"] == "priority_pass"
    assert envelope["child_records"][0]["expiry_date"] == "2027-01-01"
    assert "label" not in envelope["child_records"][0]

    reopened = store.open("synthetic passphrase")
    records = reopened.list_child_records()
    assert len(records) == 1
    assert records[0]["child_id"] == child_id
    assert "label" not in records[0]
    assert reopened.list_child_records(parent_card_id=card_id) == records
    assert reopened.list_child_records(parent_card_id="018f47f2-0f86-7b0a-bc7d-f00ba47c0099") == ()


def test_child_record_has_no_free_text_label_field(tmp_path: Path) -> None:
    """There is no way to pass arbitrary display text into a child record at all."""
    import inspect

    session = _store(tmp_path).create("synthetic passphrase")
    parameters = inspect.signature(session.add_child_record).parameters
    assert "label" not in parameters
    assert set(parameters) == {"parent_card_id", "kind", "lifecycle", "expiry_date"}


def test_child_record_requires_an_existing_parent_card(tmp_path: Path) -> None:
    session = _store(tmp_path).create("synthetic passphrase")
    with pytest.raises(VaultError):
        session.add_child_record(
            "018f47f2-0f86-7b0a-bc7d-f00ba47c0099",
            ChildRecordKind.VOUCHER,
        )


@pytest.mark.parametrize(
    "kind,lifecycle,expiry_date",
    [
        ("not-a-kind", ChildRecordLifecycle.ACTIVE, None),
        (ChildRecordKind.MEMBERSHIP, "not-a-lifecycle", None),
        (ChildRecordKind.MEMBERSHIP, ChildRecordLifecycle.ACTIVE, "not-a-date"),
        (ChildRecordKind.MEMBERSHIP, ChildRecordLifecycle.ACTIVE, "2027-13-40"),
    ],
)
def test_child_record_invalid_kind_lifecycle_or_date_fail_closed(
    tmp_path: Path,
    kind: object,
    lifecycle: object,
    expiry_date: str | None,
) -> None:
    session = _store(tmp_path).create("synthetic passphrase")
    card_id = session.add_card("offer", {"pan": "SYNTHETIC-ONLY-PAN-BRAVO"})
    with pytest.raises(VaultError):
        session.add_child_record(
            card_id,
            kind,  # type: ignore[arg-type]
            lifecycle=lifecycle,  # type: ignore[arg-type]
            expiry_date=expiry_date,
        )
    assert session.list_child_records() == ()


@pytest.mark.parametrize(
    "field,replacement",
    [
        ("parent_card_id", "018f47f2-0f86-7b0a-bc7d-f00ba47c0099"),
        ("kind", "membership"),
        ("lifecycle", "expired"),
        ("created_at", "2020-01-01T00:00:00Z"),
        ("updated_at", "2020-01-01T00:00:00Z"),
    ],
)
def test_all_child_record_metadata_is_authenticated_by_the_envelope_mac(
    tmp_path: Path, field: str, replacement: str
) -> None:
    store = _store(tmp_path)
    session = store.create("synthetic passphrase")
    card_id = session.add_card("offer", {"pan": "SYNTHETIC-ONLY-PAN-BRAVO"})
    session.add_child_record(card_id, ChildRecordKind.LOUNGE_CREDENTIAL)
    envelope = json.loads(store.path.read_text(encoding="utf-8"))
    envelope["child_records"][0][field] = replacement
    store.path.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(VaultAccessError):
        store.open("synthetic passphrase")


def test_child_record_dangling_or_unknown_kind_persisted_externally_fails_closed(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    session = store.create("synthetic passphrase")
    card_id = session.add_card("offer", {"pan": "SYNTHETIC-ONLY-PAN-BRAVO"})
    session.add_child_record(card_id, ChildRecordKind.VOUCHER)

    envelope = json.loads(store.path.read_text(encoding="utf-8"))
    envelope["child_records"][0]["parent_card_id"] = "018f47f2-0f86-7b0a-bc7d-f00ba47c0099"
    store.path.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(VaultAccessError):
        store.open("synthetic passphrase")

    envelope = json.loads(store.path.read_text(encoding="utf-8"))
    envelope["child_records"][0]["kind"] = "not-a-real-kind"
    store.path.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(VaultAccessError):
        store.open("synthetic passphrase")


def test_vault_without_a_child_records_key_opens_with_none_and_upgrades_on_next_write(
    tmp_path: Path,
) -> None:
    """A vault written before this feature existed must still open cleanly."""
    store = _store(tmp_path)
    session = store.create("synthetic passphrase")
    card_id = session.add_card("offer", {"pan": "SYNTHETIC-ONLY-PAN-BRAVO"})

    envelope = json.loads(store.path.read_text(encoding="utf-8"))
    del envelope["child_records"]
    dek = vault_core._unwrap_dek(envelope, vault_core._parse_kdf(envelope), "synthetic passphrase")
    envelope["mac"] = vault_core._envelope_mac(envelope, dek)
    store.path.write_text(json.dumps(envelope), encoding="utf-8")

    reopened = store.open("synthetic passphrase")
    assert reopened.list_child_records() == ()
    assert reopened.list_cards()[0]["card_id"] == card_id

    reopened.add_child_record(card_id, ChildRecordKind.MEMBERSHIP)
    upgraded = json.loads(store.path.read_text(encoding="utf-8"))
    assert len(upgraded["child_records"]) == 1


def test_child_record_count_is_bounded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session = _store(tmp_path).create("synthetic passphrase")
    card_id = session.add_card("offer", {"pan": "SYNTHETIC-ONLY-PAN-BRAVO"})
    monkeypatch.setattr(vault_core, "_MAX_CHILD_RECORDS", 1)
    session.add_child_record(card_id, ChildRecordKind.VOUCHER)
    with pytest.raises(VaultError):
        session.add_child_record(card_id, ChildRecordKind.VOUCHER)
