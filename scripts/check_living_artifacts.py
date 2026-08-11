"""Check the repository's same-change living-artifact contract locally."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

DECLARED_LIVING = {
    "PRODUCT_REQUIREMENTS.md",
    "ROADMAP.md",
    "PROJECT_STATUS.md",
    "DECISIONS.md",
    "docs/DECISION-TRACE.md",
    "docs/QUESTIONNAIRE-DECISIONS.md",
    "docs/IDEA-LOG.md",
    "coordination/events.jsonl",
    "coordination/jobs.jsonl",
}
APPEND_ONLY = {"coordination/events.jsonl", "coordination/jobs.jsonl"}
# Compatibility alias for local callers that used the prior registry name.
LIVING = DECLARED_LIVING | APPEND_ONLY
IMPLEMENTATION_PREFIXES = ("src/", "catalog/", "scripts/", "tests/", ".github/")
IMPLEMENTATION_FILES = {
    "dashboard.html",
    "pyproject.toml",
    "uv.lock",
    "README.md",
    "CONTRIBUTING.md",
}


def git(*args: str) -> list[str]:
    output = subprocess.check_output(["git", *args], text=True, encoding="utf-8", stderr=subprocess.STDOUT)
    return [line for line in output.splitlines() if line]


def _append_only_paths(*commits: str) -> set[str]:
    """Discover append-only coordination records from both target trees."""

    return {
        Path(path).as_posix()
        for commit in commits
        for path in git("ls-tree", "-r", "--name-only", commit, "--", "coordination")
        if Path(path).suffix == ".jsonl"
    }


def findings_for(changed: set[str], existing: set[str], append_only: set[str] | None = None) -> list[str]:
    findings: list[str] = []
    append_only = APPEND_ONLY if append_only is None else append_only
    missing = sorted((DECLARED_LIVING | append_only) - existing)
    if missing:
        findings.append("missing living artifacts: " + ", ".join(missing))
    implementation_changed = any(
        path.startswith(IMPLEMENTATION_PREFIXES)
        or path in IMPLEMENTATION_FILES
        or path.startswith("coordination/contributions/")
        for path in changed
    )
    living_changed = changed & (DECLARED_LIVING | append_only)
    if implementation_changed and not living_changed:
        findings.append("implementation changes must update a living artifact in the same range")
    return findings


def _tree_text(commit: str, path: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "show", f"{commit}:{path}"],
            text=True,
            encoding="utf-8",
            stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError:
        return None


def append_only_findings(base: str, head: str, paths: set[str]) -> list[str]:
    """Require each declared JSONL coordination record to be append-only."""

    findings: list[str] = []
    for path in sorted(paths):
        previous = _tree_text(base, path) or ""
        current = _tree_text(head, path)
        if current is None:
            continue
        if previous and not current.startswith(previous):
            findings.append(f"append-only artifact was altered before its prior end: {path}")
        try:
            lines = current.splitlines()
            for line_number in range(1, len(lines) + 1):
                line = lines[line_number - 1]
                json.loads(line)
        except json.JSONDecodeError:
            findings.append(f"append-only artifact is not valid JSONL: {path}:{line_number}")
    return findings


def existing_at(commit: str, paths: set[str]) -> set[str]:
    return {path for path in paths if _tree_text(commit, path) is not None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="local base commit; no fetch is performed")
    parser.add_argument("--head", default="HEAD", help="local head commit; defaults to HEAD")
    args = parser.parse_args()
    try:
        changed = set(git("diff", "--name-only", f"{args.base}..{args.head}"))
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"FAIL unable to inspect local range: {exc.__class__.__name__}")
        return 1
    append_only = _append_only_paths(args.base, args.head)
    registry = DECLARED_LIVING | append_only
    findings = findings_for(
        changed,
        existing_at(args.head, registry),
        append_only,
    )
    findings.extend(append_only_findings(args.base, args.head, append_only))
    living_changed = changed & (DECLARED_LIVING | append_only)
    if findings:
        for finding in findings:
            print("FAIL " + finding)
        return 1
    print(f"PASS living artifacts ({len(living_changed)} changed in range)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
