"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const appPath = process.argv[2];
assert.ok(appPath, "Expected the app.js path");
const appSource = fs.readFileSync(appPath, "utf8");
function sourceBetween(startMarker, endMarker) {
  const start = appSource.indexOf(startMarker);
  const end = appSource.indexOf(endMarker, start);
  assert.notEqual(start, -1, `Missing start marker: ${startMarker}`);
  assert.notEqual(end, -1, `Missing end marker: ${endMarker}`);
  return appSource.slice(start, end);
}

const rendererSource = [
  sourceBetween("function node(tag, text, className)", "function clear"),
  sourceBetween("function clear", "function fmtDate"),
  sourceBetween("function fmtDate", "function safeHref"),
  sourceBetween("function safeHref", "function officialBenefitHref"),
  sourceBetween("function officialBenefitHref", "function allowanceCount"),
  sourceBetween("function allowanceCount", "function benefitHowToUse"),
  sourceBetween("function benefitHowToUse", "function viewFromHash"),
  sourceBetween("function provenanceChip", "function evidenceLine"),
  sourceBetween("function evidenceLine", "function benefitCard"),
  sourceBetween("function benefitDates", "function formatEligibility"),
  sourceBetween("function formatEligibility", "function detailList"),
  sourceBetween("function detailList", "function localBenefitMatch"),
  sourceBetween("function renderBenefitDetail", "function selectBenefit"),
].join("\n");

class SyntheticElement {
  constructor(tagName) {
    this.tagName = tagName;
    this.children = [];
    this.hidden = false;
    this._textContent = "";
  }

  set textContent(value) {
    this._textContent = value === undefined ? "" : String(value);
  }

  get textContent() {
    return this._textContent + this.children
      .map(child => typeof child === "string" ? child : child.textContent)
      .join("");
  }

  append(...children) {
    this.children.push(...children);
  }

  replaceChildren(...children) {
    this._textContent = "";
    this.children = [...children];
  }

  querySelector(selector) {
    if (selector === "a" && this.tagName === "a") return this;
    for (const child of this.children) {
      if (typeof child !== "string") {
        const match = child.querySelector(selector);
        if (match) return match;
      }
    }
    return null;
  }
}

function descendants(element) {
  return element.children.flatMap(child => (
    typeof child === "string" ? [] : [child, ...descendants(child)]
  ));
}

const benefitDetail = new SyntheticElement("section");
const context = {
  URL,
  document: {
    createElement: tagName => new SyntheticElement(tagName),
    querySelector: selector => {
      assert.equal(selector, "#benefitDetail");
      return benefitDetail;
    },
  },
  state: {},
};
vm.createContext(context);
vm.runInContext(
  `${rendererSource}\nthis.renderBenefitDetailForTest = renderBenefitDetail;\nthis.consumerAllowanceTextForTest = consumerAllowanceText;\nthis.consumerFieldLabelForTest = consumerFieldLabel;\nthis.friendlyPredicateForTest = friendlyPredicate;`,
  context,
);

const sourceUrl = "https://example.invalid/SYNTHETIC-ONLY-official-terms";
const claimRoute = "SYNTHETIC-ONLY approved claim route";
const benefit = {
  id: "SYNTHETIC-ONLY-benefit",
  offering_id: "SYNTHETIC-ONLY-offering",
  benefit_type: "lounge",
  title: "SYNTHETIC-ONLY lounge voucher",
  state: "verified",
  status: "active",
  rule_version: 1,
  effective_from: "2026-01-01",
  effective_to: null,
  end_date_known: false,
  category: "lounge",
  allowance: {
    unit: "SYNTHETIC-ONLY-voucher",
    count: 2,
    period: "SYNTHETIC-ONLY-quarter",
    claim_route: claimRoute,
  },
  redemption_steps: [],
  eligibility: [],
  exclusions: [],
  evidence: [
    { state: "check_before_use", source_policy_class: "issuer_document", source_url: "javascript:alert(1)" },
    { state: "verified", source_policy_class: "issuer_document", source_url: sourceUrl },
  ],
  official_reference: null,
};

