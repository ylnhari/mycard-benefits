from __future__ import annotations

from pathlib import Path

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
    for item in (
        "Overview",
        "My Cards",
        "Benefits",
        "Ask",
        "Compare",
        "Expiring Soon",
        "Updates",
        "Sources",
        "Research Queue",
        "Settings",
    ):
        assert item in page.text
    assert 'href="#ask"' in page.text
    assert "external launcher" not in page.text
    assert "Secret card fields are never returned" in page.text
    assert "PAN, CVV, PIN" in page.text
    assert "disabled" in page.text


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
    assert 'return views.has(requested) ? requested : "overview"' in script
    assert "heading.focus({ preventScroll: true })" in script
    assert "showView(initialView);" in script
    assert "showView(view, { focus: true });" in script
    assert "innerHTML" not in script


def test_qa_ui_is_accessible_bounded_and_uses_post_only(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        page = client.get("/")
    script = (ROOT / "src" / "mycard_benefits" / "static" / "app.js").read_text(encoding="utf-8")
    style = (ROOT / "src" / "mycard_benefits" / "static" / "app.css").read_text(encoding="utf-8")

    for fragment in (
        'id="qaForm"',
        'id="qaQuery"',
        'maxlength="500"',
        'id="qaStatus"',
        'role="status"',
        'aria-live="polite"',
        'id="qaResults"',
    ):
        assert fragment in page.text
    assert 'fetch("/api/v1/qa", { method: "POST"' in script
    assert 'method: "GET"' not in script
    assert "value.length > 500" in script
    assert 'event.key === "Enter"' in script and "event.isComposing" in script
    assert 'event.key === "Escape"' in script
    assert "submit.disabled = true" in script and 'form.setAttribute("aria-busy", "true")' in script
    assert "heading.focus({ preventScroll: true })" in script
    assert "innerHTML" not in script and "insertAdjacentHTML" not in script
    assert ".qa-controls input" in style and "min-height:44px" in style
    assert ".qa-controls { display:grid; grid-template-columns:1fr; }" in style


def test_qa_renderer_covers_safe_results_examples_and_fallbacks() -> None:
    script = (ROOT / "src" / "mycard_benefits" / "static" / "app.js").read_text(encoding="utf-8")

    for fragment in (
        "function renderQaResult",
        "result.message",
        "result.benefits",
        "result.offerings",
        "result.choices",
        "result.suggestions",
        'result.intent === "no_result"',
        "function qaFactCard",
        "function qaLink",
        "safeHref(url)",
    ):
        assert fragment in script
    assert 'link.target = "_blank"' in script and 'link.rel = "noopener noreferrer"' in script
    assert "Public catalog unavailable — no private fallback is used." in script
    assert "Unable to answer that question. Try a supported public catalog question." in script
    assert (
        "data-qa-example" in script
        and "function supportedSuggestion" in script
        and "function qaButton" in script
    )
    assert "localStorage" not in script[script.index("function setQaStatus") :]


def test_private_cards_rows_join_public_catalog_metadata_without_secret_fallbacks() -> None:
    script = (ROOT / "src" / "mycard_benefits" / "static" / "app.js").read_text(encoding="utf-8")

    assert "function offeringForCard" in script
    assert "candidate.slug === card.offering_id" in script
    assert "function privateCardRow" in script
    assert "offering.issuer_id" in script and "offering.network_id.replaceAll" in script
    assert "offering.display_name" in script
    assert "UNMATCHED_CARD_LABEL" in script
    assert '"Unmatched card variant"' in script
    assert "card.offering_id.replaceAll" not in script
    assert "Local card" not in script
    assert "function privateCardDates" in script
    assert "card.created_at" in script and "card.updated_at" in script


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
    assert (
        "if (query && !cardSearchText(card, offeringForCard(card)).includes(query)) return false;"
        in script
    )
    assert "if (lifecycle && card.lifecycle !== lifecycle) return false;" in script


def test_private_cards_empty_and_unavailable_states_are_explicit_and_actionable(
    tmp_path: Path,
) -> None:
    script = (ROOT / "src" / "mycard_benefits" / "static" / "app.js").read_text(encoding="utf-8")
    with _client(tmp_path) as client:
        page = client.get("/").text

    assert (
        "No card records are in this vault yet. Import cards with the mycard-vault command line, then return here to see them listed."
        in script
    )
    assert "No cards match the current search and lifecycle filter." in script
    assert "The private vault could not be opened, so no card list can be shown." in script
    assert "not in demo mode" in script and "operating-system keyring" in script
    assert "no fallback data was used" in script
    assert "This card's product identifier has no match in the public catalog." in script
    assert "secret_fields" not in script
    assert 'id="myCardList"' in page and 'aria-live="polite"' in page
    assert "Product, bank, network, or status" in page


def test_private_cards_keep_read_only_boundary_and_browser_cache_policy() -> None:
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
    assert "PAN, CVV, PIN" in template


def test_private_card_detail_shows_only_allowlisted_public_and_envelope_fields() -> None:
    script = (ROOT / "src" / "mycard_benefits" / "static" / "app.js").read_text(encoding="utf-8")

    assert "function cardDetailSection" in script
    assert "function detailRow" in script
    for label in (
        "Product",
        "Issuer",
        "Network",
        "Lifecycle",
        "Added",
        "Updated",
        "Replacement",
        "Replaces",
    ):
        assert f'detailRow("{label}"' in script
    assert "offering.display_name" in script and "offering.issuer_id" in script
    assert "offering.network_id.replaceAll" in script
    assert "Not matched in the public catalog" in script
    assert "secret_fields" not in script
    assert 'node("dd", card.offering_id)' not in script
    assert 'node("dd", card.card_id)' not in script
    assert 'node("dd", card.replacement_card_id)' not in script
    assert "card.secret" not in script


def test_private_card_detail_is_keyboard_reachable_and_escape_closes() -> None:
    script = (ROOT / "src" / "mycard_benefits" / "static" / "app.js").read_text(encoding="utf-8")

    assert "View details" in script and "Hide details" in script
    assert "card-detail-toggle" in script
    assert "aria-expanded" in script and "aria-controls" in script
    assert "aria-label" in script
    assert "function toggleCardDetail" in script
    assert 'event.key === "Escape"' in script
    assert "heading.focus({ preventScroll: true })" in script
    assert "button.focus()" in script
    assert 'button.type = "button"' in script


def test_private_card_detail_replacement_links_and_unmatched_state_are_safe() -> None:
    script = (ROOT / "src" / "mycard_benefits" / "static" / "app.js").read_text(encoding="utf-8")

    assert "function replacementText" in script and "function replacementOfText" in script
    assert "Replaced by" in script
    assert "Replaced by a card not listed in this vault." in script
    assert "This card replaced" in script
    assert "UNMATCHED_CARD_LABEL" in script
    assert "replacement_card_id" in script
    assert "Replacement history is linked." in script
    assert "card-detail" in script and "card-detail-list" in script
    assert "Fix the identifier in the import file or request the card variant" in script
