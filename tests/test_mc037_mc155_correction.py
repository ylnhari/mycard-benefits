import json
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from mycard_benefits.vault import AuditLog, ProtectedError, VaultStore
from mycard_benefits.vault import migration as vault_migration

PASS = "SYNTHETIC-ONLY-passphrase"


def _events(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _migration_inputs(tmp_path: Path) -> tuple[Path, Path]:
    database = tmp_path / "private.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE synthetic_seed (value TEXT NOT NULL)")
        connection.execute("INSERT INTO synthetic_seed VALUES ('SYNTHETIC-ONLY-seed')")
    vault = tmp_path / "vault.json"
    VaultStore(vault).create(PASS).lock()
    return database, vault


def _tables(database: Path) -> set[str]:
    with sqlite3.connect(database) as connection:
        return {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }


def _journal_path(database: Path) -> Path:
    return database.with_name(f"{database.name}.migration-journal.json")


def _instance_anchor_path(storage: Path) -> Path:
    return storage.with_name(f"{storage.name}.migration-instance.json")


def _crash_child(database: Path, vault: Path, checkpoint: str) -> subprocess.CompletedProcess[str]:
    script = """
import os
import sys
from pathlib import Path

from mycard_benefits.vault import AuditLog
from mycard_benefits.vault import migration

crash_at = sys.argv[3]

def checkpoint(name: str) -> None:
    if name == crash_at:
        os._exit(73)

migration._migration_checkpoint = checkpoint
migration.run_safe_upgrade(
    Path(sys.argv[1]),
    Path(sys.argv[2]),
    "SYNTHETIC-ONLY-passphrase",
    audit_log=AuditLog(Path(sys.argv[2]).with_name("audit.jsonl")),
)
"""
    source_root = str(Path(__file__).parents[1] / "src")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        item for item in (source_root, environment.get("PYTHONPATH")) if item
    )
    return subprocess.run(
        [sys.executable, "-c", script, str(database), str(vault), checkpoint],
        capture_output=True,
        check=False,
        text=True,
        timeout=120,
        env=environment,
    )


def test_audit_reference_is_opaque_and_retention_normalizes_legacy_events(
    tmp_path: Path,
) -> None:
    path = tmp_path / "audit.jsonl"
    audit = AuditLog(path, retention_days=1)
    audit.record("edit", record_ref="SYNTHETIC-ONLY-card-reference")
    audit.record("copy")

    old_event = {
        "event_id": "00000000-0000-4000-8000-000000000001",
        "occurred_at": (datetime.now(UTC) - timedelta(days=2)).isoformat(),
        "action": "delete",
        "success": True,
        "raw_request": "SYNTHETIC-ONLY-private-request",
    }
    with path.open("ab") as handle:
        handle.write(json.dumps(old_event).encode("utf-8") + b"\n")

    assert audit.purge(authorizer=lambda: True) == 1
    events = _events(path)
    assert [event["action"] for event in events] == ["edit", "copy", "purge"]
    assert all(
        set(event) == {"event_id", "occurred_at", "action", "record_ref", "success"}
        for event in events
    )
    assert all(
        isinstance(event["record_ref"], str)
        and len(event["record_ref"]) == 64
        and event["record_ref"] == event["record_ref"].lower()
        and all(character in "0123456789abcdef" for character in event["record_ref"])
        for event in events
    )
    assert "SYNTHETIC-ONLY-card-reference" not in path.read_text(encoding="utf-8")
    assert "SYNTHETIC-ONLY-private-request" not in path.read_text(encoding="utf-8")

    with pytest.raises(ProtectedError, match="audit record reference is invalid"):
        audit.record("edit", record_ref="x" * 257)


class _FailingMigrationAudit:
    def __init__(self) -> None:
        self.calls: list[tuple[object, str | None, str | None]] = []

    def record(
        self,
        action: object,
        *,
        record_ref: str | None = None,
        event_id: str | None = None,
        success: bool = True,
    ) -> str:
        self.calls.append((action, record_ref, event_id))
        raise ProtectedError("SYNTHETIC-ONLY-audit-failure")


