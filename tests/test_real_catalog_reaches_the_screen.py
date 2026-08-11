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
import re
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


def _api_offerings(base: str) -> list[dict]:
    payload = json.loads(urllib.request.urlopen(base + "/api/v1/catalog/offerings", timeout=10).read())
    if isinstance(payload, list):
        return payload
    return payload.get("items") or payload.get("offerings") or []


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


@pytest.mark.rendered_ui
@pytest.mark.skipif(not RUN_RENDERED_UI or not PLAYWRIGHT_AVAILABLE, reason=SKIP_REASON)
def test_real_catalog_settings_theme_and_detail_are_human_usable(real_catalog_app: str) -> None:
    """Audit Settings, both themes, and several real-catalog benefit details."""
    offerings = _api_offerings(real_catalog_app)
    assert offerings, "the real catalog published no offerings; the fixture is wrong"

    with sync_playwright() as play:
        browser = play.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(real_catalog_app + "/#settings", wait_until="networkidle")

        assert page.locator("#settings").is_visible()
        inline_theme = page.locator("#themeToggleInline")
        rail_theme = page.locator("#themeToggle")
        assert inline_theme.is_visible() and rail_theme.is_visible()
        seen_themes = set()
        for _ in range(2):
            inline_theme.click()
            theme = page.locator("html").get_attribute("data-theme")
            assert theme in {"light", "dark"}
            seen_themes.add(theme)
            expected_label = "Use light theme" if theme == "dark" else "Use dark theme"
            assert inline_theme.inner_text() == expected_label
            assert rail_theme.inner_text() == expected_label
            assert inline_theme.get_attribute("aria-pressed") == str(theme == "dark").lower()
            assert rail_theme.get_attribute("aria-pressed") == str(theme == "dark").lower()
            assert page.evaluate("localStorage.getItem('mycard-benefits-theme')") == theme
        assert seen_themes == {"light", "dark"}
        before_rail_toggle = page.locator("html").get_attribute("data-theme")
        rail_theme.click()
        assert page.locator("html").get_attribute("data-theme") != before_rail_toggle
        assert page.evaluate("localStorage.getItem('mycard-benefits-theme')") == page.locator("html").get_attribute("data-theme")

        contrast_script = """
        selectors => {
          const parse = value => {
            const match = value.match(/rgba?\\(([^)]+)\\)/);
            if (!match) return null;
            const parts = match[1].split(',').map(item => Number.parseFloat(item.trim()));
            return {r: parts[0], g: parts[1], b: parts[2], a: parts.length > 3 ? parts[3] : 1};
          };
          const luminance = color => {
            const channel = value => {
              const normalized = value / 255;
              return normalized <= .03928 ? normalized / 12.92 : ((normalized + .055) / 1.055) ** 2.4;
            };
            return .2126 * channel(color.r) + .7152 * channel(color.g) + .0722 * channel(color.b);
          };
          const ratio = (foreground, background) => {
            const light = Math.max(luminance(foreground), luminance(background));
            const dark = Math.min(luminance(foreground), luminance(background));
            return (light + .05) / (dark + .05);
          };
          const backgroundFor = element => {
            let current = element;
            while (current) {
              const background = parse(getComputedStyle(current).backgroundColor);
              if (background && background.a > 0) return background;
              current = current.parentElement;
            }
            return parse(getComputedStyle(document.body).backgroundColor);
          };
          return selectors.map(selector => {
            const element = document.querySelector(selector);
            const foreground = parse(getComputedStyle(element).color);
            const background = backgroundFor(element);
            return {selector, ratio: ratio(foreground, background)};
          });
        }
        """
        settings_selectors = [
            "#settings-title", "#settings .lede", "#appearance-title", "#settings .settings-card p",
            "#themeToggleInline", "#data-location-title", "#settings .local-mark",
            "#stored-locally-title", "#settings .local-storage-note p",
        ]
        benefit_selectors = [
            "#benefitSummary", "#benefitCatalogStatus", "#benefitList .catbar .n",
            "#benefitList .b-card", "#benefitList .b-title", "#benefitList .b-cond",
            "#benefitList .state", "#benefitList .asof",
        ]
        for expected_theme in ("light", "dark"):
            page.goto(real_catalog_app + "/#settings", wait_until="networkidle")
            if page.locator("html").get_attribute("data-theme") != expected_theme:
                inline_theme.click()
            settings_contrast = page.evaluate(contrast_script, settings_selectors)
            assert all(sample["ratio"] >= 4.5 for sample in settings_contrast), (
                expected_theme,
                settings_contrast,
            )
            page.goto(real_catalog_app + "/#benefits", wait_until="networkidle")
            page.wait_for_function("document.querySelectorAll('#benefitList .brow').length >= 21")
            benefit_contrast = page.evaluate(contrast_script, benefit_selectors)
            assert all(sample["ratio"] >= 4.5 for sample in benefit_contrast), (
                expected_theme,
                benefit_contrast,
            )

        page.goto(real_catalog_app + "/#benefits", wait_until="networkidle")
        page.wait_for_function("document.querySelectorAll('#benefitList .brow').length >= 21")
        detail_texts = []
        for index in (0, 10, 20, 30, 40, 50, 59):
            page.locator("#benefitList .brow").nth(index).click()
            page.wait_for_selector("#benefitDetail .benefit-detail-card")
            detail_texts.append(page.locator("#benefitDetail").inner_text())
            page.get_by_role("link", name="Benefits", exact=True).click()
            page.wait_for_timeout(50)
        forbidden = re.compile(
            r"(?<![a-z])(?:calendar_quarter|eligible_net_posted_spend_inr|reward_points|"
            r"check_before_use|sources_differ|not_claimed|gte|lte|equals)(?![a-z])"
        )
        for text in detail_texts:
            lowered = text.lower()
            assert forbidden.search(lowered) is None, text

        browser.close()


