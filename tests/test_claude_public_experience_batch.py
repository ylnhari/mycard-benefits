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
APP_JS = (ROOT / "src" / "mycard_benefits" / "static" / "app.js").read_text(encoding="utf-8")
INDEX_HTML = (ROOT / "src" / "mycard_benefits" / "templates" / "index.html").read_text(encoding="utf-8")


# ---- MC-039: benefit detail view shows last verification -------------------


def test_benefit_evidence_lines_render_last_verification_date() -> None:
    assert "function evidenceLine(evidence)" in APP_JS
    start = APP_JS.index("function evidenceLine(evidence)")
    end = APP_JS.index("\n}", start)
    body = APP_JS[start:end]
    assert "evidence.retrieved_at" in body
    assert "last verified" in body


# ---- MC-040: benefit-first browsing shows local matches in the list --------


def test_benefit_list_cards_surface_local_match_state_before_detail_is_opened() -> None:
    assert "function benefitLocalMatchNote(benefit)" in APP_JS
    assert "state.privateCardsAvailable" in APP_JS
    assert "consumerBenefitState(benefit)" in APP_JS
    assert "const ownedItems = items.filter(isOwnedBenefit)" in APP_JS
    assert 'node("span", "On your cards", "mine")' in APP_JS


def test_private_card_refresh_re_renders_the_benefit_list_not_only_the_detail() -> None:
    start = APP_JS.index("async function loadPrivateCards()")
    end = APP_JS.index("\n}\n", start)
    body = APP_JS[start:end]
    assert body.count("renderBenefits();") == 2
    assert "renderBenefitDetail();" not in body


def test_every_dashboard_view_has_a_static_or_dynamic_empty_state_marker() -> None:
    """Every top-level `data-panel` view either ships static empty-state markup
    or is driven by an app.js function that appends an `empty-state` node."""

    view_ids = re.findall(r'<section id="([a-z-]+)" data-panel', INDEX_HTML)
    assert set(view_ids) == {"my-cards", "benefits", "search", "settings"}
    dynamic_or_static_empty_state = {
        "my-cards": (APP_JS, ["Your wallet is empty", "Add my first card"]),
        "benefits": (INDEX_HTML, ['id="benefitCatalogEmpty" class="empty-state"']),
        "search": (INDEX_HTML + APP_JS, ['id="searchEmpty"', "function renderSearchResults"]),
        "settings": (INDEX_HTML, ["Your private card data stays local"]),
    }
    for view_id, (haystack, markers) in dynamic_or_static_empty_state.items():
        for marker in markers:
            assert marker in haystack, f"{view_id} is missing an empty-state marker: {marker!r}"


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