def test_migration_audit_failure_rolls_back_without_event(
    tmp_path: Path,
) -> None:
    database, vault = _migration_inputs(tmp_path)
    audit = _FailingMigrationAudit()

    with pytest.raises(ProtectedError, match="migration audit unavailable"):
        vault_migration.run_safe_upgrade(database, vault, PASS, audit_log=audit)

    action, record_ref, event_id = audit.calls[0]
    assert action == "migration"
    assert isinstance(record_ref, str) and record_ref.startswith("migration:")
    assert isinstance(event_id, str)
    assert _tables(database) == {"synthetic_seed"}
    assert _tables(database.with_name(f"{database.name}.lkg")) == {"synthetic_seed"}
    assert not _journal_path(database).exists()
    assert not vault.with_name("audit.jsonl").exists()
    database_anchor = _instance_anchor_path(database).read_bytes()
    vault_anchor = _instance_anchor_path(vault).read_bytes()

    retry_audit = AuditLog(vault.with_name("audit.jsonl"))
    vault_migration.run_safe_upgrade(database, vault, PASS, audit_log=retry_audit)
    assert len(_events(vault.with_name("audit.jsonl"))) == 1
    assert _instance_anchor_path(database).read_bytes() == database_anchor
    assert _instance_anchor_path(vault).read_bytes() == vault_anchor

    # A replay after the successful retry is a no-op, not a duplicate event.
    vault_migration.run_safe_upgrade(database, vault, PASS, audit_log=retry_audit)
    assert len(_events(vault.with_name("audit.jsonl"))) == 1


def test_subprocess_crash_after_instance_anchors_restarts_same_storage(
    tmp_path: Path,
) -> None:
    database, vault = _migration_inputs(tmp_path)
    result = _crash_child(database, vault, "after-instance-anchors")
    assert result.returncode == 73, result.stderr

    database_anchor = _instance_anchor_path(database)
    vault_anchor = _instance_anchor_path(vault)
    assert database_anchor.is_file()
    assert vault_anchor.is_file()
    for anchor_path in (database_anchor, vault_anchor):
        payload = json.loads(anchor_path.read_text(encoding="utf-8"))
        assert set(payload) == {"anchor", "version"}
        assert payload["version"] == 1
        assert isinstance(payload["anchor"], str)
        assert len(payload["anchor"]) == 64
        assert all(character in "0123456789abcdef" for character in payload["anchor"])
        assert len(anchor_path.read_bytes()) <= 512
        assert PASS not in anchor_path.read_text(encoding="utf-8")

    database_anchor_bytes = database_anchor.read_bytes()
    vault_anchor_bytes = vault_anchor.read_bytes()
    assert not _journal_path(database).exists()
    assert not vault.with_name("audit.jsonl").exists()
    assert _tables(database) == {"synthetic_seed"}

    audit = AuditLog(vault.with_name("audit.jsonl"))
    vault_migration.run_safe_upgrade(database, vault, PASS, audit_log=audit)
    assert len(_events(vault.with_name("audit.jsonl"))) == 1
    assert database_anchor.read_bytes() == database_anchor_bytes
    assert vault_anchor.read_bytes() == vault_anchor_bytes


def test_cross_storage_journal_replay_fails_closed_without_event(
    tmp_path: Path,
) -> None:
    root_a = tmp_path / "storage-a"
    root_b = tmp_path / "storage-b"
    root_a.mkdir()
    root_b.mkdir()
    database_a, vault_a = _migration_inputs(root_a)
    crashed_a = _crash_child(database_a, vault_a, "after-lkg-before-audit")
    assert crashed_a.returncode == 73, crashed_a.stderr

    database_b, vault_b = _migration_inputs(root_b)
    crashed_b = _crash_child(database_b, vault_b, "after-instance-anchors")
    assert crashed_b.returncode == 73, crashed_b.stderr
    database_anchor_a = _instance_anchor_path(database_a).read_bytes()
    database_anchor_b = _instance_anchor_path(database_b).read_bytes()
    vault_anchor_a = _instance_anchor_path(vault_a).read_bytes()
    vault_anchor_b = _instance_anchor_path(vault_b).read_bytes()
    assert database_anchor_a != database_anchor_b
    assert vault_anchor_a != vault_anchor_b

    shutil.copyfile(database_a, database_b)
    shutil.copyfile(
        database_a.with_name(f"{database_a.name}.lkg"),
        database_b.with_name(f"{database_b.name}.lkg"),
    )
    shutil.copyfile(_journal_path(database_a), _journal_path(database_b))

    with pytest.raises(ProtectedError, match="migration journal instance"):
        vault_migration.run_safe_upgrade(database_b, vault_b, PASS)
    assert _journal_path(database_b).is_file()
    assert not vault_b.with_name("audit.jsonl").exists()
    assert _instance_anchor_path(database_b).read_bytes() == database_anchor_b
    assert _instance_anchor_path(vault_b).read_bytes() == vault_anchor_b

    # The original storage instance remains recoverable and emits exactly once.
    audit_a = AuditLog(vault_a.with_name("audit.jsonl"))
    vault_migration.run_safe_upgrade(database_a, vault_a, PASS, audit_log=audit_a)
    assert len(_events(vault_a.with_name("audit.jsonl"))) == 1
    vault_migration.run_safe_upgrade(database_a, vault_a, PASS, audit_log=audit_a)
    assert len(_events(vault_a.with_name("audit.jsonl"))) == 1


