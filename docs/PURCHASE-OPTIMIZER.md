# Purchase optimizer design

The optimizer answers: “For this planned purchase, which verified path gives me
the strongest usable value with the cards I already hold?” It does not keep a
spending ledger or execute the purchase.

## Route graph

A route is an ordered graph, not a list of percentages:

```text
merchant and item
  -> optional coupon or merchant price
  -> optional shopping/cashback portal click-through
  -> issuer or network payment offer
  -> selected card earn rule
  -> optional milestone effect
  -> later conversion or redemption
```

Every component retains sponsor, eligibility predicates, dates, cap, remaining
allowance (when the user records it), required click/order sequence, reversal
conditions, evidence, and compatibility edges. Unknown compatibility is not
treated as stackable.

## Value classes

- `guaranteed`: a current fixed saving once all published conditions are met.
- `conditional`: depends on tracking, eligible MCC, stock, cap availability,
  issuer/merchant confirmation, successful transfer, or another stated event.
- `estimated`: a points/miles value derived from a disclosed user or house
  valuation; it is not cash and is never presented as guaranteed.

The UI shows these totals separately. It must not headline a sum of guaranteed,
conditional, and estimated value as one “return.”

The engine and API keep the three totals strictly separate, with no combined or
summed field: `net_guaranteed` is always guaranteed value minus fees and never
includes conditional or estimated value, conditional and estimated values are
reported only as their own ranges, every ranked route carries
`value_class_totals_are_non_additive: true`, and ranking uses only
`net_guaranteed` (plus policy tie-breakers). Deterministic tests pin this
contract at the engine, API (exact response key set), and UI rendering levels.

## Caps and allowances

Cap and allowance arithmetic is deterministic and fail-closed:

- Each component's value is clamped to the scenario amount, its
  `per_transaction_cap`, and its `remaining_allowance` (the period allowance
  the user recorded), whichever is smaller. A zero cap or zero remaining
  allowance yields a zero contribution; a cap larger than the purchase amount
  can never inflate a contribution above the amount.
- The clamp happens before minor-unit quantization (half-even rounding), so a
  cap such as `33.335` INR contributes `33.34` INR and the class total stays
  the exact sum of quantized contributions.
- Within one value class, components share that class's budget of the scenario
  amount in route order, so values are never double counted.
- Members of a repeated `cap_group` must declare the same per-transaction cap.
  That declared group budget is allocated once across members in route order;
  missing or mismatched declarations fail closed. A repeated canonical
  `benefit_rule_id` is likewise rejected.

## Ranking

1. Remove inactive, expired, stale, unreviewed, incompatible, or ineligible
   components.
2. Calculate net guaranteed value after fees and charges.
3. Calculate conditional upside separately, with probability left unknown
   unless supported by an explicit user assumption.
4. Calculate estimated redemption value as a range using a named valuation.
5. Apply per-transaction and period caps without double counting shared caps.
6. Prefer greater verified guaranteed value, then fewer fragile conditions,
   fresher/higher-tier evidence, and a simpler route.
7. Show at least one fallback route and explain why every rejected card/path
   lost or could not be verified.

## Caps, allowances, and rounding

- A component's contribution is clamped to the minimum of the planned amount,
  its per-transaction cap, and its remaining (period) allowance, then to what
  is left of its value class's budget for this scenario. A cap or allowance of
  zero yields a zero contribution (fail closed); a cap larger than the planned
  amount cannot inflate a value beyond the purchase.
- Two components that draw on the same shared cap group consume its one equal
  declared budget in route order, so the cap is never double-counted. If any
  member omits the declaration or declares a different amount, the route is
  rejected rather than guessed or averaged. A repeated canonical benefit rule
  is likewise rejected.
- Contributions are quantized to the currency's minor units with half-even
  rounding before being summed, so per-component and class totals stay exact
  and a clamped range (`40–70` under a `50` cap becomes `40–50`) cannot exceed
  the shared budget.


Affiliate status never enters the score or any tie-breaker. Equal policy
factors fall through to the stable route identifier; affiliate disclosure and
the user's link-class filter affect visibility only.

## Portal example: CashKaro to Amazon

CashKaro describes a click-through model in which it receives retailer
commission and passes a portion to the user, with cashback initially pending
and later confirmed after retailer validation and the return/exchange period.
That validates the need for `pending`, `confirmed`, `rejected`, and `reversed`
tracking states; it does not establish a current Amazon rate or guarantee that
any card/merchant offer stacks.

Discovery references:

