"""Regression checks for the plain-language, clone-safe user help."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USER_DOCUMENTS = (
    ROOT / "README.md",
    ROOT / "docs" / "README.md",
    ROOT / "docs" / "USER-GUIDE.md",
)
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^]]+\]\(([^)\s]+)(?:\s+[^)]*)?\)")


def test_user_guide_covers_the_supported_journey_and_honest_limits() -> None:
    guide = (ROOT / "docs" / "USER-GUIDE.md").read_text(encoding="utf-8")

    for heading in (
        "## What MyCard Benefits does",
        "## Start it for the first time",
        "## Add and manage cards safely",
        "## Browse benefits and read their status",
        "## Reminders and alerts",
        "## Planner and affiliate disclosure",
        "## Backups and recovery",
        "## Privacy at a glance",
    ):
        assert heading in guide

    for phrase in (
        "add a card, edit private nickname/notes, change a lifecycle",
        "lifecycle, replacement, and deletion are destructive vault actions",
        "protected local **Unlock** and **Lock** controls",
        "Archived** keeps history",
        "needs_review",
        "cannot improve a recommendation or ranking",
        "local check for due-date alignment and autopay",
    ):
        assert phrase in guide


def test_in_app_help_uses_the_same_safe_plain_language() -> None:
    template = (ROOT / "src" / "mycard_benefits" / "templates" / "index.html").read_text(
        encoding="utf-8"
    )

    for phrase in (
        "Where your data lives",
        "Data location",
        "LOCAL ONLY",
        "Your private card data stays local",
        "Full card numbers, CVV, PIN, names, notes, and exact expiry details are never shown",
    ):
        assert phrase in template


def test_user_facing_markdown_has_no_product_branding_or_dead_placeholder_links() -> None:
    for document in USER_DOCUMENTS:
        content = document.read_text(encoding="utf-8")
        assert "rover" not in content.lower(), document
        assert "example.invalid" not in content.lower(), document

        for match in MARKDOWN_LINK.finditer(content):
            target = match.group(1).strip("<>")
            destination = target.split("#", 1)[0]
            if not destination or "://" in destination or destination.startswith("mailto:"):
                continue
            assert (document.parent / destination).resolve().is_file(), (
                f"{document.relative_to(ROOT)} links to missing {destination!r}"
            )
