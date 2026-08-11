"""Deterministic contract tests for the Claude public-experience/governance batch.

These are static-content and structural checks in the same style as
`tests/test_ui.py`: no browser is required, and none is claimed. Rendered
DOM/interaction coverage for these same surfaces lives in
`tests/test_rendered_ui.py` behind the Playwright opt-in gate.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parents[1]
# ---- MC-049: living artifacts stay present and structurally fresh ---------


LIVING_ARTIFACTS = (
    "PRODUCT_REQUIREMENTS.md",
    "ROADMAP.md",
    "PROJECT_STATUS.md",
    "DECISIONS.md",
    "docs/DECISION-TRACE.md",
    "docs/QUESTIONNAIRE-DECISIONS.md",
    "docs/IDEA-LOG.md",
)


def test_every_declared_living_artifact_exists_and_is_non_empty() -> None:
    for relative_path in LIVING_ARTIFACTS:
        path = ROOT / relative_path
        assert path.is_file(), f"declared living artifact is missing: {relative_path}"
        assert path.read_text(encoding="utf-8").strip(), f"declared living artifact is empty: {relative_path}"


def test_project_status_carries_a_parseable_non_future_last_updated_date() -> None:
    text = (ROOT / "PROJECT_STATUS.md").read_text(encoding="utf-8")
    match = re.search(r"^Last updated:\s*(\d{4}-\d{2}-\d{2})\s*$", text, re.MULTILINE)
    assert match, "PROJECT_STATUS.md must carry a `Last updated: YYYY-MM-DD` line"
    stamped = date.fromisoformat(match.group(1))
    assert stamped <= date.today(), "PROJECT_STATUS.md Last updated date must not be in the future"


def test_tasks_file_checkbox_lines_are_structurally_well_formed() -> None:
    text = (ROOT / "TASKS.md").read_text(encoding="utf-8")
    checkbox_lines = [line for line in text.splitlines() if line.lstrip().startswith("- [")]
    assert len(checkbox_lines) > 100
    for line in checkbox_lines:
        assert re.match(r"^\s*- \[[ x]\] \*\*MC-\d+:", line), f"malformed task checkbox line: {line!r}"
