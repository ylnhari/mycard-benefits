"""Verify that the committed quality workflow keeps its offline boundaries."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_strict_mypy_is_configured_and_required_by_fixture_ci() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["tool"]["mypy"]["strict"] is True

    workflow = (ROOT / ".github" / "workflows" / "fixture-quality.yml").read_text(
        encoding="utf-8"
    )
    assert "uv run --no-sync mypy src" in workflow
    assert "MYCARD_BENEFITS_NO_DOTENV" in workflow
    assert "MYCARD_BENEFITS_LIVE_CHECKS: \"0\"" in workflow


def test_fixture_ci_and_opt_in_live_checks_are_separate() -> None:
    fixture_workflow = (ROOT / ".github" / "workflows" / "fixture-quality.yml").read_text(
        encoding="utf-8"
    )
    live_workflow = (ROOT / ".github" / "workflows" / "live-source-checks.yml").read_text(
        encoding="utf-8"
    )
    live_harness = (ROOT / "scripts" / "check_live_sources.py").read_text(encoding="utf-8")

    assert "workflow_dispatch" not in fixture_workflow
    assert "check_live_sources.py" not in fixture_workflow
    assert "workflow_dispatch" in live_workflow
    assert "continue-on-error: true" in live_workflow
    assert "inputs.run_live_source_checks == true" in live_workflow
    assert "MYCARD_BENEFITS_ENABLE_LIVE_CHECKS" in live_harness
    assert "No live source adapter is registered" in live_harness


def test_clean_clone_verifier_is_explicitly_offline_and_cache_honest() -> None:
    verifier = (ROOT / "scripts" / "verify_clean_clone_offline.py").read_text(encoding="utf-8")
    assert '"git", "clone", "--local", "--no-hardlinks"' in verifier
    assert '"sync", "--offline", "--frozen", "--all-groups"' in verifier
    assert verifier.count('"--offline"') >= 5
    assert "local cache is cold or incomplete" in verifier
    assert "pip install" not in verifier


def test_governance_workflow_uses_exact_living_artifact_range() -> None:
    workflow = (ROOT / ".github" / "workflows" / "governance.yml").read_text(encoding="utf-8")
    assert 'check_living_artifacts.py --base "$BASE_SHA" --head "$HEAD_SHA"' in workflow
