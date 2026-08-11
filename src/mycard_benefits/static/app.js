import { createRevealController } from "./reveal.js";

const root = document.documentElement;
const themeKey = "mycard-benefits-theme";
const state = {
  offerings: [], benefits: [], discoveryResults: [], privateCards: [], ownedDiscoveryCards: [], privateAggregates: [], privateAttempts: [], privateStateRevision: null, privateCardsAvailable: false, personalStateAvailable: false, ownedDiscoveryAvailable: false,
  discoveryNextCursor: null, ownedDiscoveryDiagnostic: null,
  privateCardsRequested: false,
  reminderPreferencesRequested: false, selectedBenefitId: null,
  selectedOfferingId: null,
  cardAddSelection: new Set(), cardAddIssuers: new Set(), pendingLastFourCards: [],
  destinationWorkflows: [], destinationCandidates: [], selectedDestinationWorkflowId: null,
  destinationPlanResult: null,
  pendingSecretEraseCardId: null,
  compareDefaultsApplied: false, compareUserEdited: false,
  searchScope: "owned", benefitScope: "all", benefitCategory: "",
  cardFilters: { lifecycle: new Set(), type: new Set(), benefit: new Set(), issuer: new Set() },
};
const views = new Set([...document.querySelectorAll("[data-panel]")].map(panel => panel.id));
const legacyViewAliases = new Map([["overview", "my-cards"], ["travel-workflows", "benefits"]]);
let privateLoadPromise = null;

function requestPrivateCards() {
  if (privateLoadPromise) return privateLoadPromise;
  state.privateCardsRequested = true;
  privateLoadPromise = loadPrivateCards().finally(() => { privateLoadPromise = null; });
  return privateLoadPromise;
}

function prefersDarkTheme() {
  return Boolean(globalThis.matchMedia?.("(prefers-color-scheme: dark)")?.matches);
}
function currentTheme() {
  if (root.dataset.theme === "dark") return "dark";
  if (root.dataset.theme === "light") return "light";
  return prefersDarkTheme() ? "dark" : "light";
}
function setTheme(theme, { persist = true } = {}) {
  if (theme === "light" || theme === "dark") {
    root.dataset.theme = theme;
    if (persist) localStorage.setItem(themeKey, theme);
  } else {
    root.removeAttribute("data-theme");
    if (persist) localStorage.removeItem(themeKey);
  }
  const activeTheme = currentTheme();
  const label = activeTheme === "dark" ? "Use light theme" : "Use dark theme";
  for (const button of document.querySelectorAll("#themeToggle, #themeToggleInline")) {
    button.textContent = label;
    button.setAttribute("aria-pressed", String(activeTheme === "dark"));
  }
}
const stored = localStorage.getItem(themeKey);
setTheme(stored === "light" || stored === "dark" ? stored : null, { persist: false });
for (const button of document.querySelectorAll("#themeToggle, #themeToggleInline")) {
  button.addEventListener("click", () => setTheme(currentTheme() === "light" ? "dark" : "light"));
}

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined && text !== null) element.textContent = text;
  if (className) element.className = className;
  return element;
}
function clear(element) { element.replaceChildren(); }
function fmtDate(value) { return value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(`${value}T00:00:00`)) : "Not specified"; }
function safeHref(value) {
  try { const url = new URL(value); return ["http:", "https:"].includes(url.protocol) ? url.href : null; }
  catch { return null; }
}
function officialBenefitHref(benefit) {
  const officialReference = safeHref(benefit.official_reference);
  if (officialReference || benefit.official_reference) return officialReference;
  const officialEvidenceClasses = new Set(["administering_terms", "issuer_document", "network_rule", "merchant_terms"]);
  const approvedEvidence = Array.isArray(benefit.evidence)
    ? benefit.evidence.find(item => item?.state === "verified" && officialEvidenceClasses.has(item?.source_policy_class) && safeHref(item?.source_url))
    : null;
  return safeHref(approvedEvidence?.source_url);
}
function officialBenefitLinkText(benefit, compact = false) {
  return benefit.official_reference ? (compact ? "Official terms" : "Open official terms") : (compact ? "Official source" : "Open official source");
}
function allowanceCount(allowance, fallback) {
  return allowance?.count ?? allowance?.cap ?? fallback;
}
function benefitHowToUse(benefit) {
  const steps = Array.isArray(benefit.redemption_steps) ? [...benefit.redemption_steps] : [];
  const claimRoute = benefit.allowance?.claim_route;
  if (typeof claimRoute === "string" && claimRoute) steps.push(humanizeBenefitTerm(claimRoute));
  return steps;
}
function humanizeBenefitTerm(value) {
  return String(value || "").replaceAll("_", " ").replaceAll(".", " ").replace(/\s+/g, " ").trim();
}
function humanLifecycleLabel(value) {
  const labels = { active: "In use", archived: "Archived", lost: "Lost", stolen: "Stolen", expired: "Expired", closed: "Closed", retired: "Retired", replaced: "Replaced", renewed: "Renewed", applied: "Applied", pending: "Pending", frozen: "Frozen", upgraded: "Upgraded", downgraded: "Downgraded" };
  return labels[value] || "Status not recorded";
}
function networkLabel(value) {
  const labels = {
    mastercard: "MC", visa: "VISA", rupay: "RUPAY", amex: "AMEX", diners: "DINERS", discover: "DISCOVER", maestro: "MAESTRO",
    "visa-signature": "VISA Signature", "visa-platinum": "VISA Platinum", "visa-infinite": "VISA Infinite",
    "rupay-select": "RuPay Select", "rupay-platinum": "RuPay Platinum",
  };
  const key = String(value || "").toLocaleLowerCase().replaceAll("_", "-");
  return labels[key] || null;
}
function marketLabel(value) {
  const labels = { IN: "India" };
  const key = String(value || "").toUpperCase();
  return labels[key] || humanizeBenefitTerm(key) || "Market not recorded";
}
function humanIssuerLabel(value) {
  const labels = {
    "au-small-finance-bank": "AU Small Finance Bank", "axis-bank": "Axis Bank", "city-union-bank": "City Union Bank",
    "dbs-bank": "DBS Bank", "federal-bank": "Federal Bank", "hdfc-bank": "HDFC Bank", "hsbc-india": "HSBC India",
    "icici-bank": "ICICI Bank", "idfc-bank": "IDFC Bank", "idfc-first-bank": "IDFC FIRST Bank", "indusind-bank": "IndusInd Bank",
    "kotak-mahindra-bank": "Kotak Mahindra Bank", "rbl-bank": "RBL Bank", "sbi-card": "SBI Card", "yes-bank": "YES BANK",
  };
  const key = String(value || "").toLocaleLowerCase();
  if (labels[key]) return labels[key];
  return humanizeBenefitTerm(key).replaceAll("-", " ").replace(/\b\w/g, letter => letter.toUpperCase()) || "Card issuer";
}
function consumerFieldLabel(value) {
  const normalized = humanizeBenefitTerm(value).toLocaleLowerCase();
  const labels = {
    "calendar quarter eligible net posted spend inr": "eligible net posted spend in INR for the calendar quarter",
    "preceding calendar quarter net spend inr": "net spend in INR in the preceding calendar quarter",
    "preceding calendar quarter net retail spend inr": "net retail spend in INR in the preceding calendar quarter",
    "preceding three calendar months dbs spend inr": "DBS spend in INR over the preceding three calendar months",
    "transaction in preceding days": "a transaction in the preceding period",
    "checkout channel": "checkout channel",
    "transaction channel": "transaction channel",
    "transaction kind": "transaction type",
    "movie ticket count": "number of movie tickets",
  };
  return labels[normalized] || null;
}
function consumerCatalogState(benefit) {
  return ["verified", "sources_differ", "check_before_use"].includes(benefit?.state)
    ? benefit.state
    : "check_before_use";
}
const primaryAllowanceKeys = Object.freeze({
  lounge: ["count", "vouchers_per_quarter", "visits_per_quarter", "vouchers_per_year", "visits_per_year"],
  reward_points: ["cashpoints_percent", "partner_tata_non_emi_percent", "other_non_emi_percent", "any_upi_percent", "cashpoints", "monthly_cap_neucoins", "calendar_month_cap"],
  conversion: ["inr_per_cashpoint", "neucoins_per_inr", "maximum_airmiles_per_reward_point", "travel_booking_redemption_percent_cap"],
  movie: ["discount_percent", "ticket_cap_inr", "monthly_cap_inr"],
  cashback: ["maximum_cashback_inr", "cashback_percent", "discount_percent"],
  voucher: ["voucher_value_inr", "count", "cashpoints"],
});
const numericTextPattern = /^[+-]?(?:\d+(?:\.\d+)?|\.\d+)$/;
function numericText(value) {
  if (typeof value === "boolean") return null;
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : null;
  if (typeof value !== "string" || value.length > 64 || !numericTextPattern.test(value)) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? String(parsed) : null;
}
function numericDisplay(value) {
  const rendered = numericText(value);
  if (rendered === null) return null;
  if (!rendered.includes(".")) return Number(rendered).toLocaleString("en-US", { maximumFractionDigits: 0 });
  return rendered;
}
function consumerValue(value, inr = false) {
  if (typeof value === "boolean") return value ? "yes" : "no";
  const number = numericDisplay(value);
  if (number !== null) return inr ? `INR ${number}` : number;
  if (typeof value === "string") return humanizeBenefitTerm(value);
  if (Array.isArray(value)) return value.map(item => consumerValue(item, inr)).filter(Boolean).join(" or ") || null;
  return null;
}
function allowancePeriod(value) {
  if (value === "qualifying_calendar_quarter") return "qualifying calendar quarter";
  if (value === "calendar_quarter") return "calendar quarter";
  return typeof value === "string" ? humanizeBenefitTerm(value) : "the stated period";
}
function consumerAllowanceLine(key, value, allowance, benefit) {
  const number = numericDisplay(value);
  if (key === "count" && number !== null) {
    let unit = String(allowance.unit || "use").replaceAll("_", " ");
    if (benefit?.category === "lounge" || unit.includes("lounge")) unit = "lounge visit";
    else if (unit.includes("voucher")) unit = "voucher";
    return `Up to ${number} ${unit}${number === "1" ? "" : "s"} per ${allowancePeriod(allowance.period)}`;
  }
  if (key === "discount_percent" && number !== null) return `${number}% discount`;
  if (key === "cashpoints_percent" && number !== null) return `${number}% CashPoints`;
  if (key === "foreign_exchange_markup_percent" && number !== null) return `${number}% foreign-exchange markup`;
  if (key === "claim_window_days" && number !== null) return `Claim within ${number} days`;
  if (key === "monthly_cap_inr" && number !== null) return `Up to INR ${number} per month`;
  if (["cap_inr", "transaction_cap_inr", "ticket_cap_inr"].includes(key) && number !== null) return `Up to INR ${number}`;
  if (key.endsWith("_inr") && number !== null) return `${humanizeBenefitTerm(key.slice(0, -4)).replace(/^./, letter => letter.toUpperCase())}: INR ${number}`;
  if (key.endsWith("_percent") && number !== null) return `${number}% ${humanizeBenefitTerm(key.slice(0, -8))}`;
  if (key.endsWith("_days") && number !== null) return `${humanizeBenefitTerm(key.slice(0, -5)).replace(/^./, letter => letter.toUpperCase())}: ${number} days`;
  if (key === "india_only" && typeof value === "boolean") return value ? "India only" : "Not limited to India";
  const simpleLabels = {
    visits: "lounge visit", vouchers_per_quarter: "voucher per qualifying quarter",
    vouchers_per_year: "voucher per year", uses_per_month: "use per month",
    uses_per_financial_year: "use per financial year", complimentary_tickets: "complimentary ticket",
    cashpoints: "CashPoints",
  };
  if (Object.hasOwn(simpleLabels, key) && number !== null) {
    let label = simpleLabels[key];
    if (number !== "1") label = label.replace("visit", "visits").replace("voucher", "vouchers").replace("use", "uses").replace("ticket", "tickets");
    if (key === "vouchers_per_year" && Object.hasOwn(allowance, "vouchers_per_quarter")) return `Up to ${number} vouchers per year — only if you qualify in all four quarters`;
    return `${number} ${label}`;
  }
  const rendered = consumerValue(value, key.endsWith("_inr"));
  return rendered === null ? null : `${humanizeBenefitTerm(key).replace(/^./, letter => letter.toUpperCase())}: ${rendered}`;
}
function primaryAllowanceText(benefit) {
  const allowance = benefit?.allowance;
  if (!allowance || typeof allowance !== "object" || Array.isArray(allowance)) return null;
  const entries = Object.entries(allowance);
  if (!Object.hasOwn(allowance, "count") && Object.hasOwn(allowance, "cap")) entries.unshift(["count", allowance.cap]);
  const details = entries
    .filter(([key]) => !["not_claimed", "conditions", "claim_route"].includes(key))
    .map(([key, value]) => [key, consumerAllowanceLine(key, value, allowance, benefit)])
    .filter(([, line]) => line !== null);
  for (const key of primaryAllowanceKeys[benefit?.benefit_type] || []) {
    const match = details.find(([detailKey]) => detailKey === key);
    if (match) return match[1];
  }
  return details[0]?.[1] || null;
}
function consumerAllowanceText(benefit) {
  return primaryAllowanceText(benefit);
}
function primaryConditionText(benefit) {
  const condition = Array.isArray(benefit?.conditions)
    ? benefit.conditions.find(item => item && (typeof item === "string" || typeof item?.value === "string" || typeof item === "object"))
    : null;
  if (condition) {
    if (typeof condition === "string") return humanizeConditionText(condition);
    if (typeof condition.value === "string" && condition.value.trim()) return humanizeConditionText(condition.value.trim());
    return friendlyPredicate(condition);
  }
  const eligibility = Array.isArray(benefit?.eligibility) ? benefit.eligibility[0] : null;
  if (!eligibility) return null;
  return formatEligibility(eligibility);
}
function humanizeConditionText(value) {
  return humanizeBenefitTerm(value)
    .replace(/\bnot\s+in\b/gi, "is not one of")
    .replace(/\b(?:gte|greater\s+than\s+or\s+equal\s+to)\b/gi, "at least")
    .replace(/\b(?:lte|less\s+than\s+or\s+equal\s+to)\b/gi, "up to")
    .replace(/\b(?:equals?|eq)\b/gi, "is")
    .replace(/\s+/g, " ")
    .trim();
}
function activeLocalOfferingReferences() {
  const references = new Set();
  for (const card of state.privateCards) {
    if (card.lifecycle !== "active") continue;
    if (card.offering_id) references.add(card.offering_id);
    const offering = offeringForCard(card);
    if (offering?.id) references.add(offering.id);
    if (offering?.slug) references.add(offering.slug);
  }
  return references;
}
function benefitMatchesActiveLocalCard(benefit) {
  if (!state.privateCardsAvailable || !benefit?.offering_id) return false;
  return activeLocalOfferingReferences().has(benefit.offering_id);
}
function isOwnedBenefit(benefit) {
  if (!state.privateCardsAvailable) return false;
  const discoveryMatch = state.ownedDiscoveryCards.some(card => (card.rule_ids || []).includes(benefit.id));
  // The discovery projection can be incomplete or stale. An active local
  // product match is still enough to group a public rule under My Benefits;
  // it never proves that the cardholder meets the rule's conditions.
  return discoveryMatch || benefitMatchesActiveLocalCard(benefit);
}
function consumerBenefitState(benefit) {
  const catalogState = consumerCatalogState(benefit);
  if (catalogState === "sources_differ") return { label: "Sources differ", tone: "s-bad", note: "The recorded sources disagree. Read the current official terms before relying on this benefit." };
  if (catalogState === "verified") return { label: "Verified", tone: "s-ok", note: "The source-backed record is verified; your eligibility can still depend on its terms." };
  return { label: "Check before use", tone: "s-warn", note: "This source-backed record still needs confirmation from the current terms." };
}

