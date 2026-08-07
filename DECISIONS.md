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
- Remote access may use an owner-chosen authenticated external launcher or
  gateway, never a widened MyCard bind. MyCard does not identify, configure, or
  depend on that external tool.
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

## Useful catalog and protected read-only UI — 2026-08-07

- Public product identity and private ownership remain separate. The India
  starter catalog may contain the public variants represented by the local
  import, but it never records who owns them or how many instances exist.
- My Cards may display non-secret envelope metadata only. The app stays
  loopback-bound, opens the vault through the OS keyring, returns a bounded
  allowlist of fields, and forbids caching. An owner-selected external access
  tool is responsible for any remote authentication and is not integrated into
  MyCard.
- Add/edit/delete/reveal/copy remain disabled. Owner aliases, exact expiry,
  uncertain variants, and replacement chains require explicit human
  confirmation rather than inference.
- MyCardExpert and SaveSage are discovery-only sources. Current official issuer,
  administering-party, network, or merchant terms must support every confirmed
  benefit before the existing human review gate can activate it.
- Free or subscription-included runners are preferred when verified capable;
  primary integration and independent review remain required.

## Technical defaults

- Python/FastAPI, SQLite/SQLAlchemy/Alembic, Jinja and browser JavaScript.
- Human-authored YAML catalog compiled to deterministic JSON snapshots.
- AES-256-GCM data encryption; Argon2id passphrase wrapping; optional OS keyring.
- Stable public offering slug plus immutable UUID; private UUIDv7 card instances.
- Source agents propose; independent reviewers approve.

## Catalog integrity — 2026-08-07

- Product relationships (renamed, legacy, cloned, reskinned) are modeled as
  explicit reviewed edges in a `relationships/` catalog directory with required
  evidence assertions and human review records. The loader validates graph integrity
  and evidence provenance: no self-references, no dangling offering references,
  no duplicate edges, DAG cycle enforcement for renamed/legacy edges, and approved
  relationships require approved medium/high-confidence evidence assertions. Names
  never auto-infer inheritance (enforces questionnaire decision item 14).
- Benefit rules are temporal and versioned (`rule_version`, `supersedes`).
  `end_date_known` is strictly derived from `effective_to` (`effective_to is not None`),
  preventing contradictory values. Expired and superseded rules remain stored as historical
  records; supersession links require matching offering_id, matching benefit_type, strictly
  increasing rule_version (`rule_version > prior_rule.rule_version`), and DAG cycle prevention.
  With `include_historical=true`, active rules still respect `as_of` date range filtering,
  while historical/superseded rules remain discoverable as history.
- Every catalog assertion requires complete provenance metadata: source URL, content SHA-256 hash,
  retrieved timestamp, confidence level, review state, and approved human reviews. The numeric
  `source_tier` (1–6) is strictly derived at runtime from `source_policy_class` and exposed in API
  responses; it is omitted from authoring JSON schemas. Loader enforces that no approved assertion
  lacks full provenance and rejects tier 6 (`discovery_only`) sources from ever holding an `approved` review state.

## Linked child records and remote-access UI copy — 2026-08-07

- The private vault has no SQLAlchemy/Alembic layer despite the architecture
  blurb above; card records are an encrypted, AEAD-authenticated JSON envelope
  with no database. Non-secret linked child records (Priority Pass, lounge
  credentials, memberships, vouchers, companion credentials) are added to that
  same envelope as an additive `child_records` list, protected by the existing
  envelope MAC rather than per-field encryption, since none of their fields
  (kind, label, lifecycle, expiry date) are secret. Absent `child_records` on
  an older envelope means zero child records, not a parse failure, so an
  existing local vault opens unchanged and upgrades in place on its next
  write.
- Loopback-only startup and the remote-access boundary are stated in the app
  itself (a Settings panel), not only in docs, so a non-technical user sees
  the boundary without leaving the dashboard.
