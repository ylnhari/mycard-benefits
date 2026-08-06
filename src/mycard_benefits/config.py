"""Clone-safe application configuration with no secret-value logging."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .portlib import resolve_port

APP_ID = "mycard-benefits"
API_VERSION = "v1"
DEFAULT_PORT = 8777
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


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    catalog_dir: Path
    port: int
    demo: bool = False

    @classmethod
    def from_environment(
        cls,
        *,
        explicit_port: int | None = None,
        explicit_data_dir: str | Path | None = None,
        demo: bool = False,
    ) -> Settings:
        configured_data = explicit_data_dir or os.environ.get("MYCARD_BENEFITS_DATA_DIR")
        if configured_data:
            data_dir = Path(configured_data).expanduser().resolve()
        else:
            data_dir = (REPO_ROOT / ("demo-data" if demo else "data")).resolve()
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
        )
