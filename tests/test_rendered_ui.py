"""Opt-in rendered-DOM checks for the public dashboard.

These checks intentionally use a disposable loopback server, synthetic catalog
fixtures, synthetic API responses, and a fresh headless-browser context. They
do not open a signed-in browser profile or read a private vault.
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
from urllib.parse import urlparse

import pytest
import uvicorn

from mycard_benefits.app import create_app
from mycard_benefits.config import Settings

ROOT = Path(__file__).parents[1]
RUN_RENDERED_UI = os.environ.get("MYCARD_RENDERED_UI") == "1"
CONSUMER_STATE_LABELS = {"Verified", "Check before use", "Sources differ"}
PLAYWRIGHT_AVAILABLE = False
PLAYWRIGHT_SKIP_REASON = (
    "Set MYCARD_RENDERED_UI=1 in an already-provisioned environment with Python Playwright "
    "and its matching Chromium driver to run browser checks."
)

if RUN_RENDERED_UI:
    try:
        from playwright.sync_api import Page, Route, expect, sync_playwright
    except ModuleNotFoundError:
        PLAYWRIGHT_SKIP_REASON = (
            "Python Playwright is unavailable in this environment; no browser dependency was downloaded."
        )
    else:
        PLAYWRIGHT_AVAILABLE = True


@pytest.fixture
def synthetic_loopback_app(tmp_path: Path) -> Iterator[str]:
    """Serve the app with only committed synthetic catalog data on loopback."""

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    settings = Settings(
        data_dir=tmp_path / "synthetic-ui-data",
        catalog_dir=ROOT / "tests" / "fixtures" / "synthetic_catalog",
        port=port,
        demo=False,
    )
    server = uvicorn.Server(uvicorn.Config(create_app(settings), log_level="warning"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 10
    while True:
        try:
            with urllib.request.urlopen(f"{url}/api/v1/health", timeout=0.5) as response:
                if response.status == 200:
                    break
        except OSError:
            if time.monotonic() >= deadline:
                server.should_exit = True
                thread.join(timeout=5)
                raise RuntimeError("Synthetic UI server did not become ready") from None
            time.sleep(0.05)
    try:
        yield url
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def _synthetic_private_unavailable(route: Route) -> None:
    """Exercise the real fail-closed UI contract without opening a vault."""
    route.fulfill(
        status=503,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        json={
            "detail": {
                "code": "locked",
                "message": "The vault file exists but could not be opened",
            }
        },
    )


def _attach_synthetic_private_route(page: Page) -> None:
    page.route("**/api/v1/private/cards", _synthetic_private_unavailable)


def _attach_synthetic_not_claimed_benefit_route(page: Page) -> None:
    def respond(route: Route) -> None:
        response = route.fetch()
        benefits = response.json()
        assert benefits
        benefits[0]["not_claimed"] = ["SYNTHETIC-ONLY-unconditional terms"]
        benefits[0]["state"] = "verified"
        for index, state in enumerate(("check_before_use", "sources_differ"), start=1):
            clone = dict(benefits[0])
            clone["id"] = f"SYNTHETIC-ONLY-state-{index}"
            clone["title"] = f"SYNTHETIC-ONLY {state} illustration"
            clone["state"] = state
            benefits.append(clone)
        route.fulfill(response=response, json=benefits)

    page.route("**/api/v1/catalog/benefits", respond)


SYNTHETIC_ACTIVE_CARD = {
    "card_id": "SYNTHETIC-ONLY-active-card",
    "offering_id": "22222222-2222-4222-8222-222222222222",
    "lifecycle": "active",
    "created_at": "2026-08-01T00:00:00Z",
    "updated_at": "2026-08-01T00:00:00Z",
}


def _attach_synthetic_private_cards_route(
    page: Page,
    mode: dict[str, str],
    cards: list[dict[str, object]],
) -> None:
    def respond(route: Route) -> None:
        if mode["value"] == "failed":
            _synthetic_private_unavailable(route)
            return
        route.fulfill(
            status=200,
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
            json={"cards": cards, "lifecycle_counts": {"active": len(cards)}},
        )

    page.route("**/api/v1/private/cards", respond)


def _assert_private_storage_failure(page: Page) -> None:
    expect(page.locator("#myCardSummary")).to_have_text(
        "We could not open the local card storage automatically."
    )
    expect(page.locator("#myCardList")).to_contain_text("My Cards is unavailable")
    expect(page.locator("#myCardList")).not_to_contain_text("Your wallet is empty")
    expect(page.locator("#myCardSummary")).not_to_contain_text("0 in use")


def test_mc212_loopback_request_contract_and_focusable_status(
    synthetic_loopback_app: str,
) -> None:
    """Deterministic shipped fallback when a browser driver is unavailable.

    This boots the real loopback application and records the same request
    sequence the browser uses for a first page and a cursor page. It checks
    the desktop/mobile CSS contract and the actual focus target in the served
    document; it is deliberately reported separately from rendered-browser
    evidence and never claims pixel or keyboard execution.
    """
    def get(path: str) -> tuple[str, dict[str, str]]:
        with urllib.request.urlopen(f"{synthetic_loopback_app}{path}", timeout=5) as response:
            return response.read().decode("utf-8"), dict(response.headers.items())

    page, _ = get("/")
    style, _ = get("/static/app.css")
    assert 'id="benefitList"' in page
    assert 'id="benefitCatalogEmpty"' in page
    assert 'id="benefitSearchForm"' in page
    assert 'id="searchResults"' in page
    assert 'id="benefitLoadMore"' not in page
    for removed_id in ("vaultControl", "cardSetupPanel", "vaultUnlockPanel", "myCardsBadge"):
        assert f'id="{removed_id}"' not in page
    assert "Checking access" not in page
    assert 'id="searchStatus"' in page and 'tabindex="-1"' in page
    assert "@media (max-width:850px)" in style

    benefits, _ = get("/api/v1/catalog/benefits")
    assert len(json.loads(benefits)) == 1


@pytest.mark.rendered_ui
@pytest.mark.skipif(
    not RUN_RENDERED_UI or not PLAYWRIGHT_AVAILABLE,
    reason=PLAYWRIGHT_SKIP_REASON,
)
def test_public_benefit_and_private_card_surfaces_render_in_headless_browser(
    synthetic_loopback_app: str,
) -> None:
    """Exercise the consumer UI at desktop and mobile sizes.

    This is DOM/interaction coverage, not a screenshot or pixel-diff visual review.
    """

    with sync_playwright() as playwright:
        browser_path = Path(playwright.chromium.executable_path)
        if not browser_path.is_file():
            pytest.skip(
                "Playwright Chromium driver is unavailable locally; no browser dependency was downloaded."
            )
        browser = playwright.chromium.launch(headless=True)
        desktop = browser.new_context(
            viewport={"width": 1440, "height": 1000}, color_scheme="dark"
        )
        page = desktop.new_page()
        requests: list[str] = []
        page.on("request", lambda request: requests.append(urlparse(request.url).path))
        _attach_synthetic_not_claimed_benefit_route(page)
        page.goto(f"{synthetic_loopback_app}/#benefits", wait_until="networkidle")
        assert "/api/v1/private/cards" not in requests
        _attach_synthetic_private_route(page)

        expect(page.locator("#benefits")).to_be_visible()
        benefit_state_labels = page.locator("#benefitList .state").all_text_contents()
        assert benefit_state_labels
        assert set(benefit_state_labels) == CONSUMER_STATE_LABELS
        assert all(label in CONSUMER_STATE_LABELS for label in benefit_state_labels)
        expect(page.locator("#benefitList")).not_to_contain_text("visits left")
        expect(page.locator("#benefitList")).not_to_contain_text("visits remaining")
        expect(page.get_by_role("button", name="Use light theme")).to_be_visible()
        page.get_by_role("button", name="Use light theme").click()
        expect(page.locator("html")).to_have_attribute("data-theme", "light")

        page.get_by_role("link", name="My Cards", exact=True).click()
        page.wait_for_timeout(100)
        assert "/api/v1/private/cards" in requests
        expect(page.locator("#cards-title")).to_be_focused()
        _assert_private_storage_failure(page)

        page.get_by_role("link", name="Search", exact=True).click()
        page.get_by_role("button", name="Everything", exact=True).click()
        page.get_by_role("link", name="Benefits", exact=True).click()
        expect(page.locator("#benefits")).to_be_visible()
        expect(page.locator("#benefits-title")).to_be_focused()
        not_claimed_row = page.locator("#benefitList .brow").filter(has_text="This is not claimed").first
        expect(not_claimed_row).to_be_visible()
        not_claimed_row.click()
        expect(page.locator("#benefitDetail")).to_contain_text("This is not claimed")
        expect(page.locator("#benefitDetail")).to_contain_text("To qualify")
        expect(page.locator("#benefitDetail")).to_contain_text("Synthetic Issuer · retrieved")
        expect(page.locator("#benefitDetail")).not_to_contain_text("synthetic-issuer")
        expect(page.locator("#benefit-detail-title")).to_be_focused()

        page.get_by_role("link", name="Settings", exact=True).click()
        expect(page.locator("#settings-title")).to_be_focused()
        expect(page.get_by_role("heading", name="Your private card data stays local")).to_be_visible()

        page.get_by_role("link", name="My Cards", exact=True).click()
        page.get_by_role("link", name="Settings", exact=True).click()
        skip_link = page.get_by_role("link", name="Skip to content")
        skip_link.focus()
        skip_link.press("Enter")
        expect(page.locator("#main")).to_be_focused()
        expect(page.locator("#settings")).to_be_visible()
        page.go_back()
        expect(page.locator("#my-cards")).to_be_visible()
        page.go_forward()
        expect(page.locator("#settings")).to_be_visible()
        desktop.close()

        mobile = browser.new_context(
            viewport={"width": 390, "height": 844}, color_scheme="light"
        )
        mobile_page = mobile.new_page()
        _attach_synthetic_private_route(mobile_page)
        mobile_page.goto(f"{synthetic_loopback_app}/#benefits", wait_until="networkidle")
        expect(mobile_page.locator("#benefits")).to_be_visible()
        mobile_page.get_by_role("link", name="Benefits", exact=True).click()
        expect(mobile_page.locator("#benefits-title")).to_be_focused()
        mobile.close()
        browser.close()


@pytest.mark.rendered_ui
@pytest.mark.skipif(
    not RUN_RENDERED_UI or not PLAYWRIGHT_AVAILABLE,
    reason=PLAYWRIGHT_SKIP_REASON,
)
def test_normal_card_surfaces_do_not_request_a_credential_until_reveal(
    synthetic_loopback_app: str,
) -> None:
    """A credential prompt appears only after the user asks to reveal details."""

    with sync_playwright() as playwright:
        browser_path = Path(playwright.chromium.executable_path)
        if not browser_path.is_file():
            pytest.skip(
                "Playwright Chromium driver is unavailable locally; no browser dependency was downloaded."
            )
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        mode = {"value": "healthy"}
        _attach_synthetic_private_cards_route(page, mode, [SYNTHETIC_ACTIVE_CARD])
        page.goto(f"{synthetic_loopback_app}/#my-cards", wait_until="networkidle")

        expect(page.locator("#myCardList .cardface")).to_have_count(1)
        expect(page.locator("#myCardList .cardface")).to_contain_text("In use")
        expect(page.locator("#revealCreateState")).to_be_hidden()
        expect(page.locator("#revealShownState")).to_be_hidden()
        expect(page.locator("#revealCreateButton:visible")).to_have_count(0)
        expect(page.locator('input[autocomplete="new-password"]:visible')).to_have_count(0)

        reveal = page.locator(".reveal-trigger").first
        expect(reveal).to_be_visible()
        reveal.click()
        expect(page.locator("#revealCreateState")).to_be_visible()
        expect(page.get_by_label("Your PIN")).to_be_visible()
        browser.close()


@pytest.mark.rendered_ui
@pytest.mark.skipif(
    not RUN_RENDERED_UI or not PLAYWRIGHT_AVAILABLE,
    reason=PLAYWRIGHT_SKIP_REASON,
)
def test_public_card_browser_is_not_gated_by_private_storage(
    synthetic_loopback_app: str,
) -> None:
    """The public catalog remains usable when the private card endpoint fails."""

    with sync_playwright() as playwright:
        browser_path = Path(playwright.chromium.executable_path)
        if not browser_path.is_file():
            pytest.skip(
                "Playwright Chromium driver is unavailable locally; no browser dependency was downloaded."
            )
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        _attach_synthetic_private_route(page)
        page.goto(f"{synthetic_loopback_app}/#benefits", wait_until="networkidle")

        public_cards = page.locator("#offeringPreview .public-cardface")
        expect(public_cards).to_have_count(2)
        expect(page.locator("#offeringCount")).to_have_text("2")

        category_chip = page.locator("#benefitCategoryChips .category-chip").first
        category_label = category_chip.inner_text()
        expected_rows = int(category_label.rsplit(" ", 1)[-1])
        category_chip.click()
        expect(page.locator("#benefitList .brow")).to_have_count(expected_rows)

        selected_face = None
        for face in public_cards.all():
            if "NO BENEFITS RECORDED" not in face.inner_text().upper():
                selected_face = face
                break
        assert selected_face is not None
        selected_face.click()
        expect(page.locator("#offeringDetail")).to_be_visible()
        state_labels = page.locator("#offeringDetail .offering-benefit .state").all_text_contents()
        assert state_labels and set(state_labels) <= {"Verified", "Check before use", "Sources differ"}
        browser.close()


@pytest.mark.rendered_ui
@pytest.mark.skipif(
    not RUN_RENDERED_UI or not PLAYWRIGHT_AVAILABLE,
    reason=PLAYWRIGHT_SKIP_REASON,
)
def test_private_card_failure_empty_and_filtered_states_are_distinct(
    synthetic_loopback_app: str,
) -> None:
    """Assert the card states users see, including failure/filter transitions."""

    with sync_playwright() as playwright:
        browser_path = Path(playwright.chromium.executable_path)
        if not browser_path.is_file():
            pytest.skip(
                "Playwright Chromium driver is unavailable locally; no browser dependency was downloaded."
            )
        browser = playwright.chromium.launch(headless=True)

        failed_page = browser.new_page(viewport={"width": 390, "height": 844})
        failed_mode = {"value": "failed"}
        _attach_synthetic_private_cards_route(failed_page, failed_mode, [])
        failed_page.goto(f"{synthetic_loopback_app}/#my-cards", wait_until="networkidle")
        _assert_private_storage_failure(failed_page)
        failed_page.close()

        transition_page = browser.new_page(viewport={"width": 390, "height": 844})
        transition_mode = {"value": "healthy"}
        _attach_synthetic_private_cards_route(
            transition_page, transition_mode, [SYNTHETIC_ACTIVE_CARD]
        )

        def csrf(route: Route) -> None:
            route.fulfill(status=200, json={"csrf_token": "SYNTHETIC-ONLY-csrf"})

        def add_card(route: Route) -> None:
            route.fulfill(status=200, json={"card_id": "SYNTHETIC-ONLY-added-card"})

        transition_page.route("**/api/v1/private/csrf-token", csrf)
        transition_page.route("**/api/v1/private/cards/add", add_card)
        transition_page.goto(f"{synthetic_loopback_app}/#my-cards", wait_until="networkidle")

        products = transition_page.locator("#cardAddOfferingChoices .onboarding-product")
        expect(products).to_have_count(2)
        submit = transition_page.locator("#cardAddSubmit")
        products.first.click()
        expect(submit).to_be_enabled()
        expect(submit).to_have_text("Add 1 card")
        products.nth(1).click()
        expect(submit).to_have_text("Add 2 cards")

        transition_mode["value"] = "failed"
        submit.click()
        _assert_private_storage_failure(transition_page)

        transition_page.locator("#myCardSearch").fill("anything")
        _assert_private_storage_failure(transition_page)

        archived_filter = transition_page.locator("#myCardChips button", has_text="Archived")
        expect(archived_filter).to_have_count(1)
        archived_filter.click()
        _assert_private_storage_failure(transition_page)

        transition_page.locator("#myCardSearch").fill("")
        _assert_private_storage_failure(transition_page)
        transition_page.close()

        empty_page = browser.new_page(viewport={"width": 390, "height": 844})
        empty_mode = {"value": "healthy"}
        _attach_synthetic_private_cards_route(empty_page, empty_mode, [])
        empty_page.goto(f"{synthetic_loopback_app}/#my-cards", wait_until="networkidle")
        expect(empty_page.locator("#myCardList")).to_contain_text("Your wallet is empty")
        expect(empty_page.locator("#myCardList")).not_to_contain_text("My Cards is unavailable")
        expect(empty_page.locator("#myCardSummary")).to_have_text(
            "0 in use · 0 archived · 0 with benefits recorded"
        )
        empty_page.close()

        filtered_page = browser.new_page(viewport={"width": 390, "height": 844})
        filtered_mode = {"value": "healthy"}
        _attach_synthetic_private_cards_route(
            filtered_page, filtered_mode, [SYNTHETIC_ACTIVE_CARD]
        )
        filtered_page.goto(f"{synthetic_loopback_app}/#my-cards", wait_until="networkidle")
        expect(filtered_page.locator("#myCardSummary")).to_contain_text("1 in use")
        filtered_page.locator("#myCardChips button", has_text="Archived").click()
        expect(filtered_page.locator("#myCardList")).to_contain_text(
            "No cards match the current search and lifecycle filter."
        )
        expect(filtered_page.locator("#myCardList")).not_to_contain_text("Your wallet is empty")
        filtered_page.close()
        browser.close()


@pytest.mark.rendered_ui
@pytest.mark.skipif(
    not RUN_RENDERED_UI or not PLAYWRIGHT_AVAILABLE,
    reason=PLAYWRIGHT_SKIP_REASON,
)
def test_public_search_does_not_treat_non_searchable_queries_as_empty(
    synthetic_loopback_app: str,
) -> None:
    """Emoji and whitespace queries must not silently turn into browse-all."""

    with sync_playwright() as playwright:
        browser_path = Path(playwright.chromium.executable_path)
        if not browser_path.is_file():
            pytest.skip(
                "Playwright Chromium driver is unavailable locally; no browser dependency was downloaded."
            )
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(f"{synthetic_loopback_app}/#benefits", wait_until="networkidle")
        page.get_by_role("link", name="Search", exact=True).click()
        page.get_by_role("button", name="Everything", exact=True).click()

        search = page.locator("#benefitSearch")
        rows = page.locator("#searchResults .brow")
        empty = page.locator("#searchEmpty")
        status = page.locator("#searchStatus")

        for query in ("😀", "   "):
            search.fill(query)
            expect(rows).to_have_count(0)
            expect(empty).to_be_visible()
            expect(empty).to_contain_text("No benefits match that search")
            expect(status).to_have_text("0 results shown.")
            expect(status).not_to_contain_text("2 results shown.")
            expect(status).not_to_contain_text("60 results shown.")

        search.fill("x" * 200)
        expect(rows).to_have_count(0)
        expect(empty).to_be_visible()
        assert "…" in empty.inner_text()
        assert empty.evaluate("element => element.scrollWidth <= element.clientWidth")

        page.close()
        browser.close()
