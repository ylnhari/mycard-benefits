"""Deterministic offline dependency audit; unavailable scanners are explicit."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    lock = root / "uv.lock"
    result = {"lockfile": lock.name, "locked": lock.is_file(), "scanners": {}}
    for scanner in ("pip-audit", " osv-scanner"):
        name = scanner.strip()
        try:
            completed = subprocess.run([name, "--version"], capture_output=True, text=True, check=False)
            result["scanners"][name] = "available" if completed.returncode == 0 else "unavailable"
        except OSError:
            result["scanners"][name] = "unavailable"
    result["offline"] = True
    print(json.dumps(result, sort_keys=True))
    return 0 if result["locked"] else 1


if __name__ == "__main__":
    sys.exit(main())
