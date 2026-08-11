# Owner decision trace

This file preserves the meaning of the owner's key questionnaire responses and
later changes without depending on a chat transcript. The normative product
contract remains `PRODUCT_REQUIREMENTS.md`, `DECISIONS.md`, and `SECURITY.md`.

## Initial questionnaire

- All recommended default answers were accepted unless a later decision in
  this repository explicitly replaces one.
- Item 40 was answered **yes**: the owner's phrase “Book My Short Accredits” is
  interpreted as BookMyShow offers or credits.
- Item 64 expressed a preference for agents to continue working while the owner
  is offline. The implemented boundary permits unattended admitted-source work
  but never bypasses login, CAPTCHA, access controls, robots restrictions, or
  rate limits. A blocked source is paused, logged, and surfaced for follow-up.

## Superseded Family Finance boundary (historical)

> Historical record only: these bullets preserve an earlier owner decision and
> were superseded by the 2026-08-10 cancellation of the integration. They are
> retained for traceability and do not describe a current capability or roadmap
> item.

- Family Finance keeps its existing Cards page and remains useful without this
  repository.
- MyCard Benefits is an optional companion reached from an additional Cards
  control. If it is missing or unreachable, Family Finance opens bundled clone,
  setup, and connection guidance.
- Follow-up choice **A** was accepted: a future migration is a previewed,
  encrypted, one-time import; afterward both applications keep independent
  stores. Continuous synchronization is not implied.

## Later additions

- The planned-purchase optimizer must compare complete reward routes, including
  cashback or issuer portals, merchant offers, card earn, caps, milestones,
  fees, redemption value, and uncertain stackability. CashKaro to Amazon to a
  selected card is the motivating example, not an approved live claim.
- Video or community material is a discovery lead. Active benefit facts require
  current evidence from the official party responsible for that part of the
  benefit.
- Public benefit knowledge is reusable; personal card instances and usage state
  stay local and encrypted. Agents do not receive decrypted vault data.
- The Planner dashboard is an honest, ephemeral adapter: user-entered routing
  assumptions are submitted with fail-closed review markers (`reviewed: false`,
  `freshness: "unknown"`), the engine always rejects them as unverified, and
  the UI labels every layer "User-entered assumption". Nothing user-typed is
  ever presented as verified, no synthetic provenance can resolve (reserved
  `.invalid` domain), and the flow never navigates, persists, or fetches live
  sources. See `docs/PURCHASE-OPTIMIZER.md` "Planner UI adapter".

## Catalog review rule revision — 2026-08-10

The owner made one dated human approval sufficient for local catalog activation
at every review tier. Enhanced, ambiguous, and high-impact claims retain their
risk tier and may recommend a second independent human review, while non-human
review and author self-approval remain rejected.
