"""Every lifecycle a wallet actually holds must be findable.

The vault records fourteen lifecycles, and the distinctions are real: a closed
card is gone, an expired one may have been reissued, a replaced one points at
what replaced it. My Cards offered filters for two of them, so a closed,
expired, lost or replaced card could not be filtered for at all — which matters
most for the cards a person keeps for reference rather than use.

Chips are built from the states present rather than from the full fourteen, so
these tests check both directions: a state in the wallet gets a chip, and a
state that is absent does not clutter the row with a chip matching nothing.
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
from mycard_benefits.vault.core import CardLifecycle, VaultStore

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
PASS = "synthetic lifecycle passphrase"
CARD = "hdfc-regalia-gold-credit"

# A wallet that looks like a real one kept over years: cards in use, one closed,
# one expired and one replaced.
SEEDED = [
    CardLifecycle.ACTIVE,
    CardLifecycle.ACTIVE,
    CardLifecycle.CLOSED,
    CardLifecycle.EXPIRED,
    CardLifecycle.REPLACED,
]


class _StubKeyring:
    def get_password(self, service_name: str, username: str) -> str:
        return PASS

    def set_password(self, service_name: str, username: str, password: str) -> None:
        return None


@pytest.fixture
def mixed_wallet_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    import mycard_benefits.vault.router as router

    monkeypatch.setattr(router, "load_keyring", lambda: _StubKeyring())

    data_dir = tmp_path / "lifecycle-data"
    session = VaultStore(data_dir / "private" / "vault.json").create(PASS)
    for lifecycle in SEEDED:
        session.add_card(CARD, {}, passphrase=PASS, lifecycle=lifecycle)
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
        pytest.fail("the lifecycle server never became reachable")

    try:
        yield base
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _chip_labels(page) -> list[str]:
    return [t.strip() for t in page.locator("#myCardChips button").all_text_contents()]


@pytest.mark.rendered_ui
@pytest.mark.skipif(not RUN_RENDERED_UI or not PLAYWRIGHT_AVAILABLE, reason=SKIP_REASON)
def test_a_closed_or_expired_card_can_be_filtered_for(mixed_wallet_app: str) -> None:
    with sync_playwright() as play:
        browser = play.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(mixed_wallet_app + "/", wait_until="networkidle")
        page.wait_for_selector("#myCardChips button")

        labels = _chip_labels(page)
        total = page.locator("#myCardList .cardface").count()

        counts: dict[str, int] = {}
        for wanted in ("Closed", "Expired", "Replaced"):
            chip = page.locator("#myCardChips button", has_text=wanted).first
            chip.click()
            page.wait_for_timeout(300)
            counts[wanted] = page.locator("#myCardList .cardface").count()
            chip.click()
            page.wait_for_timeout(200)
        browser.close()

    for wanted in ("In use", "Closed", "Expired", "Replaced"):
        assert wanted in labels, f"no chip for {wanted}; chips were {labels}"
    assert total == len(SEEDED)
    # One card was seeded in each of these states, so each filter shows exactly
    # one. Asserting the number catches a chip that renders but filters nothing.
    for wanted, shown in counts.items():
        assert shown == 1, f"the {wanted} filter showed {shown} cards, expected 1"


@pytest.mark.rendered_ui
@pytest.mark.skipif(not RUN_RENDERED_UI or not PLAYWRIGHT_AVAILABLE, reason=SKIP_REASON)
def test_absent_lifecycles_get_no_chip(mixed_wallet_app: str) -> None:
    """A row of fourteen chips matching nothing would be worse than two."""
    with sync_playwright() as play:
        browser = play.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(mixed_wallet_app + "/", wait_until="networkidle")
        page.wait_for_selector("#myCardChips button")
        labels = _chip_labels(page)
        browser.close()

    for absent in ("Lost", "Stolen", "Frozen", "Applied", "Pending", "Archived"):
        assert absent not in labels, f"chip for {absent} appeared with no such card"
