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

## Family Finance boundary

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
