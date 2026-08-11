from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mycard_benefits.app import create_app
from mycard_benefits.config import Settings

ROOT = Path(__file__).parents[1]


def _client(tmp_path: Path) -> TestClient:
    settings = Settings(data_dir=tmp_path / "data", catalog_dir=ROOT / "catalog", port=8777)
    return TestClient(create_app(settings))


def test_dashboard_has_all_public_navigation_and_honest_vault_gate(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        page = client.get("/")

    assert page.status_code == 200
    for item in ("My Cards", "Benefits", "Search", "Settings"):
        assert item in page.text
    assert 'href="#search"' in page.text
    assert 'href="#which-card"' not in page.text
    assert "external launcher" not in page.text
    assert "Card numbers, CVV, PIN, names, notes, and exact expiry details are kept private." in page.text
    assert "Privacy details" in page.text
    for removed_id in (
        'id="vaultControl"',
        'id="cardSetupPanel"',
        'id="vaultUnlockPanel"',
        'id="myCardsBadge"',
    ):
        assert removed_id not in page.text
    assert "Checking access" not in page.text


def test_catalog_dashboard_assets_use_read_only_endpoints_and_safe_dom_updates() -> None:
    script = (ROOT / "src" / "mycard_benefits" / "static" / "app.js").read_text(encoding="utf-8")
    style = (ROOT / "src" / "mycard_benefits" / "static" / "app.css").read_text(encoding="utf-8")

    assert 'getCatalog("offerings")' in script
    assert 'getCatalog("benefits")' in script
    assert 'fetch("/api/v1/private/cards"' in script
    assert 'credentials: "same-origin"' in script
    assert 'cache: "no-store"' in script
    assert "Rover" not in script
    assert "Companion Dashboard" not in script
    assert "function renderPrivateCards" in script
    assert "textContent" in script
    for fragment in (
        "benefit.provider",
        "benefit.official_reference",
        "benefit.redemption_steps",
        "benefit.exclusions",
        "safeHref(benefit.official_reference)",
    ):
        assert fragment in script
    assert "innerHTML" not in script
    assert "insertAdjacentHTML" not in script
    assert 'rel = "noopener noreferrer"' in script
    assert "@media (max-width:850px)" in style
    assert "prefers-reduced-motion" in style


def test_dashboard_accessibility_follow_up_has_target_sizes_and_focus_fallback() -> None:
    script = (ROOT / "src" / "mycard_benefits" / "static" / "app.js").read_text(encoding="utf-8")
    style = (ROOT / "src" / "mycard_benefits" / "static" / "app.css").read_text(encoding="utf-8")

    assert "min-height:44px" in style
    assert "summary { display:flex; align-items:center; min-height:44px" in style
    assert (
        ".evidence-list a,.source-card a { display:inline-flex; align-items:center; min-height:44px"
        in style
    )
    assert "function viewFromHash()" in script
    assert "legacyViewAliases" in script
    assert "heading.focus({ preventScroll: true })" in script
    assert "showView(initialView);" in script
    assert "innerHTML" not in script


def test_private_cards_rows_join_public_catalog_metadata_without_secret_fallbacks() -> None:
    script = (ROOT / "src" / "mycard_benefits" / "static" / "app.js").read_text(encoding="utf-8")

    assert "function offeringForCard" in script
    assert "candidate.slug === card.offering_id" in script
    assert "function referenceCardRow" in script
    assert "cardFaceData(card, offering)" in script
    assert "offering.issuer_id" in script and "networkLabel(offering?.network_id)" in script
    assert "offering.display_name" in script
    assert "UNMATCHED_CARD_LABEL" in script
    assert '"Unmatched variant"' in script
    assert "card.offering_id.replaceAll" not in script
    assert "Local card" not in script


def test_private_card_search_covers_product_issuer_network_lifecycle_and_safe_identifiers() -> None:
    script = (ROOT / "src" / "mycard_benefits" / "static" / "app.js").read_text(encoding="utf-8")

    assert "function cardSearchText" in script
    for field in (
        "offering?.display_name",
        "offering?.issuer_id",
        "offering?.network_id",
        "offering?.slug",
        "card.lifecycle",
        "card.offering_id",
        "card.card_id",
    ):
        assert field in script
    assert "if (query && !cardSearchText(card, offeringForCard(card)).includes(query)) return false;" in script
    assert "if (filters.lifecycle.size && !filters.lifecycle.has(card.lifecycle)) return false;" in script
    assert "if (filters.type.size && !filters.type.has(cardTypeForOffering(offering))) return false;" in script


def test_private_cards_keep_protected_boundary_and_browser_cache_policy() -> None:
    script = (ROOT / "src" / "mycard_benefits" / "static" / "app.js").read_text(encoding="utf-8")
    template = (ROOT / "src" / "mycard_benefits" / "templates" / "index.html").read_text(
        encoding="utf-8"
    )
    style = (ROOT / "src" / "mycard_benefits" / "static" / "app.css").read_text(encoding="utf-8")

    assert (
        'fetch("/api/v1/private/cards", { headers: { Accept: "application/json" }, credentials: "same-origin", cache: "no-store" })'
        in script
    )
    assert 'response.headers["Cache-Control"]' in script or "no-store" in script
    assert "innerHTML" not in script and "insertAdjacentHTML" not in script
    assert ".unmatched-note" in style
    assert 'placeholder="Product, bank, network, or status"' in template
    assert "Card numbers, CVV, PIN" in template


def test_private_card_detail_shows_only_allowlisted_public_and_envelope_fields() -> None:
    script = (ROOT / "src" / "mycard_benefits" / "static" / "app.js").read_text(encoding="utf-8")
    template = (ROOT / "src" / "mycard_benefits" / "templates" / "index.html").read_text(encoding="utf-8")

    assert "secretFieldsFrom" in script
    assert "Secret fields were cleared" in script
    assert "Card numbers, CVV, PIN, names, notes, and exact expiry details are kept private." in template
    assert 'id="cardAddForm"' in template and 'id="cardDeleteForm"' in template
    assert 'node("dd", card.offering_id)' not in script
    assert 'node("dd", card.card_id)' not in script
    assert 'node("dd", card.replacement_card_id)' not in script
    assert "card.secret" not in script


def test_demo_run_shows_persistent_banner_and_switches_off_my_cards(tmp_path: Path) -> None:
    demo_settings = Settings(
        data_dir=tmp_path / "demo-data",
        catalog_dir=ROOT / "catalog",
        port=8777,
        demo=True,
    )
    with TestClient(create_app(demo_settings)) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert 'id="demoBanner"' in page.text
        assert "Synthetic demo run" in page.text
        assert "demo-data" in page.text
        assert "--demo" in page.text
        assert "an explicit" in page.text
        assert "changes only that demo activity folder" in page.text
        cards = client.get("/api/v1/private/cards")
        assert cards.status_code == 503
        assert cards.json() == {
            "detail": {"code": "demo", "message": "Private card list is switched off in demo mode"}
        }
        health = client.get("/api/v1/health").json()
        assert health["app_id"] == "mycard-benefits"
        assert health["status"] == "ok"

    with _client(tmp_path) as client:
        page = client.get("/")
        assert 'id="demoBanner"' not in page.text
        assert "Synthetic demo run" not in page.text


def test_active_surfaces_have_neutral_copy_and_self_contained_startup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class StubKeyring:
        def get_password(self, service_name: str, username: str) -> str | None:
            return None

    import mycard_benefits.vault.router as router_module

    monkeypatch.setattr(router_module, "load_keyring", lambda: StubKeyring())
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    guide = (ROOT / "docs" / "USER-GUIDE.md").read_text(encoding="utf-8")
    template = (ROOT / "src" / "mycard_benefits" / "templates" / "index.html").read_text(
        encoding="utf-8"
    )
    script = (ROOT / "src" / "mycard_benefits" / "static" / "app.js").read_text(encoding="utf-8")
    router = (ROOT / "src" / "mycard_benefits" / "vault" / "router.py").read_text(encoding="utf-8")

    forbidden = (
        "Rover sign-in",
        "Rover login",
        "Companion Dashboard",
        "rover_proxy",
        "rover_secret",
    )
    for content in (readme, guide, template, script, router):
        for term in forbidden:
            assert term.lower() not in content.lower()

    assert "MyCard <b>Benefits</b>" in template
    assert "Public catalog · private vault" in template
    assert "Local-first" in template

    assert '<h2 id="data-location-title">Data location</h2>' in template
    assert "LOCAL ONLY" in template
    assert "Your private card data stays local" in template
    assert "<h3>Remote access</h3>" not in template
    assert "external launcher" not in template

    with _client(tmp_path) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "MyCard" in page.text and "Benefits" in page.text
        assert "Public catalog · private vault" in page.text
        assert "Data location" in page.text
        assert "LOCAL ONLY" in page.text

        health = client.get("/api/v1/health").json()
        assert health["status"] == "ok"
        assert health["app_id"] == "mycard-benefits"

        cards_resp = client.get("/api/v1/private/cards")
        assert cards_resp.status_code == 200
        assert cards_resp.json()["cards"] == []
        assert (tmp_path / "data" / "private" / "vault.json").is_file()


def test_unmatched_variant_state_is_friendly_and_never_renders_raw_identifier() -> None:
    script = (ROOT / "src" / "mycard_benefits" / "static" / "app.js").read_text(encoding="utf-8")

    assert 'const UNMATCHED_CARD_LABEL = "Unmatched variant";' in script
    assert "const UNMATCHED_NOTE =" in script
    assert 'node("p", UNMATCHED_NOTE, "unmatched-note")' in script, (
        "the friendly guidance note must be used by the row"
    )
    assert script.count('node("p", UNMATCHED_NOTE, "unmatched-note")') == 1
    assert (
        'revealButton.setAttribute("aria-label", `Show full details for ${offering?.display_name || "this card"}`)'
        in script
    )
    assert '"unmatched card"' not in script
    for fragment in (
        'node("p", card.offering_id)',
        'node("h3", card.offering_id)',
        'node("dd", card.offering_id)',
        'node("p", offering?.slug)',
        'node("h3", offering?.slug)',
        'node("dd", offering?.slug)',
        'node("p", card.card_id)',
        'node("h3", card.card_id)',
        'node("dd", card.card_id)',
        'node("p", card.replacement_card_id)',
    ):
        assert fragment not in script, fragment
    card_row = script[script.index("function referenceCardRow") : script.index("function refreshCardFilters")]
    for rendered in (card_row,):
        assert 'node("p", card.offering_id)' not in rendered
        assert 'node("h3", card.offering_id)' not in rendered
        assert 'node("dd", card.offering_id)' not in rendered
        assert 'node("p", card.card_id)' not in rendered
        assert 'node("h3", card.card_id)' not in rendered
        assert 'node("dd", card.card_id)' not in rendered
        assert 'node("p", card.replacement_card_id)' not in rendered
    assert "cardFaceData(card, offering)" in card_row and "card.card_id" in card_row
    for visible_use in (
        'node("p", card.card_id)',
        'node("h3", card.card_id)',
        'node("dd", card.card_id)',
        'node("a", card.card_id)',
        'setAttribute("aria-label", card.card_id)',
        'setAttribute("href", card.card_id)',
        'dataset.card_id = card.card_id',
        'dataset.cardId = card.card_id',
    ):
        assert visible_use not in script, visible_use


def test_removed_planner_surface_matches_the_four_screen_dashboard(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        page = client.get("/")
    assert page.status_code == 200
    assert 'data-view="search"' in page.text
    assert 'href="#which-card"' not in page.text
    for fragment in (
        'id="planner"',
        'id="purchaseChoiceForm"',
        'id="purchaseMerchant"',
        'id="purchaseCategory"',
        'id="purchaseAmount"',
        'id="purchaseCardChoices"',
        'id="plannerForm"',
        'id="plannerMerchant"',
        'maxlength="200"',
        'id="plannerCategory"',
        'id="plannerAmount"',
        'id="plannerDate"',
        'id="plannerCurrency"',
        'id="plannerChannelOfficial"',
        'id="plannerChannelThirdParty"',
        'id="plannerChannelAffiliate"',
        'id="plannerCards"',
        'id="plannerAddCard"',
        'id="plannerSubmit"',
        'id="plannerReset"',
        'id="plannerStatus"',
        'id="plannerResults"',
    ):
        assert fragment not in page.text, fragment










def test_benefit_detail_distinguishes_public_terms_from_local_product_matches(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        page = client.get("/")
    script = (ROOT / "src" / "mycard_benefits" / "static" / "app.js").read_text(encoding="utf-8")
    style = (ROOT / "src" / "mycard_benefits" / "static" / "app.css").read_text(encoding="utf-8")

    assert page.status_code == 200
    for fragment in (
        'id="benefitDetail"',
        "Select a benefit to see what it is, how to qualify, how to claim it, and the official terms.",
    ):
        assert fragment in page.text, fragment
    for fragment in (
        "function renderBenefitDetail",
        "function selectBenefit",
        "function localBenefitMatch",
        "function alternativeBenefitCard",
        "function formatEligibility",
        "function benefitDates",
        "local product match is shown separately from the public benefit",
        "It never proves eligibility",
        "Other public card alternatives",
        "category. That category does not make their benefits equivalent",
        "benefit.eligibility",
        "benefit.redemption_steps",
        "benefit.exclusions",
        "safeHref(benefit.official_reference)",
    ):
        assert fragment in script, fragment
    detail_slice = script[script.index("function localBenefitMatch") : script.index("function selectBenefit")]
    for private_field in ("card.pan", "card.cvv", "card.pin", "card.card_id", "card.offering_id"):
        assert private_field not in detail_slice, private_field
    assert ".benefit-detail-card" in style and ".benefit-match-card" in style
    assert "innerHTML" not in script and "insertAdjacentHTML" not in script


def test_archived_and_expired_card_wording_remain_distinct() -> None:
    script = (ROOT / "src" / "mycard_benefits" / "static" / "app.js").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    guide = (ROOT / "docs" / "USER-GUIDE.md").read_text(encoding="utf-8")

    assert 'c.lifecycle === "archived" ? "archived" : "in use"' in script
    assert "Archived local record — kept for history. Archived does not mean expired." in script
    assert 'expired: "Expired"' in script
    assert "**archived** card record is retained history" in readme
    assert "It is not a statement that the" in readme
    assert "physical card has expired" in readme
    assert "`archived` retains a historical record" in guide
    assert "An **archived** row means the record is kept as history" in guide
