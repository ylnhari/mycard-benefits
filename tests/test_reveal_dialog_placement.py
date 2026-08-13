"""The card-details prompt must open where the owner is looking.

The prompt carries role="dialog" aria-modal="true", but it was laid out inline
and sat below the whole card list. With a real wallet — the owner has around
twenty-five cards — pressing "Show full details" asked for a PIN whose field
was several screens further down, so the control and the thing it summoned were
nowhere near each other.

This serves a seeded wallet of that size and checks the prompt is actually
within the viewport when it opens, on a phone-sized screen as well as a desktop
one. A count of cards is what makes the check meaningful: with one card the old
layout looked fine.

The stored values are synthetic; the PAN is non-numeric and cannot be Luhn-valid.
"""

from __future__ import annotations

import contextlib
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
PASS = "synthetic placement passphrase"
WALLET_SIZE = 25


class _StubKeyring:
    """Stands in for the OS keyring so the app can open its own vault."""

    def get_password(self, service_name: str, username: str) -> str:
        return PASS

    def set_password(self, service_name: str, username: str, password: str) -> None:
        return None


@pytest.fixture
def seeded_wallet_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Serve the real catalog with a wallet the size the owner actually has."""
    import mycard_benefits.vault.router as router

    monkeypatch.setattr(router, "load_keyring", lambda: _StubKeyring())

    data_dir = tmp_path / "wallet-data"
    session = VaultStore(data_dir / "private" / "vault.json").create(PASS)
    for _ in range(WALLET_SIZE):
        session.add_card(
            "hdfc-regalia-gold-credit", {"pan": "SYNTHETIC-ONLY-PAN"}, passphrase=PASS
        )
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
        pytest.fail("the seeded wallet server never became reachable")

    try:
        yield base
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.mark.rendered_ui
@pytest.mark.skipif(not RUN_RENDERED_UI or not PLAYWRIGHT_AVAILABLE, reason=SKIP_REASON)
@pytest.mark.parametrize(("width", "height"), [(1280, 900), (390, 844)])
def test_the_details_prompt_opens_within_the_viewport(
    seeded_wallet_app: str, width: int, height: int
) -> None:
    with sync_playwright() as play:
        browser = play.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        page.goto(seeded_wallet_app + "/", wait_until="networkidle")
        page.wait_for_selector(".reveal-trigger")
        assert page.locator(".reveal-trigger").count() >= WALLET_SIZE

        page.locator(".reveal-trigger").first.click()
        page.wait_for_selector("#cardRevealPrompt:visible")

        within = page.evaluate(
            """() => {
                const rect = document.querySelector('#cardRevealPrompt').getBoundingClientRect();
                return rect.top >= 0 && rect.left >= 0
                    && rect.bottom <= window.innerHeight + 1
                    && rect.right <= window.innerWidth + 1;
            }"""
        )
        # Focus is set after the reveal request resolves, so wait for it rather
        # than sampling immediately — reading it too early reports a working
        # dialog as broken, which is the flake this suite has already had once.
        with contextlib.suppress(Exception):
            page.wait_for_function(
                "() => document.activeElement && document.activeElement.id === 'revealCode'",
                timeout=8000,
            )
        focused = page.evaluate("() => document.activeElement && document.activeElement.id")
        browser.close()

    assert within, "the card-details prompt opened outside the viewport"
    # Opening in view is only half of it; the field being asked for should also
    # be ready to type into, or the owner still has to go looking for it.
    assert focused == "revealCode", f"focus landed on {focused!r} instead of the code field"
