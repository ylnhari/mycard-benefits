const root = document.documentElement;
const themeKey = "mycard-benefits-theme";
const state = { offerings: [], benefits: [], privateCards: [] };
const views = new Set([...document.querySelectorAll("[data-panel]")].map(panel => panel.id));

function setTheme(theme) {
  root.dataset.theme = theme;
  localStorage.setItem(themeKey, theme);
  const label = theme === "dark" ? "Use light theme" : "Use dark theme";
  for (const button of document.querySelectorAll("#themeToggle, #themeToggleInline")) {
    button.textContent = label;
    button.setAttribute("aria-pressed", String(theme === "dark"));
  }
}
const stored = localStorage.getItem(themeKey);
setTheme(stored === "light" || stored === "dark" ? stored : "dark");
for (const button of document.querySelectorAll("#themeToggle, #themeToggleInline")) {
  button.addEventListener("click", () => setTheme(root.dataset.theme === "light" ? "dark" : "light"));
}

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}
function clear(element) { element.replaceChildren(); }
function fmtDate(value) { return value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(new Date(`${value}T00:00:00`)) : "Not specified"; }
function safeHref(value) {
  try { const url = new URL(value); return ["http:", "https:"].includes(url.protocol) ? url.href : null; }
  catch { return null; }
}
function viewFromHash() {
  try {
    const requested = decodeURIComponent(location.hash.slice(1));
    return views.has(requested) ? requested : "overview";
  } catch { return "overview"; }
}
function showView(view, { focus = false } = {}) {
  const destination = views.has(view) ? view : "overview";
  for (const panel of document.querySelectorAll("[data-panel]")) panel.hidden = panel.id !== destination;
  for (const link of document.querySelectorAll("[data-view]")) {
    const active = link.dataset.view === destination;
    link.classList.toggle("active", active);
    if (active) link.setAttribute("aria-current", "page"); else link.removeAttribute("aria-current");
  }
  if (focus) {
    const heading = document.querySelector(`#${destination} h2`);
    if (heading) {
      heading.setAttribute("tabindex", "-1");
      heading.focus({ preventScroll: true });
    }
  }
}
for (const link of document.querySelectorAll("[data-view], [data-go]")) link.addEventListener("click", event => {
  const view = event.currentTarget.dataset.view || event.currentTarget.dataset.go;
  if (!view) return;
  event.preventDefault();
  history.replaceState(null, "", `#${view}`);
  showView(view, { focus: true });
});
window.addEventListener("hashchange", () => {
  const view = viewFromHash();
  if (location.hash.slice(1) !== view) history.replaceState(null, "", `#${view}`);
  showView(view, { focus: true });
});