context.state = {
  benefits: [benefit],
  discoveryResults: [],
  offerings: [{ id: benefit.offering_id, display_name: "SYNTHETIC-ONLY card" }],
  selectedBenefitId: benefit.id,
  privateCards: [],
  privateCardsAvailable: false,
};
context.renderBenefitDetailForTest();

assert.match(benefitDetail.textContent, /Up to 2 lounge visits/);
assert.match(benefitDetail.textContent, new RegExp(claimRoute));
assert.doesNotMatch(benefitDetail.textContent, /No redemption steps are recorded/);

const rendered = descendants(benefitDetail);
const terms = rendered.find(element => (
  element.tagName === "section" && element.textContent.includes("Official terms")
));
assert.ok(terms, "Expected the official-terms section");
const termsLink = terms.querySelector("a");
assert.ok(termsLink, "Expected the approved evidence source link");
assert.equal(termsLink.href, sourceUrl);
assert.equal(termsLink.target, "_blank");
assert.equal(termsLink.rel, "noopener noreferrer");
assert.equal(termsLink.textContent, "Open official source");

benefit.value_class = "conditional";
benefit.conditions = [
  { type: "spend_triggered", value: "SYNTHETIC-ONLY INR 50,000 qualifying spend" },
];
benefit.allowance = {
  unit: "domestic_lounge_access_voucher",
  count: 2,
  period: "qualifying_calendar_quarter",
  claim_route: claimRoute,
};
context.renderBenefitDetailForTest();
assert.match(benefitDetail.textContent, /Verified/);
assert.match(benefitDetail.textContent, /Up to 2 lounge visits per qualifying calendar quarter/);
assert.match(benefitDetail.textContent, /To qualify.*SYNTHETIC-ONLY INR 50,000 qualifying spend/);
assert.doesNotMatch(benefitDetail.textContent, /visits left|visits remaining|visits available/i);

const unknownField = "SYNTHETIC-ONLY-unknown_machine_field";
assert.equal(context.consumerFieldLabelForTest(unknownField), null);
assert.equal(
  context.friendlyPredicateForTest({ field: unknownField, operator: "gte", value: "50000" }),
  null,
);
benefit.conditions = [{ field: unknownField, operator: "gte", value: "50000" }];
context.renderBenefitDetailForTest();
assert.doesNotMatch(benefitDetail.textContent, /unknown_machine_field|gte|50,000/);

benefit.allowance = {
  unit: "SYNTHETIC-ONLY-voucher",
  cap: 3,
  period: "SYNTHETIC-ONLY-quarter",
};
benefit.value_class = null;
benefit.conditions = [];
context.renderBenefitDetailForTest();
assert.match(benefitDetail.textContent, /Up to 3 lounge visits/);

assert.equal(
  context.consumerAllowanceTextForTest({
    benefit_type: "reward_points",
    allowance: { any_upi_percent: "0.5", cashpoints_percent: "1.25" },
  }),
  "1.25% CashPoints",
);
assert.equal(
  context.consumerAllowanceTextForTest({
    benefit_type: "reward_points",
    allowance: { cashpoints_percent: "0.5", any_upi_percent: "1" },
  }),
  "0.5% CashPoints",
);

benefit.evidence = [
  { state: "check_before_use", source_policy_class: "discovery_only", source_url: sourceUrl },
];
context.renderBenefitDetailForTest();
assert.match(benefitDetail.textContent, /No official terms link is recorded yet/);
const discoveryTerms = descendants(benefitDetail).find(element => (
  element.tagName === "section" && element.textContent.includes("Official terms")
));
assert.ok(discoveryTerms, "Expected the official-terms section for the discovery-only case");
assert.equal(discoveryTerms.querySelector("a"), null);
