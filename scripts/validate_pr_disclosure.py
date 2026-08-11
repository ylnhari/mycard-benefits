"""Fail-closed CI entry point for MC-096's contribution disclosure.

Extracts the fenced ```yaml block from a pull request body (matching
`.github/PULL_REQUEST_TEMPLATE.md`) and runs it through
`mycard_benefits.catalog.contribution.validate_contribution_disclosure`.
Exits non-zero with the validator's own message on any failure: a missing
block, invalid YAML, or a disclosure that fails validation (no sources, an
undisclosed or unexplained conflict of interest, or a missing fixture-only
confirmation). This is the enforcement path the counterpart review found
missing: a validator that exists but nothing calls is not a gate.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mycard_benefits.catalog.contribution import (  # noqa: E402
    ContributionValidationError,
    validate_contribution_disclosure,
)

_YAML_BLOCK = re.compile(r"```yaml\s*\n(.*?)```", re.DOTALL)


def extract_disclosure_yaml(pr_body: str) -> str:
    match = _YAML_BLOCK.search(pr_body)
    if match is None:
        raise ContributionValidationError(
            "no fenced ```yaml contribution disclosure block was found in the PR description; "
            "copy the block from .github/PULL_REQUEST_TEMPLATE.md and fill it in"
        )
    return match.group(1)


def validate_pr_body(pr_body: str) -> None:
    raw_yaml = extract_disclosure_yaml(pr_body)
    try:
        parsed = yaml.safe_load(raw_yaml)
    except yaml.YAMLError as exc:
        raise ContributionValidationError(f"contribution disclosure block is not valid YAML: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ContributionValidationError("contribution disclosure block must parse to a YAML mapping")
    validate_contribution_disclosure(parsed)


def main() -> None:
    if len(sys.argv) == 2:
        pr_body = Path(sys.argv[1]).read_text(encoding="utf-8")
    else:
        pr_body = sys.stdin.read()
    try:
        validate_pr_body(pr_body)
    except ContributionValidationError as exc:
        print(f"::error::contribution disclosure invalid: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print("contribution disclosure valid")


if __name__ == "__main__":
    main()
