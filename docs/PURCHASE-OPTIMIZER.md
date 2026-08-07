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

No affiliate compensation enters the score. Equal-value ties prefer the
non-affiliate path unless the user explicitly chooses otherwise.

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
  and 8 approved origins. Money is accepted as decimal strings or integers;
  JSON numbers are rejected so values stay exact.
- All evidence, expiry, review, stacking, currency, and origin rules are the
  engine's. The adapter adds only the structural bounds above and never
  reimplements ranking.
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