const benefitCategoryLabels = Object.freeze({
  movie: "Movies and entertainment", reward_points: "Reward points", cashback: "Cashback",
  lounge: "Airport lounge", conversion: "Conversion", food: "Food and dining",
  insurance: "Insurance", hotel: "Hotels", travel: "Travel", fuel: "Fuel",
  shopping: "Shopping", voucher: "Vouchers", other: "Other benefits",
  foreign_exchange: "Foreign exchange", wellness: "Wellness", education: "Education",
  joining: "Joining benefits", milestone: "Milestone benefits", annual_fee: "Annual fee",
  priority_pass: "Priority Pass",
});
const benefitCategoryChipLabels = Object.freeze({
  lounge: "Lounge", movie: "Movie", reward_points: "Rewards", food: "Dining",
  cashback: "Cashback", voucher: "Vouchers", conversion: "Conversion",
});
const featuredBenefitCategories = Object.freeze(["lounge", "movie", "reward_points", "food", "cashback", "voucher"]);
function humanBenefitCategory(value) {
  const key = String(value || "other").toLocaleLowerCase();
  // Never return null. A null label removed the benefit from the Benefits list
  // outright, which silently hid nine of the sixty catalog benefits: every
  // category the map did not name simply vanished from the screen. Falling back
  // to the neutral bucket keeps an unlabelled benefit visible without surfacing
  // a raw machine term, which is why this does not humanise the key instead.
  return benefitCategoryLabels[key] || benefitCategoryLabels.other;
}
function benefitCategoryChipLabel(value) {
  const key = String(value || "other").toLocaleLowerCase();
  return benefitCategoryChipLabels[key] || humanBenefitCategory(key);
}
function benefitCategoryRank(value) {
  const index = featuredBenefitCategories.indexOf(value);
  return index === -1 ? featuredBenefitCategories.length : index;
}
function orderedBenefitCategories(values, counts = {}) {
  return [...new Set(values)].sort((a, b) =>
    benefitCategoryRank(a) - benefitCategoryRank(b)
    || (counts[b] || 0) - (counts[a] || 0)
    || (benefitCategoryChipLabel(a) || "").localeCompare(benefitCategoryChipLabel(b) || "")
  );
}
function benefitOffering(benefit) {
  return state.offerings.find(item => item.id === benefit?.offering_id || item.slug === benefit?.offering_id) || null;
}
function publicBenefitsForOffering(offering) {
  return state.benefits.filter(item =>
    (item.offering_id === offering?.id || item.offering_id === offering?.slug)
    && Boolean(humanBenefitCategory(item.category || item.benefit_type))
  );
}
function benefitAsOf(benefit) {
  const retrieved = Array.isArray(benefit?.evidence)
    ? benefit.evidence.find(item => typeof item?.retrieved_at === "string" && item.retrieved_at)?.retrieved_at
    : null;
  const offering = benefitOffering(benefit);
  const owner = offering?.issuer_id || benefit.provider || "Official source";
  return retrieved ? `${offering?.issuer_id ? humanIssuerLabel(owner) : humanizeBenefitTerm(owner)} · ${fmtDate(retrieved.slice(0, 10))}` : `${offering?.issuer_id ? humanIssuerLabel(owner) : humanizeBenefitTerm(owner)} · Date not recorded`;
}
function benefitSearchText(benefit) {
  const offering = benefitOffering(benefit);
  if (!humanBenefitCategory(benefit.category || benefit.benefit_type)) return "";
  const ownedCards = state.privateCards
    .filter(card => offeringForCard(card)?.id === benefit.offering_id)
    .map(card => [offering?.display_name, humanLifecycleLabel(card.lifecycle)]);
  const values = [
    benefit.title,
    humanBenefitCategory(benefit.category || benefit.benefit_type),
    // The raw category as well as its label. Matching compares whole tokens, so
    // the label alone makes the screen's own promise that search spans
    // categories false for every category whose label is not the word a person
    // would type: "movie" does not match "Movies and entertainment", and
    // "forex" does not match "Foreign exchange".
    benefit.category || benefit.benefit_type,
    offering?.display_name,
    offering?.issuer_id,
    networkLabel(offering?.network_id),
    ...(offering?.aliases || []),
    benefit.provider,
    consumerAllowanceText(benefit),
    primaryConditionText(benefit),
    ...(benefit.conditions || []).map(condition => typeof condition === "string" ? humanizeConditionText(condition) : typeof condition?.value === "string" ? humanizeConditionText(condition.value) : friendlyPredicate(condition)),
    ...(benefit.eligibility || []).map(condition => typeof condition === "string" ? humanizeConditionText(condition) : friendlyPredicate(condition)),
    ...benefitHowToUse(benefit),
    ...(benefit.exclusions || []).map(condition => typeof condition === "string" ? humanizeConditionText(condition) : friendlyPredicate(condition)),
    ...ownedCards.flat(),
  ];
  return values.filter(value => typeof value === "string" && value.trim()).join(" ").toLocaleLowerCase();
}
function searchTokens(value) {
  return humanizeBenefitTerm(value).toLocaleLowerCase().replaceAll("₹", " inr ").split(/[^a-z0-9]+/).filter(Boolean);
}
function searchMatches(benefit, query) {
  const rawQuery = typeof query === "string" ? query : String(query || "");
  const terms = searchTokens(rawQuery);
  if (!rawQuery.length) return true;
  if (!terms.length) return false;
  const haystack = searchTokens(benefitSearchText(benefit));
  return terms.every(term => haystack.includes(term));
}
function displaySearchQuery(value, maxLength = 120) {
  const query = String(value || "").trim();
  if (query.length <= maxLength) return query;
  return `${Array.from(query).slice(0, maxLength - 1).join("")}…`;
}
function safePublicValue(value) {
  if (typeof value === "string") return numericDisplay(value) || humanizeBenefitTerm(value);
  if (typeof value === "number" && Number.isFinite(value)) return numericDisplay(value) || null;
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (Array.isArray(value)) return value.map(safePublicValue).filter(Boolean).join(" or ") || null;
  return null;
}
function friendlyPredicate(predicate) {
  if (!predicate || typeof predicate !== "object") return "Check the qualifying terms before use.";
  const rawField = predicate.field || predicate.type;
  const field = consumerFieldLabel(rawField);
  if (!field) return null;
  const operator = String(predicate.operator || "matches").toLocaleLowerCase();
  const value = safePublicValue(predicate.value);
  if (!value && operator === "exists") return `${field} is required`;
  if (!value) return "Check the qualifying terms before use.";
  const phrases = { gte: "at least", gt: "more than", lte: "up to", lt: "less than", eq: "is", equals: "is", equal: "is", matches: "is", in: "one of", contains: "includes", not_in: "is not one of", between: "between" };
  if (operator === "between" && Array.isArray(predicate.value) && predicate.value.length >= 2) return `${field}: between ${safePublicValue(predicate.value[0])} and ${safePublicValue(predicate.value[1])}`;
  return `${field}: ${phrases[operator] || "matches"} ${value}`;
}
function openBenefitDetails(benefitId) {
  state.selectedBenefitId = benefitId;
  navigateTo("search");
  renderBenefitDetail({ focus: true });
}
function viewFromHash() {
  try {
    const requested = decodeURIComponent(location.hash.slice(1));
    const aliased = legacyViewAliases.get(requested) || requested;
    return views.has(aliased) ? aliased : "my-cards";
  } catch { return "my-cards"; }
}
function navigateTo(view, { focus = true, replace = false, loadPrivate = false } = {}) {
  const aliased = legacyViewAliases.get(view) || view;
  const destination = views.has(aliased) ? aliased : "my-cards";
  if (location.hash.slice(1) !== destination) {
    if (replace) history.replaceState(null, "", `#${destination}`);
    else history.pushState(null, "", `#${destination}`);
  }
  showView(destination, { focus, loadPrivate });
}
function showView(view, { focus = false, loadPrivate = false } = {}) {
  const aliased = legacyViewAliases.get(view) || view;
  const destination = views.has(aliased) ? aliased : "my-cards";
  if (destination === "my-cards" || loadPrivate) void requestPrivateCards();
  for (const panel of document.querySelectorAll("[data-panel]")) panel.hidden = panel.id !== destination;
  for (const link of document.querySelectorAll("[data-view]")) {
    const active = link.dataset.view === destination;
    link.classList.toggle("active", active);
    if (active) link.setAttribute("aria-current", "page"); else link.removeAttribute("aria-current");
  }
  const announcement = document.querySelector("#viewAnnouncement");
  const heading = document.querySelector(`#${destination} h1, #${destination} h2`);
  if (announcement) announcement.textContent = `${heading?.textContent || destination} view`;
  if (focus) {
    if (heading) {
      heading.setAttribute("tabindex", "-1");
      heading.focus({ preventScroll: true });
    }
  }
  if (destination === "search" && state.benefits.length) renderSearchResults();
}

function focusMainContent() {
  const main = document.querySelector("#main");
  if (main) main.focus({ preventScroll: false });
}
document.querySelector(".skip-link")?.addEventListener("click", event => {
  event.preventDefault();
  focusMainContent();
});

function viewLink(label, view) {
  const link = node("a", label, "button secondary");
  link.href = `#${view}`;
  link.addEventListener("click", event => { event.preventDefault(); navigateTo(view, { loadPrivate: view === "search" }); });
  return link;
}
for (const link of document.querySelectorAll("[data-view], [data-go]")) link.addEventListener("click", event => {
  const view = event.currentTarget.dataset.view || event.currentTarget.dataset.go;
  if (!view) return;
  event.preventDefault();
  navigateTo(view, { loadPrivate: view === "search" });
});
function syncViewFromLocation() {
  const view = viewFromHash();
  if (location.hash.slice(1) !== view) history.replaceState(null, "", `#${view}`);
  showView(view, { focus: true, loadPrivate: view === "search" });
}
window.addEventListener("popstate", syncViewFromLocation);
window.addEventListener("hashchange", () => {
  if (location.hash === "#main") {
    const currentPanel = [...document.querySelectorAll("[data-panel]")].find(panel => !panel.hidden)?.id || "my-cards";
    history.replaceState(null, "", `#${currentPanel}`);
    focusMainContent();
    return;
  }
  syncViewFromLocation();
});