def test_full_storage_bundle_copy_fails_closed_without_event(
    tmp_path: Path,
) -> None:
    root_a = tmp_path / "storage-a"
    root_c = tmp_path / "storage-c"
    root_a.mkdir()
    root_c.mkdir()
    database_a, vault_a = _migration_inputs(root_a)
    crashed_a = _crash_child(database_a, vault_a, "after-lkg-before-audit")
    assert crashed_a.returncode == 73, crashed_a.stderr

    database_c, vault_c = _migration_inputs(root_c)
    crashed_c = _crash_child(database_c, vault_c, "after-instance-anchors")
    assert crashed_c.returncode == 73, crashed_c.stderr

    bundle = (
        (database_a, database_c),
        (database_a.with_name(f"{database_a.name}.lkg"), database_c.with_name(f"{database_c.name}.lkg")),
        (_journal_path(database_a), _journal_path(database_c)),
        (vault_a, vault_c),
        (_instance_anchor_path(database_a), _instance_anchor_path(database_c)),
        (_instance_anchor_path(vault_a), _instance_anchor_path(vault_c)),
    )
    for source, destination in bundle:
        shutil.copyfile(source, destination)

    with pytest.raises(ProtectedError, match="migration journal instance"):
        vault_migration.run_safe_upgrade(database_c, vault_c, PASS)
    assert _journal_path(database_c).is_file()
    assert not vault_c.with_name("audit.jsonl").exists()
    assert vault_c.read_bytes() == vault_a.read_bytes()
    assert _instance_anchor_path(database_c).read_bytes() == _instance_anchor_path(database_a).read_bytes()
    assert _instance_anchor_path(vault_c).read_bytes() == _instance_anchor_path(vault_a).read_bytes()

    # The original path remains the only location authorized to recover.
    audit_a = AuditLog(vault_a.with_name("audit.jsonl"))
    vault_migration.run_safe_upgrade(database_a, vault_a, PASS, audit_log=audit_a)
    assert len(_events(vault_a.with_name("audit.jsonl"))) == 1
    vault_migration.run_safe_upgrade(database_a, vault_a, PASS, audit_log=audit_a)
    assert len(_events(vault_a.with_name("audit.jsonl"))) == 1


def test_storage_identity_normalizes_windows_case_and_separators(
    tmp_path: Path,
) -> None:
    database, vault = _migration_inputs(tmp_path)
    identity = vault_migration._canonical_storage_identity(database)
    separator_alias = Path(str(database).replace("\\", "/"))
    assert vault_migration._canonical_storage_identity(separator_alias) == identity
    assert vault_migration._canonical_storage_identity(vault) != identity

    if os.name == "nt":
        case_alias = Path(str(database).upper())
        assert vault_migration._canonical_storage_identity(case_alias) == identity

    ambiguous_alias = Path(f"\\\\?\\{database}")
    with pytest.raises(ProtectedError, match="migration instance identity") as error:
        vault_migration._canonical_storage_identity(ambiguous_alias)
    assert str(database) not in str(error.value)


def test_tampered_instance_anchor_fails_closed_with_journal_evidence(
    tmp_path: Path,
) -> None:
    database, vault = _migration_inputs(tmp_path)
    crashed = _crash_child(database, vault, "after-lkg-before-audit")
    assert crashed.returncode == 73, crashed.stderr
    _instance_anchor_path(database).write_text("{}", encoding="utf-8")

    with pytest.raises(ProtectedError, match="migration instance identity"):
        vault_migration.run_safe_upgrade(database, vault, PASS)
    assert _journal_path(database).is_file()
    assert not vault.with_name("audit.jsonl").exists()


_INITIAL_CRASH_BOUNDARIES = (
    "journal-prepared",
    "before-db-commit",
    "after-db-commit-before-journal",
    "journal-committed-before-lkg",
    "after-lkg-before-audit",
    "after-audit-before-journal-cleanup",
)


