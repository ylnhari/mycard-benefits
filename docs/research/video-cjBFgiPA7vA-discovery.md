# Video discovery handoff — `cjBFgiPA7vA`

## Status and boundary

**Discovery only — not catalog facts, advice, or a current offer list.** This
note records feature leads recovered in `docs/IDEA-LOG.md` from the public
video discovery process. It does not reproduce a transcript, assert any current
reward rate or eligibility rule, or authorize a catalog publication. The video
is a lead; specific administering-party terms are the evidence standard.

## Chapter-derived product ideas

- Treat a card portfolio as a spend-pattern fit, not a universal "best card":
  a broad core offering plus optional merchant/category specialists.
- Compare an ordered purchase route: merchant/item -> coupon or price ->
  cashback/affiliate portal -> issuer or network offer -> card earn ->
  milestone -> redemption.
- Make route inputs explicit: merchant, category/MCC where known, channel,
  amount, date, payment method, owned offerings, and cap allowance.
- Keep immediate savings, tracked-but-unconfirmed cashback, and estimated
  points/miles redemption values visibly separate.
- Explain friction and risk before a user opens a route: portal click sequence,
  coupon compatibility, exclusions, caps, return/reversal effects, expiry, and
  devaluation risk.
- Surface education-only safeguards for EMI, high utilisation, extraordinary
  purchases, and business-use exclusions. Never use rewards to encourage extra
  spending.
- Keep compensated/affiliate routes identifiable and unable to affect ranking.

## Candidate names to investigate

The following are names from the discovery note only; none is an active
catalog offering or verified route:

- HDFC SmartBuy; ICICI iShop.
- HDFC Regalia Gold; Tata Neu HDFC; HSBC Live+; Axis Magnus Burgundy.
- Fuel co-brands; hotel and airline-mile pairings.
- CashKaro -> Amazon as an example portal-to-merchant sequence.

## Questions for future video Ask or official-source research

Future YouTube Ask use may clarify the creator's *claimed method*, but cannot
verify facts. Ask narrowly:

1. Which named card, portal, merchant, and channel did the speaker use in each
   example, and was it presented as illustrative or current?
2. What exact steps were stated for the CashKaro -> Amazon route, including
   coupons, payment method, cart timing, and tracking caveats?
3. Which claimed components were said to stack, and which were explicitly
   mutually exclusive?
4. What spend amount, cardholder type, and cap period underlie each portfolio
   example?
5. Which point valuation, transfer partner, conversion ratio, minimum, fee, or
   availability assumption was used?
6. Which cautions were given for EMI, tax/property/business payments, fuel,
   utilisation, and returns or reversals?

For every answer, capture only a concise candidate assertion and timestamp;
do not store a transcript or treat the answer as primary evidence.

## Official evidence required before a live claim

| Candidate claim | Required primary source types | Required checks |
| --- | --- | --- |
| A card's rewards, fee, eligibility, waiver, milestone, cap, MCC/channel exclusion | Issuer product page, MITC/card agreement, programme T&Cs | Effective dates, card variant, reward currency, cap scope/reset, exclusions, and issuer change notice |
| Issuer shopping portal multiplier or voucher route | Issuer portal T&Cs plus the card programme T&Cs | Eligible cards, merchant/category, multiplier/cap, voucher price, transaction sequence, and whether points earn on the route |
| Network offer | Network-specific offer T&Cs and issuer eligibility confirmation | Issuing-country/network/card tier, dates, redemption method, caps, and conflict rule |
| Merchant discount or fulfilment condition | Merchant campaign T&Cs/checkout terms | Eligible inventory, channel, payment method, coupon/EMI restrictions, cancellations, and stock/usage limits |
| Portal cashback (including CashKaro -> Amazon) | Portal store-specific terms, portal general terms, and merchant terms | Click-through/session rules, category exclusions, tracking/validation delay, reversal/return effect, payout basis, and coexistence with coupons/cards |
| Points transfer or travel value | Issuer transfer terms and the loyalty partner's terms | Current ratio, minimum/fee, expiry, irreversibility, availability, taxes, and valuation assumptions |
| Any multi-party stack | All component terms above | An explicit compatibility edge; unknown compatibility means `not verified`, never stackable |

## Verification and publication gate

1. Create a candidate record with the video as `discovery_only`; attach no
   active benefit data.
2. Retrieve the current official sources allowed by `docs/SOURCE-POLICY.md`;
   do not bypass login, CAPTCHA, robots restrictions, access controls, rate
   limits, or terms.
3. Extract independently written structured facts with source URL, effective
   date, retrieval time, hash, confidence, and `needs_review` state.
4. A human reviewer verifies the terms against the candidate. Ambiguous or
   high-impact claims require two independent human reviewers.
5. Only then may a reviewed fact appear in `catalog/`. A changed, expired, or
   missing source returns it to `needs_review`.

## Affiliate-neutral presentation rule

Every route must show an official destination alongside any compensated link,
label the compensation beside the action, and offer an official-links-only
view. Compensation is excluded from recommendation scoring; equal-value ties
prefer an equivalent non-affiliate route unless the user deliberately chooses
otherwise.
