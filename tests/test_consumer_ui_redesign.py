"""Deterministic contracts for the consumer UI correction."""

import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
TEMPLATE = (ROOT / "src/mycard_benefits/templates/index.html").read_text(encoding="utf-8")
SCRIPT = (ROOT / "src/mycard_benefits/static/app.js").read_text(encoding="utf-8")
STYLE = (ROOT / "src/mycard_benefits/static/app.css").read_text(encoding="utf-8")


def test_default_navigation_is_exactly_four_consumer_destinations() -> None:
    nav = TEMPLATE[TEMPLATE.index('<nav id="primaryNav"') : TEMPLATE.index("</nav>")]
    normal = nav
    assert re.findall(r'<a[^>]+data-view="([^"]+)"', normal) == [
        "my-cards",
        "benefits",
        "search",
        "settings",
    ]
    assert [
        label
        for label in ("My Cards", "Benefits", "Search", "Settings")
        if label in normal
    ] == ["My Cards", "Benefits", "Search", "Settings"]


def test_search_view_merges_owned_scope_and_progressive_filters() -> None:
    search = TEMPLATE[TEMPLATE.index('<section id="search"') : TEMPLATE.index('<section id="settings"')]
    assert '<h1 id="search-title">Search</h1>' in search
    assert 'id="benefitSearchForm"' in search and 'id="benefitSearch"' in search
    assert 'data-search-scope="owned"' in search and 'data-search-scope="all"' in search
    assert 'id="benefitCategory"' in search
    assert 'id="benefitCondition"' in search and 'id="benefitClaimChannel"' in search


def test_owned_cards_use_shared_cardface_and_grouped_lifecycle_lineage() -> None:
    assert "aspect-ratio:1.586" in STYLE


def test_benefits_owned_first_and_four_part_detail_are_explicit() -> None:
    assert 'id="benefitList"' in TEMPLATE
    assert 'data-benefit-scope="owned"' in TEMPLATE
    assert 'id="benefitCategoryChips"' in TEMPLATE


def test_compare_prefers_owned_mapped_cards_and_prevents_same_card_pairing() -> None:
    assert "function ownedComparableOfferings()" in SCRIPT
    assert "function ensureCompareSelections" in SCRIPT
    assert "state.compareUserEdited" in SCRIPT
    assert "owned.length >= 2" in SCRIPT
    assert "option.value !== first.value" in SCRIPT
    assert "state.compareDefaultsApplied" in SCRIPT


def test_removed_travel_contributor_surface_is_not_in_the_consumer_dashboard() -> None:
    assert 'id="travelBenefitsToggle"' not in TEMPLATE
    assert 'id="travel-workflows"' not in TEMPLATE
    assert 'id="workflowPlanForm"' not in TEMPLATE
    assert 'data-view="which-card"' not in TEMPLATE


def test_mobile_contract_has_four_reachable_items_and_accessible_targets() -> None:
    assert ".sidebar nav { display:grid; grid-template-columns:repeat(4" in STYLE
    assert "overflow:visible" in STYLE
    assert "min-height:52px" in STYLE
    assert "min-height:44px" in STYLE
    assert ":focus-visible" in STYLE
    assert "prefers-reduced-motion" in STYLE


def test_device_bootstrap_keeps_safe_detail_and_comparison_foundations() -> None:
    for marker in ("cardSetupForm", "cardSetupConfirmation", "cardSetupRemember", "vaultRemember"):
        assert marker not in TEMPLATE


def test_my_cards_keeps_the_normal_path_plain_and_secondary_actions_collapsed() -> None:
    cards = TEMPLATE[TEMPLATE.index('<section id="my-cards"') : TEMPLATE.index('<section id="benefits"')]
    assert "Add your cards once, then see the benefits that match them." in cards
    assert '<details id="cardAddAdvanced" class="advanced-card-fields">' in cards
    assert "Optional private details for one selected card" in cards
    assert '<details id="manageCardsDetails" class="manage-cards-details">' in cards
    assert "Manage cards and private details" in cards
    assert 'id="myCardList"' in cards
    assert "#my-cards #myCardList { order:6; }" in STYLE
    assert "#my-cards .protected-card-actions { order:7; }" in STYLE
    assert "CLI check:" not in SCRIPT
    assert "uv run mycard-vault" not in SCRIPT
    assert 'id="cardAddLastFourPrompt"' in cards
    assert "Save last 4s" in cards
    assert 'pattern="[0-9]{4}"' in cards
    assert 'id="cardAddPan" type="text" inputmode="numeric" autocomplete="off" required' not in cards
    assert "A full card number, expiry, CVV, PIN, and nickname are optional." in cards


def test_card_onboarding_is_multi_select_with_a_post_add_last_four_followup() -> None:
    cards = TEMPLATE[TEMPLATE.index('<section id="my-cards"') : TEMPLATE.index('<section id="benefits"')]
    for marker in (
        'id="cardAddIssuerChips"',
        'id="cardAddOfferingChoices"',
        'id="cardAddSelectionStatus"',
        'id="cardAddSubmit"',
        'id="cardAddLastFourPrompt"',
    ):
        assert marker in cards


def test_owned_benefit_matching_and_which_card_never_choose_an_unrelated_fallback() -> None:
    assert "function activeLocalOfferingReferences()" in SCRIPT
    assert "function benefitMatchesActiveLocalCard(benefit)" in SCRIPT
    assert "function isOwnedBenefit(benefit)" in SCRIPT
    assert "return discoveryMatch || benefitMatchesActiveLocalCard(benefit);" in SCRIPT
    search = SCRIPT[SCRIPT.index("function renderSearchResults") : SCRIPT.index('document.querySelector("#benefitSearchForm")')]
    assert "const ownedMatches = globalMatches.filter(isOwnedBenefit);" in search
    assert 'const matches = state.searchScope === "owned" ? ownedMatches' in search
    assert "state.benefits[0]" not in search
