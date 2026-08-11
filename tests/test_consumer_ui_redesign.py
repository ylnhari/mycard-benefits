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
    assert "function renderSearchResults" in SCRIPT
    assert 'document.querySelector("#benefitSearchForm")?.addEventListener' in SCRIPT
    assert "state.searchScope" in SCRIPT


def test_provenance_chip_is_reusable_and_keeps_primary_actions_distinct() -> None:
    assert "function provenanceChip(evidence)" in SCRIPT
    assert "provenance-verified" in SCRIPT and "provenance-conditional" in SCRIPT
    assert "provenance-conflict" in SCRIPT
    assert "provenance-unknown" not in SCRIPT
    for label in ('"Verified"', '"Check before use"', '"Sources differ"'):
        assert label in SCRIPT
    assert "as of" in SCRIPT and "Official source" in SCRIPT
    assert "line.append(provenanceChip(evidence));" in SCRIPT
    assert "--action" in STYLE
    assert "background:var(--action)" in STYLE


def test_device_held_vault_has_no_default_lock_or_onboarding_surface() -> None:
    for identifier in ("vaultControl", "cardSetupPanel", "vaultUnlockPanel", "myCardsBadge"):
        assert f'id="{identifier}"' not in TEMPLATE
        assert f"#{identifier}" not in SCRIPT
    assert "function updateVaultNavigation(unlocked)" not in SCRIPT
    assert "Locks after 10 min idle." not in TEMPLATE
    assert "countdown" not in TEMPLATE.lower()
    assert "vault path" not in TEMPLATE.lower()
    for credential_id in (
        "cardAddPassphrase",
        "cardEditPassphrase",
        "cardLifecyclePassphrase",
        "cardReplacePassphrase",
        "cardDeletePassphrase",
        "secretErasePassphrase",
    ):
        assert credential_id not in TEMPLATE
        assert credential_id not in SCRIPT
    assert "current passphrase" not in TEMPLATE.lower()


def test_owned_cards_use_shared_cardface_and_grouped_lifecycle_lineage() -> None:
    assert "cardface" in SCRIPT and "function referenceCardRow" in SCRIPT
    assert "card.masked_last4" in SCRIPT
    assert "Add last 4" in SCRIPT
    assert 'active: "In use"' in SCRIPT
    assert 'archived: "Archived"' in SCRIPT
    assert 'c.lifecycle === "archived"' in SCRIPT
    assert "revealController.open(card, offering)" in SCRIPT
    assert "aspect-ratio:1.586" in STYLE


def test_benefits_owned_first_and_four_part_detail_are_explicit() -> None:
    assert 'id="benefitList"' in TEMPLATE
    assert 'data-benefit-scope="owned"' in TEMPLATE
    assert 'id="benefitCategoryChips"' in TEMPLATE
    assert "const ownedItems = items.filter(isOwnedBenefit)" in SCRIPT
    for section in ("Most you get", "To qualify", "How to claim", "Guests", "Evidence", "Official terms"):
        assert section in SCRIPT
    assert "Other public card alternatives" in SCRIPT
    assert "No official terms link is recorded yet." in SCRIPT


def test_benefit_chips_are_scope_counted_and_public_cards_are_browsable() -> None:
    benefits = TEMPLATE[TEMPLATE.index('<section id="benefits"') : TEMPLATE.index('<section id="search"')]
    for identifier in (
        'id="publicCardBrowser"',
        'id="offeringIssuer"',
        'id="offeringNetwork"',
        'id="offeringSearch"',
        'id="offeringPreview"',
        'id="offeringDetail"',
    ):
        assert identifier in benefits
    assert "const scopedBenefits = state.benefits.filter" in SCRIPT
    assert "const counts = scopedBenefits.reduce" in SCRIPT
    assert "benefitCategoryChipLabel(value)" in SCRIPT
    assert "More categories" in SCRIPT
    assert "const orderedItems = [...ownedItems, ...items.filter(item => !isOwnedBenefit(item))]" in SCRIPT
    assert "public: true" in SCRIPT
    assert "classList.add(\"public-cardface\")" in SCRIPT
    assert "function renderOfferingFilter" in SCRIPT
    assert "state badge" in SCRIPT
    assert "Some terms are not claimed by the source record." in SCRIPT


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
    boot = SCRIPT[SCRIPT.index("async function boot()") : SCRIPT.index("const initialView")]
    assert "loadDestinationWorkflows" not in boot
    assert "initDestinationWorkflow" not in boot


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
        assert marker not in SCRIPT
    assert "function getCatalog" in SCRIPT
    assert "function offeringCard(offering)" in SCRIPT
    assert 'card.setAttribute("role", "button")' in SCRIPT
    assert "function renderOfferingDetail()" in SCRIPT
    assert "function renderComparison()" in SCRIPT
    assert "comparison-table" in SCRIPT
    assert "Comparison data is not ready yet" in SCRIPT
    assert "innerHTML" not in SCRIPT and "insertAdjacentHTML" not in SCRIPT


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
    assert "function submitCardBatch" in SCRIPT
    assert "for (const offeringId of offeringIds)" in SCRIPT
    assert 'if (includeLastFour) values.last_four' in SCRIPT
    assert 'secretFieldsFrom("cardAdd", { includeNickname: true })' in SCRIPT


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
    assert "cardAddSelection: new Set()" in SCRIPT
    assert "cardAddIssuers: new Set()" in SCRIPT
    assert "state.cardAddIssuers.add(value)" in SCRIPT
    assert "state.cardAddSelection.add(offeringId)" in SCRIPT
    assert 'submit.textContent = count ? `Add ${count} card' in SCRIPT
    assert 'showCardAddLastFourPrompt(added)' in SCRIPT
    assert 'changes: { last_four: item.value }' in SCRIPT
    assert 'secret_fields: secretFields' in SCRIPT


def test_owned_benefit_matching_and_which_card_never_choose_an_unrelated_fallback() -> None:
    assert "function activeLocalOfferingReferences()" in SCRIPT
    assert "function benefitMatchesActiveLocalCard(benefit)" in SCRIPT
    assert "function isOwnedBenefit(benefit)" in SCRIPT
    assert "return discoveryMatch || benefitMatchesActiveLocalCard(benefit);" in SCRIPT
    search = SCRIPT[SCRIPT.index("function renderSearchResults") : SCRIPT.index('document.querySelector("#benefitSearchForm")')]
    assert "const ownedMatches = globalMatches.filter(isOwnedBenefit);" in search
    assert 'const matches = state.searchScope === "owned" ? ownedMatches' in search
    assert "state.benefits[0]" not in search


def test_benefit_detail_leads_with_consumer_information_before_rule_metadata() -> None:
    detail = SCRIPT[SCRIPT.index("function renderBenefitDetail") : SCRIPT.index("function selectBenefit")]
    assert "function consumerBenefitState(benefit)" in SCRIPT
    assert 'label: "Verified"' in SCRIPT and 'label: "Check before use"' in SCRIPT and 'label: "Sources differ"' in SCRIPT
    for section in ("Most you get", "To qualify", "How to claim", "Guests", "Evidence"):
        assert section in detail
    assert 'const details = node("dl"' in detail
    assert 'node("dt", label)' in detail
    assert detail.index('node("dt", label)') < detail.index('node("h4", "Official terms")')