async function getCatalog(path) {
  const response = await fetch(`/api/v1/catalog/${path}`, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(response.status === 503 ? "Catalog unavailable" : "Catalog request failed");
  return response.json();
}
function setCatalogState(message, kind) {
  const target = document.querySelector("#catalogState");
  if (!target) return;
  target.textContent = message;
  target.className = `catalog-state${kind ? ` ${kind}` : ""}`;
}
function offeringCard(offering) {
  const benefits = publicBenefitsForOffering(offering);
  const network = networkLabel(offering.network_id);
  const card = cardFace({
    issuer: humanIssuerLabel(offering.issuer_id),
    issuer_id: offering.issuer_id,
    name: offering.display_name,
    network,
    lifecycle: "public",
    public: true,
    benefits: benefits.length,
    verified: benefits.filter(benefit => consumerCatalogState(benefit) === "verified").length,
    conflicts: benefits.filter(benefit => consumerCatalogState(benefit) === "sources_differ").length,
  });
  card.classList.add("public-cardface");
  card.dataset.offeringId = offering.id;
  card.setAttribute("role", "button");
  card.setAttribute("aria-label", `Browse benefits for ${[offering.display_name, humanIssuerLabel(offering.issuer_id), network].filter(Boolean).join(" · ")}`);
  card.addEventListener("click", () => selectOffering(offering.id));
  return card;
}
function offeringBenefitSummary(benefit) {
  const item = node("article", undefined, "offering-benefit");
  const stateBadge = consumerBenefitState(benefit);
  const heading = node("div", undefined, "offering-benefit-head");
  heading.append(node("h4", benefit.title), node("span", stateBadge.label, `state badge ${stateBadge.tone}`));
  const categoryLabel = humanBenefitCategory(benefit.category || benefit.benefit_type);
  item.append(heading);
  if (categoryLabel) item.append(node("p", categoryLabel, "eyebrow"));
  const allowance = consumerAllowanceText(benefit);
  if (allowance) item.append(node("p", allowance, "allowance"));
  const condition = primaryConditionText(benefit);
  if (condition) item.append(node("p", `To qualify: ${condition}`, "quiet-copy"));
  const howToUse = benefitHowToUse(benefit);
  if (howToUse.length) item.append(node("p", `How to use: ${howToUse.join(" ")}`, "quiet-copy"));
  if (benefit.not_claimed?.length) {
    const note = node("p", "Some terms are not claimed by the source record.", "quiet-copy");
    item.append(note);
  }
  const href = officialBenefitHref(benefit);
  if (href) { const link = node("a", officialBenefitLinkText(benefit)); link.href = href; link.target = "_blank"; link.rel = "noopener noreferrer"; item.append(link); }
  return item;
}
function renderOfferingDetail() {
  const target = document.querySelector("#offeringDetail");
  if (!target) return;
  clear(target);
  const offering = state.offerings.find(item => item.id === state.selectedOfferingId);
  if (!offering) { target.hidden = true; return; }
  target.hidden = false;
  const heading = node("h3", offering.display_name); heading.id = "offering-detail-title"; heading.tabIndex = -1;
  target.append(node("div", undefined, "section-head"));
  target.firstChild.append(node("div", undefined), node("button", "Close", "secondary"));
  target.firstChild.firstChild.append(node("p", "Card details", "eyebrow"), heading);
  target.firstChild.lastChild.type = "button";
  target.firstChild.lastChild.addEventListener("click", () => {
    state.selectedOfferingId = null;
    renderOfferingDetail();
    document.querySelector(`[data-offering-id="${offering.id}"]`)?.focus();
  });
  target.append(node("p", [humanIssuerLabel(offering.issuer_id), networkLabel(offering.network_id), marketLabel(offering.market)].filter(Boolean).join(" · "), "quiet-copy"));
  const benefits = publicBenefitsForOffering(offering);
  const categories = [...new Set(benefits.map(item => humanBenefitCategory(item.category || item.benefit_type)).filter(Boolean))];
  target.append(node("p", categories.length ? `Recorded benefit categories: ${categories.join(", ")}.` : "No public benefit details are recorded for this card yet.", "allowance"));
  if (benefits.length) {
    const list = node("div", undefined, "offering-benefit-list");
    for (const benefit of benefits) list.append(offeringBenefitSummary(benefit));
    target.append(list);
  }
  const actions = node("div", undefined, "actions");
  const add = node("button", "Add this card"); add.type = "button"; add.addEventListener("click", () => beginAddCard(offering.id));
  actions.append(add);
  target.append(actions);
  heading.focus({ preventScroll: true });
}
function selectOffering(offeringId) {
  state.selectedOfferingId = offeringId;
  navigateTo("benefits", { focus: false });
  renderOfferingDetail();
}
function renderChoiceButtons(inputSelector, buttonSelector, choicesSelector, choices, placeholder, onChoose) {
  const input = document.querySelector(inputSelector);
  const summary = document.querySelector(buttonSelector);
  const target = document.querySelector(choicesSelector);
  if (!input || !summary || !target) return;
  const selected = choices.find(([value]) => value === input.value);
  summary.textContent = selected?.[1] || placeholder;
  summary.setAttribute("aria-label", selected ? `Selected: ${selected[1]}` : placeholder);
  clear(target);
  if (!choices.length) {
    target.append(node("p", "No choices are available yet.", "quiet-copy"));
    return;
  }
  for (const [value, label] of choices) {
    const choice = node("button", label, "chip");
    choice.type = "button";
    const active = value === input.value;
    choice.classList.toggle("on", active);
    choice.setAttribute("aria-pressed", String(active));
    choice.addEventListener("click", () => {
      input.value = value;
      if (onChoose) onChoose(value);
      renderChoiceButtons(inputSelector, buttonSelector, choicesSelector, choices, placeholder, onChoose);
    });
    target.append(choice);
  }
}
function renderCardOfferingChoices() {
  const issuerTarget = document.querySelector("#cardAddIssuerChips");
  const productTarget = document.querySelector("#cardAddOfferingChoices");
  if (!issuerTarget || !productTarget) return;
  const issuers = [...new Set(state.offerings.map(offering => offering.issuer_id).filter(Boolean))]
    .sort((a, b) => humanIssuerLabel(a).localeCompare(humanIssuerLabel(b)));
  state.cardAddIssuers = new Set([...state.cardAddIssuers].filter(issuer => issuers.includes(issuer)));
  clear(issuerTarget);
  const appendIssuerChip = (value, label) => {
    const selected = value ? state.cardAddIssuers.has(value) : state.cardAddIssuers.size === 0;
    const chip = node("button", label, `chip${selected ? " on" : ""}`);
    chip.type = "button";
    chip.setAttribute("aria-pressed", String(selected));
    chip.addEventListener("click", () => {
      if (!value) state.cardAddIssuers.clear();
      else if (state.cardAddIssuers.has(value)) state.cardAddIssuers.delete(value);
      else state.cardAddIssuers.add(value);
      renderCardOfferingChoices();
    });
    issuerTarget.append(chip);
  };
  appendIssuerChip("", "All issuers");
  for (const issuer of issuers) appendIssuerChip(issuer, humanIssuerLabel(issuer));

  clear(productTarget);
  const filtered = state.offerings
    .filter(offering => !state.cardAddIssuers.size || state.cardAddIssuers.has(offering.issuer_id))
    .sort((a, b) => humanIssuerLabel(a.issuer_id).localeCompare(humanIssuerLabel(b.issuer_id)) || a.display_name.localeCompare(b.display_name));
  const grouped = new Map();
  for (const offering of filtered) {
    if (!grouped.has(offering.issuer_id)) grouped.set(offering.issuer_id, []);
    grouped.get(offering.issuer_id).push(offering);
  }
  if (!filtered.length) productTarget.append(node("p", "No public card products match this issuer filter yet.", "quiet-copy"));
  for (const [issuer, offerings] of grouped) {
    productTarget.append(node("h4", `${humanIssuerLabel(issuer)} · ${offerings.length} product${offerings.length === 1 ? "" : "s"}`, "onboarding-product-group-title"));
    for (const offering of offerings) {
      const selected = state.cardAddSelection.has(offering.id);
      const choice = node("button", undefined, `onboarding-product${selected ? " selected" : ""}`);
      choice.type = "button";
      choice.disabled = !state.privateCardsAvailable;
      choice.setAttribute("aria-pressed", String(selected));
      choice.setAttribute("aria-label", `${selected ? "Remove" : "Add"} ${offering.display_name}`);
      choice.append(
        node("span", selected ? "✓" : "", "onboarding-product-check"),
        node("span", offering.display_name, "onboarding-product-name"),
      );
      const network = networkLabel(offering.network_id);
      if (network) choice.append(node("span", network, "onboarding-product-network"));
      choice.addEventListener("click", () => {
        if (state.cardAddSelection.has(offering.id)) state.cardAddSelection.delete(offering.id);
        else state.cardAddSelection.add(offering.id);
        renderCardOfferingChoices();
      });
      productTarget.append(choice);
    }
  }
  const count = state.cardAddSelection.size;
  const status = document.querySelector("#cardAddSelectionStatus");
  if (status) status.textContent = count ? `${count} card${count === 1 ? "" : "s"} selected.` : "No cards selected yet.";
  const submit = document.querySelector("#cardAddSubmit");
  if (submit) {
    submit.textContent = count ? `Add ${count} card${count === 1 ? "" : "s"}` : "Add cards";
    submit.disabled = !state.privateCardsAvailable || count === 0;
  }
  const advanced = document.querySelector("#cardAddAdvanced");
  const oneSelected = count === 1;
  if (advanced) {
    advanced.hidden = !oneSelected;
    if (!oneSelected) advanced.open = false;
    for (const input of advanced.querySelectorAll("input")) input.disabled = !oneSelected;
  }
}
function beginAddCard(offeringId) {
  state.cardAddSelection.add(offeringId);
  const offering = state.offerings.find(item => item.id === offeringId);
  state.cardAddIssuers = offering?.issuer_id ? new Set([offering.issuer_id]) : new Set();
  navigateTo("my-cards");
  renderCardOfferingChoices();
  document.querySelector("#myCardStatus").textContent = state.privateCardsAvailable
    ? "This card is selected below. Choose any other cards, then add them together."
    : "Load My Cards to add this card.";
}
function ownedComparableOfferings() {
  const result = [];
  const seen = new Set();
  const add = card => {
    const offering = offeringForCard(card);
    if (offering && !seen.has(offering.id)) { seen.add(offering.id); result.push(offering); }
  };
  for (const card of state.privateCards.filter(card => card.lifecycle === "active")) add(card);
  for (const card of state.privateCards) add(card);
  return result;
}
function ensureCompareSelections({ preferOwned = false } = {}) {
  const first = document.querySelector("#compareA");
  const second = document.querySelector("#compareB");
  if (!first || !second || first.options.length < 2) return;
  const owned = ownedComparableOfferings();
  if (preferOwned && !state.compareUserEdited && owned.length >= 2) {
    first.value = owned[0].slug;
    second.value = owned[1].slug;
    state.compareDefaultsApplied = true;
  }
  if (!first.value) first.value = first.options[0].value;
  if (!second.value || second.value === first.value) {
    const alternative = [...second.options].find(option => option.value !== first.value);
    if (alternative) second.value = alternative.value;
  }
}
function renderOfferingFilter(selectId, values, placeholder, labelFor) {
  const select = document.querySelector(selectId);
  if (!select) return;
  const keep = select.value;
  clear(select);
  select.append(new Option(placeholder, ""));
  for (const value of values) select.append(new Option(labelFor(value), value));
  if ([...select.options].some(option => option.value === keep)) select.value = keep;
}
function renderOfferings() {
  const search = document.querySelector("#offeringSearch");
  const preview = document.querySelector("#offeringPreview");
  const query = search?.value.trim().toLocaleLowerCase() || "";
  const issuer = document.querySelector("#offeringIssuer")?.value || "";
  const network = document.querySelector("#offeringNetwork")?.value || "";
  renderOfferingFilter(
    "#offeringIssuer",
    [...new Set(state.offerings.map(offering => offering.issuer_id).filter(Boolean))].sort((a, b) => humanIssuerLabel(a).localeCompare(humanIssuerLabel(b))),
    "All issuers",
    humanIssuerLabel,
  );
  renderOfferingFilter(
    "#offeringNetwork",
    [...new Set(state.offerings.map(offering => offering.network_id).filter(value => networkLabel(value)))].sort((a, b) => (networkLabel(a) || "").localeCompare(networkLabel(b) || "")),
    "All networks",
    networkLabel,
  );
  if (preview) {
    document.querySelector("#offeringCount")?.replaceChildren(document.createTextNode(String(state.offerings.length)));
    clear(preview);
    const filtered = state.offerings.filter(offering =>
      (!issuer || offering.issuer_id === issuer)
      && (!network || offering.network_id === network)
      && (!query || [offering.display_name, offering.issuer_id, offering.network_id, offering.slug].some(value => String(value || "").toLocaleLowerCase().includes(query)))
    );
    document.querySelector("#offeringSearchStatus")?.replaceChildren(document.createTextNode(`${filtered.length} public card${filtered.length === 1 ? "" : "s"} shown`));
    if (!filtered.length) preview.append(node("p", "No public card matches those filters.", "empty-state"));
    for (const offering of filtered) preview.append(offeringCard(offering));
  }
  for (const select of document.querySelectorAll("#benefitOffering, #compareA, #compareB")) {
    const keep = select.value; clear(select);
    if (select.id === "benefitOffering") select.append(new Option("All offerings", ""));
    for (const offering of state.offerings) {
      select.append(new Option(offering.display_name, offering.slug));
    }
    if ([...select.options].some(option => option.value === keep)) select.value = keep;
  }
  renderCardOfferingChoices();
  ensureCompareSelections({ preferOwned: state.privateCardsAvailable && !state.compareDefaultsApplied });
  renderOfferingDetail();
}
document.querySelector("#offeringSearch")?.addEventListener("input", renderOfferings);
document.querySelector("#offeringIssuer")?.addEventListener("change", renderOfferings);
document.querySelector("#offeringNetwork")?.addEventListener("change", renderOfferings);
function provenanceChip(evidence) {
  const source = humanizeBenefitTerm(evidence?.source_policy_class || "Official source");
  const confidence = humanizeBenefitTerm(evidence?.confidence || "");
  const stateName = String(evidence?.state || "").toLocaleLowerCase();
  const tone = stateName === "sources_differ" ? "provenance-conflict" : stateName === "verified" ? "provenance-verified" : "provenance-conditional";
  const chip = node("span", undefined, `provenance-chip ${tone}`);
  const date = typeof evidence?.retrieved_at === "string" && evidence.retrieved_at ? fmtDate(evidence.retrieved_at.slice(0, 10)) : "Date not recorded";
  const label = tone === "provenance-verified" ? "Verified" : tone === "provenance-conflict" ? "Sources differ" : "Check before use";
  chip.append(node("strong", label), node("span", `${source}${confidence ? ` · ${confidence}` : ""} · as of ${date}`));
  const href = safeHref(evidence?.source_url);
  if (href) { const link = node("a", "Official source"); link.href = href; link.target = "_blank"; link.rel = "noopener noreferrer"; chip.append(link); }
  return chip;
}
function evidenceLine(evidence) {
  const line = node("li");
  line.append(provenanceChip(evidence));
  const retrieved = typeof evidence.retrieved_at === "string" && evidence.retrieved_at ? fmtDate(evidence.retrieved_at.slice(0, 10)) : null;
  if (retrieved) line.append(node("span", ` · last verified ${retrieved}`, "quiet-copy"));
  const href = safeHref(evidence.source_url);
  if (href) { const link = node("a", "Open source"); link.href = href; link.target = "_blank"; link.rel = "noopener noreferrer"; line.append(" ", link); }
  return line;
}
function benefitCard(benefit) {
  const offering = benefitOffering(benefit);
  const row = node("article", undefined, "brow benefit-card");
  row.tabIndex = 0;
  row.addEventListener("click", event => { if (!event.target.closest("a,button,details,summary")) selectBenefit(benefit.id); });
  row.addEventListener("keydown", event => { if ((event.key === "Enter" || event.key === " ") && event.target === row) { event.preventDefault(); selectBenefit(benefit.id); } });
  const main = node("div");
  const ownedCard = state.privateCards.find(card => offeringForCard(card)?.id === benefit.offering_id && card.lifecycle === "active") || state.privateCards.find(card => offeringForCard(card)?.id === benefit.offering_id);
  const cardLabel = ownedCard
    ? [offering?.display_name || benefit._offeringName || "Public card", humanLifecycleLabel(ownedCard.lifecycle)].filter(Boolean).join(" · ")
    : [offering?.display_name || benefit._offeringName || "Public card", networkLabel(offering?.network_id)].filter(Boolean).join(" · ");
  main.append(node("p", cardLabel, "b-card"));
  main.append(node("h3", benefit.title, "b-title"));
  const allowance = consumerAllowanceText(benefit);
  if (allowance) main.append(node("p", allowance, "b-val"));
  const condition = primaryConditionText(benefit);
  main.append(node("p", condition || "Check the current qualifying terms before use.", "b-cond"));
  if (benefit.not_claimed?.length) {
    const notClaimed = node("div", undefined, "notclaim");
    notClaimed.append(node("p", "This is not claimed", "notclaim-heading"));
    const claims = node("ul");
    for (const item of benefit.not_claimed) claims.append(node("li", safePublicValue(item) || "A claim is not recorded."));
    notClaimed.append(claims); main.append(notClaimed);
  }
  if (benefit.source_divergence?.length) {
    const divergence = node("details", undefined, "source-difference");
    divergence.append(node("summary", "See both retained source claims"));
    const claims = node("ul");
    for (const claim of benefit.source_divergence) {
      const item = node("li");
       const claimCategory = humanBenefitCategory(claim.category || claim.benefit_type);
       const claimValue = safePublicValue(claim.allowance?.count ?? claim.allowance?.cap) || "recorded terms differ";
       item.append(node("span", claimCategory ? `${claimCategory}: ${claimValue}` : claimValue));
      const href = safeHref(claim.source_url);
      if (href) { const link = node("a", "Open source", "srclink"); link.href = href; link.target = "_blank"; link.rel = "noopener noreferrer"; item.append(link); }
      claims.append(item);
    }
    divergence.append(claims); main.append(divergence);
  }
  row.append(main);
  const right = node("div", undefined, "b-right");
  const stateBadge = consumerBenefitState(benefit);
  right.append(node("span", stateBadge.label, `state ${stateBadge.tone}`), node("span", benefitAsOf(benefit), "asof"));
  const officialHref = officialBenefitHref(benefit);
  if (officialHref) { const link = node("a", "Official terms", "srclink"); link.href = officialHref; link.target = "_blank"; link.rel = "noopener noreferrer"; right.append(link); }
  const button = node("button", "Details", "secondary benefit-detail-toggle");
  button.type = "button"; button.setAttribute("aria-label", `Open details for ${benefit.title}`); button.addEventListener("click", () => selectBenefit(benefit.id));
  right.append(button); row.append(right);
  return row;
}
function renderBenefits() {
  const list = document.querySelector("#benefitList");
  if (!list) return;
  clear(list);
  const category = state.benefitCategory || "";
  const ownedOnly = state.benefitScope === "owned";
  const scopedBenefits = state.benefits.filter(benefit =>
    Boolean(humanBenefitCategory(benefit.category || benefit.benefit_type))
    && (!ownedOnly || isOwnedBenefit(benefit))
  );
  const matches = scopedBenefits.filter(benefit => !category || (benefit.category || benefit.benefit_type) === category);
  const categoryChips = document.querySelector("#benefitCategoryChips");
  if (categoryChips) {
    clear(categoryChips);
    const counts = scopedBenefits.reduce((result, benefit) => {
      const key = benefit.category || benefit.benefit_type || "other";
      result[key] = (result[key] || 0) + 1;
      return result;
    }, {});
    const allCategories = orderedBenefitCategories(Object.keys(counts), counts);
    const topCategories = [...new Set([
      ...featuredBenefitCategories.filter(value => counts[value]),
      ...allCategories,
    ])].slice(0, 6);
    const appendChip = value => {
      const selected = category === value;
      const chip = node("button", `${benefitCategoryChipLabel(value)} ${counts[value]}`, `category-chip${selected ? " selected" : ""}`);
      chip.type = "button";
      chip.setAttribute("aria-pressed", String(selected));
      chip.addEventListener("click", () => {
        state.benefitCategory = state.benefitCategory === value ? "" : value;
        renderBenefits();
      });
      categoryChips.append(chip);
    };
    for (const value of topCategories) appendChip(value);
    const remaining = allCategories.filter(value => !topCategories.includes(value));
    if (remaining.length) {
      const more = node("details", undefined, "more-benefit-categories");
      more.open = Boolean(category && remaining.includes(category));
      more.append(node("summary", "More categories"));
      const moreChips = node("div", undefined, "benefit-category-more-list");
      for (const value of remaining) {
        const selected = category === value;
        const chip = node("button", `${benefitCategoryChipLabel(value)} ${counts[value]}`, `category-chip${selected ? " selected" : ""}`);
        chip.type = "button";
        chip.setAttribute("aria-pressed", String(selected));
        chip.addEventListener("click", () => {
          state.benefitCategory = state.benefitCategory === value ? "" : value;
          renderBenefits();
        });
        moreChips.append(chip);
      }
      more.append(moreChips);
      categoryChips.append(more);
    }
  }
  for (const button of document.querySelectorAll("[data-benefit-scope]")) {
    const selected = (button.dataset.benefitScope === "owned") === ownedOnly;
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  }
  const grouped = new Map();
  for (const benefit of matches) { const key = benefit.category || benefit.benefit_type || "other"; if (!grouped.has(key)) grouped.set(key, []); grouped.get(key).push(benefit); }
  const groupCounts = Object.fromEntries([...grouped.entries()].map(([key, items]) => [key, items.length]));
  for (const key of orderedBenefitCategories([...grouped.keys()], groupCounts)) {
    const items = grouped.get(key);
    const ownedItems = items.filter(isOwnedBenefit);
    const orderedItems = [...ownedItems, ...items.filter(item => !isOwnedBenefit(item))];
    const heading = node("div", undefined, "catbar");
    heading.append(node("h4", humanBenefitCategory(key)));
    if (ownedItems.length) heading.append(node("span", "On your cards", "mine"));
    heading.append(node("span", ownedItems.length ? `${ownedItems.length} OF ${items.length}` : `${items.length} BENEFIT${items.length === 1 ? "" : "S"}`, "n"));
    list.append(heading);
    for (const benefit of orderedItems) list.append(benefitCard(benefit));
  }
  const empty = document.querySelector("#benefitCatalogEmpty");
  if (empty) { empty.hidden = matches.length > 0; empty.textContent = ownedOnly ? "Your saved cards have no recorded benefits in this category yet." : "The public catalog has no benefit records in this category yet."; }
  const status = document.querySelector("#benefitCatalogStatus");
  const matchCategoryCount = new Set(matches.map(item => item.category || item.benefit_type)).size;
  if (status) status.textContent = `${matches.length} public benefit${matches.length === 1 ? "" : "s"} across ${matchCategoryCount} categor${matchCategoryCount === 1 ? "y" : "ies"}.`;
  const summary = document.querySelector("#benefitSummary");
  if (summary) {
     const renderableBenefits = state.benefits.filter(benefit => humanBenefitCategory(benefit.category || benefit.benefit_type));
     const counts = renderableBenefits.reduce((result, benefit) => { const key = consumerCatalogState(benefit); result[key] = (result[key] || 0) + 1; return result; }, {});
     summary.textContent = `${renderableBenefits.length} benefits · ${new Set(renderableBenefits.map(item => item.category || item.benefit_type)).size} categories · ${counts.verified || 0} Verified · ${counts.check_before_use || 0} Check before use · ${counts.sources_differ || 0} Sources differ`;
  }
  updateTravelAvailability();
}
function renderSearchResults({ focus = false } = {}) {
  const list = document.querySelector("#searchResults");
  if (!list) return;
  clear(list);
  const query = document.querySelector("#benefitSearch")?.value || "";
  const category = document.querySelector("#benefitCategory")?.value || "";
  const merchant = document.querySelector("#benefitMerchant")?.value || "";
  const cap = document.querySelector("#benefitCap")?.value || "";
  const condition = document.querySelector("#benefitCondition")?.value || "";
  const claimChannel = document.querySelector("#benefitClaimChannel")?.value || "";
  const status = document.querySelector("#benefitStatus")?.value || "";
  const globalMatches = state.benefits.filter(benefit => {
    const offering = benefitOffering(benefit);
    if (!humanBenefitCategory(benefit.category || benefit.benefit_type)) return false;
    if (!searchMatches(benefit, query)) return false;
    if (category && (benefit.category || benefit.benefit_type) !== category) return false;
    if (status && consumerCatalogState(benefit) !== status) return false;
    if (merchant && !searchMatches(benefit, merchant)) return false;
    if (cap && !searchMatches(benefit, cap)) return false;
    if (condition && !searchMatches(benefit, condition)) return false;
    if (claimChannel && !benefitHowToUse(benefit).join(" ").toLocaleLowerCase().includes(claimChannel.toLocaleLowerCase())) return false;
    return Boolean(offering || benefit._offeringName);
  });
  const ownedMatches = globalMatches.filter(isOwnedBenefit);
  const matches = state.searchScope === "owned" ? ownedMatches : [...ownedMatches, ...globalMatches.filter(item => !isOwnedBenefit(item))];
  for (const benefit of matches) list.append(benefitCard(benefit));
  const categorySelect = document.querySelector("#benefitCategory");
  if (categorySelect) {
    const keep = categorySelect.value;
    clear(categorySelect); categorySelect.append(new Option("All categories", ""));
    for (const value of [...new Set(state.benefits.map(item => item.category || item.benefit_type).filter(value => humanBenefitCategory(value)))].sort((a, b) => (humanBenefitCategory(a) || "").localeCompare(humanBenefitCategory(b) || ""))) categorySelect.append(new Option(humanBenefitCategory(value), value));
    categorySelect.value = keep;
  }
  for (const button of document.querySelectorAll("[data-search-scope]")) {
    const selected = button.dataset.searchScope === state.searchScope;
    button.classList.toggle("selected", selected); button.setAttribute("aria-pressed", String(selected));
  }
  const summary = document.querySelector("#searchSummary");
  if (summary) summary.textContent = `${ownedMatches.length} on your cards · ${Math.max(0, globalMatches.length - ownedMatches.length)} elsewhere in the catalog`;
  const statusTarget = document.querySelector("#searchStatus");
  if (statusTarget) statusTarget.textContent = matches.length ? `${matches.length} result${matches.length === 1 ? "" : "s"} shown.` : (query.length ? "0 results shown." : "");
  const empty = document.querySelector("#searchEmpty");
  if (empty) {
    empty.hidden = matches.length > 0;
    if (matches.length) empty.replaceChildren();
    else if (state.searchScope === "owned" && !state.privateCardsAvailable) {
      empty.replaceChildren(node("h3", "Your cards are not loaded yet"), node("p", "Load My Cards to search benefits for cards in your wallet."), viewLink("Open My Cards", "my-cards"));
    } else if (state.searchScope === "owned" && !state.privateCards.length) {
      empty.replaceChildren(node("h3", "Your wallet is empty"), node("p", "Add your first card in My Cards to search benefits on your cards."), viewLink("Add your first card", "my-cards"));
    } else if (!globalMatches.length && query.length) {
      const terms = searchTokens(query);
      if (!terms.length) {
        empty.replaceChildren(node("h3", "No benefits match that search"), node("p", "Enter a word or clear the search to browse the catalog."));
      } else {
        const headingText = state.searchScope === "owned" ? "Nothing recorded for any of your cards" : "Nothing recorded in the public catalog";
        const queryText = query.trim().toLocaleLowerCase();
        const echoedQuery = displaySearchQuery(query);
        const subject = queryText.includes("meet") && queryText.includes("greet") ? "meet-and-greet" : `“${echoedQuery}”`;
        empty.replaceChildren(node("h3", headingText), node("p", `MyCard has no verified ${subject} terms yet — for your cards or any of the other cards in the catalog. This is missing research, not a “no”. Your card may still offer it; check the issuer directly.`));
      }
    } else if (state.searchScope === "owned" && globalMatches.length) {
      empty.replaceChildren(node("h3", "Nothing recorded for your cards"), node("p", "None of your saved cards has a recorded benefit for this search. That does not prove your cards lack it; check the issuer directly."));
    } else {
      empty.replaceChildren(node("h3", "No public benefit matches those filters"), node("p", "Try a shorter phrase or clear a filter to browse the catalog."));
    }
  }
  if (focus) statusTarget?.focus({ preventScroll: true });
  if (state.selectedBenefitId && !matches.some(benefit => benefit.id === state.selectedBenefitId)) state.selectedBenefitId = null;
  renderBenefitDetail();
}
function discoveryParams(cursor = null) {
  const params = new URLSearchParams();
  const fields = [["q", "#benefitSearch"], ["category", "#benefitCategory"], ["issuer", "#benefitIssuer"], ["network", "#benefitNetwork"], ["merchant", "#benefitMerchant"], ["cap", "#benefitCap"], ["condition", "#benefitCondition"], ["claim_channel", "#benefitClaimChannel"], ["status", "#benefitStatus"], ["as_of", "#benefitAsOf"]];
  for (const [key, selector] of fields) { const value = document.querySelector(selector)?.value.trim(); if (value) params.set(key, value); }
  if (document.querySelector("#benefitAsOf")?.value) params.set("date_usable", "true");
  if (document.querySelector("#benefitOwnedOnly")?.checked) params.set("owned_only", "true");
  if (cursor) params.set("cursor", cursor);
  params.set("page_size", "25");
  return params;
}
function discoveryBenefitCard(result) {
  const state = result.state || result.benefit.state || "check_before_use";
  const benefit = { ...result.benefit, _offeringName: result.offering.display_name, _matchedTerms: result.matched_terms, _exactMatch: result.exact_match, _discoveryState: result.date_usable ? state : (state === "verified" ? "not_usable_on_date" : state) };
  return benefitCard(benefit);
}
async function runDiscovery({ focus = false } = {}) {
  renderBenefits();
  renderSearchResults({ focus });
}

async function loadMoreDiscovery() {
  if (!state.discoveryNextCursor) return;
  const button = document.querySelector("#benefitLoadMore");
  button.disabled = true;
  try {
    const response = await fetch(`/api/v1/catalog/discovery?${discoveryParams(state.discoveryNextCursor).toString()}`, { headers: { Accept: "application/json" }, cache: "no-store" });
    if (response.status === 409) throw new Error("restart");
    if (!response.ok) throw new Error("unavailable");
    const page = await response.json();
    state.discoveryResults = state.discoveryResults.concat(page.map(result => ({
      ...result, _ownedMatch: isOwnedBenefit(result.benefit),
    })));
    state.discoveryNextCursor = response.headers.get("X-Discovery-Next-Cursor") || null;
    const ownedList = document.querySelector("#benefitOwnedList");
    const list = document.querySelector("#benefitList");
    for (const result of page) (result._ownedMatch ? ownedList : list).append(discoveryBenefitCard(result));
    button.hidden = !state.discoveryNextCursor;
    document.querySelector("#benefitSearchStatus").textContent = `${state.discoveryResults.length} catalog matches loaded. Search results are public facts only.`;
  } catch (error) {
    document.querySelector("#benefitSearchStatus").textContent = error.message === "restart" ? "The catalog changed while loading more. Restart the search." : "More benefits are unavailable; the loaded results remain visible.";
  } finally { button.disabled = false; }
}

function benefitDates(benefit) {
  const end = benefit.end_date_known ? fmtDate(benefit.effective_to) : "No end date is recorded";
  return `Effective from ${fmtDate(benefit.effective_from)} · ${end}`;
}
function sourceDivergenceSection(benefit) {
  const claims = Array.isArray(benefit?.source_divergence) ? benefit.source_divergence : [];
  if (!claims.length) return null;
  const section = node("section", undefined, "benefit-detail-section divergence-section");
  section.append(node("h4", "Recorded source differences"), node("p", "These sources disagree about the benefit. Read both current claims before relying on it.", "benefit-first-note"));
  const list = node("ul", undefined, "evidence-list");
  for (const claim of claims) {
    const item = node("li");
    const kind = humanBenefitCategory(claim.category || claim.benefit_type);
    item.append(node("strong", kind || "Recorded source claim"));
    if (claim.effective_from) item.append(node("span", ` · effective from ${fmtDate(claim.effective_from)}`, "quiet-copy"));
    if (claim.allowance && typeof claim.allowance === "object") {
      const allowance = primaryAllowanceText({ allowance: claim.allowance, benefit_type: claim.benefit_type, category: claim.category });
      item.append(node("p", allowance || "Recorded allowance details differ.", "quiet-copy"));
    }
    const href = safeHref(claim.source_url);
    if (href) {
      const link = node("a", "Open source");
      link.href = href; link.target = "_blank"; link.rel = "noopener noreferrer";
      item.append(link);
    }
    list.append(item);
  }
  section.append(list);
  return section;
}
function formatEligibility(predicate) {
  return friendlyPredicate(predicate);
}
function detailList(title, values, emptyText) {
  const section = node("section", undefined, "benefit-detail-section");
  section.append(node("h4", title));
  if (!values.length) section.append(node("p", emptyText, "quiet-copy"));
  else {
    const list = node("ul", undefined, "evidence-list");
    for (const value of values) list.append(node("li", value));
    section.append(list);
  }
  return section;
}
function localBenefitMatch(card) {
  const row = node("article", undefined, "benefit-match-card");
  const offering = offeringForCard(card);
  const title = node("div", undefined, "card-title");
  title.append(node("h5", offering ? offering.display_name : "Matching local card record"), node("span", humanLifecycleLabel(card.lifecycle), privateCardBadge(card.lifecycle)));
  row.append(title);
  if (card.lifecycle === "archived") row.append(node("p", "Archived local record — kept for history. Archived does not mean expired.", "quiet-copy"));
  else if (card.lifecycle === "active") row.append(node("p", "In-use local product match. Check the public conditions below before relying on this benefit.", "quiet-copy"));
  else row.append(node("p", `Local record status: ${humanLifecycleLabel(card.lifecycle)}. This is not proof of current eligibility.`, "quiet-copy"));
  return row;
}
function alternativeBenefitCard(benefit) {
  const offering = state.offerings.find(item => item.id === benefit.offering_id);
  if (!offering) return null;
  const categoryLabel = humanBenefitCategory(benefit.category || benefit.benefit_type);
  if (!categoryLabel) return null;
  const card = node("article", undefined, "benefit-match-card");
  card.append(node("p", [humanIssuerLabel(offering.issuer_id), networkLabel(offering.network_id)].filter(Boolean).join(" · "), "eyebrow"), node("h5", offering.display_name));
  card.append(node("p", `Also lists a ${categoryLabel} benefit. Its terms, caps, and eligibility can differ.`, "quiet-copy"));
  const button = node("button", "Explore this public rule", "secondary benefit-detail-toggle");
  button.type = "button";
  button.addEventListener("click", () => selectBenefit(benefit.id));
  card.append(button);
  return card;
}
function renderBenefitDetail({ focus = false } = {}) {
  const target = document.querySelector("#benefitDetail");
  if (!target) return;
  clear(target);
  const benefit = state.benefits.find(item => item.id === state.selectedBenefitId) || state.discoveryResults.find(item => item.benefit.id === state.selectedBenefitId)?.benefit;
  if (!benefit) {
    target.append(node("p", "Select a public benefit to see what it is, how to qualify, how to claim it, and the official terms.", "quiet-copy"));
    return;
  }
  if (!humanBenefitCategory(benefit.category || benefit.benefit_type)) {
    target.append(node("p", "This public benefit cannot be displayed until its category is mapped.", "quiet-copy"));
    return;
  }
  const offering = benefitOffering(benefit) || state.discoveryResults.find(item => item.benefit.id === benefit.id)?.offering;
  const card = node("article", undefined, "benefit-card benefit-detail-card");
  const heading = node("h3", benefit.title); heading.id = "benefit-detail-title"; heading.tabIndex = -1;
  card.append(node("p", "Selected · what you need to know", "eyebrow"), heading);
  const benefitState = consumerBenefitState(benefit);
  card.append(node("span", benefitState.label, `state ${benefitState.tone}`), node("p", benefitState.note, "benefit-first-note"));
  const divergence = sourceDivergenceSection(benefit);
  if (divergence) card.append(divergence);
  const details = node("dl", undefined, "dl");
  const detailPair = (label, value) => details.append(node("dt", label), node("dd", value || "Not recorded in the source."));
  detailPair("Most you get", consumerAllowanceText(benefit));
  detailPair("To qualify", primaryConditionText(benefit));
  detailPair("How to claim", benefitHowToUse(benefit).join(" ") || (benefit.provider ? `Use the benefit with ${benefit.provider}.` : null));
  const guestCondition = [...(benefit.conditions || []), ...(benefit.eligibility || []), ...(benefit.exclusions || [])].find(item => String(item?.value || item?.field || item || "").toLocaleLowerCase().includes("guest"));
  detailPair("Guests", guestCondition ? (typeof guestCondition === "string" ? humanizeBenefitTerm(guestCondition) : formatEligibility(guestCondition)) : null);
  const firstEvidence = Array.isArray(benefit.evidence) ? benefit.evidence[0] : null;
  detailPair("Evidence", firstEvidence ? `${offering?.issuer_id ? humanIssuerLabel(offering.issuer_id) : "Official source"} · retrieved ${fmtDate(String(firstEvidence.retrieved_at || "").slice(0, 10))}` : null);
  card.append(details);
  if (benefit.not_claimed?.length) {
    const notClaimed = node("div", undefined, "notclaim"); notClaimed.append(node("p", "This is not claimed", "notclaim-heading"));
    const claims = node("ul"); for (const item of benefit.not_claimed) claims.append(node("li", safePublicValue(item) || "A claim is not recorded."));
    notClaimed.append(claims); card.append(notClaimed);
  }
  const terms = node("section", undefined, "benefit-detail-section"); terms.append(node("h4", "Official terms"));
  const officialHref = officialBenefitHref(benefit);
  if (officialHref) { const link = node("a", officialBenefitLinkText(benefit)); link.href = officialHref; link.target = "_blank"; link.rel = "noopener noreferrer"; terms.append(link); }
  if (!terms.querySelector("a")) terms.append(node("p", "No official terms link is recorded yet.", "quiet-copy"));
  card.append(terms, node("p", benefitDates(benefit), "quiet-copy"));
  target.append(card);

  const matches = node("section", undefined, "benefit-match-section");
  matches.append(node("h4", "Your local product matches"), node("p", "A local product match is shown separately from the public benefit. It never proves eligibility, spend requirements, or current availability.", "quiet-copy"));
  if (!state.privateCardsAvailable) matches.append(node("p", "Load My Cards to see which saved cards match this benefit.", "empty-state"));
  else {
    const matched = state.privateCards.filter(localCard => offeringForCard(localCard)?.id === benefit.offering_id);
    if (!matched.length) matches.append(node("p", "No saved card record matches this public product. This does not prove your cards lack it.", "empty-state"));
    else { const list = node("div", undefined, "benefit-match-list"); for (const matchedCard of matched) list.append(localBenefitMatch(matchedCard)); matches.append(list); }
  }
  target.append(matches);

  const alternatives = node("section", undefined, "benefit-match-section");
  const selectedCategoryLabel = humanBenefitCategory(benefit.category || benefit.benefit_type);
  alternatives.append(node("h4", "Other public card alternatives"), node("p", selectedCategoryLabel ? `These cards list a benefit in the same ${selectedCategoryLabel} category. That category does not make their benefits equivalent.` : "These cards list similar public benefits. Their terms, caps, and eligibility can differ.", "quiet-copy"));
  const seenOfferingIds = new Set([benefit.offering_id]);
  const alternativeList = node("div", undefined, "benefit-match-list");
  for (const alternative of state.benefits.filter(item =>
    humanBenefitCategory(item.category || item.benefit_type)
    && (item.category || item.benefit_type) === (benefit.category || benefit.benefit_type)
    && item.id !== benefit.id
  )) {
    if (seenOfferingIds.has(alternative.offering_id)) continue;
    seenOfferingIds.add(alternative.offering_id);
    const alternativeCard = alternativeBenefitCard(alternative);
    if (alternativeCard) alternativeList.append(alternativeCard);
  }
  if (alternativeList.childElementCount) alternatives.append(alternativeList);
  else alternatives.append(node("p", "No other public card benefit is listed in this category.", "empty-state"));
  target.append(alternatives);
  if (focus) heading.focus({ preventScroll: true });
}
function selectBenefit(benefitId) {
  state.selectedBenefitId = benefitId;
  navigateTo("search");
  renderBenefitDetail({ focus: true });
}
const PORTFOLIO_BROAD_CATEGORY_THRESHOLD = 3;
function portfolioRoleNote(offering) {
  const categories = new Set(state.benefits.filter(item => item.offering_id === offering.id && item.state === "verified").map(item => item.benefit_type));
  if (!categories.size) return node("p", "No active catalog benefit category is recorded yet, so no portfolio role can be suggested from verified facts.", "quiet-copy portfolio-note");
  const text = categories.size >= PORTFOLIO_BROAD_CATEGORY_THRESHOLD
    ? `Spans ${categories.size} active benefit categories (${[...categories].sort().join(", ").replaceAll("_", " ")}) — often fits a broad "core" role in a portfolio.`
    : `Concentrated in ${categories.size} active benefit categor${categories.size === 1 ? "y" : "ies"} (${[...categories].sort().join(", ").replaceAll("_", " ")}) — often fits a "specialist" role alongside a broader core card.`;
  const note = node("p", text, "quiet-copy portfolio-note");
  return note;
}
function comparisonValue(benefits, emptyText = "Not reviewed") {
  const wrapper = node("div", undefined, "comparison-cell");
  if (!benefits.length) { wrapper.append(node("span", emptyText, "quiet-copy")); return wrapper; }
  for (const benefit of benefits.slice(0, 3)) {
    const item = node("div", undefined, "comparison-benefit");
    item.append(node("strong", benefit.title));
    const conditions = [...(benefit.exclusions || []), ...(benefit.eligibility || [])].slice(0, 2);
    if (conditions.length) item.append(node("span", conditions.join(" · "), "quiet-copy"));
    const href = officialBenefitHref(benefit);
    if (href) { const link = node("a", officialBenefitLinkText(benefit, true)); link.href = href; link.target = "_blank"; link.rel = "noopener noreferrer"; item.append(link); }
    wrapper.append(item);
  }
  if (benefits.length > 3) wrapper.append(node("span", `+ ${benefits.length - 3} more`, "quiet-copy"));
  return wrapper;
}
function renderComparison() {
  const target = document.querySelector("#comparison"); clear(target);
  const a = state.offerings.find(item => item.slug === document.querySelector("#compareA").value);
  const b = state.offerings.find(item => item.slug === document.querySelector("#compareB").value);
  if (!a || !b) { target.append(node("p", "Choose two cards to compare the same decision categories.", "empty-state")); return; }
  target.append(portfolioRoleNote(a), portfolioRoleNote(b));
  const benefitsA = state.benefits.filter(item => item.offering_id === a.id && item.state === "verified");
  const benefitsB = state.benefits.filter(item => item.offering_id === b.id && item.state === "verified");
  if (!benefitsA.length || !benefitsB.length) {
    const empty = node("div", undefined, "empty-state comparison-empty");
    empty.append(node("h3", "Comparison data is not ready yet"), node("p", "MyCard does not turn two empty card records into a recommendation. Find a reviewed benefit or add a card, then come back when both cards have useful data."));
    const actions = node("div", undefined, "actions");
    const benefitsLink = node("a", "Find a benefit", "button"); benefitsLink.href = "#benefits"; benefitsLink.dataset.go = "benefits";
    const cardsLink = node("a", "Add cards", "button"); cardsLink.href = "#my-cards"; cardsLink.dataset.go = "my-cards";
    actions.append(benefitsLink, cardsLink); empty.append(actions); target.append(empty);
    for (const link of actions.querySelectorAll("[data-go]")) link.addEventListener("click", event => { event.preventDefault(); navigateTo(link.dataset.go); });
    return;
  }
  const groups = [
    ["Reward", ["reward_points", "reward", "miles"]], ["Movies", ["movie"]], ["Lounge", ["lounge", "airport"]], ["Travel", ["travel", "hotel", "forex", "insurance"]], ["Dining", ["food", "dining"]], ["Cashback / vouchers", ["cashback", "voucher"]],
  ];
  const table = node("div", undefined, "comparison-table");
  const header = node("div", undefined, "comparison-row comparison-header"); header.append(node("strong", "Decision area"), node("strong", a.display_name), node("strong", b.display_name)); table.append(header);
  for (const [label, terms] of groups) {
    const matches = list => list.filter(item => terms.some(term => `${item.category || ""} ${item.benefit_type || ""}`.toLocaleLowerCase().includes(term)));
    const row = node("div", undefined, "comparison-row"); row.append(node("strong", label), comparisonValue(matches(benefitsA)), comparisonValue(matches(benefitsB))); table.append(row);
  }
  const conditionsRow = node("div", undefined, "comparison-row"); conditionsRow.append(node("strong", "Conditions"), comparisonValue(benefitsA.flatMap(item => item.conditions || item.eligibility || []).map(condition => ({ title: formatEligibility(condition) }))), comparisonValue(benefitsB.flatMap(item => item.conditions || item.eligibility || []).map(condition => ({ title: formatEligibility(condition) })))); table.append(conditionsRow);
  const termsA = benefitsA.filter(item => officialBenefitHref(item));
  const termsB = benefitsB.filter(item => officialBenefitHref(item));
  const termsRow = node("div", undefined, "comparison-row"); termsRow.append(node("strong", "Official terms"), comparisonValue(termsA, "No link listed"), comparisonValue(termsB, "No link listed")); table.append(termsRow);
  target.append(node("p", "Rows show reviewed public facts only. Caps, exclusions, and conditions stay attached to each benefit. This is not a spend-return calculation and never names one universal best card.", "quiet-copy"), table);
}
document.querySelector("#benefitSearchForm")?.addEventListener("submit", event => { event.preventDefault(); runDiscovery({ focus: true }); });
document.querySelector("#benefitSearchReset")?.addEventListener("click", () => { document.querySelector("#benefitSearchForm")?.reset(); renderSearchResults(); document.querySelector("#benefitSearch")?.focus(); });
for (const button of document.querySelectorAll("[data-benefit-scope]")) button.addEventListener("click", () => {
  state.benefitScope = button.dataset.benefitScope === "owned" ? "owned" : "all";
  if (state.benefitScope === "owned") void requestPrivateCards();
  renderBenefits();
});
for (const button of document.querySelectorAll("[data-search-scope]")) button.addEventListener("click", () => {
  state.searchScope = button.dataset.searchScope === "all" ? "all" : "owned";
  if (state.searchScope === "owned") void requestPrivateCards();
  renderSearchResults();
});
function hasActionableTravelRule() {
  return state.destinationWorkflows.some(workflow =>
    workflow?.publication_state === "reviewed_active"
    && workflow?.review_state === "approved"
    && workflow?.effective_state === "active"
  );
}
function updateTravelAvailability() {
  const toggle = document.querySelector("#travelBenefitsToggle");
  const target = document.querySelector("#travel-workflows");
  if (!toggle || !target) return;
  const available = hasActionableTravelRule();
  toggle.hidden = !available;
  if (!available) {
    target.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
  }
}
document.querySelector("#travelBenefitsToggle")?.addEventListener("click", event => {
  const target = document.querySelector("#travel-workflows");
  const open = target.hidden;
  target.hidden = !open;
  event.currentTarget.setAttribute("aria-expanded", String(open));
  if (open) target.querySelector("h2")?.focus({ preventScroll: true });
});
for (const control of document.querySelectorAll("#benefitCategory, #benefitMerchant, #benefitCap, #benefitCondition, #benefitClaimChannel, #benefitStatus")) control.addEventListener("change", () => renderSearchResults());
for (const control of document.querySelectorAll("#benefitSearch, #benefitMerchant, #benefitCap, #benefitCondition, #benefitClaimChannel")) control.addEventListener("input", () => renderSearchResults());
for (const select of document.querySelectorAll("#compareA, #compareB")) select.addEventListener("change", () => {
  state.compareUserEdited = true;
  ensureCompareSelections();
  renderComparison();
});

const UNMATCHED_CARD_LABEL = "Unmatched variant";
const UNMATCHED_NOTE = "This card's product identifier has no match in the public catalog. Fix the identifier in the import file or request the card variant; its product name will appear once the match succeeds.";
function offeringForCard(card) {
  return state.offerings.find(candidate => candidate.slug === card.offering_id || candidate.id === card.offering_id);
}
function cardSearchText(card, offering) {
  const benefitNames = state.benefits.filter(benefit => benefit.offering_id === offering?.id || benefit.offering_id === offering?.slug || benefit.offering_id === card.offering_id).map(benefit => benefit.title);
  return [offering?.display_name, offering?.issuer_id, networkLabel(offering?.network_id), humanLifecycleLabel(card.lifecycle), ...benefitNames].filter(Boolean).join(" ").toLocaleLowerCase();
}
/* ---------- issuer-derived colourway: generated, never hand-assigned ---------- */
function issuerHue(id){
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return h % 360;
}
function issuerGradient(id){
  const h = issuerHue(id);
  const h2 = (h + 24) % 360;
  return `linear-gradient(135deg, hsl(${h} 46% 32%), hsl(${h2} 52% 20%))`;
}

/* ---------- benefit count line: honest, including the gap ---------- */
function countLine(c){
  if (!c.benefits) return "No benefits recorded";
  const bits = [`${c.benefits} benefit${c.benefits === 1 ? "" : "s"}`];
  if (c.verified) bits.push(`${c.verified} verified`);
  if (c.conflicts) bits.push(`${c.conflicts} conflict${c.conflicts === 1 ? "" : "s"}`);
  return bits.join(" · ");
}

function cardFace(c){
  const el = document.createElement("button");
  el.type = "button";
  el.className = "cardface" + (c.lifecycle === "archived" ? " archived" : "");
  el.style.background = issuerGradient(c.issuer_id);
  const publicCard = c.public === true;
  const lifecycleText = publicCard ? "public card" : (c.lifecycle === "archived" ? "archived" : "in use");
  el.setAttribute("aria-label",
    [c.issuer, c.name, lifecycleText, countLine(c)].filter(Boolean).join(", "));

  const top = document.createElement("div");
  top.className = "cf-top";
  const iss = document.createElement("span");
  iss.className = "cf-issuer"; iss.textContent = c.issuer;
  const st = document.createElement("span");
  st.className = "cf-status";
  st.textContent = publicCard ? "Public card" : (c.lifecycle === "archived" ? "Archived" : "In use");
  top.append(iss, st);

  const mid = document.createElement("div");
  const nm = document.createElement("p"); nm.className = "cf-name"; nm.textContent = c.name;
  const ct = document.createElement("p"); ct.className = "cf-count"; ct.textContent = countLine(c);
  mid.append(nm, ct);

  const bot = document.createElement("div");
  bot.className = "cf-bottom";
  const l4 = document.createElement("span");
  if (publicCard) { l4.className = "cf-public"; l4.textContent = "Browse benefits"; }
  else if (c.last4) { l4.className = "cf-last4"; l4.textContent = "•••• " + c.last4; }
  else { l4.className = "cf-add4"; l4.textContent = "Add last 4"; }
  const nw = document.createElement("span");
  nw.className = "cf-network"; nw.textContent = c.network || "";
  bot.append(l4);
  if (c.network) bot.append(nw);

  el.append(top, mid, bot);
  return el;
}

function catalogBenefitsForCard(card, offering) {
  const offeringId = offering?.id || card?.offering_id;
  if (!offeringId) return [];
  return state.benefits.filter(benefit =>
    benefit.offering_id === offeringId
    && Boolean(humanBenefitCategory(benefit.category || benefit.benefit_type))
  );
}
function benefitCountForCard(card, offering) {
  return catalogBenefitsForCard(card, offering).length;
}
function cardTypeForOffering(offering) {
  const identity = `${offering?.product_variant_id || ""} ${offering?.slug || ""}`.toLocaleLowerCase();
  if (/\bcredit\b/.test(identity)) return "credit";
  if (/\bdebit\b/.test(identity)) return "debit";
  return null;
}
function cardFaceData(card, offering) {
  const benefits = catalogBenefitsForCard(card, offering);
  const maskedLastFour = typeof card.masked_last4 === "string" ? /^•••• ([0-9]{4})$/.exec(card.masked_last4) : null;
  return {
    issuer: humanIssuerLabel(offering?.issuer_id),
    issuer_id: offering?.issuer_id || card.offering_id || "issuer",
    name: offering?.display_name || UNMATCHED_CARD_LABEL,
    network: networkLabel(offering?.network_id),
    last4: maskedLastFour?.[1] || null,
    lifecycle: card.lifecycle,
    benefits: benefits.length,
    verified: benefits.filter(benefit => consumerCatalogState(benefit) === "verified").length,
    conflicts: benefits.filter(benefit => consumerCatalogState(benefit) === "sources_differ").length,
  };
}
function focusLastFour(cardId) {
  const details = document.querySelector("#manageCardsDetails");
  if (details) details.open = true;
  const input = document.querySelector("#cardEditId");
  if (input) input.value = cardId;
  renderProtectedCardChoices();
  document.querySelector("#cardEditLastFour")?.focus();
}
function privateCardBadge(lifecycle) {
  if (lifecycle === "active") return "badge active";
  if (["lost", "stolen"].includes(lifecycle)) return "badge error";
  return "badge pending";
}
function viewCardBenefits(card) {
  const joined = state.ownedDiscoveryCards.find(item => item.local_card_ref === card.card_id);
  const offering = offeringForCard(card);
  const ruleIds = joined?.catalog_match === "matched" ? new Set(joined.rule_ids || []) : new Set();
  const matchingBenefits = state.benefits.filter(benefit =>
    Boolean(humanBenefitCategory(benefit.category || benefit.benefit_type))
    && (ruleIds.has(benefit.id) || benefit.offering_id === offering?.id || benefit.offering_id === offering?.slug || benefit.offering_id === card.offering_id)
  );
  if (!matchingBenefits.length) return;
  state.discoveryResults = state.benefits
    .filter(benefit => matchingBenefits.includes(benefit))
    .map(benefit => ({
      benefit,
      offering: state.offerings.find(item => item.id === benefit.offering_id) || offering,
      matched_terms: [],
      exact_match: false,
      date_usable: true,
      state: benefit.state,
      _ownedMatch: true,
    }));
  navigateTo("search");
  const list = document.querySelector("#searchResults"); clear(list);
  for (const result of state.discoveryResults) list.append(discoveryBenefitCard(result));
  document.querySelector("#searchStatus").textContent = "Showing public catalog benefits for the selected card. A product match is not proof of eligibility.";
  document.querySelector("#searchEmpty").hidden = state.discoveryResults.length > 0;
}
function renderCardChips() {
  const target = document.querySelector("#myCardChips");
  if (!target) return;
  const filters = state.cardFilters;
  clear(target);
  const definitions = [
    ["In use", "lifecycle", "active"],
    ["Archived", "lifecycle", "archived"],
    ["Credit", "type", "credit"],
    ["Debit", "type", "debit"],
    ["Has lounge", "benefit", "lounge"],
    ["Has movie", "benefit", "movie"],
  ];
  const offerings = state.privateCards.map(card => offeringForCard(card)).filter(Boolean);
  const issuerChoices = [...new Set(offerings.map(offering => offering.issuer_id).filter(Boolean))]
    .sort((a, b) => humanIssuerLabel(a).localeCompare(humanIssuerLabel(b)))
    .map(issuerId => [humanIssuerLabel(issuerId), "issuer", issuerId]);
  for (const [label, group, value] of [...definitions, ...issuerChoices]) {
    const chip = node("button", label, "chip");
    chip.type = "button";
    const selected = filters[group].has(value);
    chip.classList.toggle("on", selected);
    chip.setAttribute("aria-pressed", String(selected));
    chip.addEventListener("click", () => {
      if (filters[group].has(value)) filters[group].delete(value);
      else filters[group].add(value);
      renderPrivateCards();
    });
    target.append(chip);
  }
}
function cardMatchesChips(card, offering) {
  const filters = state.cardFilters;
  const benefits = catalogBenefitsForCard(card, offering);
  if (filters.lifecycle.size && !filters.lifecycle.has(card.lifecycle)) return false;
  if (filters.type.size && !filters.type.has(cardTypeForOffering(offering))) return false;
  if (filters.benefit.size && ![...filters.benefit].some(category => benefits.some(benefit => (benefit.category || benefit.benefit_type) === category))) return false;
  if (filters.issuer.size && !filters.issuer.has(offering?.issuer_id)) return false;
  return true;
}
function referenceCardRow(card) {
  const offering = offeringForCard(card);
  const item = node("article", undefined, "private-card card-reference");
  const face = cardFace(cardFaceData(card, offering));
  face.addEventListener("click", () => {
    if (!card.masked_last4) {
      focusLastFour(card.card_id);
      return;
    }
    if (catalogBenefitsForCard(card, offering).length) viewCardBenefits(card);
  });
  item.append(face);
  const actions = node("div", undefined, "private-card-actions");
  const revealButton = node("button", "Show full details", "secondary reveal-trigger");
  // The control is not disabled by hostname. It is the same person whether they
  // opened MyCard on the machine it runs on or reached it through the gateway
  // that starts these programs and puts them behind one authenticated URL, and
  // the server answers a request from either identically. Disabling the button
  // off loopback split the behaviour by device and told the owner their own
  // card details were unavailable on their own phone, which was never true.
  revealButton.type = "button";
  revealButton.setAttribute("aria-label", `Show full details for ${offering?.display_name || "this card"}`);
  revealButton.addEventListener("click", () => revealController.open(card, offering));
  actions.append(revealButton);
  item.append(actions);
  if (!offering) item.append(node("p", UNMATCHED_NOTE, "unmatched-note"));
  return item;
}
function refreshCardFilters() {
  renderCardChips();
}
function renderPrivateCards() {
  if (!state.privateCardsAvailable) return;
  refreshCardFilters();
  const query = document.querySelector("#myCardSearch")?.value.trim().toLocaleLowerCase() || "";
  const cards = state.privateCards.filter(card => {
    const offering = offeringForCard(card);
    if (!cardMatchesChips(card, offering)) return false;
    if (query && !cardSearchText(card, offeringForCard(card)).includes(query)) return false;
    return true;
  });
  cards.sort((a, b) => (a.lifecycle === "archived") - (b.lifecycle === "archived"));
  const target = document.querySelector("#myCardList"); clear(target);
  const inUse = state.privateCards.filter(card => card.lifecycle === "active").length;
  const archived = state.privateCards.filter(card => card.lifecycle === "archived").length;
  const withBenefits = state.privateCards.filter(card => benefitCountForCard(card, offeringForCard(card)) > 0).length;
  setText("#myCardSummary", `${inUse} in use · ${archived} archived · ${withBenefits} with benefits recorded`);
  setText("#myCardStatus", "");
  if (!state.privateCards.length) {
    const empty = node("div", undefined, "empty-state");
    empty.append(node("p", "Your wallet is empty", "eyebrow"), node("h3", "Add your cards"), node("p", "Tick everything in your wallet. You can add details later — nothing is required now."), node("p", "Skipping entirely is allowed — the catalog is browsable with zero cards.", "quiet-copy"));
    const action = node("a", "Add my first card", "button"); action.href = "#cardAddForm"; action.addEventListener("click", () => document.querySelector("#cardAddIssuerChips button")?.focus()); empty.append(action);
    target.append(empty);
    return;
  }
  if (!cards.length) {
    target.append(node("p", "No cards match the current search and lifecycle filter. Clear the search or choose a different status.", "empty-state"));
    return;
  }
  cards.forEach(card => target.append(referenceCardRow(card)));
}
const VAULT_DIAGNOSTICS = {
  demo: {
    title: "My Cards is unavailable in demo mode",
    text: "Open your normal MyCard app to see and manage your own cards.",
    status: "Your personal cards are not opened in this demo.",
    note: "Your real cards are not shown in demo mode.",
    action: "Try again",
  },
  vault_missing: {
    title: "My Cards is unavailable",
    text: "Secure card storage could not be created on this computer.",
    status: "Your cards could not be opened.",
    note: "Your existing cards were not changed.",
    action: "Try again",
  },
  passphrase_only: {
    title: "My Cards is unavailable",
    text: "The local card key is not available for this data location.",
    status: "Your cards could not be opened.",
    note: "Your existing cards were not changed.",
    action: "Try again",
  },
  wrong_data_dir: {
    title: "Your cards are not available here",
    text: "MyCard was opened without the card storage you used before. Reopen it the same way, then try again.",
    status: "No cards were opened from this location.",
    note: "Your existing cards were not changed.",
    action: "Try again",
  },
  locked: {
    title: "My Cards is unavailable",
    text: "We could not open the local card storage automatically.",
    status: "Your cards could not be opened.",
    note: "Your existing cards were not changed.",
    action: "Try again",
  },
  expired: { title: "My Cards is unavailable", text: "The local card storage session expired. Try again to load My Cards.", status: "Your cards could not be opened.", note: "Your existing cards were not changed.", action: "Try again" },
  keyring_unavailable: {
    title: "My Cards is unavailable",
    text: "The local device key could not be read on this computer.",
    status: "Your cards could not be opened.",
    note: "Your existing cards were not changed.",
    action: "Try again",
  },
  generic: {
    title: "My Cards is unavailable right now",
    text: "Try again. Your existing cards have not been changed.",
    status: "Your cards could not be opened.",
    note: "If this keeps happening, check the local data location in Settings.",
    action: "Try again",
  },
  wrong_passphrase: { title: "My Cards is unavailable", text: "The local card storage could not be opened.", status: "Your cards could not be opened.", note: "Your existing cards were not changed.", action: "Try again" },
  rate_limited: { title: "Please wait before trying again", text: "The local card storage is temporarily unavailable. Try again shortly.", status: "My Cards is temporarily unavailable.", note: "Your existing cards were not changed.", action: "Try again" },
};
function setText(selector, value) {
  try { const target = document.querySelector(selector); if (target) target.textContent = value; } catch { /* optional consumer-only control */ }
}
function setPrivateAccess(title, text, status) {
  setText("#vaultSummaryTitle", title);
  setText("#vaultSummaryText", text);
  setText("#myCardStatus", status);
  setText("#myCardSummary", text);
}
function setPrivateUnavailable(diagnostic) {
  clearSecretErasePrompt();
  setPrivateAccess(diagnostic.title, diagnostic.text, diagnostic.status);
  const target = document.querySelector("#myCardList");
  if (!target) return;
  clear(target);
  const box = node("div", undefined, "empty-state");
  box.append(node("h3", diagnostic.title), node("p", diagnostic.text), node("p", diagnostic.note, "quiet-copy"));
  const action = node("button", diagnostic.action || "Try again", "secondary");
  action.type = "button";
  action.addEventListener("click", () => void loadPrivateCards());
  box.append(action);
  target.append(box);
  state.privateStateRevision = null;
}
async function loadOwnedDiscovery() {
  try {
    const response = await fetch("/api/v1/private/discovery/cards", { headers: { Accept: "application/json" }, credentials: "same-origin", cache: "no-store" });
    if (!response.ok) throw new Error("unavailable");
    const payload = await response.json();
    state.ownedDiscoveryCards = Array.isArray(payload.cards) ? payload.cards : [];
    state.ownedDiscoveryAvailable = true;
    state.ownedDiscoveryDiagnostic = null;
  } catch {
    state.ownedDiscoveryCards = [];
    state.ownedDiscoveryAvailable = false;
    state.ownedDiscoveryDiagnostic = "Private card matching is unavailable; public discovery remains available.";
  }
}
async function loadPrivateCards() {
  let response;
  try {
    response = await fetch("/api/v1/private/cards", { headers: { Accept: "application/json" }, credentials: "same-origin", cache: "no-store" });
    if (!response.ok) throw new Error("unavailable");
    const payload = await response.json();
    state.privateCards = Array.isArray(payload.cards) ? payload.cards : [];
    state.privateCardsAvailable = true;
    setPrivateAccess("Saved cards are ready", `${state.privateCards.length} saved card${state.privateCards.length === 1 ? "" : "s"} are ready to use with the benefit library.`, "");
    refreshCardFilters();
    await loadOwnedDiscovery();
    renderPrivateCards();
    refreshProtectedActionOptions();
    setProtectedActionAvailability(true);
    renderBenefits();
    if (typeof renderSearchResults === "function") renderSearchResults();
    if (document.querySelector("#compareA") && document.querySelector("#compareB")) {
      ensureCompareSelections({ preferOwned: !state.compareDefaultsApplied });
      renderComparison();
    }
  } catch {
    let code = "generic";
    if (response && !response.ok) {
      try {
        const body = await response.json();
        if (body && typeof body.detail === "object" && body.detail && typeof body.detail.code === "string") code = body.detail.code;
      } catch { /* keep the generic fallback */ }
    }
    const diagnostic = VAULT_DIAGNOSTICS[code] || VAULT_DIAGNOSTICS.generic;
    state.privateCards = [];
    state.privateCardsAvailable = false;
    state.privateAggregates = [];
    state.privateAttempts = [];
    state.privateStateRevision = null;
    state.personalStateAvailable = false;
    state.ownedDiscoveryCards = [];
    state.ownedDiscoveryAvailable = false;
    setProtectedActionAvailability(false);
    refreshProtectedActionOptions();
    setPrivateUnavailable(diagnostic);
    setText("#myCardCount", "Unknown");
    setText("#myCardCountNote", "Try again to load your cards");
    renderBenefits();
    if (typeof renderSearchResults === "function") renderSearchResults();
  }
}
function setPersonalStateAvailability(enabled) {
  state.personalStateAvailable = enabled;
  if (!enabled) state.privateStateRevision = null;
  const badge = document.querySelector("#personalStateBadge");
  if (badge) badge.textContent = enabled ? "Private state ready" : "Private state unavailable";
  for (const form of document.querySelectorAll(".personal-state-form")) {
    for (const control of form.querySelectorAll("input, select, textarea, button")) control.disabled = !enabled;
  }
  const status = document.querySelector("#personalStateStatus");
  if (status) status.textContent = enabled
    ? "Private progress is available locally; it is not public eligibility evidence."
    : "Private progress is unavailable right now.";
}
function privateStateCardLabel(card) {
  const offering = offeringForCard(card);
  return `${offering?.display_name || "Unmatched variant"} · ${card.masked_last4 || "number not shown"} · ${humanLifecycleLabel(card.lifecycle)}`;
}
function refreshPersonalStateOptions() {
  for (const selector of ["#manualAggregateCard", "#manualAggregateClearCard", "#privateAttemptCard"]) {
    const select = document.querySelector(selector); if (!select) continue;
    const keep = select.value; clear(select); select.append(new Option("Choose a card", ""));
    for (const card of state.privateCards) {
      const cardId = card["card_id"];
      select.append(new Option(privateStateCardLabel(card), cardId));
    }
    if ([...select.options].some(option => option.value === keep)) select.value = keep;
  }
  const attempts = document.querySelector("#privateAttemptDeleteId");
  if (!attempts) return;
  const keep = attempts.value; clear(attempts); attempts.append(new Option("Choose an attempt", ""));
  for (const attempt of state.privateAttempts) {
    const card = state.privateCards.find(item => item.card_id === attempt.card_id);
    attempts.append(new Option(`${attempt.outcome} · ${offeringForCard(card)?.display_name || "Unmatched variant"}`, attempt.attempt_id));
  }
  if ([...attempts.options].some(option => option.value === keep)) attempts.value = keep;
}
function privateStateCardText(cardId) {
  const card = state.privateCards.find(item => item.card_id === cardId);
  return privateStateCardLabel(card || { lifecycle: "unmatched" });
}
function renderPersonalState() {
  const target = document.querySelector("#personalStateList"); clear(target);
  const aggregateCount = state.privateAggregates.length;
  const attemptCount = state.privateAttempts.length;
  if (!aggregateCount && !attemptCount) {
    target.append(node("p", "No private progress records are loaded.", "empty-state"));
    refreshPersonalStateOptions();
    return;
  }
  if (aggregateCount) {
    target.append(node("h4", "Manual aggregate snapshots"));
    for (const aggregate of state.privateAggregates) {
      const card = node("article", undefined, "personal-state-row");
      card.append(node("p", `${aggregate.amount} ${aggregate.currency} · ${aggregate.period}`));
      card.append(node("p", `${privateStateCardText(aggregate.card_id)} · rule version ${aggregate.rule_version}`, "quiet-copy"));
      card.append(node("p", "Private manual context only; not a transaction ledger or eligibility proof.", "quiet-copy"));
      target.append(card);
    }
  }
  if (attemptCount) {
    target.append(node("h4", "Attempt history"));
    for (const attempt of state.privateAttempts) {
      const card = node("article", undefined, "personal-state-row");
      card.append(node("p", `${attempt.outcome} · ${privateStateCardText(attempt.card_id)} · rule version ${attempt.rule_version}`));
      card.append(node("p", attempt.note || "No local note.", "quiet-copy"));
      card.append(node("p", "Private history only; it does not alter public eligibility or ranking.", "quiet-copy"));
      target.append(card);
    }
  }
  refreshPersonalStateOptions();
}
async function loadPrivateState() {
  let response;
  try {
    response = await fetch("/api/v1/private/personal-state", { headers: { Accept: "application/json" }, credentials: "same-origin", cache: "no-store" });
    if (!response.ok) throw new Error("unavailable");
    const payload = await response.json();
    state.privateAggregates = Array.isArray(payload.aggregates) ? payload.aggregates : [];
    state.privateAttempts = Array.isArray(payload.attempts) ? payload.attempts : [];
    if (typeof payload.private_state_revision !== "string") throw new Error("unavailable");
    state.privateStateRevision = payload.private_state_revision;
    setPersonalStateAvailability(true);
    renderPersonalState();
  } catch {
    state.privateAggregates = [];
    state.privateAttempts = [];
    state.privateStateRevision = null;
    setPersonalStateAvailability(false);
    renderPersonalState();
    if (response?.status === 401) {
      const status = document.querySelector("#personalStateStatus");
      if (status) status.textContent = "Open My Cards before opening private progress.";
    }
  }
}
function setProtectedActionAvailability(enabled) {
  if (!enabled) clearSecretErasePrompt();
  for (const panel of document.querySelectorAll("[data-private-only]")) panel.hidden = !enabled;
  const badge = document.querySelector("#protectedActionBadge");
  if (badge) badge.textContent = enabled ? "Protected actions ready" : "Cards unavailable";
  for (const form of document.querySelectorAll("#cardAddForm, #cardEditForm, #cardLifecycleForm, #cardReplaceForm, #cardDeleteForm, #secretEraseForm")) {
    for (const control of form.querySelectorAll("input, select, textarea, button")) control.disabled = !enabled;
  }
  const status = document.querySelector("#protectedActionStatus");
  if (status) status.textContent = enabled
    ? "Changes are encrypted on this computer; sensitive fields clear after submission."
    : "My Cards is unavailable right now.";
  renderCardOfferingChoices();
}
function managementCardChoices() {
  return state.privateCards.map(card => {
    const offering = offeringForCard(card);
    return [card.card_id, `${offering?.display_name || UNMATCHED_CARD_LABEL} · ${card.masked_last4 || "Add last 4"} · ${humanLifecycleLabel(card.lifecycle)}`];
  });
}
function renderProtectedCardChoices() {
  const choices = managementCardChoices();
  for (const id of ["cardEditId", "cardLifecycleId", "cardReplaceId", "cardDeleteId"]) {
    renderChoiceButtons(`#${id}`, `#${id}Button`, `#${id}Choices`, choices, "Choose a card");
  }
  renderChoiceButtons(
    "#cardLifecycleValue",
    "#cardLifecycleValueButton",
    "#cardLifecycleValueChoices",
    [["active", "In use"], ["archived", "Archived"], ["lost", "Lost"], ["stolen", "Stolen"], ["expired", "Expired"], ["closed", "Closed"]],
    "Choose a new card status",
  );
  renderChoiceButtons(
    "#cardDeleteAction",
    "#cardDeleteActionButton",
    "#cardDeleteActionChoices",
    [["delete", "Remove record"], ["purge", "Remove permanently"]],
    "Choose a removal action",
  );
}
function refreshProtectedActionOptions() {
  renderProtectedCardChoices();
  refreshPersonalStateOptions();
}
function secretFieldsFrom(prefix, { includeNickname = false, includeLastFour = false } = {}) {
  const fields = {};
  const values = {
    pan: document.querySelector(`#${prefix}Pan`)?.value,
    expiry_month: document.querySelector(`#${prefix}ExpiryMonth`)?.value,
    expiry_year: document.querySelector(`#${prefix}ExpiryYear`)?.value,
    cvv: document.querySelector(`#${prefix}Cvv`)?.value,
    pin: document.querySelector(`#${prefix}Pin`)?.value,
  };
  if (includeNickname) values.nickname = document.querySelector(`#${prefix}Nickname`)?.value;
  if (includeLastFour) values.last_four = (document.querySelector(`#${prefix}LastFour`)?.value || "").trim();
  for (const [key, value] of Object.entries(values)) if (value) fields[key] = value;
  return fields;
}
async function protectedJson(path, payload, method = "POST") {
  const csrfResponse = await fetch("/api/v1/private/csrf-token", { headers: { Accept: "application/json" }, credentials: "same-origin", cache: "no-store" });
  if (!csrfResponse.ok) throw new Error("protected action unavailable");
  const csrf = (await csrfResponse.json()).csrf_token;
  const response = await fetch(path, {
    method, credentials: "same-origin", cache: "no-store",
    headers: { "Content-Type": "application/json", Accept: "application/json", "X-CSRF-Token": csrf },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const error = new Error("protected action unavailable");
    error.status = response.status;
    try {
      const body = await response.json();
      if (body && body.detail && typeof body.detail === "object" && typeof body.detail.code === "string") {
        error.code = body.detail.code;
      }
    } catch { /* keep the generic protected-action error */ }
    throw error;
  }
  return response.json();
}

const revealController = createRevealController({ protectedJson });

function privateAttemptContract() {
  if (typeof state.privateStateRevision !== "string" || !globalThis.crypto?.randomUUID) throw new Error("protected action unavailable");
  return { idempotency_key: globalThis.crypto.randomUUID(), expected_private_state_revision: state.privateStateRevision };
}
function clearSecretErasePrompt() {
  state.pendingSecretEraseCardId = null;
  const prompt = document.querySelector("#secretErasePrompt");
  const form = document.querySelector("#secretEraseForm");
  if (prompt) prompt.hidden = true;
  if (form) form.reset();
}
function showSecretErasePrompt(cardId) {
  if (!state.privateCards.some(card => card["card_id"] === cardId)) return;
  state.pendingSecretEraseCardId = cardId;
  const prompt = document.querySelector("#secretErasePrompt");
  const heading = document.querySelector("#secretErasePromptTitle");
  document.querySelector("#secretEraseForm").reset();
  prompt.hidden = false;
  document.querySelector("#protectedActionStatus").textContent = "Lifecycle updated. Choose whether to keep or erase stored CVV/PIN; keeping them is the default.";
  heading.setAttribute("tabindex", "-1");
  heading.focus({ preventScroll: true });
}
function keepSecretErasePrompt() {
  clearSecretErasePrompt();
  document.querySelector("#protectedActionStatus").textContent = "Stored CVV/PIN were kept. The card envelope, history, and lineage remain.";
}
async function submitSecretErase() {
  const form = document.querySelector("#secretEraseForm");
  const button = form.querySelector("button[type=submit]");
  const cardId = state.pendingSecretEraseCardId;
  if (!cardId) return;
  let committed = false;
  button.disabled = true;
  try {
    await protectedJson(`/api/v1/private/cards/${encodeURIComponent(cardId)}/erase-cvv-pin`, {});
    committed = true;
    clearSecretErasePrompt();
    document.querySelector("#protectedActionStatus").textContent = "Stored CVV/PIN were erased. The card envelope, history, and lineage remain; no secret field was returned.";
    try {
      await loadPrivateCards();
      await runDiscovery();
    } catch { /* the committed local action remains true even if refresh is unavailable */ }
  } catch {
    if (!committed) document.querySelector("#protectedActionStatus").textContent = "Secret erase failed; stored CVV/PIN were not changed and no private field was displayed.";
  } finally {
    button.disabled = !state.privateCardsAvailable;
  }
}
async function submitProtected(form, path, payload, method = "POST", erasePromptCardId = null) {
  const button = form.querySelector("button[type=submit]");
  let committed = false;
  button.disabled = true;
  try {
    const result = await protectedJson(path, payload, method);
    committed = true;
    form.reset();
    document.querySelector("#protectedActionStatus").textContent = "Protected card action completed. Secret fields were cleared and were not returned.";
    try {
      await loadPrivateCards();
      await runDiscovery();
    } catch { /* the committed local action remains true even if refresh is unavailable */ }
    if (result?.erase_prompt === true && erasePromptCardId && state.privateCardsAvailable) showSecretErasePrompt(erasePromptCardId);
  } catch {
    if (!committed) document.querySelector("#protectedActionStatus").textContent = "Protected card action failed; no private field was displayed. Check the selected record and try again.";
  } finally {
    for (const input of form.querySelectorAll("input[type=password], input[inputmode=numeric], textarea")) input.value = "";
    button.disabled = !state.privateCardsAvailable;
  }
}
function renderCardAddLastFourPrompt() {
  const prompt = document.querySelector("#cardAddLastFourPrompt");
  const fields = document.querySelector("#cardAddLastFourFields");
  if (!prompt || !fields) return;
  clear(fields);
  if (!state.pendingLastFourCards.length) {
    prompt.hidden = true;
    return;
  }
  prompt.hidden = false;
  for (const item of state.pendingLastFourCards) {
    const label = node("label", undefined, "card-add-followup-field");
    label.append(node("span", item.displayName, "card-add-followup-name"));
    const input = node("input");
    input.type = "text";
    input.inputMode = "numeric";
    input.pattern = "[0-9]{4}";
    input.maxLength = 4;
    input.autocomplete = "off";
    input.placeholder = "Optional · 4 digits";
    input.dataset.cardId = item.cardId;
    input.setAttribute("aria-label", `Last 4 for ${item.displayName}`);
    label.append(input);
    fields.append(label);
  }
  const status = document.querySelector("#cardAddLastFourStatus");
  if (status) status.textContent = "Leave any field blank to skip it.";
}
function showCardAddLastFourPrompt(addedCards) {
  state.pendingLastFourCards = addedCards.map(item => ({
    cardId: item.cardId,
    displayName: state.offerings.find(offering => offering.id === item.offeringId)?.display_name || "Added card",
  }));
  renderCardAddLastFourPrompt();
  const heading = document.querySelector("#cardAddLastFourTitle");
  if (heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }); }
}
function skipCardAddLastFour() {
  state.pendingLastFourCards = [];
  renderCardAddLastFourPrompt();
  const status = document.querySelector("#protectedActionStatus");
  if (status) status.textContent = "Last 4 skipped. You can add it later in Manage cards and private details.";
}
async function submitCardAddLastFour() {
  const fields = document.querySelector("#cardAddLastFourFields");
  const save = document.querySelector("#cardAddLastFourSave");
  if (!fields || !save) return;
  const inputs = [...fields.querySelectorAll("input[data-card-id]")];
  const updates = inputs.map(input => ({ cardId: input.dataset.cardId, value: input.value.trim() }));
  if (updates.some(item => item.value && !/^\d{4}$/.test(item.value))) {
    document.querySelector("#cardAddLastFourStatus").textContent = "Enter four digits or leave a field blank.";
    return;
  }
  const pending = [];
  let saved = 0;
  save.disabled = true;
  document.querySelector("#cardAddLastFourSkip").disabled = true;
  try {
    for (const item of updates.filter(item => item.value)) {
      try {
        await protectedJson(`/api/v1/private/cards/${encodeURIComponent(item.cardId)}/edit`, { changes: { last_four: item.value } });
        saved += 1;
      } catch {
        pending.push(state.pendingLastFourCards.find(card => card.cardId === item.cardId));
      }
    }
    if (saved) await loadPrivateCards();
    state.pendingLastFourCards = pending.filter(Boolean);
    renderCardAddLastFourPrompt();
    const status = document.querySelector("#cardAddLastFourStatus");
    if (pending.length) status.textContent = `${saved} last 4${saved === 1 ? "" : "s"} saved. The remaining field${pending.length === 1 ? "" : "s"} can be tried again.`;
    else if (saved) document.querySelector("#protectedActionStatus").textContent = `${saved} last 4${saved === 1 ? "" : "s"} saved. The cards are ready to recognise.`;
    else skipCardAddLastFour();
  } finally {
    save.disabled = !state.privateCardsAvailable || !state.pendingLastFourCards.length;
    document.querySelector("#cardAddLastFourSkip").disabled = false;
  }
}
async function submitCardBatch(form, offeringIds) {
  const submit = form.querySelector("#cardAddSubmit");
  if (!submit) return;
  const added = [];
  const failed = [];
  const secretFields = offeringIds.length === 1
    ? secretFieldsFrom("cardAdd", { includeNickname: true })
    : {};
  submit.disabled = true;
  try {
    for (const offeringId of offeringIds) {
      try {
        const result = await protectedJson("/api/v1/private/cards/add", {
          offering_id: offeringId,
          secret_fields: secretFields,
        });
        if (typeof result?.card_id === "string" && result.card_id) added.push({ cardId: result.card_id, offeringId });
        else failed.push(offeringId);
      } catch {
        failed.push(offeringId);
      }
    }
    if (added.length) {
      form.reset();
      state.cardAddSelection = new Set(failed);
      await loadPrivateCards();
      await runDiscovery();
      state.cardAddSelection = new Set(failed);
      renderCardOfferingChoices();
      showCardAddLastFourPrompt(added);
    }
    const status = document.querySelector("#protectedActionStatus");
    if (status) {
      if (added.length && failed.length) status.textContent = `Added ${added.length} card${added.length === 1 ? "" : "s"}. ${failed.length} could not be added and remain selected to try again.`;
      else if (added.length) status.textContent = `Added ${added.length} card${added.length === 1 ? "" : "s"}. Add last 4s below if useful.`;
      else status.textContent = "No cards were added. Check the selected products and try again.";
    }
  } finally {
    renderCardOfferingChoices();
  }
}
async function submitPersonalState(form, path, payload, method = "POST") {
  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  try {
    await protectedJson(path, payload, method);
    form.reset();
    document.querySelector("#personalStateStatus").textContent = "Private progress action completed; no public catalog or agent state changed.";
    await loadPrivateState();
  } catch {
    document.querySelector("#personalStateStatus").textContent = "Private progress action failed; the vault and public eligibility state were not changed.";
  } finally {
    for (const input of form.querySelectorAll("input[type=password], input[inputmode=decimal], textarea")) input.value = "";
    button.disabled = !state.personalStateAvailable;
  }
}
document.querySelector("#cardAddForm").addEventListener("submit", event => {
  event.preventDefault(); const form = event.currentTarget;
  const offeringIds = [...state.cardAddSelection].filter(offeringId => state.offerings.some(offering => offering.id === offeringId));
  if (!offeringIds.length) {
    document.querySelector("#protectedActionStatus").textContent = "Choose at least one catalog card before adding them.";
    return;
  }
  submitCardBatch(form, offeringIds);
});
document.querySelector("#cardAddLastFourSave")?.addEventListener("click", submitCardAddLastFour);
document.querySelector("#cardAddLastFourSkip")?.addEventListener("click", skipCardAddLastFour);
document.querySelector("#cardEditForm").addEventListener("submit", event => {
  event.preventDefault(); const form = event.currentTarget; const changes = {};
  const nickname = document.querySelector("#cardEditNickname").value; const notes = document.querySelector("#cardEditNotes").value; const lastFour = document.querySelector("#cardEditLastFour").value.trim();
  if (lastFour) changes.last_four = lastFour;
  if (nickname) changes.nickname = nickname; if (notes) changes.notes = notes;
  submitProtected(form, `/api/v1/private/cards/${encodeURIComponent(document.querySelector("#cardEditId").value)}/edit`, { changes });
});
document.querySelector("#cardLifecycleForm").addEventListener("submit", event => {
  event.preventDefault(); const form = event.currentTarget;
  const cardId = document.querySelector("#cardLifecycleId").value;
  submitProtected(form, `/api/v1/private/cards/${encodeURIComponent(cardId)}/lifecycle`, { lifecycle: document.querySelector("#cardLifecycleValue").value }, "POST", cardId);
});
document.querySelector("#cardReplaceForm").addEventListener("submit", event => {
  event.preventDefault(); const form = event.currentTarget;
  submitProtected(form, `/api/v1/private/cards/${encodeURIComponent(document.querySelector("#cardReplaceId").value)}/replace`, { secret_fields: secretFieldsFrom("cardReplace") });
});
document.querySelector("#cardDeleteForm").addEventListener("submit", event => {
  event.preventDefault(); const form = event.currentTarget; const cardId = encodeURIComponent(document.querySelector("#cardDeleteId").value);
  const path = document.querySelector("#cardDeleteAction").value === "purge" ? `/api/v1/private/cards/${cardId}/purge` : `/api/v1/private/cards/${cardId}`;
  submitProtected(form, path, { confirmation: document.querySelector("#cardDeleteConfirmation").value }, path.endsWith("/purge") ? "POST" : "DELETE");
});
document.querySelector("#secretEraseForm").addEventListener("submit", event => { event.preventDefault(); submitSecretErase(); });
document.querySelector("#secretEraseKeepButton").addEventListener("click", keepSecretErasePrompt);
setProtectedActionAvailability(false);
refreshProtectedActionOptions();
async function loadReminders() {
  const status = document.querySelector("#reminderStatus");
  const target = document.querySelector("#reminderList");
  try {
    const response = await fetch("/api/v1/private/reminders", { headers: { Accept: "application/json" }, credentials: "same-origin", cache: "no-store" });
    if (!response.ok) throw new Error("unavailable");
    const payload = await response.json(); clear(target);
    for (const reminder of Array.isArray(payload.reminders) ? payload.reminders : []) {
      const card = node("article", undefined, "benefit-match-card update-card");
      card.append(node("h3", reminder.title), node("p", reminder.message), node("p", `${reminder.status.replaceAll("_", " ")} · priority ${reminder.priority}`, "quiet-copy"));
      if (reminder.education_only) card.append(node("p", "Education only — not a transaction ledger or spending tracker.", "quiet-copy"));
      target.append(card);
    }
    for (const notification of Array.isArray(payload.notifications) ? payload.notifications : []) {
      const card = node("article", undefined, "benefit-match-card update-card");
      card.append(node("h3", "Public catalog conflict"), node("p", notification.message),
        node("p", `${notification.review_state || "unresolved"} · review required`, "quiet-copy"));
      target.append(card);
    }
    if (!target.children.length) target.append(node("p", "No local reminder signals are currently available.", "empty-state"));
    status.textContent = `${payload.count || 0} local reminder signal${payload.count === 1 ? "" : "s"}. Network delivery is off by default.`;
  } catch { clear(target); target.append(node("p", "Local reminder data is unavailable. Recover the vault, then retry.", "empty-state")); status.textContent = "Reminders unavailable."; }
}
async function loadReminderPreferences() {
  const checkbox = document.querySelector("#reminderDueDateAutopay");
  if (!checkbox) return;
  try {
    const response = await fetch("/api/v1/private/reminders/preferences", { cache: "no-store", credentials: "same-origin" });
    if (response.ok) checkbox.checked = Boolean((await response.json()).due_date_autopay);
  } catch { /* unavailable state is reported when the user changes it */ }
}
document.querySelector("#reminderDueDateAutopay")?.addEventListener("change", async (event) => {
  const checkbox = event.currentTarget;
  const status = document.querySelector("#reminderPreferenceStatus");
  try {
    const response = await fetch("/api/v1/private/reminders/preferences", { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, credentials: "same-origin", cache: "no-store", body: JSON.stringify({ due_date_autopay: checkbox.checked }) });
    if (!response.ok) throw new Error("unavailable");
    status.textContent = "Reminder preference saved locally.";
    await loadReminders();
  } catch { checkbox.checked = !checkbox.checked; status.textContent = "Could not save this local preference."; }
});
document.querySelector("#myCardSearch")?.addEventListener("input", renderPrivateCards);


