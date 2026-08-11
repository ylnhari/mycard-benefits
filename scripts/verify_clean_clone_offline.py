"""Verify a clean clone using only an already-populated local uv cache.

This is deliberately an offline verification, not a claim that dependencies
can be downloaded without a network. ``uv sync --offline`` fails honestly if
the local cache is cold or incomplete.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def _run(command: list[str], *, cwd: Path, env: dict[str, str]) -> None:
    print("+", " ".join(command))
    completed = subprocess.run(command, cwd=cwd, env=env, check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)


def _output(command: list[str], *, cwd: Path) -> str:
    return subprocess.check_output(command, cwd=cwd, text=True).strip()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the clean-clone quality gates offline")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    repository = Path(_output(["git", "rev-parse", "--show-toplevel"], cwd=args.repo))
    if _output(["git", "status", "--porcelain"], cwd=repository):
        raise SystemExit("Refuse to verify a dirty tree; commit or discard changes first.")
    uv = shutil.which("uv")
    node = shutil.which("node")
    if uv is None or node is None:
        raise SystemExit("Both uv and node must already be available on PATH.")

    with tempfile.TemporaryDirectory(prefix="mycard-benefits-offline-") as temporary:
        temporary_root = Path(temporary)
        clone = temporary_root / "clone"
        _run(
            ["git", "clone", "--local", "--no-hardlinks", str(repository), str(clone)],
            cwd=temporary_root,
            env=dict(os.environ),
        )
        if (clone / ".env").exists():
            raise SystemExit("Clean clone unexpectedly contains .env; refusing to inspect it.")
        environment = dict(os.environ)
        environment.pop("VIRTUAL_ENV", None)
        environment["MYCARD_BENEFITS_NO_DOTENV"] = "1"
        _run([uv, "sync", "--offline", "--frozen", "--all-groups"], cwd=clone, env=environment)
        for command in (
            [uv, "run", "--offline", "--no-sync", "ruff", "check", "."],
            [uv, "run", "--offline", "--no-sync", "mypy", "src"],
            [uv, "run", "--offline", "--no-sync", "pytest", "-q"],
            [node, "--check", "src/mycard_benefits/static/app.js"],
            [uv, "build", "--offline"],
        ):
            _run(command, cwd=clone, env=environment)
    print("Clean-clone offline verification passed with the existing local dependency cache.")


if __name__ == "__main__":
    main()
