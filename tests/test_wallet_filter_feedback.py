"""Applying a wallet filter must change something the owner can see.

Reported from a phone: "filters not changing cards, UI not shifting". The
filters were in fact working — Credit narrowed eighteen cards to nine — but the
only line above the fold was computed from every saved card, so it read the
same before and after. The grid that did change sat below the visible area.
A filter that silently narrows an off-screen list is indistinguishable from a
filter that does nothing.

These tests seed a wallet of a realistic size and assert the visible summary
moves with the filter, since counting the grid alone would have passed
throughout the period the owner was reporting the bug.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn

from mycard_benefits.app import create_app
from mycard_benefits.config import Settings
from mycard_benefits.vault.core import VaultStore

ROOT = Path(__file__).parents[1]
RUN_RENDERED_UI = os.environ.get("MYCARD_RENDERED_UI") == "1"
PLAYWRIGHT_AVAILABLE = False

if RUN_RENDERED_UI:
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError:
        PLAYWRIGHT_AVAILABLE = False
    else:
        PLAYWRIGHT_AVAILABLE = True

SKIP_REASON = (
    "Set MYCARD_RENDERED_UI=1 with Python Playwright and its Chromium driver "
    "to run browser checks."
)
PASS = "synthetic filter passphrase"
WALLET_SIZE = 18


class _StubKeyring:
    def get_password(self, service_name: str, username: str) -> str:
        return PASS

    def set_password(self, service_name: str, username: str, password: str) -> None:
        return None


def _wallet_slugs() -> list[str]:
    """Real products from several issuers, so issuer chips have something to do."""
    slugs: list[str] = []
    for path in sorted((ROOT / "catalog" / "offerings").glob("*.json")):
        offering = json.loads(path.read_text(encoding="utf-8"))
        issuer = str(offering.get("issuer_id", "")).lower()
        if any(bank in issuer for bank in ("hdfc", "icici", "axis", "dbs", "indusind", "rbl")):
            slug = offering.get("slug") or offering.get("id")
            if slug:
                slugs.append(slug)
    return slugs[:WALLET_SIZE]


@pytest.fixture
def filled_wallet_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    import mycard_benefits.vault.router as router

    monkeypatch.setattr(router, "load_keyring", lambda: _StubKeyring())

    slugs = _wallet_slugs()
    assert len(slugs) >= 6, "the catalog no longer has enough issuers to exercise the chips"

    data_dir = tmp_path / "filter-data"
    session = VaultStore(data_dir / "private" / "vault.json").create(PASS)
    for slug in slugs:
        session.add_card(slug, {}, passphrase=PASS)
    session.lock()

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    listener.close()

    settings = Settings(
        data_dir=data_dir, catalog_dir=ROOT / "catalog", port=port, demo=False
    )
    server = uvicorn.Server(uvicorn.Config(create_app(settings), port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base = f"http://127.0.0.1:{port}"
    for _ in range(200):
        try:
            urllib.request.urlopen(base + "/", timeout=1).read()
            break
        except OSError:
            time.sleep(0.05)
    else:
        server.should_exit = True
        pytest.fail("the wallet server never became reachable")

    try:
        yield base
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.mark.rendered_ui
@pytest.mark.skipif(not RUN_RENDERED_UI or not PLAYWRIGHT_AVAILABLE, reason=SKIP_REASON)
def test_a_filter_that_narrows_the_wallet_says_so_on_screen(filled_wallet_app: str) -> None:
    """Phone-sized viewport, because that is where the grid is off-screen."""
    silent: list[str] = []

    with sync_playwright() as play:
        browser = play.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(filled_wallet_app + "/", wait_until="networkidle")
        page.wait_for_selector("#myCardChips button")

        chips = page.locator("#myCardChips button")
        assert chips.count() >= 4, "the wallet filter chips did not render"
        total = page.locator("#myCardList .cardface").count()
        assert total, "no cards rendered, so the filters cannot be exercised"

        for index in range(chips.count()):
            chip = chips.nth(index)
            if not chip.is_visible():
                continue
            label = chip.inner_text().strip()
            before_summary = page.locator("#myCardSummary").inner_text().strip()
            chip.click()
            page.wait_for_timeout(350)
            shown = page.locator("#myCardList .cardface").count()
            after_summary = page.locator("#myCardSummary").inner_text().strip()
            if shown != total and before_summary == after_summary:
                silent.append(f"{label} ({total} -> {shown})")
            chip.click()
            page.wait_for_timeout(200)

        browser.close()

    assert not silent, (
        "these filters changed the card list without changing anything visible: "
        + "; ".join(silent)
    )


@pytest.mark.rendered_ui
@pytest.mark.skipif(not RUN_RENDERED_UI or not PLAYWRIGHT_AVAILABLE, reason=SKIP_REASON)
def test_an_unfiltered_wallet_does_not_claim_to_be_filtered(filled_wallet_app: str) -> None:
    """The narrowing note must not appear when nothing is narrowed."""
    with sync_playwright() as play:
        browser = play.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(filled_wallet_app + "/", wait_until="networkidle")
        page.wait_for_selector("#myCardChips button")
        summary = page.locator("#myCardSummary").inner_text()
        browser.close()

    assert "Showing" not in summary, f"an unfiltered wallet reported itself filtered: {summary!r}"
