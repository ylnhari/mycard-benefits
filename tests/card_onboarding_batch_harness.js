"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const appSource = fs.readFileSync(process.argv[2], "utf8");
const renderStart = appSource.indexOf("function renderCardOfferingChoices");
const renderEnd = appSource.indexOf("function beginAddCard", renderStart);
const start = appSource.indexOf("async function protectedJson");
const end = appSource.indexOf("async function submitPersonalState", start);
assert.notEqual(renderStart, -1, "Missing onboarding renderer");
assert.notEqual(renderEnd, -1, "Missing onboarding renderer boundary");
assert.notEqual(start, -1, "Missing protected request helper");
assert.notEqual(end, -1, "Missing onboarding boundary");

function element(overrides = {}) {
  return {
    children: [],
    hidden: false,
    textContent: "",
    dataset: {},
    append(...children) { this.children.push(...children); },
    replaceChildren(...children) { this.children = children; },
    setAttribute() {},
    addEventListener() {},
    focus() {},
    ...overrides,
  };
}

const submit = element({ disabled: false });
const form = element({
  querySelector(selector) {
    assert.equal(selector, "#cardAddSubmit");
    return submit;
  },
  reset() { this.resetCalled = true; },
});
const elements = new Map([
  ["#cardAddLastFourPrompt", element()],
  ["#cardAddLastFourFields", element()],
  ["#cardAddLastFourStatus", element()],
  ["#cardAddLastFourTitle", element()],
  ["#protectedActionStatus", element()],
  ["#cardAddLastFourSkip", element()],
]);
const state = {
  offerings: [1, 2, 3].map(index => ({
    id: `SYNTHETIC-ONLY-OFFERING-${index}`,
    display_name: `SYNTHETIC-ONLY Card ${index}`,
    issuer_id: index === 3 ? "SYNTHETIC-ONLY-ISSUER-B" : "SYNTHETIC-ONLY-ISSUER-A",
    network: "visa",
    tier: null,
    acceptance_marks: [],
    lounge_programme: null,
  })),
  privateCards: Array.from({ length: 18 }, (_, index) => ({ card_id: `SYNTHETIC-ONLY-EXISTING-${index}` })),
  privateCardsAvailable: true,
  cardAddSelection: new Set(),
  cardAddIssuers: new Set(),
  pendingLastFourCards: [],
};

const addCalls = [];
const issuerChips = element();
const productChoices = element();
const selectionStatus = element();
const advanced = element({ open: false, querySelectorAll() { return []; } });
const context = {
  clear(target) { target.replaceChildren(); },
  document: {
    querySelector(selector) {
      const found = elements.get(selector);
      if (selector === "#cardAddIssuerChips") return issuerChips;
      if (selector === "#cardAddOfferingChoices") return productChoices;
      if (selector === "#cardAddSelectionStatus") return selectionStatus;
      if (selector === "#cardAddSubmit") return submit;
      if (selector === "#cardAddAdvanced") return advanced;
      assert.ok(found, `Unexpected selector: ${selector}`);
      return found;
    },
  },
  fetch: async (url, options = {}) => {
    if (url === "/api/v1/private/csrf-token") {
      return { ok: true, async json() { return { csrf_token: "SYNTHETIC-ONLY-CSRF" }; } };
    }
    assert.equal(url, "/api/v1/private/cards/add");
    const payload = JSON.parse(options.body);
    assert.equal(Object.hasOwn(payload, "passphrase"), false, "onboarding must not send a credential");
    addCalls.push(payload);
    return {
      ok: true,
      async json() { return { card_id: `SYNTHETIC-ONLY-ADDED-${addCalls.length}` }; },
    };
  },
  loadPrivateCards: async () => {
    state.privateCards = Array.from({ length: 21 }, (_, index) => ({ card_id: `SYNTHETIC-ONLY-AFTER-${index}` }));
  },
  node(tag, text, className) { return element({ tag, text, className }); },
  humanIssuerLabel(value) { return value; },
  networkLabel(value) { return value; },
  offeringNetworkLabel(offering) { return offering?.network || null; },
  runDiscovery: async () => {},
  secretFieldsFrom() { return {}; },
  state,
};

vm.createContext(context);
vm.runInContext(
  `${appSource.slice(renderStart, renderEnd)}\n${appSource.slice(start, end)}\nthis.renderCardOfferingChoicesForTest = renderCardOfferingChoices;\nthis.submitCardBatchForTest = submitCardBatch;`,
  context,
);

(async () => {
  state.cardAddSelection = new Set(state.offerings.map(item => item.id));
  context.renderCardOfferingChoicesForTest();
  assert.equal(submit.textContent, "Add 3 cards", "three selected products must update the submit label");
  state.cardAddIssuers = new Set(["SYNTHETIC-ONLY-ISSUER-A"]);
  context.renderCardOfferingChoicesForTest();
  assert.equal(submit.textContent, "Add 3 cards", "issuer filtering must not drop selected products");
  await context.submitCardBatchForTest(form, [...state.cardAddSelection]);
  assert.equal(addCalls.length, 3, "one submit must add all three selected products");
  assert.equal(state.privateCards.length, 21, "three additions must coexist with eighteen existing cards");
  assert.equal(state.pendingLastFourCards.length, 3, "last-4 must be offered after the add");
  assert.equal(elements.get("#protectedActionStatus").textContent, "Added 3 cards. Add last 4s below if useful.");
  process.stdout.write("synthetic onboarding batch: Add 3 cards -> 18 existing + 3 added; no credential sent\n");
})().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
