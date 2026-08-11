"""Fail-closed local Alembic migration runner.

The live SQLite connection holds a real write lock for the whole snapshot and
activation protocol.  Staging uses SQLite's backup API, so WAL pages are part
of the consistent image; no filesystem copy of a live ``.db`` is used.
"""
from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import tempfile
import uuid
from pathlib import Path
from typing import Final, Literal, TypedDict, cast

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, create_engine
from sqlalchemy.pool import NullPool

from .core import AuditSink, VaultStore, _exclusive_lock, _PlatformPermissions
from .protected import (
    AuditLog,
    BackupManager,
    ProtectedError,
    _atomic,
    _read_held,
    _reject_reparse,
)

_JOURNAL_VERSION: Final = 1
_JOURNAL_MAX_BYTES: Final = 8 * 1024
_JOURNAL_KEY_PREFIX: Final = b"mycard-benefits/migration-journal/v1:"
_MAX_JOURNAL_PASSPHRASE_BYTES: Final = 1_024
_MAX_DATABASE_HASH_INPUT: Final = 64 * 1024 * 1024
_INSTANCE_ANCHOR_VERSION: Final = 1
_INSTANCE_ANCHOR_MAX_BYTES: Final = 512
_INSTANCE_ANCHOR_DIGEST_DOMAIN: Final = b"mycard-benefits/migration-instance-digest/v2\0"
_MAX_STORAGE_IDENTITY_BYTES: Final = 4_096
_INSTANCE_ANCHOR_FIELDS = frozenset({"version", "anchor"})
_MIGRATION_ACTION: Final = "migration"
_JOURNAL_STATES = frozenset({"prepared", "committed"})
_JOURNAL_FIELDS = frozenset(
    {
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
)


class _JournalBody(TypedDict):
    version: int
    state: Literal["prepared", "committed"]
    action: str
    target_schema: str
    operation_id: str
    event_id: str
    record_ref: str
    database_identity: str
    vault_identity: str
    database_before_hash: str
    database_target_hash: str


class _Journal(_JournalBody):
    integrity: str


def _migration_checkpoint(_name: str) -> None:
    """Test-only process boundary hook; production has no external behavior."""


def _journal_path(database: Path) -> Path:
    return database.with_name(f"{database.name}.migration-journal.json")


def _instance_anchor_path(storage: Path) -> Path:
    return storage.with_name(f"{storage.name}.migration-instance.json")


def _canonical_storage_identity(storage: Path) -> bytes:
    """Return a transient, normalized identity for one protected storage file.

    This deliberately performs lexical normalization without resolving links.
    Every existing component is checked before and after normalization so a
    reparse point cannot silently become part of the identity.  The canonical
    value is used only in the digest and is never persisted or exposed.
    """
    try:
        raw = os.fspath(storage)
        if not isinstance(raw, str) or not raw or "\x00" in raw:
            raise ValueError
        raw_path = Path(raw)
        if os.name == "nt":
            raw_windows = raw.replace("/", "\\")
            if raw_windows.startswith(("\\\\?\\", "\\\\.\\")):
                raise ValueError
        lexical_path = raw_path if raw_path.is_absolute() else Path.cwd() / raw_path
        _reject_reparse(lexical_path)
        normalized_path = Path(os.path.normpath(os.path.abspath(raw)))
        if not normalized_path.is_absolute():
            raise ValueError
        _reject_reparse(normalized_path)
        if normalized_path.is_symlink() or not normalized_path.is_file():
            raise ValueError
        normalized = os.path.normcase(os.fspath(normalized_path))
        if os.name == "nt":
            normalized = normalized.replace("\\", "/").casefold()
        encoded = normalized.encode("utf-8")
        if not 1 <= len(encoded) <= _MAX_STORAGE_IDENTITY_BYTES:
            raise ValueError
        return encoded
    except (OSError, TypeError, UnicodeError, ValueError, ProtectedError):
        raise ProtectedError("migration instance identity is unavailable") from None


def _instance_anchor_digest(anchor: str, storage_identity: bytes) -> str:
    anchor_bytes = anchor.encode("ascii")
    digest_input = (
        _INSTANCE_ANCHOR_DIGEST_DOMAIN
        + len(anchor_bytes).to_bytes(2, "big")
        + anchor_bytes
        + len(storage_identity).to_bytes(4, "big")
        + storage_identity
    )
    return hashlib.sha256(digest_input).hexdigest()


def _instance_anchor(storage: Path, *, create: bool) -> str:
    storage_identity = _canonical_storage_identity(storage)
    path = _instance_anchor_path(storage)
    _reject_reparse(path.parent)
    with _exclusive_lock(path, _PlatformPermissions()):
        _reject_reparse(path, allow_missing=True)
        if not path.exists():
            if not create:
                raise ProtectedError("migration instance identity is unavailable")
            encoded = json.dumps(
                {
                    "anchor": secrets.token_hex(32),
                    "version": _INSTANCE_ANCHOR_VERSION,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("ascii")
            if len(encoded) > _INSTANCE_ANCHOR_MAX_BYTES:
                raise ProtectedError("migration instance identity is invalid")
            _atomic(path, encoded)
            _fsync_directory(path.parent)
        raw = _read_held(path, limit=_INSTANCE_ANCHOR_MAX_BYTES)
    try:
        item = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        raise ProtectedError("migration instance identity is invalid") from None
    if (
        not isinstance(item, dict)
        or set(item) != _INSTANCE_ANCHOR_FIELDS
        or type(item.get("version")) is not int
        or item.get("version") != _INSTANCE_ANCHOR_VERSION
        or not _valid_hex(item.get("anchor"))
    ):
        raise ProtectedError("migration instance identity is invalid")
    return _instance_anchor_digest(cast(str, item["anchor"]), storage_identity)


def _journal_key(passphrase: str) -> bytes:
    try:
        encoded = passphrase.encode("utf-8")
    except (AttributeError, UnicodeEncodeError):
        raise ProtectedError("migration passphrase is invalid") from None
    if not 12 <= len(encoded) <= _MAX_JOURNAL_PASSPHRASE_BYTES:
        raise ProtectedError("migration passphrase is invalid")
    return hashlib.sha256(_JOURNAL_KEY_PREFIX + encoded).digest()


def _journal_body_bytes(body: _JournalBody) -> bytes:
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _journal_encoded(body: _JournalBody, passphrase: str) -> bytes:
    integrity = hmac.new(_journal_key(passphrase), _journal_body_bytes(body), hashlib.sha256).hexdigest()
    return json.dumps(
        {**body, "integrity": integrity}, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _journal_write(path: Path, body: _JournalBody, passphrase: str) -> None:
    encoded = _journal_encoded(body, passphrase)
    if len(encoded) > _JOURNAL_MAX_BYTES:
        raise ProtectedError("migration journal is too large")
    _atomic(path, encoded)
    _fsync_directory(path.parent)


def _journal_body(journal: _Journal) -> _JournalBody:
    return {
        "version": journal["version"],
        "state": journal["state"],
        "action": journal["action"],
        "target_schema": journal["target_schema"],
        "operation_id": journal["operation_id"],
        "event_id": journal["event_id"],
        "record_ref": journal["record_ref"],
        "database_identity": journal["database_identity"],
        "vault_identity": journal["vault_identity"],
        "database_before_hash": journal["database_before_hash"],
        "database_target_hash": journal["database_target_hash"],
    }


def _valid_hex(value: object, length: int = 64) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
    )


def _valid_uuid(value: object) -> bool:
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value
    except (ValueError, AttributeError, TypeError):
        return False


def _read_journal(path: Path, passphrase: str) -> _Journal | None:
    if not path.exists():
        return None
    _reject_reparse(path)
    raw = _read_held(path, limit=_JOURNAL_MAX_BYTES)
    try:
        item = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        raise ProtectedError("migration journal is invalid") from None
    if not isinstance(item, dict) or set(item) != _JOURNAL_FIELDS:
        raise ProtectedError("migration journal is invalid")
    integrity = item.get("integrity")
    body = cast(
        _JournalBody,
        {key: item[key] for key in _JOURNAL_FIELDS if key != "integrity"},
    )
    if (
        not isinstance(integrity, str)
        or not hmac.compare_digest(
            integrity,
            hmac.new(_journal_key(passphrase), _journal_body_bytes(body), hashlib.sha256).hexdigest(),
        )
        or type(body["version"]) is not int
        or body["version"] != _JOURNAL_VERSION
        or not isinstance(body["state"], str)
        or body["state"] not in _JOURNAL_STATES
        or body["action"] != _MIGRATION_ACTION
        or not isinstance(body["target_schema"], str)
        or not 1 <= len(body["target_schema"]) <= 128
        or not body["target_schema"].isascii()
        or not _valid_uuid(body["operation_id"])
        or not _valid_uuid(body["event_id"])
        or not _valid_hex(body["record_ref"])
        or not _valid_hex(body["database_identity"])
        or not _valid_hex(body["vault_identity"])
        or not _valid_hex(body["database_before_hash"])
        or not _valid_hex(body["database_target_hash"])
        or body["database_before_hash"] == body["database_target_hash"]
        or body["record_ref"]
        != AuditLog.opaque_record_ref(f"{_MIGRATION_ACTION}:{body['operation_id']}")
    ):
        raise ProtectedError("migration journal is invalid")
    return cast(_Journal, {**body, "integrity": integrity})


def _journal_remove(path: Path) -> None:
    if not path.exists():
        return
    _reject_reparse(path)
    path.unlink()
    _fsync_directory(path.parent)


def _database_state_hash(path: Path) -> str:
    digest = hashlib.sha256()
    total = 0
    try:
        connection = sqlite3.connect(path, timeout=30)
    except sqlite3.Error:
        raise ProtectedError("migration database is unavailable") from None
    try:
        for line in connection.iterdump():
            encoded = (line + "\n").encode("utf-8")
            total += len(encoded)
            if total > _MAX_DATABASE_HASH_INPUT:
                raise ProtectedError("migration database is too large")
            digest.update(encoded)
    except (sqlite3.Error, UnicodeError):
        raise ProtectedError("migration database is unavailable") from None
    finally:
        connection.close()
    return digest.hexdigest()


def _config(database: Path) -> Config:
    config = Config(str(Path(__file__).parents[3] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    return config


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _checkpoint(path: Path) -> None:
    connection = sqlite3.connect(path, timeout=30, isolation_level=None)
    try:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        connection.execute("PRAGMA synchronous=FULL")
    finally:
        connection.close()


def _sqlite_backup(source: Path, destination: Path) -> None:
    """Make a durable, transactionally consistent SQLite copy, including WAL."""
    source_connection = sqlite3.connect(source, timeout=30)
    destination_connection = sqlite3.connect(destination, timeout=30)
    try:
        source_connection.backup(destination_connection)
        destination_connection.commit()
    finally:
        destination_connection.close()
        source_connection.close()
    _checkpoint(destination)
    with destination.open("r+b") as handle:
        handle.flush()
        os.fsync(handle.fileno())


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute("select name from sqlite_master where type='table'")
    }


def _schema_marker(connection: sqlite3.Connection) -> str | None:
    if not {"audit_events", "attachment_metadata"}.issubset(_tables(connection)):
        return None
    tables = _tables(connection)
    if "alembic_version" not in tables:
        return "private-metadata:v1"
    try:
        raw_versions = tuple(
            row[0] for row in connection.execute("select version_num from alembic_version")
        )
    except sqlite3.Error:
        raise ProtectedError("migration schema is unavailable") from None
    if not raw_versions or any(not isinstance(version, str) or not version for version in raw_versions):
        return None
    versions = tuple(sorted(cast(tuple[str, ...], raw_versions)))
    marker = "alembic:" + ",".join(versions)
    return marker if len(marker) <= 128 and marker.isascii() else None


def _schema_marker_path(path: Path) -> str | None:
    try:
        connection = sqlite3.connect(path, timeout=30)
    except sqlite3.Error:
        raise ProtectedError("migration database is unavailable") from None
    try:
        return _schema_marker(connection)
    finally:
        connection.close()


def _validate(connection: sqlite3.Connection) -> None:
    if not {"audit_events", "attachment_metadata"}.issubset(_tables(connection)):
        raise ProtectedError("migration validation failed")


def _validate_path(path: Path, *, require_metadata: bool = True) -> None:
    connection = sqlite3.connect(path)
    try:
        if require_metadata:
            _validate(connection)
        elif not _tables(connection):
            raise ProtectedError("migration LKG validation failed")
    finally:
        connection.close()


def _durable_lkg(stage: Path, lkg: Path) -> None:
    """Promote a closed/validated image without overwriting the old LKG in place."""
    _PlatformPermissions().secure_file(stage)
    os.replace(stage, lkg)
    _PlatformPermissions().secure_file(lkg)
    _fsync_directory(lkg.parent)


def _migration_record_input(journal: _JournalBody) -> str:
    return f"{_MIGRATION_ACTION}:{journal['operation_id']}"


def _record_migration_event(active_audit: AuditSink, journal: _JournalBody) -> None:
    try:
        persisted_event_id = active_audit.record(
            _MIGRATION_ACTION,
            record_ref=_migration_record_input(journal),
            event_id=journal["event_id"],
        )
    except Exception as exc:
        raise ProtectedError("migration audit unavailable") from exc
    if persisted_event_id != journal["event_id"]:
        raise ProtectedError("migration audit identity is invalid")


def _ensure_recovered_lkg(
    database: Path,
    lkg: Path,
    journal: _JournalBody,
) -> None:
    if lkg.is_symlink() or (lkg.exists() and not lkg.is_file()):
        raise ProtectedError("migration LKG is unavailable")
    if lkg.is_file():
        lkg_hash = _database_state_hash(lkg)
        if lkg_hash == journal["database_target_hash"]:
            return
        if lkg_hash != journal["database_before_hash"]:
            raise ProtectedError("migration LKG state is ambiguous")
    with tempfile.TemporaryDirectory(dir=database.parent) as temp_dir:
        stage = Path(temp_dir) / f"{database.name}.recovered"
        _sqlite_backup(database, stage)
        _validate_path(stage)
        if (
            _schema_marker_path(stage) != journal["target_schema"]
            or _database_state_hash(stage) != journal["database_target_hash"]
        ):
            raise ProtectedError("migration recovery state is invalid")
        _durable_lkg(stage, lkg)


def _restore_live_from_image(
    source: Path,
    database: Path,
    live_connection: sqlite3.Connection,
    expected_hash: str,
) -> None:
    try:
        source_connection = sqlite3.connect(source, timeout=30)
        try:
            source_connection.backup(live_connection)
            live_connection.commit()
        finally:
            source_connection.close()
        _checkpoint(database)
        if _database_state_hash(database) != expected_hash:
            raise ProtectedError("migration rollback state is invalid")
    except ProtectedError:
        raise
    except (OSError, sqlite3.Error) as exc:
        raise ProtectedError("migration rollback is unavailable") from exc


def _rollback_committed_migration(
    database: Path,
    lkg: Path,
    prior_lkg: Path,
    live_connection: sqlite3.Connection,
    expected_hash: str,
) -> None:
    """Restore controlled audit failures to the pre-migration image."""
    _restore_live_from_image(prior_lkg, database, live_connection, expected_hash)
    _durable_lkg(prior_lkg, lkg)
    if _database_state_hash(lkg) != expected_hash:
        raise ProtectedError("migration rollback LKG is invalid")


def _recover_migration_journal(
    database: Path,
    lkg: Path,
    vault: Path,
    passphrase: str,
    active_audit: AuditSink,
) -> bool:
    """Resolve one durable migration intent before starting another one."""
    path = _journal_path(database)
    journal = _read_journal(path, passphrase)
    if journal is None:
        return False
    body = _journal_body(journal)
    if (
        _instance_anchor(database, create=False) != journal["database_identity"]
        or _instance_anchor(vault, create=False) != journal["vault_identity"]
    ):
        raise ProtectedError("migration journal instance mismatch")
    current_hash = _database_state_hash(database)
    current_schema = _schema_marker_path(database)
    if journal["state"] == "prepared":
        if current_hash == journal["database_before_hash"]:
            if isinstance(active_audit, AuditLog) and active_audit._has_event(
                journal["event_id"],
                _MIGRATION_ACTION,
                record_ref=_migration_record_input(body),
            ):
                raise ProtectedError("migration journal is ambiguous")
            if not lkg.is_file() or lkg.is_symlink():
                raise ProtectedError("migration journal state is ambiguous")
            if _database_state_hash(lkg) != journal["database_before_hash"]:
                raise ProtectedError("migration journal state is ambiguous")
            _journal_remove(path)
            return False
        if (
            current_hash != journal["database_target_hash"]
            or current_schema != journal["target_schema"]
        ):
            raise ProtectedError("migration journal state is ambiguous")
        body["state"] = "committed"
        _journal_write(path, body, passphrase)
    elif (
        current_hash != journal["database_target_hash"]
        or current_schema != journal["target_schema"]
    ):
        raise ProtectedError("migration journal state is ambiguous")

    _ensure_recovered_lkg(database, lkg, body)
    _migration_checkpoint("recovery-before-audit")
    _record_migration_event(active_audit, body)
    _migration_checkpoint("recovery-after-audit")
    _journal_remove(path)
    return True


def _upgrade(database: Path, *, live_connection: Connection | None = None) -> None:
    """Run Alembic against a stage or an already writer-locked live DB."""
    config = _config(database)
    if live_connection is None:
        command.upgrade(config, "head")
        return
    # Alembic normally opens a second writer connection.  Supplying the
    # coordinator preserves BEGIN IMMEDIATE's real writer exclusion through
    # the live migration transaction.
    config.attributes["connection"] = live_connection
    command.upgrade(config, "head")


def run_safe_upgrade(
    database: Path,
    vault: Path,
    passphrase: str,
    *,
    audit_log: AuditSink | None = None,
) -> None:
    """Run a WAL-safe migration while coordinating with SQLite writers.

    A real ``BEGIN IMMEDIATE`` is acquired before every source snapshot and
    held through live Alembic application.  That blocks independent SQLite
    writers (not just our sidecar users), while allowing SQLite's backup API
    to make a WAL-consistent rehearsal.  The live schema changes commit in one
    SQLite transaction.  Durable per-storage anchors and a passphrase-bound
    journal record that intent before the commit; the value-free success event
    is appended only after the database state is authoritative and is
    replay-safe on recovery.
    """
    if (
        not database.is_file() or database.is_symlink()
        or not vault.is_file() or vault.is_symlink()
    ):
        raise ProtectedError("migration inputs are invalid")
    active_audit = audit_log or AuditLog(vault.with_name("audit.jsonl"))
    lkg = database.with_name(f"{database.name}.lkg")
    permissions = _PlatformPermissions()
    migration_completed = False
    with _exclusive_lock(database, permissions):
        if _recover_migration_journal(database, lkg, vault, passphrase, active_audit):
            migration_completed = True
        elif _schema_marker_path(database) is not None:
            return
        else:
            database_identity = _instance_anchor(database, create=True)
            vault_identity = _instance_anchor(vault, create=True)
            _migration_checkpoint("after-instance-anchors")
            # A migration owns one live connection. NullPool guarantees Windows
            # releases the database handle after the transaction instead of
            # retaining it in a SQLite pool and blocking cleanup/retry.
            engine = create_engine(
                f"sqlite:///{database.as_posix()}",
                connect_args={"timeout": 30},
                poolclass=NullPool,
            )
            raw_coordinator: sqlite3.Connection | None = None
            live_committed = False
            try:
                with engine.connect() as coordinator:
                    # Keep this SQLAlchemy-owned connection for both BEGIN
                    # IMMEDIATE and Alembic so no second writer can bypass it.
                    coordinator.exec_driver_sql("BEGIN IMMEDIATE")
                    raw_coordinator = coordinator.connection.driver_connection
                    if not isinstance(raw_coordinator, sqlite3.Connection):
                        raise ProtectedError("migration connection is invalid")
                    try:
                        # This is SQLite's writer coordination point, not merely
                        # our advisory sidecar. Real SQLite writers cannot commit.
                        before_hash = _database_state_hash(database)
                        with tempfile.TemporaryDirectory(dir=database.parent) as temp_dir:
                            temp = Path(temp_dir)
                            prior_lkg = temp / f"{database.name}.prior"
                            if lkg.is_file() and not lkg.is_symlink():
                                _sqlite_backup(lkg, prior_lkg)
                                # An LKG can legitimately predate the first
                                # metadata migration, so prove it is a readable
                                # non-empty SQLite image rather than requiring the
                                # schema this run is about to add.
                                _validate_path(prior_lkg, require_metadata=False)
                            else:
                                _sqlite_backup(database, prior_lkg)
                                _validate_path(prior_lkg, require_metadata=False)
                                initial = database.parent / f".{database.name}.lkg.initial"
                                _sqlite_backup(prior_lkg, initial)
                                _durable_lkg(initial, lkg)

                            rehearsal = temp / database.name
                            # A second reader can snapshot while BEGIN IMMEDIATE
                            # blocks writers, so rehearsal includes committed WAL.
                            _sqlite_backup(database, rehearsal)
                            _upgrade(rehearsal)
                            _checkpoint(rehearsal)
                            _validate_path(rehearsal)
                            target_schema = _schema_marker_path(rehearsal)
                            if target_schema is None:
                                raise ProtectedError("migration validation failed")
                            target_hash = _database_state_hash(rehearsal)
                            if target_hash == before_hash:
                                raise ProtectedError("migration produced no state change")
                            VaultStore(vault, audit_log=active_audit).open(passphrase).lock()

                            operation_id = str(uuid.uuid4())
                            journal_body: _JournalBody = {
                                "version": _JOURNAL_VERSION,
                                "state": "prepared",
                                "action": _MIGRATION_ACTION,
                                "target_schema": target_schema,
                                "operation_id": operation_id,
                                "event_id": str(uuid.uuid4()),
                                "record_ref": AuditLog.opaque_record_ref(
                                    f"{_MIGRATION_ACTION}:{operation_id}"
                                ),
                                "database_identity": database_identity,
                                "vault_identity": vault_identity,
                                "database_before_hash": before_hash,
                                "database_target_hash": target_hash,
                            }
                            journal_path = _journal_path(database)
                            _journal_write(journal_path, journal_body, passphrase)
                            _migration_checkpoint("journal-prepared")

                            # Do not replace an open database: on Windows a
                            # close/reopen gap could lose a writer. Apply through
                            # the locked live connection for an atomic commit.
                            _upgrade(database, live_connection=coordinator)
                            _validate(raw_coordinator)
                            # The new LKG is staged, fsynced, validated, and
                            # ready before the commit boundary.
                            next_lkg = temp / f"{database.name}.switched"
                            _sqlite_backup(rehearsal, next_lkg)
                            _validate_path(next_lkg)

                            _migration_checkpoint("before-db-commit")
                            coordinator.commit()
                            live_committed = True
                            _migration_checkpoint("after-db-commit-before-journal")
                            if (
                                _database_state_hash(database) != target_hash
                                or _schema_marker_path(database) != target_schema
                            ):
                                raise ProtectedError("migration commit state is invalid")

                            journal_body["state"] = "committed"
                            _journal_write(journal_path, journal_body, passphrase)
                            _migration_checkpoint("journal-committed-before-lkg")
                            _durable_lkg(next_lkg, lkg)
                            _migration_checkpoint("after-lkg-before-audit")

                            # SQLite is authoritative.  If this append fails,
                            # AuditLog restores its own bytes.  A controlled
                            # failure also restores the pre-migration image;
                            # an uncatchable process exit leaves the committed
                            # journal for deterministic retry.
                            try:
                                _record_migration_event(active_audit, journal_body)
                            except ProtectedError:
                                journal_body["state"] = "prepared"
                                _journal_write(journal_path, journal_body, passphrase)
                                _rollback_committed_migration(
                                    database,
                                    lkg,
                                    prior_lkg,
                                    raw_coordinator,
                                    before_hash,
                                )
                                _journal_remove(journal_path)
                                raise
                            _migration_checkpoint("after-audit-before-journal-cleanup")
                            _journal_remove(journal_path)
                            migration_completed = True
                    except Exception:
                        if not live_committed:
                            with contextlib.suppress(Exception):
                                coordinator.rollback()
                        # Once SQLite commits, never restore it from an older
                        # LKG. The journal is the recoverable audit boundary.
                        raise
            finally:
                # Alembic's environment retains the supplied DB-API object until
                # its command context unwinds. Explicitly close the exact owned
                # connection after the SQLAlchemy context exits so Windows can
                # release the live file for the caller's cleanup or retry.
                if raw_coordinator is not None:
                    raw_coordinator.close()
                engine.dispose()
    if not migration_completed:
        return
    backup = BackupManager(database.parent / "migration-backups", keep=10).create(
        vault, passphrase, label="manual"
    )
    if not backup.exists():
        raise ProtectedError("migration backup is missing")
