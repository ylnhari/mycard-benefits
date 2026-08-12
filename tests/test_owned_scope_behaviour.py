"""Searching "My cards" must return only benefits the wallet actually has.

An independent audit found this guarantee covered by a test that searched
app.js for the text of the functions implementing it. That test passes whether
or not the functions work, breaks when they are renamed, and would keep passing
if the scope silently fell back to an unrelated benefit — which is the exact
failure its name promises to catch.

This runs the search and checks the results against the wallet, which is what
the promise was.
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
PASS = "synthetic owned scope passphrase"


class _StubKeyring:
    def get_password(self, service_name: str, username: str) -> str:
        return PASS

    def set_password(self, service_name: str, username: str, password: str) -> None:
        return None


def _offering_with_benefits() -> tuple[str, str]:
    """Pick a real offering that has benefits, and one that has none."""
    benefits = [json.loads(p.read_text(encoding="utf-8"))
                for p in (ROOT / "catalog" / "benefits").glob("*.json")]
    covered = {b["offering_id"] for b in benefits}
    with_benefits = without = None
    for path in sorted((ROOT / "catalog" / "offerings").glob("*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        if d["id"] in covered and with_benefits is None:
            with_benefits = d["slug"]
        if d["id"] not in covered and without is None:
            without = d["slug"]
    assert with_benefits and without, "the catalog no longer has both covered and uncovered offerings"
    return with_benefits, without


@pytest.fixture
def owned_wallet_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[str, str]]:
    import mycard_benefits.vault.router as router

    monkeypatch.setattr(router, "load_keyring", lambda: _StubKeyring())
    owned_slug, _ = _offering_with_benefits()

    data_dir = tmp_path / "owned-data"
    session = VaultStore(data_dir / "private" / "vault.json").create(PASS)
    session.add_card(owned_slug, {}, passphrase=PASS)
    session.lock()

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    listener.close()

    settings = Settings(data_dir=data_dir, catalog_dir=ROOT / "catalog", port=port, demo=False)
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
        pytest.fail("the owned-scope server never became reachable")

    try:
        yield base, owned_slug
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.mark.rendered_ui
@pytest.mark.skipif(not RUN_RENDERED_UI or not PLAYWRIGHT_AVAILABLE, reason=SKIP_REASON)
def test_owned_scope_returns_only_benefits_of_cards_in_the_wallet(
    owned_wallet_app: tuple[str, str],
) -> None:
    base, owned_slug = owned_wallet_app
    offering = json.loads(
        (ROOT / "catalog" / "offerings" / f"{owned_slug}.json").read_text(encoding="utf-8")
    )
    owned_name = offering["display_name"]

    with sync_playwright() as play:
        browser = play.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(base + "/#search", wait_until="networkidle")
        page.wait_for_selector("#benefitSearch")

        page.click('button[data-search-scope="owned"]')
        page.fill("#benefitSearch", "")
        page.click("#benefitSearchSubmit")
        page.wait_for_timeout(700)

        owned_results = page.locator("#searchResults .brow, #searchResults .benefit-card")
        owned_count = owned_results.count()
        owned_text = owned_results.all_text_contents()

        page.click('button[data-search-scope="all"]')
        page.click("#benefitSearchSubmit")
        page.wait_for_timeout(700)
        all_count = page.locator("#searchResults .brow, #searchResults .benefit-card").count()
        browser.close()

    assert owned_count, "the owned scope returned nothing for a card that has benefits"
    # The wallet holds exactly one card, so a result naming a different product
    # is the unrelated fallback this guarantee exists to prevent.
    stray = [t for t in owned_text if owned_name.split()[0] not in t]
    assert not stray, (
        f"{len(stray)} of {owned_count} owned-scope results do not belong to "
        f"{owned_name!r}; the scope fell back to unrelated benefits"
    )
    assert all_count > owned_count, (
        "the catalog-wide scope returned no more than the single owned card's "
        "benefits, so the scopes are not actually distinct"
    )


@pytest.mark.rendered_ui
@pytest.mark.skipif(not RUN_RENDERED_UI or not PLAYWRIGHT_AVAILABLE, reason=SKIP_REASON)
def test_owned_scope_says_so_rather_than_showing_someone_elses_benefits(
    owned_wallet_app: tuple[str, str],
) -> None:
    """A term matching nothing owned must return nothing, not a nearest guess."""
    base, _ = owned_wallet_app

    with sync_playwright() as play:
        browser = play.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(base + "/#search", wait_until="networkidle")
        page.wait_for_selector("#benefitSearch")
        page.click('button[data-search-scope="owned"]')
        page.fill("#benefitSearch", "zzzznotarealbenefitterm")
        page.click("#benefitSearchSubmit")
        page.wait_for_timeout(700)
        count = page.locator("#searchResults .brow, #searchResults .benefit-card").count()
        status = page.locator("#searchStatus").inner_text()
        browser.close()

    assert count == 0, f"a term matching nothing returned {count} results"
    assert "0 results" in status, f"the status did not report an empty result: {status!r}"
