"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const appPath = process.argv[2];
assert.ok(appPath, "Expected the served app.js path");
const appSource = fs.readFileSync(appPath, "utf8");

function sourceBetween(startMarker, endMarker) {
  const start = appSource.indexOf(startMarker);
  const end = appSource.indexOf(endMarker, start);
  assert.notEqual(start, -1, `Missing start marker: ${startMarker}`);
  assert.notEqual(end, -1, `Missing end marker: ${endMarker}`);
  return appSource.slice(start, end);
}

function domElement(overrides = {}) {
  return {
    children: [],
    hidden: false,
    textContent: "",
    append(...children) { this.children.push(...children); },
    addEventListener() {},
    ...overrides,
  };
}

const elements = new Map([
  ["#myCardList", domElement()],
  ["#myCardCount", domElement()],
  ["#myCardCountNote", domElement()],
  ["#cardLifecycle", domElement()],
  ["#compareA", domElement({ value: "" })],
  ["#compareB", domElement({ value: "" })],
  ["#cardAddPan", domElement({ value: "" })],
  ["#cardAddExpiryMonth", domElement({ value: "" })],
  ["#cardAddExpiryYear", domElement({ value: "" })],
  ["#cardAddCvv", domElement({ value: "" })],
  ["#cardAddPin", domElement({ value: "" })],
  ["#cardAddNickname", domElement({ value: "" })],
  ["#cardAddLastFour", domElement({ value: "" })],
  ["#familyFinanceApplyForm", domElement({ reset() { this.resetCalled = true; } })],
  ["#familyFinancePreview", domElement()],
  ["#familyFinanceImportStatus", domElement()],
]);

class SyntheticOption {
  constructor(text, value) {
    this.text = text;
    this.value = value;
  }
}

const context = {
  Option: SyntheticOption,
  clear(target) { target.children = []; },
  clearSecretErasePrompt() {},
  document: {
    querySelector(selector) {
      const element = elements.get(selector);
      assert.ok(element, `Unexpected selector: ${selector}`);
      return element;
    },
  },
  fetch: async () => { throw new Error("Fetch response not configured"); },
  loadOwnedDiscovery: async () => {},
  loadExpirySignals: async () => {},
  loadPrivateState: async () => {},
  node(tag, text, className) {
    return domElement({ tag, text, className });
  },
  refreshCardFilters() {},
  refreshProtectedActionOptions() {},
  renderBenefits() {},
  renderComparison() {},
  renderPrivateCards() {},
  ensureCompareSelections() {},
  setPersonalStateAvailability() {},
  setPrivateAccess() {},
  setProtectedActionAvailability() {},
  state: {
    ownedDiscoveryAvailable: false,
    ownedDiscoveryCards: [],
    personalStateAvailable: false,
    privateAggregates: [],
    privateAttempts: [],
    privateCards: [],
    privateCardsAvailable: false,
    privateStateRevision: null,
    compareDefaultsApplied: false,
  },
};

vm.createContext(context);
vm.runInContext(
  [
    sourceBetween("const VAULT_DIAGNOSTICS = {", "function setPrivateAccess"),
    sourceBetween("function setPrivateUnavailable", "async function loadOwnedDiscovery"),
    sourceBetween("async function loadPrivateCards()", "\nfunction setPersonalStateAvailability"),
    sourceBetween("function secretFieldsFrom", "async function protectedJson"),
    "this.loadPrivateCardsForTest = loadPrivateCards;",
    "this.secretFieldsFromForTest = secretFieldsFrom;",
  ].join("\n"),
  context,
);

function runProductOnlyAddPayloadCheck() {
  const fields = context.secretFieldsFromForTest("cardAdd", { includeNickname: true, includeLastFour: true });
  assert.equal(JSON.stringify(fields), "{}", "empty optional fields must be omitted from a product-only add");
  elements.get("#cardAddLastFour").value = "1234";
  assert.equal(
    JSON.stringify(context.secretFieldsFromForTest("cardAdd", { includeNickname: true, includeLastFour: true })),
    JSON.stringify({ last_four: "1234" }),
    "last four must be retained only when entered",
  );
  elements.get("#cardAddLastFour").value = "";
}

async function runAuthenticatedReloadSuccess() {
  context.fetch = async (url, options) => {
    assert.equal(url, "/api/v1/private/cards");
    assert.equal(options.credentials, "same-origin");
    assert.equal(options.cache, "no-store");
    assert.equal(options.headers.Accept, "application/json");
    return {
      ok: true,
      async json() {
        return {
          cards: [
            { card_id: "SYNTHETIC-ONLY-card-a", offering_id: "synthetic-example-in", lifecycle: "active" },
            { card_id: "SYNTHETIC-ONLY-card-b", offering_id: "synthetic-example-in", lifecycle: "active" },
          ],
          lifecycle_counts: { active: 2 },
        };
      },
    };
  };

  await context.loadPrivateCardsForTest();

  assert.equal(context.state.privateCardsAvailable, true, "device bootstrap reload must expose cards");
}

async function runUnavailable(code) {
  context.fetch = async () => ({
    ok: false,
    async json() {
      return { detail: { code, message: "Synthetic private-card failure" } };
    },
  });

  await context.loadPrivateCardsForTest();

  assert.equal(context.state.privateCardsAvailable, false, `${code} must not expose cards`);
  assert.ok(elements.get("#myCardList").children.length, `${code} must render a retry state`);
}

(async () => {
  runProductOnlyAddPayloadCheck();
  await runAuthenticatedReloadSuccess();
  await runUnavailable("locked");
  await runUnavailable("demo");
  await runUnavailable("generic");
  await runUnavailable("keyring_unavailable");
  await runUnavailable("passphrase_only");
})().catch(error => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
