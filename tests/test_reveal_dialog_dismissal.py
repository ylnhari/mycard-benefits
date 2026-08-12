"""There must always be a way out of the card-details dialog.

The dialog tells the owner that the rest of MyCard keeps working. Once it
covered the viewport it was also the only thing on screen and offered no way
back to that rest — no close control, no Escape, nothing. If setting up a code
failed, the message said the app still worked while the app was unreachable.

Laying it out inline had hidden this: you could always scroll past it. Making
it a real modal is what made the omission matter, so the three ordinary ways
out are pinned here.
"""

from __future__ import annotations

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
PASS = "synthetic dismissal passphrase"


class _StubKeyring:
    def get_password(self, service_name: str, username: str) -> str:
        return PASS

    def set_password(self, service_name: str, username: str, password: str) -> None:
        return None


@pytest.fixture
def wallet_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    import mycard_benefits.vault.router as router

    monkeypatch.setattr(router, "load_keyring", lambda: _StubKeyring())

    data_dir = tmp_path / "dismissal-data"
    session = VaultStore(data_dir / "private" / "vault.json").create(PASS)
    for _ in range(3):
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
        pytest.fail("the dismissal server never became reachable")

    try:
        yield base
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.mark.rendered_ui
@pytest.mark.skipif(not RUN_RENDERED_UI or not PLAYWRIGHT_AVAILABLE, reason=SKIP_REASON)
@pytest.mark.parametrize("how", ["close", "escape", "backdrop"])
def test_the_dialog_can_always_be_dismissed(wallet_app: str, how: str) -> None:
    with sync_playwright() as play:
        browser = play.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(wallet_app + "/", wait_until="networkidle")
        page.wait_for_selector(".reveal-trigger")

        page.locator(".reveal-trigger").first.click()
        page.wait_for_selector("#cardRevealPrompt:visible")

        if how == "close":
            page.locator("#revealClose").click()
        elif how == "escape":
            page.keyboard.press("Escape")
        else:
            # Outside the panel: the dimmed page behind it.
            page.mouse.click(5, 5)

        # Wait for the state rather than for a duration. A fixed pause passed
        # alone and failed inside the full rendered run, which is a flaky test
        # reporting a working feature as broken — the most expensive kind,
        # because it teaches you to distrust a red suite.
        try:
            page.wait_for_selector("#cardRevealPrompt", state="hidden", timeout=5000)
            dismissed = True
        except Exception:
            dismissed = False
        # Focus must land somewhere usable, or a keyboard user is stranded with
        # the caret nowhere after the dialog vanishes.
        focus_class = page.evaluate(
            "() => document.activeElement ? document.activeElement.className : ''"
        )
        browser.close()

    assert dismissed, f"the dialog could not be dismissed by {how}"
    assert "reveal-trigger" in focus_class, (
        f"focus went to {focus_class!r} instead of returning to the control that opened it"
    )


@pytest.mark.rendered_ui
@pytest.mark.skipif(not RUN_RENDERED_UI or not PLAYWRIGHT_AVAILABLE, reason=SKIP_REASON)
def test_dismissing_clears_the_entered_code(wallet_app: str) -> None:
    """Closing is a teardown, not just a repaint: nothing typed may survive it."""
    with sync_playwright() as play:
        browser = play.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(wallet_app + "/", wait_until="networkidle")
        page.wait_for_selector(".reveal-trigger")

        page.locator(".reveal-trigger").first.click()
        page.wait_for_selector("#cardRevealPrompt:visible")
        page.fill("#revealCode", "135790")
        page.fill("#revealCodeConfirm", "135790")
        page.locator("#revealClose").click()
        page.wait_for_timeout(300)

        page.locator(".reveal-trigger").first.click()
        page.wait_for_selector("#cardRevealPrompt:visible")
        code = page.input_value("#revealCode")
        confirm = page.input_value("#revealCodeConfirm")
        browser.close()

    assert code == "" and confirm == "", "a previously typed code survived the dialog closing"