function setWorkflowStatus(message, kind) {
  const target = document.querySelector("#workflowStatus");
  target.textContent = message;
  target.className = `qa-status${kind ? ` ${kind}` : ""}`;
}
function workflowScopeText(scope) {
  if (!scope || scope.kind === "unknown") return "Destination scope is unknown pending human review.";
  if (scope.kind === "any") return "Any destination recorded by the official terms.";
  return `${scope.kind.replaceAll("_", " ")}: ${scope.values.join(", ")}`;
}
function workflowStateClass(workflow) {
  return workflow.publication_state === "reviewed_active" && workflow.effective_state === "active"
    ? "badge active"
    : "badge pending";
}
function workflowStateLabel(workflow) {
  return workflow.publication_state === "reviewed_active"
    ? `${workflow.effective_state.replaceAll("_", " ")} · reviewed`
    : "needs review · candidate";
}
function workflowSourceText(provenance) {
  const source = provenance?.[0];
  if (!source) return "No provenance is available.";
  return `${source.source_policy_class.replaceAll("_", " ")} · tier ${source.source_tier} · ${source.review_state} · ${source.confidence} confidence`;
}
function workflowCard(workflow, candidate = false) {
  const card = node("article", undefined, `benefit-card workflow-card${candidate ? " workflow-candidate" : ""}`);
  const head = node("div", undefined, "card-title");
  const titleGroup = node("div");
  titleGroup.append(
    node("p", candidate ? "Not ready to use" : "Reviewed travel benefit", "eyebrow"),
    node("h3", workflow.title),
  );
  head.append(titleGroup, node("span", workflowStateLabel(workflow), workflowStateClass(workflow)));
  card.append(head);
  card.append(node("p", `Available from ${fmtDate(workflow.effective_from)}${workflow.effective_to ? ` to ${fmtDate(workflow.effective_to)}` : ""}. ${workflow.qualifying_flight.payment_card_dependency === "independent" ? "The flight card may be different from the card with this benefit." : "Check whether the purchase card is part of the conditions."}`, "quiet-copy"));
  card.append(node("p", workflowScopeText(workflow.destination_scope)));
  if (candidate) {
    card.append(node("p", "This travel benefit is not ready to use. It cannot be selected or used to submit a claim.", "workflow-review-note"));
    return card;
  }
  const officialHref = safeHref(workflow.official_url);
  if (officialHref) {
    const link = node("a", "Open official terms");
    link.href = officialHref;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    card.append(link);
  }
  const details = node("details");
  details.append(node("summary", "See conditions and how to use"));
  const metadata = node("div", undefined, "workflow-metadata");
  const checklist = node("div");
  checklist.append(node("h4", "Evidence checklist"));
  checklist.append(workflowList(workflow.evidence_checklist.map(item => `${item.required ? "Required" : "Optional"}: ${item.label}`)));
  metadata.append(checklist);
  const steps = node("div");
  steps.append(node("h4", "Claim steps"));
  steps.append(workflowList(workflow.claim_steps.map(step => `${step.order}. ${step.instruction} (${step.channel.replaceAll("_", " ")})`)));
  metadata.append(steps);
  metadata.append(node("p", `How to use: ${workflow.claim_channel.replaceAll("_", " ")}. Deadline: ${workflow.deadline.kind.replaceAll("_", " ")}${workflow.deadline.offset_days === null ? "" : ` · ${workflow.deadline.offset_days} days`}.`, "quiet-copy"));
  if (workflow.reminder_offsets.length) metadata.append(node("p", `Optional local reminder: ${workflow.reminder_offsets.map(item => `${item.days_before_deadline} days before`).join(", ")}.`, "quiet-copy"));
  metadata.append(node("p", `Exclusions: ${workflow.exclusions.join(" · ")}`, "quiet-copy"));
  details.append(metadata);
  card.append(details);
  return card;
}
function workflowList(items) {
  const list = node("ul", undefined, "evidence-list");
  for (const item of items) list.append(node("li", item));
  return list;
}
function renderWorkflowChoices() {
  const select = document.querySelector("#workflowChoice");
  const keep = state.selectedDestinationWorkflowId || "";
  clear(select);
  select.append(new Option("Choose a reviewed travel benefit", ""));
  for (const workflow of state.destinationWorkflows) select.append(new Option(workflow.title, workflow.id));
  if ([...select.options].some(option => option.value === keep)) select.value = keep;
  else state.selectedDestinationWorkflowId = null;
  document.querySelector("#workflowPlanSubmit").disabled = !select.value;
}
function selectedDestinationWorkflow() {
  return state.destinationWorkflows.find(item => item.id === state.selectedDestinationWorkflowId) || null;
}
function renderWorkflowChecklist() {
  const target = document.querySelector("#workflowChecklist");
  clear(target);
  const workflow = selectedDestinationWorkflow();
  if (!workflow) {
    target.append(node("p", "Choose a reviewed workflow to see its checklist.", "empty-state"));
    return;
  }
  target.append(node("p", "Tick only the bounded evidence items you have checked locally. No file or document is selected by this control.", "quiet-copy"));
  const list = node("div", undefined, "workflow-checklist-items");
  for (const item of workflow.evidence_checklist) {
    const label = node("label", undefined, "workflow-check");
    const checkbox = node("input");
    checkbox.type = "checkbox";
    checkbox.dataset.evidenceId = item.id;
    checkbox.className = "workflow-evidence-item";
    label.append(checkbox, `${item.required ? "Required" : "Optional"}: ${item.label}`);
    list.append(label);
  }
  target.append(list);
}
function readLocalWorkflowPlan() {
  return {
    workflow_id: state.selectedDestinationWorkflowId || "",
    departure_date: document.querySelector("#workflowDepartureDate").value || null,
    arrival_date: document.querySelector("#workflowArrivalDate").value || null,
    destination: document.querySelector("#workflowDestination").value.trim() || null,
    boarding_pass_available: document.querySelector("#workflowBoardingPass").checked,
    checked_evidence_ids: [...document.querySelectorAll(".workflow-evidence-item:checked")].map(item => item.dataset.evidenceId),
  };
}
function localIsoDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || "")) return null;
  const parsed = new Date(`${value}T00:00:00Z`);
  return Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== value ? null : parsed;
}
function addIsoDays(value, days) {
  const parsed = localIsoDate(value);
  if (!parsed) return null;
  parsed.setUTCDate(parsed.getUTCDate() + days);
  return parsed.toISOString().slice(0, 10);
}
function localWorkflowPlan(workflow, plan) {
  const reasons = [];
  if (!workflow || !plan.workflow_id || workflow.id !== plan.workflow_id) return { status: "suppressed", reasons: ["workflow_id_mismatch"], deadline: null, reminders: [] };
  if (workflow.publication_state !== "reviewed_active" || workflow.review_state !== "approved") reasons.push("workflow_not_approved");
  if (workflow.effective_state !== "active") reasons.push(`workflow_${workflow.effective_state === "expired" ? "expired" : workflow.effective_state === "future" ? "not_yet_effective" : "effective_dates_unknown"}`);
  const predicate = workflow.qualifying_flight;
  if (predicate.payment_card_dependency !== "independent") reasons.push("card_payment_dependency_not_independent");
  if (predicate.boarding_pass === "unknown" || predicate.departure_date === "unknown" || predicate.arrival_date === "unknown" || workflow.destination_scope.kind === "unknown" || workflow.claim_channel === "unknown" || workflow.deadline.kind === "unknown") reasons.push("workflow_terms_unknown");
  if (reasons.length) return { status: "suppressed", reasons, deadline: null, reminders: [] };
  const unknown = [];
  const incomplete = [];
  const departure = localIsoDate(plan.departure_date);
  const arrival = localIsoDate(plan.arrival_date);
  if (predicate.arrival_date === "required" && !arrival) unknown.push("arrival_date_unknown");
  if (predicate.departure_date === "required" && !departure) unknown.push("departure_date_unknown");
  if (predicate.boarding_pass === "required" && !plan.boarding_pass_available) incomplete.push("boarding_pass_not_marked_available");
  if (workflow.destination_scope.kind !== "any") {
    if (!plan.destination) unknown.push("destination_unknown");
    else if (!workflow.destination_scope.values.some(value => value.toLocaleLowerCase() === plan.destination.toLocaleLowerCase())) incomplete.push("destination_outside_scope");
  }
  const expected = workflow.evidence_checklist.filter(item => item.required).map(item => item.id);
  const knownIds = new Set(workflow.evidence_checklist.map(item => item.id));
  if (plan.checked_evidence_ids.some(id => !knownIds.has(id))) unknown.push("checklist_item_unknown");
  else if (!expected.every(id => plan.checked_evidence_ids.includes(id))) incomplete.push("evidence_checklist_incomplete");
  const flightDate = arrival || departure;
  if (flightDate && workflow.effective_from && workflow.effective_to && (flightDate < workflow.effective_from || flightDate > workflow.effective_to)) incomplete.push("flight_outside_effective_dates");
  let deadline = null;
  if (workflow.deadline.kind === "days_after_arrival") deadline = arrival ? addIsoDays(plan.arrival_date, workflow.deadline.offset_days) : null;
  else if (workflow.deadline.kind === "days_after_departure") deadline = departure ? addIsoDays(plan.departure_date, workflow.deadline.offset_days) : null;
  if (!deadline) unknown.push("deadline_anchor_unknown");
  const reminders = deadline ? workflow.reminder_offsets.map(item => addIsoDays(deadline, -item.days_before_deadline)).filter(Boolean).sort() : [];
  if (unknown.length) return { status: "unknown", reasons: unknown, deadline, reminders };
  if (incomplete.length) return { status: "incomplete", reasons: incomplete, deadline, reminders };
  return { status: "ready", reasons: [], deadline, reminders };
}
function renderWorkflowPlanResult(result) {
  const target = document.querySelector("#workflowPlanResult");
  const reminderButton = document.querySelector("#workflowReminderButton");
  clear(target);
  reminderButton.disabled = !(result && result.status === "ready" && result.reminders?.length);
  if (!result) {
    target.append(node("p", "No local plan has been checked.", "empty-state"));
    return;
  }
  const card = node("article", undefined, "catalog-card workflow-plan-result");
  const heading = node("h4", `Local readiness: ${result.status.replaceAll("_", " ")}`);
  card.append(heading, node("p", "This is a local checklist result, not an eligibility decision or a claim submission.", "quiet-copy"));
  if (result.reasons.length) card.append(node("p", `Reason: ${result.reasons.join(" · ")}`, "workflow-review-note"));
  if (result.deadline) card.append(node("p", `Calculated deadline: ${fmtDate(result.deadline)}.`, "allowance"));
  if (result.reminders.length) card.append(node("p", `Reminder dates: ${result.reminders.map(fmtDate).join(", ")}. The reminder is not created until you explicitly download it.`, "quiet-copy"));
  target.append(card);
}
function resetWorkflowPlan() {
  document.querySelector("#workflowPlanForm").reset();
  state.selectedDestinationWorkflowId = null;
  state.destinationPlanResult = null;
  renderWorkflowChoices();
  renderWorkflowChecklist();
  renderWorkflowPlanResult(null);
  document.querySelector("#workflowPlanStatus").textContent = "Local worksheet cleared — nothing was saved or sent.";
}
function downloadWorkflowReminder() {
  const result = state.destinationPlanResult;
  const workflow = selectedDestinationWorkflow();
  const reminderDate = result?.reminders?.[0] || result?.deadline;
  if (!workflow || result?.status !== "ready" || !reminderDate) return;
  const day = reminderDate.replaceAll("-", "");
  const nextDay = (addIsoDays(reminderDate, 1) || reminderDate).replaceAll("-", "");
  const escapeIcs = value => String(value).replaceAll("\\", "\\\\").replaceAll(";", "\\;").replaceAll(",", "\\,").replaceAll("\n", "\\n");
  const stamp = new Date().toISOString().replaceAll(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
  const ics = [
    "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//MyCard Benefits//Local workflow//EN", "BEGIN:VEVENT",
    `UID:${escapeIcs(workflow.id)}-${day}@mycard-benefits.invalid`, `DTSTAMP:${stamp}`, `DTSTART;VALUE=DATE:${day}`, `DTEND;VALUE=DATE:${nextDay}`,
    `SUMMARY:${escapeIcs(`MyCard local reminder: ${workflow.title}`)}`, "DESCRIPTION:Local-only reminder. No boarding pass was uploaded and no claim was submitted.",
    "END:VEVENT", "END:VCALENDAR", "",
  ].join("\r\n");
  const url = URL.createObjectURL(new Blob([ics], { type: "text/calendar;charset=utf-8" }));
  const link = node("a");
  link.href = url; link.download = "mycard-local-workflow-reminder.ics"; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
  document.querySelector("#workflowPlanStatus").textContent = "Local reminder downloaded after your explicit action; nothing was uploaded or sent.";
}
function renderDestinationWorkflows(data) {
  if (Array.isArray(data.workflows)) state.destinationWorkflows = data.workflows;
  const list = document.querySelector("#workflowList");
  clear(list);
  for (const workflow of state.destinationWorkflows) list.append(workflowCard(workflow));
  state.destinationCandidates = [];
  if (!state.destinationWorkflows.length) list.append(node("p", "No reviewed travel benefit is ready yet. Find a benefit or check back after the public catalog is updated.", "empty-state"));
  const activeText = `${state.destinationWorkflows.length} reviewed travel benefit${state.destinationWorkflows.length === 1 ? "" : "s"}`;
  setWorkflowStatus(`${activeText}. Unreviewed records are never used for readiness.`, state.destinationWorkflows.length ? "ready" : "");
  const badge = document.querySelector("#workflowBadge");
  badge.textContent = state.destinationWorkflows.length ? `${state.destinationWorkflows.length} reviewed` : "No reviewed travel benefit";
  badge.className = state.destinationWorkflows.length ? "badge active" : "badge pending";
  renderWorkflowChoices();
  renderWorkflowChecklist();
  updateTravelAvailability();
}
async function loadDestinationWorkflows() {
  try {
    const response = await fetch("/api/v1/catalog/destination-workflows", { headers: { Accept: "application/json" }, cache: "no-store" });
    if (!response.ok) throw new Error("workflow metadata unavailable");
    renderDestinationWorkflows(await response.json());
  } catch {
    state.destinationWorkflows = [];
    state.destinationCandidates = [];
    const list = document.querySelector("#workflowList");
    clear(list); list.append(node("p", "Travel benefit details are unavailable; no local fallback or claim action is offered.", "empty-state"));
    setWorkflowStatus("Travel benefit details unavailable.", "error");
    const badge = document.querySelector("#workflowBadge"); badge.textContent = "Unavailable"; badge.className = "badge error";
    renderWorkflowChoices(); renderWorkflowChecklist();
    updateTravelAvailability();
  }
}
function initDestinationWorkflow() {
  document.querySelector("#workflowChoice").addEventListener("change", event => {
    state.selectedDestinationWorkflowId = event.target.value || null;
    state.destinationPlanResult = null;
    renderWorkflowChecklist(); renderWorkflowPlanResult(null);
    document.querySelector("#workflowPlanSubmit").disabled = !state.selectedDestinationWorkflowId;
  });
  document.querySelector("#workflowPlanForm").addEventListener("submit", event => {
    event.preventDefault();
    const workflow = selectedDestinationWorkflow();
    if (!workflow) {
      document.querySelector("#workflowPlanStatus").textContent = "Choose a reviewed travel benefit before checking local readiness.";
      return;
    }
    state.destinationPlanResult = localWorkflowPlan(workflow, readLocalWorkflowPlan());
    renderWorkflowPlanResult(state.destinationPlanResult);
    document.querySelector("#workflowPlanStatus").textContent = "Local readiness checked. This does not prove eligibility and nothing was sent.";
  });
  document.querySelector("#workflowPlanReset").addEventListener("click", resetWorkflowPlan);
  document.querySelector("#workflowReminderButton").addEventListener("click", downloadWorkflowReminder);
  renderWorkflowPlanResult(null);
}

async function boot() {
  try {
    const [offerings, benefits] = await Promise.all([getCatalog("offerings"), getCatalog("benefits")]);
    state.offerings = offerings; state.benefits = benefits;
    renderOfferings(); renderBenefits();
    if (state.privateCardsAvailable) renderPrivateCards();
    if (document.querySelector("#compareA") && document.querySelector("#compareB")) renderComparison();
    setCatalogState(`${offerings.length} offering${offerings.length === 1 ? "" : "s"} · public catalog ready`, "ready");
  } catch (error) {
    setCatalogState("Catalog unavailable — no private fallback", "error");
    for (const target of [document.querySelector("#offeringPreview"), document.querySelector("#benefitList"), document.querySelector("#searchResults")]) {
      if (target) { clear(target); target.append(node("p", "Public catalog data is unavailable. Try again after a reviewed catalog is installed.", "empty-state")); }
    }
    const catalogEmpty = document.querySelector("#benefitCatalogEmpty");
    if (catalogEmpty) catalogEmpty.hidden = true;
  }
  await runDiscovery();
}
const initialView = viewFromHash();
if (location.hash.slice(1) !== initialView) history.replaceState(null, "", `#${initialView}`);
showView(initialView);
boot();
