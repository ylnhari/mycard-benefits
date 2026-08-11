"""Clone-safe application configuration with no secret-value logging."""

from __future__ import annotations

import contextlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from . import data_location
from .portlib import resolve_port

APP_ID = "mycard-benefits"
API_VERSION = "v1"
DEFAULT_PORT = 8777
USER_DATA_DIRECTORY_NAME = "MyCard Benefits"
REMEMBERED_LOCATION_FILENAME = "selected-data-location.json"
PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parents[1]


def _load_local_env() -> None:
    """Load the repository .env without overriding the process environment."""
    if os.environ.get("MYCARD_BENEFITS_NO_DOTENV") == "1":
        return
    path = REPO_ROOT / ".env"
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_local_env()


def _absolute_lexical(path: Path) -> Path:
    """Anchor and normalize a path without consulting the filesystem."""

    return data_location.lexical_absolute(path)


def user_data_root() -> Path:
    """Return the stable per-user application-data root.

    This is configuration state, not vault state. It is intentionally kept
    outside the checkout so a fresh clone cannot silently select repository
    data as a user's normal vault.
    """

    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / USER_DATA_DIRECTORY_NAME
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / USER_DATA_DIRECTORY_NAME
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home) / "mycard-benefits"
    return Path.home() / ".local" / "share" / "mycard-benefits"


def _remembered_location_path() -> Path:
    return user_data_root() / REMEMBERED_LOCATION_FILENAME


def load_remembered_data_dir() -> Path | None:
    """Read a local, value-free pointer to a deliberately selected data root.

    Malformed, inaccessible, relative, or reparse-backed pointers are ignored
    without surfacing their contents. The file is never part of the repository
    and its value never crosses an HTTP or logging boundary.
    """

    try:
        root = data_location.reject_reparse(user_data_root(), allow_missing=True)
        path = data_location.reject_reparse(root / REMEMBERED_LOCATION_FILENAME)
        if not data_location.existing_regular_file(path):
            return None
        payload = json.loads(
            data_location.read_guarded_bytes(path, maximum=4096).decode("utf-8")
        )
        if not isinstance(payload, dict) or set(payload) != {"version", "data_dir"}:
            return None
        if payload["version"] != 1 or not isinstance(payload["data_dir"], str):
            return None
        selected = Path(payload["data_dir"])
        if not selected.is_absolute():
            return None
        return data_location.validate_data_root(selected)
    except (OSError, TypeError, ValueError, UnicodeError, data_location.DataLocationError):
        return None


def remember_data_dir(data_dir: Path) -> None:
    """Persist only the local pointer needed to rediscover a selected root."""

    selected = data_location.validate_data_root(_absolute_lexical(data_dir))
    root = data_location.reject_reparse(user_data_root(), allow_missing=True)
    payload = json.dumps(
        {"version": 1, "data_dir": str(selected)},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    temporary = root / f".{REMEMBERED_LOCATION_FILENAME}.{os.getpid()}.tmp"
    try:
        data_location.data_location_checkpoint("before-pointer-root-create", root)
        data_location.reject_reparse(root, allow_missing=True)
        root.mkdir(parents=True, exist_ok=True)
        data_location.reject_reparse(root)
        data_location.reject_reparse(temporary, allow_missing=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(temporary, flags, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                descriptor = -1
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        destination = root / REMEMBERED_LOCATION_FILENAME
        data_location.data_location_checkpoint("before-pointer-replace", destination)
        data_location.reject_reparse(root)
        data_location.reject_reparse(destination, allow_missing=True)
        os.replace(temporary, destination)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    catalog_dir: Path
    port: int
    demo: bool = False
    ntfy_enabled: bool = False

    @classmethod
    def from_environment(
        cls,
        *,
        explicit_port: int | None = None,
        explicit_data_dir: str | Path | None = None,
        demo: bool = False,
        resolve_data_dir: bool = True,
    ) -> Settings:
        """Build settings, optionally preserving a caller's lexical data root.

        Normal application configuration continues to canonicalize its data
        directory.  Maintenance boundaries that must inspect reparse points
        first can disable that normalization and pass the resulting lexical
        path to their own guarded validator.
        """
        configured_data = explicit_data_dir or os.environ.get("MYCARD_BENEFITS_DATA_DIR")
        if configured_data:
            data_dir = _absolute_lexical(Path(configured_data).expanduser())
            data_dir = data_location.validate_data_root(data_dir)
        elif demo:
            data_dir = data_location.validate_data_root(REPO_ROOT / "demo-data")
        else:
            data_dir = load_remembered_data_dir() or data_location.validate_data_root(user_data_root())
        port = resolve_port(
            APP_ID,
            explicit=explicit_port,
            env_var="MYCARD_BENEFITS_PORT",
            default=DEFAULT_PORT,
            start=REPO_ROOT,
        )
        catalog_dir = (REPO_ROOT / "catalog").resolve()
        if not catalog_dir.is_dir():
            catalog_dir = (PACKAGE_ROOT / "catalog_data").resolve()
        return cls(
            data_dir=data_dir,
            catalog_dir=catalog_dir,
            port=port,
            demo=demo,
            ntfy_enabled=os.environ.get("MYCARD_BENEFITS_NTFY_ENABLED", "0") == "1",
        )
