"""Offline public-catalog release snapshots and safe installation."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import shutil
import tempfile
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

from .catalog.loader import Catalog, load_catalog


class SnapshotError(ValueError):
    """A snapshot is invalid or cannot be installed safely."""


_LOCK_LEASE_NS = 30_000_000_000


def _fsync_file(path: Path) -> None:
    try:
        with path.open("r+b") as stream:
            os.fsync(stream.fileno())
    except OSError as exc:
        raise SnapshotError("file durability check failed") from exc


def _fsync_directory(directory: Path) -> None:
    """Synchronize a directory entry, or fail closed if this host cannot."""
    try:
        if os.name == "nt":
            # Python cannot open directories on Windows.  The backup-semantics
            # handle is the documented equivalent and FlushFileBuffers makes
            # the operation observable to the filesystem.
            import ctypes
            from ctypes import wintypes

            create_file = ctypes.windll.kernel32.CreateFileW
            create_file.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                    wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
                                    wintypes.HANDLE]
            create_file.restype = wintypes.HANDLE
            handle = create_file(str(directory), 0x40000000, 0x00000007, None, 3,
                                 0x02000000, None)  # write, shared, OPEN_EXISTING, BACKUP_SEMANTICS
            invalid = ctypes.c_void_p(-1).value
            if handle == invalid or not ctypes.windll.kernel32.FlushFileBuffers(handle):
                raise OSError("FlushFileBuffers failed")
            if not ctypes.windll.kernel32.CloseHandle(handle):
                raise OSError("CloseHandle failed")
        else:
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            descriptor = os.open(directory, flags)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    except (AttributeError, OSError) as exc:
        # A rename may be atomic without being power-loss durable.  Do not
        # pretend otherwise on a filesystem/runtime that cannot expose this.
        raise SnapshotError("directory durability check failed") from exc


def _fsync_tree(root: Path) -> None:
    """Make copied snapshot contents and every directory entry durable."""
    try:
        paths = sorted(root.rglob("*"), key=lambda path: (len(path.parts), str(path)), reverse=True)
        for path in paths:
            if path.is_file():
                _fsync_file(path)
            elif path.is_dir():
                _fsync_directory(path)
        _fsync_directory(root)
    except SnapshotError:
        raise
    except OSError as exc:
        raise SnapshotError("snapshot durability check failed") from exc


def _durable_replace(source: Path, destination: Path) -> None:
    """Replace only after the source is durable, then sync its parent entry."""
    if source.is_dir():
        # Snapshot copies call _fsync_tree before their first publication.
        # For a later rename the directory entry is the mutable object; doing
        # a second full-file sweep here would not add a durability guarantee.
        _fsync_directory(source)
    elif source.is_file():
        _fsync_file(source)
    _fsync_directory(source.parent)
    try:
        os.replace(source, destination)
    except OSError as exc:
        raise SnapshotError("atomic replace failed") from exc
    _fsync_directory(destination.parent)


def _durable_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        raise SnapshotError("durable removal failed") from exc
    _fsync_directory(path.parent)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _safe_version(version: str) -> str:
    if not version or version in {".", ".."} or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for c in version):
        raise SnapshotError("invalid snapshot version")
    return version


def export_snapshot(catalog_dir: Path, destination: Path, *, version: str | None = None) -> Path:
    """Copy a validated catalog into a versioned directory with a checksum manifest."""
    catalog = load_catalog(catalog_dir)
    version = _safe_version(version or catalog.release.schema_version)
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    _fsync_directory(destination.parent)
    target = destination / version
    if target.exists():
        raise SnapshotError("snapshot version already exists")
    staging = Path(tempfile.mkdtemp(prefix=f".{version}-", dir=destination))
    try:
        for source in sorted(catalog_dir.rglob("*.json")):
            relative = source.relative_to(catalog_dir)
            if any(part in {"", ".", ".."} for part in relative.parts):
                raise SnapshotError("unsafe catalog path")
            output = staging / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, output)
        files = {}
        for path in sorted(staging.rglob("*.json")):
            files[str(path.relative_to(staging)).replace(os.sep, "/")] = hashlib.sha256(path.read_bytes()).hexdigest()
        (staging / "SNAPSHOT.json").write_bytes(_canonical({"version": version, "files": files}))
        _fsync_tree(staging)
        _durable_replace(staging, target)
        return target
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _verify_snapshot(snapshot: Path) -> None:
    snapshot = snapshot.resolve()
    manifest_path = snapshot / "SNAPSHOT.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        version = manifest["version"]
        files = manifest["files"]
    except (OSError, ValueError, KeyError, TypeError):
        raise SnapshotError("invalid snapshot manifest") from None
    if not isinstance(version, str) or not isinstance(files, dict):
        raise SnapshotError("invalid snapshot manifest")
    actual = {
        str(path.relative_to(snapshot)).replace(os.sep, "/")
        for path in snapshot.rglob("*.json")
        if path.name != "SNAPSHOT.json"
    }
    if set(files) != actual:
        raise SnapshotError("snapshot manifest file set mismatch")
    for relative, expected in files.items():
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise SnapshotError("invalid snapshot manifest entry")
        candidate = (snapshot / relative).resolve()
        if snapshot not in candidate.parents or candidate.name == "SNAPSHOT.json":
            raise SnapshotError("snapshot contains an unsafe path")
        if not candidate.is_file() or hashlib.sha256(candidate.read_bytes()).hexdigest() != expected:
            raise SnapshotError("snapshot checksum mismatch")
    load_catalog(snapshot)


def _journal_path(catalog_dir: Path) -> Path:
    return catalog_dir.parent / f".{catalog_dir.name}.install.json"


def _verified_root(catalog_dir: Path) -> Path:
    return catalog_dir.parent / f".{catalog_dir.name}.verified"


def _pointer_path(catalog_dir: Path) -> Path:
    return catalog_dir.parent / f".{catalog_dir.name}.active"


def _lock_path(catalog_dir: Path) -> Path:
    return catalog_dir.parent / f".{catalog_dir.name}.install.lock"


def _try_lock(handle: Any) -> bool:
    """Acquire a process-held byte lock; no timestamp may steal a live owner."""
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                return False
        else:
            fcntl: Any = importlib.import_module("fcntl")

            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return False
        return True
    except (AttributeError, ImportError, OSError) as exc:
        raise SnapshotError("safe catalog lock is unavailable") from exc


def _unlock(handle: Any) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl: Any = importlib.import_module("fcntl")

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except (AttributeError, ImportError, OSError):
        # Closing the handle releases the OS lock.  There is no accepted
        # transition here to claim if the optional unlock call itself fails.
        pass


@contextmanager
def _install_lock(catalog_dir: Path) -> Iterator[None]:
    """Recover stale lock *files* only by acquiring the released OS lock.

    The lease metadata is diagnostic/restart evidence, never authority to take
    a lock: PIDs may be recycled and wall clocks may roll backward.
    """
    lock = _lock_path(catalog_dir)
    lock.parent.mkdir(parents=True, exist_ok=True)
    _fsync_directory(lock.parent)
    deadline = time.monotonic() + 10
    handle = None
    acquired = False
    try:
        # The first byte is reserved for the platform byte lock; JSON begins
        # at byte one. Open existing artifacts read/write first so a waiter
        # never appends or rewrites diagnostic bytes while a live owner holds
        # the lock. Creation is a separate race-safe operation.
        while not acquired:
            if handle is None:
                try:
                    handle = lock.open("r+b")
                except FileNotFoundError:
                    try:
                        handle = lock.open("x+b")
                    except FileExistsError:
                        continue
                    except PermissionError:
                        if time.monotonic() >= deadline:
                            raise SnapshotError("catalog install is already in progress") from None
                        time.sleep(0.01)
                        continue
                except PermissionError:
                    # Windows can deny opening a byte-locked file entirely.
                    # Waiting is safe; expiry metadata never grants takeover.
                    if time.monotonic() >= deadline:
                        raise SnapshotError("catalog install is already in progress") from None
                    time.sleep(0.01)
                    continue
                if handle is not None and handle.seek(0, os.SEEK_END) == 0:
                    handle.write(b"\0")
                    handle.flush()
                    try:
                        os.fsync(handle.fileno())
                    except OSError as exc:
                        raise SnapshotError("catalog lock durability check failed") from exc
                    _fsync_directory(lock.parent)
            acquired = _try_lock(handle)
            if acquired:
                break
            handle.close()
            handle = None
            if time.monotonic() >= deadline:
                raise SnapshotError("catalog install is already in progress") from None
            time.sleep(0.01)
        assert handle is not None
        metadata = _canonical({
            "pid": os.getpid(), "owner": uuid.uuid4().hex,
            "lease_expires_ns": time.time_ns() + _LOCK_LEASE_NS,
        })
        handle.seek(1)
        handle.truncate()
        handle.write(metadata)
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except OSError as exc:
            raise SnapshotError("catalog lock durability check failed") from exc
        _fsync_directory(lock.parent)
        yield
    finally:
        if handle is not None:
            if acquired:
                _unlock(handle)
            handle.close()


def _quarantine(path: Path, label: str) -> None:
    if path.exists():
        _durable_replace(path, path.with_name(f".{path.name}.{label}-{time.time_ns()}"))


def _verified_snapshots(catalog_dir: Path) -> list[tuple[str, Path]]:
    root = _verified_root(catalog_dir)
    if not root.is_dir():
        return []
    valid: list[tuple[str, Path]] = []
    for candidate in sorted(root.iterdir()):
        if candidate.is_dir():
            try:
                _verify_snapshot(candidate)
            except SnapshotError:
                continue
            valid.append((candidate.name, candidate))
    return valid


def _snapshot_identity(snapshot: Path) -> str:
    return hashlib.sha256((snapshot / "SNAPSHOT.json").read_bytes()).hexdigest()


def _read_pointer(catalog_dir: Path) -> str | None:
    try:
        value = _pointer_path(catalog_dir).read_text(encoding="ascii").strip()
    except OSError:
        return None
    return value or None


def _copy_verified(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination)
    _verify_snapshot(destination)
    _fsync_tree(destination)


def _publish_pointer(pointer: Path, value: str) -> None:
    temporary = pointer.with_name(pointer.name + ".tmp")
    temporary.write_text(value + "\n", encoding="ascii")
    _fsync_file(temporary)
    _durable_replace(temporary, pointer)


def _write_journal(journal: Path, payload: dict[str, str]) -> None:
    """Publish a journal atomically so a crash leaves old or new JSON."""
    temporary = journal.with_name(journal.name + ".tmp")
    temporary.write_bytes(_canonical(payload))
    _fsync_file(temporary)
    _durable_replace(temporary, journal)


def _recover_install(catalog_dir: Path) -> None:
    """Recover only from a manifest-verified immutable snapshot."""
    journal = _journal_path(catalog_dir)
    staged = catalog_dir.parent / f".{catalog_dir.name}.staged"
    try:
        valid = dict(_verified_snapshots(catalog_dir))
        pointer = _read_pointer(catalog_dir)
        selected = valid.get(pointer) if pointer else None
        legacy = catalog_dir.parent / f".{catalog_dir.name}.previous"
        active_valid = False
        if catalog_dir.is_dir():
            try:
                _verify_snapshot(catalog_dir)
                active_valid = True
            except SnapshotError:
                pass
        active_identity = _snapshot_identity(catalog_dir) if active_valid else None
        if selected is None and active_identity is not None:
            selected = valid.get(active_identity)
        # A valid durable pointer is authoritative.  Compatibility trees are
        # merely candidates and must never disqualify the selected immutable
        # snapshot (or cause it to be quarantined).
        if selected is None and valid:
            # A stale/corrupt pointer does not make surviving verified
            # snapshots unavailable.  Directory names are content identities;
            # sorting gives recovery deterministic behavior.
            selected = valid[sorted(valid)[0]]
        if selected is None and not active_valid and legacy.is_dir():
            try:
                _verify_snapshot(legacy)
                identity = _snapshot_identity(legacy)
                if selected is None:
                    root = _verified_root(catalog_dir)
                    root.mkdir(parents=True, exist_ok=True)
                    _fsync_directory(root.parent)
                    migrated = root / identity
                    if not migrated.exists():
                        _copy_verified(legacy, migrated)
                    selected = migrated
            except (OSError, SnapshotError):
                # Do not clear a previously selected pointer target.  The
                # legacy tree is untrusted compatibility material.
                pass
        active_matches_selected = active_valid and selected is not None and active_identity == selected.name
        if not active_matches_selected:
            if selected is None:
                raise SnapshotError("no verified catalog snapshot available")
            replacement = catalog_dir.with_name(catalog_dir.name + ".recovery-staged")
            _quarantine(replacement, "recovery")
            _copy_verified(selected, replacement)
            if catalog_dir.exists():
                _quarantine(catalog_dir, "recovery-replaced")
            _durable_replace(replacement, catalog_dir)
        if selected is not None and _read_pointer(catalog_dir) != selected.name:
            _publish_pointer(_pointer_path(catalog_dir), selected.name)
        if staged.exists():
            _quarantine(staged, "interrupted")
        _durable_unlink(journal)
    except SnapshotError:
        raise
    except OSError as exc:
        raise SnapshotError("catalog install recovery failed") from exc


def install_snapshot(snapshot: Path, catalog_dir: Path) -> None:
    """Install through immutable verified snapshots and an atomic switch-over."""
    snapshot = snapshot.resolve()
    catalog_dir = catalog_dir.resolve()
    with _install_lock(catalog_dir):
        if catalog_dir.exists() or _verified_root(catalog_dir).exists():
            _recover_install(catalog_dir)
        _verify_snapshot(snapshot)
        parent = catalog_dir.parent
        root = _verified_root(catalog_dir)
        root.mkdir(parents=True, exist_ok=True)
        _fsync_directory(root.parent)
        staging = parent / f".{catalog_dir.name}.staged"
        _quarantine(staging, "replaced")
        identity = _snapshot_identity(snapshot)
        verified = root / identity
        journal = _journal_path(catalog_dir)
        try:
            _write_journal(journal, {"catalog": catalog_dir.name, "state": "staging", "snapshot": identity})
            _copy_verified(snapshot, staging)
            if verified.exists():
                # The existing directory is immutable verified evidence.  It
                # is already the desired content-addressed result, so retain
                # it and discard only the newly copied candidate.
                _verify_snapshot(verified)
                _quarantine(staging, "duplicate")
            else:
                _durable_replace(staging, verified)
            _write_journal(journal, {"catalog": catalog_dir.name, "state": "verified", "snapshot": identity})
            live = parent / f".{catalog_dir.name}.live-staged"
            _quarantine(live, "replaced")
            _copy_verified(verified, live)
            if catalog_dir.exists():
                legacy = parent / f".{catalog_dir.name}.previous"
                _quarantine(legacy, "superseded")
                try:
                    _verify_snapshot(catalog_dir)
                except SnapshotError:
                    # Preserve corrupt evidence under a unique quarantine name;
                    # it is never allowed to become the LKG.
                    _quarantine(catalog_dir, "corrupt-active")
                else:
                    _durable_replace(catalog_dir, legacy)
            _durable_replace(live, catalog_dir)
            _write_journal(journal, {"catalog": catalog_dir.name, "state": "switched", "snapshot": identity})
            _publish_pointer(_pointer_path(catalog_dir), identity)
            _durable_unlink(journal)
        except BaseException as exc:
            if staging.exists():
                _quarantine(staging, "failed")
            if not catalog_dir.exists() and not isinstance(exc, (KeyboardInterrupt, SystemExit)):
                with suppress(SnapshotError):
                    _recover_install(catalog_dir)
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            raise SnapshotError("catalog install failed") from None


def rollback_catalog(catalog_dir: Path) -> None:
    catalog_dir = catalog_dir.resolve()
    with _install_lock(catalog_dir):
        _recover_install(catalog_dir)
        valid = _verified_snapshots(catalog_dir)
        current = _read_pointer(catalog_dir)
        previous = None
        legacy = catalog_dir.parent / f".{catalog_dir.name}.previous"
        if legacy.is_dir():
            try:
                _verify_snapshot(legacy)
                legacy_identity = _snapshot_identity(legacy)
            except SnapshotError:
                legacy_identity = None
            if legacy_identity and legacy_identity != current:
                previous = next(((identity, path) for identity, path in valid if identity == legacy_identity), None)
        if previous is None:
            previous = next(((identity, path) for identity, path in valid if identity != current), None)
        if previous is None:
            raise SnapshotError("no last-known-good catalog")
        identity, verified = previous
        live = catalog_dir.parent / f".{catalog_dir.name}.rollback-live"
        _quarantine(live, "replaced")
        _copy_verified(verified, live)
        if catalog_dir.exists():
            _quarantine(catalog_dir, "rollback-old")
        _durable_replace(live, catalog_dir)
        _publish_pointer(_pointer_path(catalog_dir), identity)
        _durable_unlink(_journal_path(catalog_dir))


def load_catalog_with_fallback(catalog_dir: Path) -> Catalog:
    """Load the installed catalog, falling back to the verified previous tree."""
    catalog_dir = catalog_dir.resolve()
    with _install_lock(catalog_dir):
        _recover_install(catalog_dir)
        try:
            return load_catalog(catalog_dir)
        except (OSError, ValueError):
            valid = dict(_verified_snapshots(catalog_dir))
            pointer = _read_pointer(catalog_dir)
            if pointer not in valid:
                raise SnapshotError("no verified catalog snapshot available") from None
            return load_catalog(valid[pointer])


def public_catalog_payload(catalog: Catalog) -> dict[str, Any]:
    """Return the exact reviewed public release shape, with no private state."""
    relationships = []
    for relationship in catalog.relationships:
        relationships.append({
            "id": relationship.id, "from_offering_id": relationship.from_offering_id,
            "to_offering_id": relationship.to_offering_id, "relationship_type": relationship.relationship_type,
            "effective_from": relationship.effective_from.isoformat() if relationship.effective_from else None,
            "effective_to": relationship.effective_to.isoformat() if relationship.effective_to else None,
            "review_state": relationship.review_state,
            "evidence": [{"id": e.id, "source_policy_class": e.source_policy_class, "source_tier": e.source_tier,
                          "source_url": e.url, "content_sha256": e.content_sha256, "retrieved_at": e.retrieved_at.isoformat(),
                          "confidence": e.confidence, "review_state": e.review_state} for e in relationship.evidence],
        })
    return {
        "release": {"schema_version": catalog.release.schema_version, "release_id": catalog.release.release_id,
                    "generated_at": catalog.release.generated_at.isoformat(), "market_scope": list(catalog.release.market_scope)},
        "offerings": [o.__dict__ | {"aliases": list(o.aliases), "effective_from": o.effective_from.isoformat() if o.effective_from else None,
                                    "effective_to": o.effective_to.isoformat() if o.effective_to else None} for o in catalog.offerings],
        "benefits": [{"id": b.id, "offering_id": b.offering_id, "benefit_type": b.benefit_type, "title": b.title,
                      "status": b.status, "review_tier": b.review_tier, "rule_version": b.rule_version,
                      "effective_from": b.effective_from.isoformat() if b.effective_from else None,
                      "effective_to": b.effective_to.isoformat() if b.effective_to else None,
                      "eligibility": list(b.eligibility), "allowance": b.allowance,
                      "quantities": [
                          {
                              "metric": quantity.metric,
                              "value": quantity.value,
                              "unit": quantity.unit,
                              "basis": quantity.basis,
                              "scope": quantity.scope,
                              "period": quantity.period,
                              "cap": quantity.cap,
                          }
                          for quantity in b.quantities
                      ],
                      "conflicts_with": list(b.conflicts_with),
                      "evidence": [{"id": e.id, "source_policy_class": e.source_policy_class, "source_tier": e.source_tier,
                                    "source_url": e.url, "content_sha256": e.content_sha256, "retrieved_at": e.retrieved_at.isoformat(),
                                    "confidence": e.confidence, "review_state": e.review_state} for e in b.evidence]} for b in catalog.benefits],
        "relationships": relationships,
    }


def export_public_catalog(catalog_dir: Path, destination: Path) -> Path:
    catalog = load_catalog(catalog_dir)
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    _fsync_directory(destination.parent)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_bytes(_canonical(public_catalog_payload(catalog)))
    _fsync_file(temporary)
    _durable_replace(temporary, destination)
    return destination