async function getCatalog(path) {
  const response = await fetch(`/api/v1/catalog/${path}`, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(response.status === 503 ? "Catalog unavailable" : "Catalog request failed");
  return response.json();
}
function setCatalogState(message, kind) {
  const target = document.querySelector("#catalogState");
  target.textContent = message;
  target.className = `catalog-state${kind ? ` ${kind}` : ""}`;
}
function offeringCard(offering) {
  const card = node("article", undefined, "catalog-card");
  card.append(node("p", `${offering.issuer_id} · ${offering.network_id.toUpperCase()}`, "eyebrow"), node("h3", offering.display_name), node("p", `Market ${offering.market} · effective ${fmtDate(offering.effective_from)}`));
  return card;
}
function renderOfferings() {
  document.querySelector("#offeringCount").textContent = String(state.offerings.length);
  const preview = document.querySelector("#offeringPreview"); clear(preview);
  const query = document.querySelector("#offeringSearch").value.trim().toLocaleLowerCase();
  const filtered = state.offerings.filter(offering => [offering.display_name, offering.issuer_id, offering.network_id, offering.slug].some(value => value.toLocaleLowerCase().includes(query)));
  document.querySelector("#offeringSearchStatus").textContent = query ? `${filtered.length} matching card variant${filtered.length === 1 ? "" : "s"}` : `${state.offerings.length} card variants available`;
  if (!filtered.length) preview.append(node("p", "No card variant matches that search.", "empty-state"));
  for (const offering of filtered) preview.append(offeringCard(offering));
  for (const select of document.querySelectorAll("#benefitOffering, #compareA, #compareB")) {
    const keep = select.value; clear(select);
    if (select.id === "benefitOffering") select.append(new Option("All offerings", ""));
    for (const offering of state.offerings) select.append(new Option(offering.display_name, offering.slug));
    if ([...select.options].some(option => option.value === keep)) select.value = keep;
  }
}
document.querySelector("#offeringSearch").addEventListener("input", renderOfferings);
function evidenceLine(evidence) {
  const line = node("li");
  line.append(node("span", `${evidence.source_policy_class.replaceAll("_", " ")} · ${evidence.review_state} · ${evidence.confidence} confidence`));
  const href = safeHref(evidence.source_url);
  if (href) { const link = node("a", "Open source"); link.href = href; link.target = "_blank"; link.rel = "noopener noreferrer"; line.append(" ", link); }
  return line;
}
function benefitCard(benefit) {
  const card = node("article", undefined, "benefit-card");
  const head = node("div", undefined, "card-title"); head.append(node("div", undefined));
  head.firstChild.append(node("p", benefit.benefit_type.replaceAll("_", " "), "eyebrow"), node("h3", benefit.title));
  head.append(node("span", benefit.status, "badge active")); card.append(head);
  card.append(node("p", `Effective ${fmtDate(benefit.effective_from)} · review tier: ${benefit.review_tier}`));
  if (benefit.allowance) card.append(node("p", `Allowance: ${benefit.allowance.cap ?? "—"} ${benefit.allowance.unit || ""} per ${benefit.allowance.period || "period"}`, "allowance"));
  const details = node("details"); details.append(node("summary", `Evidence (${benefit.evidence.length})`)); const list = node("ul", undefined, "evidence-list"); for (const evidence of benefit.evidence) list.append(evidenceLine(evidence)); details.append(list); card.append(details);
  return card;
}
function renderBenefits() {
  document.querySelector("#benefitCount").textContent = String(state.benefits.length);
  const selected = document.querySelector("#benefitOffering").value;
  const offering = state.offerings.find(item => item.slug === selected);
  const benefits = offering ? state.benefits.filter(item => item.offering_id === offering.id) : state.benefits;
  const list = document.querySelector("#benefitList"); clear(list);
  document.querySelector("#benefitEmpty").hidden = benefits.length > 0;
  for (const benefit of benefits) list.append(benefitCard(benefit));
}
function renderSources() {
  const list = document.querySelector("#sourceList"); clear(list);
  const evidence = state.benefits.flatMap(benefit => benefit.evidence.map(item => ({ ...item, title: benefit.title })));
  if (!evidence.length) list.append(node("p", "No reviewed evidence is available.", "empty-state"));
  for (const item of evidence) { const card = node("article", undefined, "source-card"); card.append(node("p", item.title, "eyebrow"), node("h3", item.source_policy_class.replaceAll("_", " ")), node("p", `Retrieved ${fmtDate(item.retrieved_at.slice(0, 10))} · ${item.approved_review_count} approval(s) · ${item.confidence} confidence`)); const href = safeHref(item.source_url); if (href) { const link = node("a", "Open source"); link.href = href; link.target = "_blank"; link.rel = "noopener noreferrer"; card.append(link); } list.append(card); }
}
function renderComparison() {
  const target = document.querySelector("#comparison"); clear(target);
  const a = state.offerings.find(item => item.slug === document.querySelector("#compareA").value);
  const b = state.offerings.find(item => item.slug === document.querySelector("#compareB").value);
  if (!a || !b) { target.append(node("p", "Choose two public offerings to compare.", "empty-state")); return; }
  for (const offering of [a, b]) { const card = offeringCard(offering); const count = state.benefits.filter(item => item.offering_id === offering.id).length; card.append(node("p", `${count} active catalog benefit${count === 1 ? "" : "s"}`, "allowance")); target.append(card); }
}
document.querySelector("#benefitOffering").addEventListener("change", renderBenefits);
for (const select of document.querySelectorAll("#compareA, #compareB")) select.addEventListener("change", renderComparison);

const UNMATCHED_CARD_LABEL = "Unmatched card variant";
function offeringForCard(card) {
  return state.offerings.find(candidate => candidate.slug === card.offering_id);
}
function cardSearchText(card, offering) {
  return [offering?.display_name, offering?.issuer_id, offering?.network_id, offering?.slug, card.lifecycle, card.offering_id, card.card_id].filter(Boolean).join(" ").toLocaleLowerCase();
}
function privateCardBadge(lifecycle) {
  if (lifecycle === "active") return "badge active";
  if (["lost", "stolen"].includes(lifecycle)) return "badge error";
  return "badge pending";
}
function privateCardDates(card) {
  const created = fmtDate((card.created_at || "").slice(0, 10));
  const updated = fmtDate((card.updated_at || "").slice(0, 10));
  return `Added ${created} · updated ${updated}`;
}
function detailRow(label, value) {
  const row = node("div", undefined, "card-detail-row");
  row.append(node("dt", label), node("dd", value));
  return row;
}
function replacementText(card) {
  if (!card.replacement_card_id || card.replacement_card_id === card.card_id) return null;
  const replaced = state.privateCards.find(candidate => candidate.card_id === card.replacement_card_id);
  if (!replaced) return "Replaced by a card not listed in this vault.";
  const offering = offeringForCard(replaced);
  return `Replaced by ${offering ? offering.display_name : UNMATCHED_CARD_LABEL}`;
}
function replacementOfText(card) {
  const predecessor = state.privateCards.find(candidate => candidate.replacement_card_id === card.card_id);
  if (!predecessor) return null;
  const offering = offeringForCard(predecessor);
  return `This card replaced ${offering ? offering.display_name : "an earlier card record"}`;
}
function cardDetailSection(card, index) {
  const offering = offeringForCard(card);
  const section = node("div", undefined, "card-detail");
  section.id = `card-detail-${index}`;
  section.hidden = true;
  const heading = node("h4", "Card details", "card-detail-title");
  heading.tabIndex = -1;
  const list = node("dl", undefined, "card-detail-list");
  if (offering) {
    list.append(detailRow("Product", offering.display_name));
    list.append(detailRow("Issuer", offering.issuer_id));
    list.append(detailRow("Network", offering.network_id.replaceAll("-", " ").toUpperCase()));
  } else {
    list.append(detailRow("Product", "Not matched in the public catalog"));
  }
  list.append(detailRow("Lifecycle", card.lifecycle));
  list.append(detailRow("Added", fmtDate((card.created_at || "").slice(0, 10))));
  list.append(detailRow("Updated", fmtDate((card.updated_at || "").slice(0, 10))));
  const replaced = replacementText(card);
  if (replaced) list.append(detailRow("Replacement", replaced));
  const replaces = replacementOfText(card);
  if (replaces) list.append(detailRow("Replaces", replaces));
  section.append(heading, list);
  if (!offering) section.append(node("p", "This card's product identifier has no match in the public catalog. Fix the identifier in the import file or request the card variant; its product name will appear once the match succeeds.", "unmatched-note"));
  return section;
}
function toggleCardDetail(button, section, heading) {
  const opening = section.hidden;
  section.hidden = !opening;
  button.setAttribute("aria-expanded", String(opening));
  button.textContent = opening ? "Hide details" : "View details";
  if (opening) heading.focus({ preventScroll: true });
}
function privateCardRow(card, index) {
  const offering = offeringForCard(card);
  const item = node("article", undefined, "catalog-card private-card");
  const head = node("div", undefined, "card-title");
  const title = node("div");
  const matched = Boolean(offering);
  title.append(node("p", matched ? `${offering.issuer_id} · ${offering.network_id.replaceAll("-", " ").toUpperCase()}` : "Not matched in the public catalog", "eyebrow"), node("h3", matched ? offering.display_name : UNMATCHED_CARD_LABEL));
  head.append(title, node("span", card.lifecycle, privateCardBadge(card.lifecycle)));
  item.append(head);
  item.append(node("p", privateCardDates(card), "quiet-copy"));
  if (!matched) item.append(node("p", "This card's product identifier has no match in the public catalog. Its product name will appear once the identifier matches or the card variant is added.", "unmatched-note"));
  if (card.replacement_card_id) item.append(node("p", "Replacement history is linked.", "allowance"));
  const section = cardDetailSection(card, index);
  const button = node("button", "View details", "secondary card-detail-toggle");
  button.type = "button";
  button.setAttribute("aria-expanded", "false");
  button.setAttribute("aria-controls", section.id);
  button.setAttribute("aria-label", `View details for ${matched ? offering.display_name : "unmatched card"}`);
  button.addEventListener("click", () => toggleCardDetail(button, section, section.querySelector("h4")));
  section.addEventListener("keydown", event => {
    if (event.key === "Escape") {
      event.preventDefault();
      section.hidden = true;
      button.setAttribute("aria-expanded", "false");
      button.textContent = "View details";
      button.focus();
    }
  });
  item.append(button, section);
  return item;
}
function renderPrivateCards() {
  const lifecycle = document.querySelector("#cardLifecycle").value;
  const query = document.querySelector("#myCardSearch").value.trim().toLocaleLowerCase();
  const cards = state.privateCards.filter(card => {
    if (lifecycle && card.lifecycle !== lifecycle) return false;
    if (query && !cardSearchText(card, offeringForCard(card)).includes(query)) return false;
    return true;
  });
  const target = document.querySelector("#myCardList"); clear(target);
  if (!state.privateCards.length) {
    target.append(node("p", "No card records are in this vault yet. Import cards with the mycard-vault command line, then return here to see them listed.", "empty-state"));
    return;
  }
  if (!cards.length) {
    target.append(node("p", "No cards match the current search and lifecycle filter. Clear the search or choose a different status.", "empty-state"));
    return;
  }
  cards.forEach((card, index) => target.append(privateCardRow(card, index)));
}
function setPrivateAccess(title, text, badge, status) {
  document.querySelector("#vaultSummaryTitle").textContent = title;
  document.querySelector("#vaultSummaryText").textContent = text;
  document.querySelector("#myCardsBadge").textContent = badge;
  document.querySelector("#myCardStatus").textContent = status;
}
function setPrivateUnavailable(title, text, badge, status) {
  setPrivateAccess(title, text, badge, status);
  const target = document.querySelector("#myCardList"); clear(target);
  target.append(node("p", "The private vault could not be opened, so no card list can be shown. Make sure the app is not in demo mode, the vault exists, and it can be unlocked through the operating-system keyring.", "empty-state"));
}
async function loadPrivateCards() {
  try {
    const response = await fetch("/api/v1/private/cards", { headers: { Accept: "application/json" }, credentials: "same-origin", cache: "no-store" });
    if (!response.ok) throw new Error("unavailable");
    const payload = await response.json();
    state.privateCards = Array.isArray(payload.cards) ? payload.cards : [];
    const active = payload.lifecycle_counts?.active || 0;
    document.querySelector("#myCardCount").textContent = String(state.privateCards.length);
    document.querySelector("#myCardCountNote").textContent = `${active} active · encrypted locally`;
    setPrivateAccess("Private card list ready", `${state.privateCards.length} card records are mapped to the public catalog. Secret fields remain encrypted and are not returned.`, "Local vault available", `${state.privateCards.length} cards loaded; ${active} active.`);
    const lifecycleSelect = document.querySelector("#cardLifecycle");
    for (const lifecycle of Object.keys(payload.lifecycle_counts || {})) lifecycleSelect.append(new Option(`${lifecycle} (${payload.lifecycle_counts[lifecycle]})`, lifecycle));
    renderPrivateCards();
  } catch {
    setPrivateUnavailable("Private vault unavailable", "The public catalog still works. Check that the app is not in demo mode, that the vault exists, and that it can be unlocked through the OS keyring before retrying.", "Unavailable", "Private card list could not be opened; no fallback data was used.");
    document.querySelector("#myCardCount").textContent = "—";
    document.querySelector("#myCardCountNote").textContent = "Vault unavailable";
  }
}
document.querySelector("#cardLifecycle").addEventListener("change", renderPrivateCards);
document.querySelector("#myCardSearch").addEventListener("input", renderPrivateCards);

function setQaStatus(message, kind) {
  const target = document.querySelector("#qaStatus");
  target.textContent = message;
  target.className = `qa-status${kind ? ` ${kind}` : ""}`;
}
function qaLink(url, label = "Open evidence") {
  const href = safeHref(url);
  if (!href) return null;
  const link = node("a", label);
  link.href = href;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  return link;
}
function qaFactCard(fact) {
  const card = node("article", undefined, "benefit-card");
  const benefit = fact.benefit || {};
  const offering = fact.offering || {};
  card.append(node("p", offering.display_name || offering.slug || "Public offering", "eyebrow"));
  card.append(node("h4", benefit.title || benefit.type || "Catalog benefit"));
  const evidence = Array.isArray(fact.evidence) ? fact.evidence : [];
  const list = node("ul", undefined, "evidence-list");
  for (const item of evidence) {
    const line = node("li", `${item.source_class || "evidence"} · ${item.confidence || "confidence not specified"}`);
    const link = qaLink(item.url);
    if (link) line.append(" ", link);
    list.append(line);
  }
  if (evidence.length) card.append(list);
  return card;
}
function supportedSuggestion(text) {
  const first = state.offerings[0];
  if (text.startsWith("benefits") && first) return `benefits for ${first.slug}`;
  if (text.startsWith("benefit") && first) return `benefit reward points for ${first.slug}`;
  if (text.startsWith("offerings")) return "offerings for reward points";
  if (text.startsWith("compare") && state.offerings.length > 1) return `compare ${state.offerings[0].slug} and ${state.offerings[1].slug}`;
  return "offerings for reward points";
}
function qaButton(label, query) {
  const button = node("button", label, "secondary");
  button.type = "button";
  button.addEventListener("click", () => submitQuestion(query));
  return button;
}
function renderQaResult(result) {
  const target = document.querySelector("#qaResults"); clear(target);
  const heading = node("h3", result.intent === "no_result" ? "No matching verified benefit" : "Catalog answer");
  heading.tabIndex = -1;
  target.append(heading);
  if (result.message) target.append(node("p", result.message));
  if (result.offering) target.append(node("p", result.offering.display_name || result.offering.slug, "eyebrow"));
  if (Array.isArray(result.benefits)) for (const fact of result.benefits) target.append(qaFactCard(fact));
  if (Array.isArray(result.offerings)) for (const item of result.offerings) {
    const card = node("article", undefined, "catalog-card");
    const offering = item.offering || item;
    card.append(node("h4", offering.display_name || offering.slug || "Public offering"));
    for (const fact of item.benefits || []) card.append(qaFactCard(fact));
    target.append(card);
  }
  if (Array.isArray(result.choices) && result.choices.length) {
    const choices = node("div", undefined, "qa-actions");
    choices.append(node("p", "Choose one public offering:"));
    for (const choice of result.choices) choices.append(qaButton(choice.display_name || choice.slug, `benefits for ${choice.slug}`));
    target.append(choices);
  }
  if (Array.isArray(result.suggestions) && result.suggestions.length) {
    const suggestions = node("div", undefined, "qa-actions");
    suggestions.append(node("p", "Try a supported question:"));
    for (const suggestion of result.suggestions) suggestions.append(qaButton(suggestion, supportedSuggestion(suggestion)));
    target.append(suggestions);
  }
  heading.focus({ preventScroll: true });
}
async function submitQuestion(query) {
  const input = document.querySelector("#qaQuery");
  const submit = document.querySelector("#qaSubmit");
  const form = document.querySelector("#qaForm");
  const value = typeof query === "string" ? query : input.value;
  if (!value.trim() || value.length > 500) { setQaStatus("Enter a question of up to 500 characters.", "error"); input.focus(); return; }
  input.value = value;
  submit.disabled = true;
  form.setAttribute("aria-busy", "true");
  setQaStatus("Asking the public catalog…", "loading");
  try {
    const response = await fetch("/api/v1/qa", { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify({ query: value }) });
    if (response.status === 503) throw new Error("catalog");
    if (response.status === 422) throw new Error("invalid");
    if (!response.ok) throw new Error("network");
    renderQaResult(await response.json());
    setQaStatus("Catalog answer ready.", "ready");
  } catch (error) {
    clear(document.querySelector("#qaResults"));
    setQaStatus(error.message === "catalog" ? "Public catalog unavailable — no private fallback is used." : "Unable to answer that question. Try a supported public catalog question.", "error");
  } finally {
    submit.disabled = false;
    form.removeAttribute("aria-busy");
  }
}
document.querySelector("#qaForm").addEventListener("submit", event => { event.preventDefault(); submitQuestion(); });
document.querySelector("#qaQuery").addEventListener("keydown", event => {
  if (event.key === "Enter" && !event.isComposing) {
    event.preventDefault();
    submitQuestion();
    return;
  }
  if (event.key === "Escape") {
    event.preventDefault();
    document.querySelector("#qaQuery").value = "";
    clear(document.querySelector("#qaResults"));
    setQaStatus("Question cleared.");
  }
});
document.querySelector("#qaReset").addEventListener("click", () => {
  document.querySelector("#qaQuery").value = "";
  clear(document.querySelector("#qaResults"));
  setQaStatus("Question cleared.");
  document.querySelector("#qaQuery").focus();
});
for (const button of document.querySelectorAll("[data-qa-example]")) button.addEventListener("click", () => submitQuestion(button.dataset.qaExample));

async function boot() {
  try {
    const [offerings, benefits] = await Promise.all([getCatalog("offerings"), getCatalog("benefits")]);
    state.offerings = offerings; state.benefits = benefits;
    renderOfferings(); renderBenefits(); renderSources(); renderComparison();
    setCatalogState(`${offerings.length} offering${offerings.length === 1 ? "" : "s"} · public catalog ready`, "ready");
  } catch (error) {
    setCatalogState("Catalog unavailable — no private fallback", "error");
    for (const target of [document.querySelector("#offeringPreview"), document.querySelector("#benefitList"), document.querySelector("#sourceList"), document.querySelector("#comparison")]) { clear(target); target.append(node("p", "Public catalog data is unavailable. Try again after a reviewed catalog is installed.", "empty-state")); }
    document.querySelector("#benefitEmpty").hidden = true;
  }
  await loadPrivateCards();
}
const initialView = viewFromHash();
if (location.hash.slice(1) !== initialView) history.replaceState(null, "", `#${initialView}`);
showView(initialView);
boot();