- [CashKaro explanation](https://cashkaro.com/blog/shop-online-via-cashkaro-to-get-cashback/124655)
- [CashKaro confirmed cashback help](https://cashkaro.com/gethelp/questions-about-my-cashback-or-rewards/what-are-confirmed-cashback-rewards)
- [CashKaro terms](https://cashkaro.com/terms-conditions)

Before recommending a live route, verify the current store-specific portal
terms, merchant offer, issuer/network terms, category, coupon compatibility,
payment method, cap, and dates. A tracking link is opened only after the user
chooses it.

## Affiliate disclosure

Every route stores whether its link is official, ordinary third-party, or
affiliate/compensated. The UI puts the disclosure next to the action—not in a
footer—and offers “show official links only.” Redirect URLs are never hidden or
shortened in a way that prevents destination inspection.

## Privacy and safety

The optimizer needs card offering IDs, not PAN/CVV/PIN. It accepts a planned
purchase amount and context but does not persist them unless the user explicitly
saves a private plan. Agents receive only public offering IDs and public rules.
The app does not sign in to portals, place orders, redeem points, or submit
forms.

## Loopback API

The reviewed engine is reachable locally through one narrowly scoped endpoint:
`POST /api/v1/optimizer/routes` on the loopback-bound application.

- The request is a fully self-contained planned-purchase scenario plus
  candidate routes. It is ephemeral: nothing is persisted, logged, or sent
  over the network, and responses carry `Cache-Control: no-store`.
- The request must be at most 128 KiB and holds at most 20 routes, 8
  components per route, 5 scenario fees, 5 route fees, 8 source references,
  and 8 admitted action origins. Money is accepted as decimal strings or integers;
  JSON numbers are rejected so values stay exact.
- Every action reference is an anonymous HTTPS URL from the caller-admitted
  origin set and has an explicit `approved` human action-link state. `data:`,
  `javascript:`, unknown, unreviewed, stale, expired, and otherwise ineligible
  inputs are rejected rather than ranked. The adapter adds only structural
  bounds and never reimplements ranking.
- The response mirrors the engine exactly: ranked routes with net guaranteed
  value after fees, separate conditional and estimated ranges, per-component
  provenance (source references, evidence tier, verification and expiry
  dates, conditions and assumptions, named valuation for estimated layers),
  explanation, link class, and official reference, plus rejected routes with
  their reasons.
- Stale, unreviewed, inactive/expired, incompatible, and ineligible routes
  are never silently dropped: they appear under `rejected_routes` with
  reasons. Malformed, duplicated, unsupported, or oversized input fails the
  request (`422`, or `413` when the body exceeds the size limit).
- The endpoint never opens a link, never reads the vault or private card
  inventory, and cannot trigger a purchase.

## Planner UI adapter

The dashboard Planner is the only UI caller of the loopback API. It submits a
general, synthetic planned-purchase scenario built entirely from user-entered
assumptions. The adapter mapping below is the documented, bounded
translation; the engine's ranking and rejection semantics are never changed
or bypassed.

- **Input surface** — merchant or site label, category, amount, date,
  currency (INR/USD/EUR/GBP/JPY), allowed channels (official, third-party,
  affiliate), and up to 8 cards, each with a card label, one routing
  assumption, a value class, and a percentage of the planned amount
  (guaranteed: single value; conditional/estimated: minimum and maximum),
  an optional condition, and a channel.
- **Percent-to-money mapping** — each percentage is converted with exact
  BigInt decimal arithmetic (no floating point) to
  `percent / 100 × amount`, quantized to six decimal places with half-even
  rounding. The engine itself quantizes totals to the currency's minor
  units.
- **Synthetic provenance** — user-entered assumptions have no source, so
  the adapter supplies reserved `.invalid` provenance that can never
  resolve: `benefit_rule_id` is a fresh canonical UUID v4,
  `source_refs`/`official_reference` point at
  `https://planner-user-entered.invalid`, `evidence_tier` is `low`,
  `verified_on` equals the scenario date, and `approved_official_origins`
  contains only that origin. The UI renders provenance as non-navigating
  text, never as links.
- **Honest review markers** — every user-entered component is submitted as
  `reviewed: false` and `freshness: "unknown"`. The engine therefore rejects
  every planner route with the verbatim reasons "source is not human
  reviewed" and "source freshness is unknown", and the result is always
  `no_verified_route` while the reviewed catalog has no verified benefits
  for these cards. The UI labels every rendered layer "User-entered
  assumption" and never claims verified information; rejection reasons are
  displayed verbatim so the verified-vs-user-entered distinction comes from
  the engine itself. The planner cannot and must not mark user data as
  reviewed.
- **Ephemerality** — the form stores nothing (no `localStorage`, no
  history), the request is sent with `Cache-Control: no-store`, results
  replace the previous result in the page, and the flow never navigates,
  opens a link, fetches a live source, or triggers a purchase.
- **Error mapping** — client validation messages name the exact field and
  focus it; server `422` shows the API's value-free detail message, `413`
  explains the size limit, and network failures tell the user the local app
  did not answer. Form values are preserved on every error path.
