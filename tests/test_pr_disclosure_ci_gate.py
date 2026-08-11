"""Counterpart-review remediation (P1 finding 1): MC-096's disclosure
validator must actually gate a PR, not just exist as an importable function.

These tests execute `scripts/validate_pr_disclosure.py`'s parsing/validation
logic directly (the same functions `.github/workflows/pr-disclosure-check.yml`
calls in CI) against realistic PR-body strings, including the literal
unfilled `.github/PULL_REQUEST_TEMPLATE.md` content, which must fail closed.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from mycard_benefits.catalog.contribution import ContributionValidationError

ROOT = Path(__file__).parents[1]


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("validate_pr_disclosure", ROOT / "scripts" / "validate_pr_disclosure.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCRIPT = _load_script()

VALID_BODY = """
## Summary

Fixes a typo.

## Contribution disclosure (sources and conflict of interest)

```yaml
summary: "SYNTHETIC-ONLY fix a typo in the benefit description"
primary_sources:
  - "https://example.invalid/synthetic-terms"
has_conflict_of_interest: false
conflict_of_interest_detail: null
uses_only_synthetic_or_public_fixtures: true
```

## Checklist
- [x] done
"""


def test_a_correctly_filled_pr_body_validates() -> None:
    SCRIPT.validate_pr_body(VALID_BODY)  # must not raise


def test_the_literal_unfilled_pull_request_template_fails_closed() -> None:
    template = (ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md").read_text(encoding="utf-8")
    with pytest.raises(ContributionValidationError):
        SCRIPT.validate_pr_body(template)


def test_a_pr_body_with_no_yaml_block_fails_closed_with_a_clear_message() -> None:
    with pytest.raises(ContributionValidationError, match="no fenced"):
        SCRIPT.validate_pr_body("Just a plain description with no disclosure block at all.")


def test_malformed_yaml_fails_closed() -> None:
    body = """
```yaml
summary: "unterminated
primary_sources: [
```
"""
    with pytest.raises(ContributionValidationError, match="not valid YAML"):
        SCRIPT.validate_pr_body(body)


def test_a_disclosed_conflict_of_interest_without_detail_fails_closed() -> None:
    body = VALID_BODY.replace("has_conflict_of_interest: false", "has_conflict_of_interest: true")
    with pytest.raises(ContributionValidationError, match="conflict_of_interest_detail is required"):
        SCRIPT.validate_pr_body(body)


def test_a_properly_disclosed_conflict_of_interest_still_validates() -> None:
    body = VALID_BODY.replace("has_conflict_of_interest: false", "has_conflict_of_interest: true").replace(
        "conflict_of_interest_detail: null",
        'conflict_of_interest_detail: "SYNTHETIC-ONLY I am employed by the issuer named in this PR"',
    )
    SCRIPT.validate_pr_body(body)  # must not raise


def test_cli_entry_point_exits_non_zero_and_prints_the_reason_on_stderr() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_pr_disclosure.py")],
        input="No disclosure block here.",
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    assert result.returncode != 0
    assert "contribution disclosure invalid" in result.stderr


def test_cli_entry_point_exits_zero_on_a_valid_disclosure() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_pr_disclosure.py")],
        input=VALID_BODY,
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    assert result.returncode == 0
    assert "valid" in result.stdout


def test_workflow_invokes_the_script_and_never_shell_interpolates_the_pr_body() -> None:
    workflow = (ROOT / ".github" / "workflows" / "pr-disclosure-check.yml").read_text(encoding="utf-8")
    assert "validate_pr_disclosure.py" in workflow
    assert "PR_BODY: ${{ github.event.pull_request.body }}" in workflow
    # The PR body must flow through an env var, never be spliced directly
    # into a `run:` command string (which would be a script-injection risk).
    for line in workflow.splitlines():
        if line.strip().startswith("- run:"):
            assert "github.event.pull_request" not in line
