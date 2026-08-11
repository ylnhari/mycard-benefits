"""Every catalog benefit must reach the Benefits screen.

The other rendered checks serve a synthetic catalog fixture, so they cannot see
a defect that depends on the real data. One slipped through exactly there: the
category label map returned null for any category it did not name, a null label
dropped the row, and nine of sixty benefits disappeared from the screen while
the API still returned all sixty and the whole suite stayed green.

This test serves the real catalog/ directory with an empty vault — the state a
new user starts in — and compares what the API offers against what the DOM
shows. It is deliberately a count, not a snapshot: the failure it exists to
catch is silent omission, and only a count makes that visible.
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


@pytest.fixture
def real_catalog_app(tmp_path: Path) -> Iterator[str]:
    """Serve the committed public catalog on loopback with an empty vault."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    listener.close()

    settings = Settings(
        data_dir=tmp_path / "audit-data",
        catalog_dir=ROOT / "catalog",
        port=port,
        demo=False,
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
        pytest.fail("the audit server never became reachable on loopback")

    try:
        yield base
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _api_benefits(base: str) -> list[dict]:
    payload = json.loads(urllib.request.urlopen(base + "/api/v1/catalog/benefits", timeout=10).read())
    if isinstance(payload, list):
        return payload
    return payload.get("items") or payload.get("benefits") or []


@pytest.mark.rendered_ui
@pytest.mark.skipif(not RUN_RENDERED_UI or not PLAYWRIGHT_AVAILABLE, reason=SKIP_REASON)
def test_every_catalog_benefit_reaches_the_benefits_list(real_catalog_app: str) -> None:
    """The screen shows as many benefits as the catalog actually publishes."""
    expected = len(_api_benefits(real_catalog_app))
    assert expected, "the real catalog published no benefits; the fixture is wrong"

    with sync_playwright() as play:
        browser = play.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(real_catalog_app + "/", wait_until="networkidle")
        rendered = page.locator("#benefitList .brow").count()
        chips = page.locator("#benefitCategoryChips .category-chip").all_text_contents()
        browser.close()

    assert rendered == expected, (
        f"the API publishes {expected} benefits but the Benefits list rendered "
        f"{rendered}; {expected - rendered} are missing from the screen"
    )

    # The chips partition the same rows, so their counts must total the same
    # number. A category whose label is missing used to drop out of both at
    # once, which is what made the loss invisible.
    chip_total = 0
    for chip in chips:
        tail = chip.rsplit(" ", 1)[-1]
        if tail.isdigit():
            chip_total += int(tail)
    assert chip_total == expected, (
        f"category chips account for {chip_total} benefits but the catalog "
        f"publishes {expected}; a category is being dropped"
    )


@pytest.mark.rendered_ui
@pytest.mark.skipif(not RUN_RENDERED_UI or not PLAYWRIGHT_AVAILABLE, reason=SKIP_REASON)
def test_no_credential_is_demanded_before_the_first_reveal(real_catalog_app: str) -> None:
    """A new user browses the whole catalog without being asked for anything.

    Password inputs exist in the markup for the reveal and card-editing dialogs;
    what matters is that none is on screen, so this asserts visibility rather
    than absence from the DOM.
    """
    with sync_playwright() as play:
        browser = play.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(real_catalog_app + "/", wait_until="networkidle")
        visible = page.locator("input[type='password']:visible").count()
        browser.close()

    assert visible == 0, f"{visible} password inputs are visible before any reveal was requested"
