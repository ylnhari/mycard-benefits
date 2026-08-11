"""Fail-closed SQLite reads for public, side-effect-free surfaces.

SQLite can modify a ``-shm`` file while opening a WAL-mode database with a
normal read-only connection. ``immutable=1`` avoids every source-side write,
but intentionally ignores WAL pages. Public read paths therefore use only
immutable connections, and only while a before/after source generation check
proves that the main database stayed stable and no WAL or SHM sidecar existed.
"""

from __future__ import annotations

import os
import sqlite3
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote


@dataclass(frozen=True)
class _SourceGeneration:
    """The filesystem identity needed to reject an unstable SQLite source."""

    device: int
    inode: int
    size: int
    modified_ns: int
    changed_ns: int


def _source_generation(
    path: Path, *, allow_missing: bool = False
) -> _SourceGeneration | None:
    """Capture one WAL-free regular-file generation or fail closed.

    ``allow_missing`` is reserved for a whole-response guard: an absent
    database remains a valid empty public response only while it stays absent.
    """
    try:
        source = os.lstat(path)
    except FileNotFoundError as exc:
        if allow_missing:
            _assert_no_sidecars(path)
            return None
        raise sqlite3.DatabaseError("SQLite database is unavailable") from exc
    except OSError as exc:
        raise sqlite3.DatabaseError("SQLite database is unavailable") from exc

    if stat.S_ISLNK(source.st_mode) or not stat.S_ISREG(source.st_mode) or source.st_size <= 0:
        raise sqlite3.DatabaseError("SQLite database is unavailable or empty")

    _assert_no_sidecars(path)

    return _SourceGeneration(
        device=source.st_dev,
        inode=source.st_ino,
        size=source.st_size,
        modified_ns=source.st_mtime_ns,
        changed_ns=source.st_ctime_ns,
    )


def _assert_no_sidecars(path: Path) -> None:
    """Reject any sidecar without opening it or changing source state."""
    for suffix in ("-wal", "-shm"):
        try:
            os.lstat(path.with_name(f"{path.name}{suffix}"))
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise sqlite3.DatabaseError("SQLite database sidecar is unavailable") from exc
        raise sqlite3.DatabaseError("SQLite source has an active WAL or SHM sidecar")


def _immutable_uri(path: Path) -> str:
    """Build an immutable URI only after the source generation was captured."""
    uri_path = quote(str(path.absolute().as_posix()), safe="/:")
    return f"file:{uri_path}?mode=ro&immutable=1"


@contextmanager
def read_only_sqlite_connection(path: Path) -> Iterator[sqlite3.Connection]:
    """Open a source-side-effect-free SQLite connection or raise ``DatabaseError``.

    The source is checked before opening, so no WAL/SHM source is ever handed
    to SQLite. It is checked again after closing, which rejects a WAL created
    between preflight and the immutable read as well as replacement or mutation
    of the main file during the read. Callers must surface this as unavailable,
    never as a possibly stale success response.
    """
    before = _source_generation(path)
    assert before is not None
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(_immutable_uri(path), uri=True)
        yield connection
    finally:
        if connection is not None:
            connection.close()
        after = _source_generation(path)
        assert after is not None
        if after != before:
            raise sqlite3.DatabaseError("SQLite source changed during read")


@contextmanager
def read_only_sqlite_snapshot(*paths: Path) -> Iterator[None]:
    """Reject a public response if any of its SQLite sources changes in flight.

    ``read_only_sqlite_connection`` protects each immutable connection. Public
    endpoints that compose a response over several connections also use this
    guard, so replacing a database between otherwise individually-safe reads
    cannot produce a mixed-generation success response. Missing databases are
    allowed only when they remain absent for the full logical read.
    """
    if not paths:
        raise ValueError("at least one SQLite source is required")
    before = tuple(_source_generation(path, allow_missing=True) for path in paths)
    try:
        yield
    finally:
        after = tuple(_source_generation(path, allow_missing=True) for path in paths)
        if after != before:
            raise sqlite3.DatabaseError("SQLite source changed during public read")