@pytest.mark.rendered_ui
@pytest.mark.skipif(not RUN_RENDERED_UI or not PLAYWRIGHT_AVAILABLE, reason=SKIP_REASON)
def test_real_catalog_keyboard_reaches_every_control_and_can_hide_reveal(
    real_catalog_app: str,
) -> None:
    """Use real Tab navigation across all views and the revealed-card state."""
    offerings = _api_offerings(real_catalog_app)
    assert offerings, "the real catalog published no offerings; the fixture is wrong"
    synthetic_card = {
        "card_id": "SYNTHETIC-ONLY-keyboard-card",
        "offering_id": offerings[0]["id"],
        "lifecycle": "active",
    }

    def visible_focusable_keys(page, panel_id: str) -> list[str]:
        return page.locator(f"#{panel_id}").evaluate(
            """
            element => {
              const selector = 'a[href],button,input,select,textarea,summary,[tabindex]:not([tabindex="-1"])';
              const visible = item => {
                const style = getComputedStyle(item);
                return !item.disabled && !item.closest('details:not([open])') && !item.closest('[hidden]')
                  && style.display !== 'none' && style.visibility !== 'hidden' && item.getClientRects().length > 0;
              };
              return [...element.querySelectorAll(selector)].filter(visible).map((item, index) => {
                const key = `audit-${index}`;
                item.dataset.auditTabKey = key;
                return key;
              });
            }
            """
        )

    def traverse_panel(page, panel_id: str) -> None:
        expected = set(visible_focusable_keys(page, panel_id))
        assert expected, f"{panel_id} has no visible keyboard controls"
        seen: dict[str, bool] = {}
        for _ in range(max(80, len(expected) * 3)):
            page.keyboard.press("Tab")
            active = page.evaluate(
                """
                () => {
                  const item = document.activeElement;
                  return {
                    key: item?.dataset?.auditTabKey || null,
                    focusVisible: Boolean(item?.matches?.(':focus-visible')),
                  };
                }
                """
            )
            if active["key"]:
                seen[active["key"]] = active["focusVisible"]
            if expected.issubset(seen):
                break
        if set(seen) < expected:
            missed = page.locator(f"#{panel_id}").evaluate(
                """
                element => [...element.querySelectorAll('[data-audit-tab-key]')]
                  .filter(item => !item.dataset.auditTabKey || item.dataset.auditTabKey)
                  .map(item => ({key: item.dataset.auditTabKey, tag: item.tagName, id: item.id, text: (item.innerText || item.getAttribute('aria-label') || '').trim().slice(0, 80)}))
                """
            )
            missed = [item for item in missed if item["key"] in expected - set(seen)]
            raise AssertionError(f"{panel_id} controls missed by Tab: {missed}")
        assert all(seen[key] for key in expected), f"{panel_id} has a focus target without a visible keyboard indicator"

    with sync_playwright() as play:
        browser = play.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        def private_cards(route) -> None:
            route.fulfill(status=200, json={"cards": [synthetic_card], "lifecycle_counts": {"active": 1}})

        def csrf(route) -> None:
            route.fulfill(status=200, json={"csrf_token": "SYNTHETIC-ONLY-csrf"})

        def reveal(route) -> None:
            route.fulfill(
                status=200,
                json={
                    "card_number": "SYNTHETIC-ONLY-card-number",
                    "expiry": "SYNTHETIC-ONLY-expiry",
                    "cvv": "SYNTHETIC-ONLY-cvv",
                },
            )

        page.route("**/api/v1/private/cards", private_cards)
        page.route("**/api/v1/private/csrf-token", csrf)
        page.route("**/api/v1/private/cards/**/reveal-authorize", reveal)

        for view in ("my-cards", "benefits", "search", "settings"):
            page.goto(real_catalog_app + f"/#{view}", wait_until="networkidle")
            page.wait_for_function(
                "view => document.querySelector(`#${view}`)?.hidden === false",
                arg=view,
            )
            if view == "my-cards":
                page.wait_for_selector("#myCardList .reveal-trigger")
            traverse_panel(page, view)
            if view == "my-cards":
                opened_manage = False
                for _ in range(120):
                    page.keyboard.press("Tab")
                    active = page.evaluate(
                        """
                        () => document.activeElement?.matches('#manageCardsDetails > summary') || false
                        """
                    )
                    if active:
                        page.keyboard.press("Enter")
                        opened_manage = True
                        break
                assert opened_manage, "Tab never reached the Manage cards disclosure"
                assert page.locator("#manageCardsDetails").get_attribute("open") == ""
                traverse_panel(page, view)

        page.goto(real_catalog_app + "#my-cards", wait_until="networkidle")
        page.wait_for_selector("#myCardList .reveal-trigger")
        opened = False
        for _ in range(240):
            page.keyboard.press("Tab")
            active = page.evaluate(
                """
                () => ({
                  reveal: document.activeElement?.classList?.contains('reveal-trigger') || false,
                  focusVisible: Boolean(document.activeElement?.matches?.(':focus-visible')),
                })
                """
            )
            if active["reveal"]:
                assert active["focusVisible"]
                page.keyboard.press("Enter")
                opened = True
                break
        assert opened, "Tab never reached the card reveal control"
        page.wait_for_selector("#revealShownState", state="visible")

        # The controller puts focus on Hide now after a successful reveal.
        # Walk backwards through every reveal control with real keyboard
        # navigation so this does not turn a programmatic focus into a false
        # keyboard pass.
        for expected_id in ("revealCvvButton", "revealCopyExpiry", "revealCopyNumber"):
            page.keyboard.press("Shift+Tab")
            active = page.evaluate(
                """
                () => ({
                  id: document.activeElement?.id || '',
                  focusVisible: Boolean(document.activeElement?.matches?.(':focus-visible')),
                })
                """
            )
            assert active["id"] == expected_id
            assert active["focusVisible"]
        page.keyboard.press("Tab")
        page.keyboard.press("Tab")
        active = page.evaluate(
            """
            () => ({
              id: document.activeElement?.id || '',
              focusVisible: Boolean(document.activeElement?.matches?.(':focus-visible')),
            })
            """
        )
        assert active["id"] == "revealCvvButton"
        assert active["focusVisible"]
        page.keyboard.press("Enter")
        assert page.locator("#revealCvv").inner_text() == "SYNTHETIC-ONLY-cvv"
        page.keyboard.press("Enter")
        assert page.locator("#revealCvv").inner_text() == "•••"
        page.keyboard.press("Tab")
        active = page.evaluate(
            """
            () => ({
              id: document.activeElement?.id || '',
              focusVisible: Boolean(document.activeElement?.matches?.(':focus-visible')),
            })
            """
        )
        assert active["id"] == "revealHideNow"
        assert active["focusVisible"]
        page.keyboard.press("Enter")
        assert page.locator("#revealCardNumber").inner_text() == "•••• •••• ••••"
        assert page.locator("#revealExpiry").inner_text() == "•• / ••"
        assert page.locator("#revealCvv").inner_text() == "•••"
        browser.close()
