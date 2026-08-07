# Decisions

## Accepted product decisions — 2026-08-06

- The owner accepted the recommended defaults from the initial product
  questionnaire except where a later decision explicitly replaces one.
- Questionnaire item 40 was confirmed: the phrase “Book My Short Accredits”
  means BookMyShow offers or credits.
- Unattended agents may continue while the owner is offline. They still may not
  bypass authentication, CAPTCHA, access controls, robots restrictions, or rate
  limits; a blocked source is paused and reported instead.
- Name: MyCard Benefits; repository slug: `mycard-benefits`.
- MIT-licensed, local-first, India-first/global-ready, English/localization-ready.
- Public reviewed benefit catalog plus private encrypted local card vault.
- Full card fields are supported locally; issuer credentials and OTPs are not.
- Agents never receive payment secrets; reveal/copy is a human-facing action.
- Family Finance retains its existing Cards page and remains fully standalone.
- Companion launch is optional and opens separately; absence shows setup docs.
- Existing Family Finance cards may be imported once through an encrypted,
  previewed bundle; no continuous synchronization follows.
- Remote access uses an authenticated Rover proxy URL, never client loopback.
- Source work may run unattended but may not bypass CAPTCHA, authentication,
  robots restrictions, access controls, rate limits, or terms.
- Deterministic behavior works without an LLM. Paid calls require explicit
  provider configuration and budget.
- Expired benefits remain as clearly historical structured facts.
- Pilot offerings: Tata Neu HDFC Infinity and HDFC Regalia Gold.
- Create and verify locally first; public remote creation/push is a later gate.
- Planned-purchase optimization compares whole routes (portal, coupon,
  issuer/network/merchant offer, card earn, milestone, and redemption) without
  becoming a spending ledger or executing a purchase.
- Guaranteed, conditional, and estimated values remain separate; unknown
  stackability is never inferred.
- Affiliate links are disclosed, hideable, paired with an official link, and
  cannot influence recommendation ranking.

## Initial private migration and publication — 2026-08-07

- The owner authorized the first public repository push and synchronization of
  the optional Family Finance companion commit.
- The owner-authorized Drive inventory is the source for the initial private
  migration. Newer consolidated credit/debit entries are treated as current;
  legacy `CC`/`Dc`-only entries are retained as archived history.
- Cardholder names from source metadata are represented by private owner aliases
  where needed. Ambiguous product, owner, duplicate, and lifecycle matches stay
  marked for confirmation rather than being guessed.
- The migration extracts card/product identity only. PAN, CVV, PIN, account
  numbers, scan bytes, and full document text are not copied.
- This workstation uses an OS-keyring-generated vault passphrase. Real manifests,
  receipts, vault files, and backups remain ignored and local.
- Claude Opus is eligible for large end-to-end public-code tasks; its lower
  subscription quota is a scheduling constraint, not a capability assumption.

## Technical defaults

- Python/FastAPI, SQLite/SQLAlchemy/Alembic, Jinja and browser JavaScript.
- Human-authored YAML catalog compiled to deterministic JSON snapshots.
- AES-256-GCM data encryption; Argon2id passphrase wrapping; optional OS keyring.
- Stable public offering slug plus immutable UUID; private UUIDv7 card instances.
- Source agents propose; independent reviewers approve.
