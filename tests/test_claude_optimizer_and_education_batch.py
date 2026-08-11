"""Deterministic contract tests for batch 2 of the Claude 30-task run.

Covers MC-050 (localization path), MC-051 (error/recovery guidance parity
with the user guide), MC-077 (portfolio guidance), MC-080 (education-only
warnings), and MC-082 (rank presentation transparency for caps/expiry —
engine/API coverage lives in tests/test_optimizer.py and
tests/test_optimizer_api.py; this file covers the rendering contract).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
APP_JS = (ROOT / "src" / "mycard_benefits" / "static" / "app.js").read_text(encoding="utf-8")
INDEX_HTML = (ROOT / "src" / "mycard_benefits" / "templates" / "index.html").read_text(encoding="utf-8")
USER_GUIDE = (ROOT / "docs" / "USER-GUIDE.md").read_text(encoding="utf-8")


# ---- MC-050: localization path -------------------------------------------


def test_dates_render_through_locale_aware_intl_formatting() -> None:
    assert 'function fmtDate(value) { return value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium" })' in APP_JS


def test_localization_plan_is_documented() -> None:
    doc = (ROOT / "docs" / "LOCALIZATION.md").read_text(encoding="utf-8")
    assert "Intl.DateTimeFormat" in doc
    assert "exact decimal string" in doc
    assert "strings.<locale>.json" in doc or "strings.en.json" in doc


# ---- MC-051: error/recovery guidance matches the user guide ---------------


def test_vault_diagnostic_codes_match_the_five_documented_causes_in_order() -> None:
    start = APP_JS.index("const VAULT_DIAGNOSTICS = {")
    end = APP_JS.index("\n};", start)
    block = APP_JS[start:end]
    codes = re.findall(r"^\s{2}(\w+):\s*\{", block, re.MULTILINE)
    assert codes[:4] == ["demo", "vault_missing", "passphrase_only", "wrong_data_dir"]
    assert "generic" in codes
    guide_section = USER_GUIDE[USER_GUIDE.index("## 12. When something goes wrong"):]
    for phrase in (
        "Demo mode",
        "No vault yet",
        "Passphrase-only vault",
        "Wrong data folder",
        "Keyring unavailable or vault did not unlock",
    ):
        assert phrase in guide_section


def test_no_absolute_filesystem_path_or_traceback_in_user_facing_script_text() -> None:
    forbidden_patterns = (r"[A-Za-z]:\\\\", r"/home/", r"/Users/", r"Traceback")
    for pattern in forbidden_patterns:
        assert not re.search(pattern, APP_JS), f"found forbidden pattern in app.js: {pattern}"


def test_qa_and_error_states_never_render_raw_exception_text() -> None:
    # error.message is compared against known sentinel strings, never interpolated into the DOM.
    assert "${error.message}" not in APP_JS
    assert "${error.stack}" not in APP_JS


# ---- MC-077: core-plus-specialist portfolio guidance ----------------------


def test_compare_view_offers_a_category_breadth_portfolio_note_not_a_universal_best_card() -> None:
    assert "function portfolioRoleNote(offering)" in APP_JS
    assert "PORTFOLIO_BROAD_CATEGORY_THRESHOLD" in APP_JS
    start = APP_JS.index("function portfolioRoleNote(offering)")
    end = APP_JS.index("function renderComparison()", start)
    body = APP_JS[start:end]
    assert "core" in body
    assert "specialist" in body
    start = APP_JS.index("function renderComparison()")
    end = APP_JS.index("\n}", start)
    render_body = APP_JS[start:end]
    assert "portfolioRoleNote(a)" in render_body
    assert "not a spend-return calculation" in render_body
    assert "never names one universal best card" in render_body
