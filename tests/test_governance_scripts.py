from __future__ import annotations

import runpy
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "check_living_artifacts.py"


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_living_artifact_check_has_positive_and_negative_cases() -> None:
    living = runpy.run_path(str(SCRIPT))
    changed = {"dashboard.html"}
    assert living["findings_for"](changed, set(living["LIVING"]))
    assert not living["findings_for"](changed | {"PROJECT_STATUS.md"}, set(living["LIVING"]))
    assert "coordination/jobs.jsonl" in living["LIVING"]
    assert "coordination/tasks/LUNA-GOVERNANCE-CI-BATCH.md" not in living["LIVING"]
    assert living["findings_for"](
        set(), {path for path in living["LIVING"] if path != "coordination/jobs.jsonl"}
    )


def test_append_only_living_artifact_rejects_history_rewrite(tmp_path: Path, monkeypatch) -> None:
    living = runpy.run_path(str(SCRIPT))
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "synthetic@example.invalid")
    _git(tmp_path, "config", "user.name", "Synthetic Test")
    path = tmp_path / "coordination"
    path.mkdir()
    record = '{"event":"original"}\n'
    (path / "jobs.jsonl").write_text(record, encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    (path / "jobs.jsonl").write_text('{"event":"rewritten"}\n' + record, encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "rewrite")
    head = _git(tmp_path, "rev-parse", "HEAD")
    monkeypatch.chdir(tmp_path)
    findings = living["append_only_findings"](base, head, {"coordination/jobs.jsonl"})
    assert "altered before its prior end" in findings[0]


def test_base_only_jsonl_deletion_fails_closed(tmp_path: Path) -> None:
    living = runpy.run_path(str(SCRIPT))
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "synthetic@example.invalid")
    _git(tmp_path, "config", "user.name", "Synthetic Test")
    for relative_path in sorted(living["DECLARED_LIVING"]):
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            '{"event":"base"}\n' if path.suffix == ".jsonl" else "synthetic\n",
            encoding="utf-8",
        )
    deleted_path = tmp_path / "coordination" / "preexisting.jsonl"
    deleted_path.write_text('{"event":"preexisting"}\n', encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base with preexisting record")
    base = _git(tmp_path, "rev-parse", "HEAD")
    deleted_path.unlink()
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "delete append-only record")
    head = _git(tmp_path, "rev-parse", "HEAD")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--base", base, "--head", head],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "missing living artifacts: coordination/preexisting.jsonl" in result.stdout


def test_head_only_jsonl_is_checked_from_target_tree(tmp_path: Path) -> None:
    living = runpy.run_path(str(SCRIPT))
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "synthetic@example.invalid")
    _git(tmp_path, "config", "user.name", "Synthetic Test")
    for relative_path in sorted(living["DECLARED_LIVING"]):
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"event":"base"}\n' if path.suffix == ".jsonl" else "synthetic\n", encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")
    new_jsonl = tmp_path / "coordination" / "head-only.jsonl"
    new_jsonl.write_text('{"event":\n', encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "hostile head-only record")
    head = _git(tmp_path, "rev-parse", "HEAD")
    new_jsonl.unlink()

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--base", base, "--head", head],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "append-only artifact is not valid JSONL: coordination/head-only.jsonl:1" in result.stdout


def test_existing_jsonl_unchanged_and_appended_records_pass(tmp_path: Path) -> None:
    living = runpy.run_path(str(SCRIPT))
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.email", "synthetic@example.invalid")
    _git(tmp_path, "config", "user.name", "Synthetic Test")
    for relative_path in sorted(living["DECLARED_LIVING"]):
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            '{"event":"base"}\n' if path.suffix == ".jsonl" else "synthetic\n",
            encoding="utf-8",
        )
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "base")
    base = _git(tmp_path, "rev-parse", "HEAD")

    unchanged = subprocess.run(
        [sys.executable, str(SCRIPT), "--base", base, "--head", base],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert unchanged.returncode == 0
    assert "PASS living artifacts (0 changed in range)" in unchanged.stdout

    jobs_path = tmp_path / "coordination" / "jobs.jsonl"
    jobs_path.write_text('{"event":"base"}\n{"event":"appended"}\n', encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-m", "append record")
    head = _git(tmp_path, "rev-parse", "HEAD")
    appended = subprocess.run(
        [sys.executable, str(SCRIPT), "--base", base, "--head", head],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert appended.returncode == 0
    assert "PASS living artifacts (1 changed in range)" in appended.stdout
