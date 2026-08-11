"""Lexical, reparse-safe paths for local application data."""

from __future__ import annotations

import os
import stat
from pathlib import Path

_FILE_ATTRIBUTE_REPARSE_POINT = 0x400


class DataLocationError(RuntimeError):
    """A local path cannot be used without following an unsafe component."""


def lexical_absolute(path: str | Path) -> Path:
    """Normalize a path lexically without consulting or following the filesystem."""

    value = Path(os.path.abspath(os.fspath(path)))
    if not value.is_absolute():
        raise DataLocationError("data location is unavailable")
    return value


def data_location_checkpoint(_phase: str, _path: Path) -> None:
    """Synthetic race-test seam; production performs no additional action."""


def reject_reparse(path: str | Path, *, allow_missing: bool = False) -> Path:
    """Reject symlinks, junctions, and reparse points in every existing prefix.

    The walk is lexical and uses ``lstat``. It never calls ``resolve``. Missing
    trailing components are allowed only when the caller explicitly permits a
    not-yet-created target.
    """

    value = lexical_absolute(path)
    current = Path(value.anchor)
    parts = value.relative_to(value.anchor).parts
    for part in parts:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            if allow_missing:
                break
            raise DataLocationError("data location is unavailable") from None
        except OSError:
            raise DataLocationError("data location is unavailable") from None
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT:
            raise DataLocationError("data location is unavailable")
    return value


def existing_regular_file(path: str | Path) -> bool:
    """Return whether a guarded path is an existing regular file."""

    # A missing vault is a valid first-run state.  Continue checking every
    # existing prefix for reparses, but do not turn an absent trailing target
    # into a generic unsafe-location failure.
    value = reject_reparse(path, allow_missing=True)
    try:
        return stat.S_ISREG(value.lstat().st_mode)
    except FileNotFoundError:
        return False
    except OSError:
        raise DataLocationError("data location is unavailable") from None


def read_guarded_bytes(path: str | Path, *, maximum: int) -> bytes:
    """Read a regular file through a no-follow descriptor where supported."""

    value = reject_reparse(path)
    data_location_checkpoint("before-read", value)
    reject_reparse(value)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(value, flags)
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            data = handle.read(maximum + 1)
    except (OSError, ValueError):
        raise DataLocationError("data location is unavailable") from None
    finally:
        if "descriptor" in locals() and descriptor >= 0:
            os.close(descriptor)
    if len(data) > maximum:
        raise DataLocationError("data location is too large")
    return data


def validate_data_root(data_dir: str | Path) -> Path:
    """Validate a data root, its private child, and its vault target."""

    root = reject_reparse(data_dir, allow_missing=True)
    reject_reparse(root / "private", allow_missing=True)
    reject_reparse(root / "private" / "vault.json", allow_missing=True)
    reject_reparse(root / "private" / "device-key", allow_missing=True)
    return root


def vault_path_for_data_dir(data_dir: str | Path) -> Path:
    """Return the lexical vault path after validating its complete hierarchy."""

    root = validate_data_root(data_dir)
    return root / "private" / "vault.json"


def device_key_path_for_data_dir(data_dir: str | Path) -> Path:
    """Return the guarded local fallback path for the device-held vault key."""

    root = validate_data_root(data_dir)
    return root / "private" / "device-key"