@pytest.mark.parametrize("checkpoint", _INITIAL_CRASH_BOUNDARIES)
def test_subprocess_crash_boundaries_recover_without_false_or_duplicate_events(
    tmp_path: Path,
    checkpoint: str,
) -> None:
    database, vault = _migration_inputs(tmp_path)
    result = _crash_child(database, vault, checkpoint)
    assert result.returncode == 73, result.stderr

    journal_path = _journal_path(database)
    assert journal_path.is_file()
    journal_bytes = journal_path.read_bytes()
    for marker in (
        PASS,
        "SYNTHETIC-ONLY",
        database.name,
        vault.name,
        str(database),
        str(vault),
    ):
        assert marker.encode("utf-8") not in journal_bytes
    journal = json.loads(journal_bytes)
    assert set(journal) == {
        "version",
        "state",
        "action",
        "target_schema",
        "operation_id",
        "event_id",
        "record_ref",
        "database_identity",
        "vault_identity",
        "database_before_hash",
        "database_target_hash",
        "integrity",
    }
    assert len(journal["record_ref"]) == 64
    assert len(journal["database_identity"]) == 64
    assert len(journal["vault_identity"]) == 64
    assert journal["database_identity"] != journal["database_before_hash"]
    for anchor_path in (_instance_anchor_path(database), _instance_anchor_path(vault)):
        anchor = json.loads(anchor_path.read_text(encoding="utf-8"))["anchor"]
        assert anchor.encode("ascii") not in journal_bytes
    assert not vault.with_name("audit.jsonl").exists() or checkpoint == "after-audit-before-journal-cleanup"

    if checkpoint in {"journal-prepared", "before-db-commit"}:
        assert _tables(database) == {"synthetic_seed"}
    else:
        assert {"audit_events", "attachment_metadata"}.issubset(_tables(database))

    audit = AuditLog(vault.with_name("audit.jsonl"))
    vault_migration.run_safe_upgrade(database, vault, PASS, audit_log=audit)
    events = _events(vault.with_name("audit.jsonl"))
    assert len(events) == 1
    assert events[0]["action"] == "migration"
    assert events[0]["success"] is True
    if checkpoint in {"journal-prepared", "before-db-commit"}:
        # The abandoned intent is discarded; the later retry is a new
        # operation, so it must not reuse the rolled-back event identity.
        assert events[0]["event_id"] != journal["event_id"]
        assert events[0]["record_ref"] != journal["record_ref"]
    else:
        assert events[0]["event_id"] == journal["event_id"]
        assert events[0]["record_ref"] == journal["record_ref"]
    assert not journal_path.exists()

    # A second supported boundary must not replay a completed success.
    vault_migration.run_safe_upgrade(database, vault, PASS, audit_log=audit)
    assert len(_events(vault.with_name("audit.jsonl"))) == 1


@pytest.mark.parametrize("checkpoint", ("recovery-before-audit", "recovery-after-audit"))
def test_subprocess_recovery_boundaries_are_idempotent(
    tmp_path: Path,
    checkpoint: str,
) -> None:
    database, vault = _migration_inputs(tmp_path)
    first = _crash_child(database, vault, "after-lkg-before-audit")
    assert first.returncode == 73, first.stderr

    recovery = _crash_child(database, vault, checkpoint)
    assert recovery.returncode == 73, recovery.stderr
    audit_path = vault.with_name("audit.jsonl")
    if checkpoint == "recovery-before-audit":
        assert not audit_path.exists()
    else:
        assert len(_events(audit_path)) == 1
    assert _journal_path(database).is_file()

    journal = json.loads(
        _journal_path(database).read_text(encoding="utf-8")
    )
    audit = AuditLog(audit_path)
    vault_migration.run_safe_upgrade(database, vault, PASS, audit_log=audit)
    events = _events(audit_path)
    assert len(events) == 1
    assert events[0]["event_id"] == journal["event_id"]
    assert events[0]["record_ref"] == journal["record_ref"]
    assert not _journal_path(database).exists()


def test_tampered_migration_journal_fails_closed_without_event_or_replay(
    tmp_path: Path,
) -> None:
    database, vault = _migration_inputs(tmp_path)
    child = _crash_child(database, vault, "after-lkg-before-audit")
    assert child.returncode == 73, child.stderr
    journal_path = _journal_path(database)
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    journal["database_target_hash"] = "f" * 64
    journal_path.write_text(json.dumps(journal, sort_keys=True), encoding="utf-8")

    with pytest.raises(ProtectedError, match="migration journal is invalid"):
        vault_migration.run_safe_upgrade(database, vault, PASS)
    assert journal_path.is_file()
    assert not vault.with_name("audit.jsonl").exists()


def test_valid_but_ambiguous_migration_journal_fails_closed(
    tmp_path: Path,
) -> None:
    database, vault = _migration_inputs(tmp_path)
    child = _crash_child(database, vault, "after-lkg-before-audit")
    assert child.returncode == 73, child.stderr
    journal_path = _journal_path(database)
    original = vault_migration._read_journal(journal_path, PASS)
    assert original is not None
    body = vault_migration._journal_body(original)
    body["database_target_hash"] = "e" * 64
    vault_migration._journal_write(journal_path, body, PASS)

    with pytest.raises(ProtectedError, match="migration journal state is ambiguous"):
        vault_migration.run_safe_upgrade(database, vault, PASS)
    assert journal_path.is_file()
    assert not vault.with_name("audit.jsonl").exists()
