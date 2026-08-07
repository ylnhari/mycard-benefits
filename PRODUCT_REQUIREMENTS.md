# Product requirements

This is the durable product contract for MyCard Benefits. Update it when the
owner adds an idea or answers a product question; do not rely on chat history
for requirements.

## Product outcome

Give a user one local place to record credit, debit, prepaid, membership, and
benefit cards and understand everything those products can do for them. The
focus is benefits and eligibility, not a spending ledger or payment execution.

The repository is open source and clone-self-contained. Public card knowledge
is reusable across installations. Personal card instances and usage state are
private to one installation.

## Private card lifecycle

A user can add, inspect, edit, replace, retire, archive, restore, and delete a
card instance. Lifecycle states include active, expired, lost, stolen, closed,
and archived. A replacement is a new immutable instance linked to the prior
instance so history survives expiry, loss, or reissue.

A public offering has a stable slug and immutable public ID. Each private card
instance has its own UUIDv7 and points to an offering. A user can select an
exact network, co-brand, market, product generation, or benefit cohort when it
matters.

PAN, expiry, CVV, PIN, private notes, usage allowances, reminders, and
attachments are encrypted locally. Bank usernames/passwords, OTPs, session
cookies, and account-access tokens are never stored. Agents and remote models
never receive decrypted vault values.

## Benefit scope

The catalog must represent at least:

- Reward points, miles, cashback, and their earn rates.
- Conversion and transfer partners, ratios, fees, minimums, expiry, and value
  assumptions.
- Movie benefits, including BookMyShow and comparable providers.
- Hotels, flights, dining/food, fuel, shopping, vouchers, and coupons.
- Airport lounge, Priority Pass, meet-and-greet, concierge, insurance, and
  travel assistance.
- Welcome, milestone, annual-fee waiver, renewal, spend-triggered, geography,
  currency, channel, MCC, and time-window conditions.
- Indirect/inherited benefits supplied by a network, co-brand, merchant,
  membership tier, or event rather than the issuing bank. The motivating
  examples include Visa Infinite-wide programs and a boarding-pass-triggered
  destination benefit attached to an eligible card.

Benefits remain temporal and versioned. Expired rules stay historical, never
silently disappear. A missing end date means unknown, not perpetual.

## Discovery, comparison, and answers

Users can explore by card or by benefit. A benefit detail view explains what it
is, eligible cards, conditions, exclusions, caps, where/how to use it, current
status, last verification, and official issuer/network/merchant links. Card
comparison shows differences without collapsing conditional or estimated value
into a misleading single number.

Question answering is traceable: every factual answer cites the exact catalog
rules and official evidence used. The deterministic catalog works without an
LLM. Optional agents may help discover and draft public facts but never approve
their own candidates or access the vault.

## Purchase optimizer

For a contemplated purchase, the user may enter merchant/site/app, category,
amount, date, currency, channel, and the card names they hold. This scenario is
ephemeral by default and is not a spending record.

The optimizer compares complete purchase routes, which may contain:

1. Merchant price or coupon.
2. Cashback/reward shopping portal or issuer shopping portal.
3. Merchant, issuer, or network promotion.
4. The chosen card's base/accelerated earn rule.
5. Milestone progress or cap consumption.
6. Point transfer/redemption value and its uncertainty.
7. Fees, taxes, convenience charges, return/reversal risk, and exclusions.

An example candidate is CashKaro → Amazon → an eligible card. Each layer is
independent and conditional; the product may only show them as stackable when
evidence supports every relevant combination. See
`docs/PURCHASE-OPTIMIZER.md`.

The app never auto-navigates, purchases, books, redeems, uploads, or applies for
a card. The user chooses a route and follows transparent instructions.

## Public-source and review contract

Official administering terms, issuer documents, network rules, and merchant
fulfillment terms are authoritative for their respective parts. Aggregators,
videos, social posts, and communities are discovery leads only. Public-source
automation needs a human-approved source admission and may not bypass login,
CAPTCHA, robots restrictions, access controls, rate limits, or terms.

Agents write candidates in `needs_review`. At least one independent human
reviews standard claims; ambiguous/high-impact claims require two. Changed,
missing, or stale evidence withdraws an active claim pending review.

## Family Finance and remote access

My Family Finance keeps its existing Cards page. Its optional companion button
opens this separate application and shares no card or user data. When the
companion is absent or stopped, it opens bundled setup documentation. The
approved future migration is a previewed one-time encrypted import followed by
independent stores, not continuous synchronization.

The application binds to loopback. Remote use, if enabled by an owner, goes
through an authenticated external gateway or launcher; the direct app port is
never exposed remotely. That tool is not a MyCard dependency.

## Business neutrality

Affiliate links are optional and disabled from influencing rankings. Every
affiliate relationship and compensated destination has an adjacent disclosure,
an audit record, and a user control to hide affiliate routes. A non-affiliate
official link is always available. Recommendations rank user value, evidence,
and confidence—not project revenue.

## Current pilots and release boundary

The first real offerings to research are Tata Neu HDFC Infinity and HDFC
Regalia Gold. No real claims enter the catalog until official-source review.
Local implementation and tests may proceed; creating a public remote or pushing
requires a separate recorded human approval.
