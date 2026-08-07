# Project Status

Last updated: 2026-08-07

## Current milestone

Useful local alpha: real public card-variant identities plus a local, read-only
view of the encrypted portfolio.

## Completed

- Clone-safe loopback FastAPI application, signed installation identity, port
  resolution, public dashboard, isolated test catalog, and offline test suite.
- Versioned public catalog loader/API, source policy, evidence governance,
  immutable candidate/diff store, and resumable SQLite research queue.
- Deterministic public catalog Q&A API/UI and a pure purchase-route optimizer;
  neither requires an LLM or private card values.
- Ephemeral loopback optimizer API (`POST /api/v1/optimizer/routes`): a
  bounded, self-contained planned-purchase scenario returns ranked routes
  with engine provenance, assumptions, value classes, and rejection reasons.
  It rejects stale, unreviewed, inactive, malformed, oversized, or ineligible
  inputs, persists and logs nothing, and answers with `Cache-Control:
  no-store`.
- Encrypted vault core with Argon2id key wrapping, AES-GCM records, complete
  envelope authentication, bounded persistence, locking, backups, lifecycle,
  auto-lock, reauthentication, and one-use reveal authorization.
- Strict one-time JSON manifest import with atomic batch persistence,
  cleartext-identifier validation, optional OS-keyring unlock, and count-only
  integrity verification. The owner-authorized local migration completed; its
  data and receipt remain ignored.
- Optional, data-isolated Family Finance launcher and bundled setup guide.
- Public India starter catalog with 68 real product-variant identities. Product
  presence is not presented as benefit verification; synthetic fixtures are
  isolated from runtime catalog views and APIs.
- Reviewed product-relationship graph with DAG-enforced integrity and required evidence
  assertions for renamed, legacy, cloned, and reskinned products. Relationships are explicit
  reviewed data with provenance; names never auto-infer inheritance.
- Temporal and versioned benefit rules (`rule_version`, `supersedes`). Missing end dates are
  treated as unknown (`end_date_known: False`), strictly derived from `effective_to`; expired
  and superseded rules remain discoverable as history; supersession chains enforce matching offering,
  matching benefit type, and strictly increasing rule version.
- Full provenance metadata enforced on every catalog assertion: source URL, retrieved timestamp,
  content hash, confidence, review state, and approved human reviews. The numeric source_tier (1-6)
  is strictly derived at runtime from source_policy_class and exposed in API responses. Tier 6
  discovery-only sources are strictly forbidden from being approved.
- Re-verified official lounge, airport service, travel edge, and meet-and-greet research candidates
  for the Tata Neu Infinity and Regalia Gold pilots with official source URLs (Tier 2/3), content hashes,
  retrieval timestamps, and spend-gate eligibility rules (`docs/research/lounge-and-meet-greet-verification-2026-08-07.md`).
- Loopback-local, read-only My Cards API/UI. It opens the existing vault through
  the operating-system keyring, returns only card UUID, offering, lifecycle,
  timestamps, and replacement metadata, and applies `no-store`. The view renders
  each card as a readable row joined to public catalog product, issuer/bank,
  network, lifecycle, and record dates; unmatched identifiers appear as a
  clearly labeled "Unmatched variant" row — never a raw slug — with import-fix
  and request-a-variant guidance, and search and lifecycle
  filtering return exact subsets. A keyboard-reachable "View details" action
  expands an envelope-only detail panel with product, issuer, network,
  lifecycle, record dates, and the replacement relationship; an unmatched
  card's panel says so honestly without printing the raw identifier.
- MyCard remains loopback-bound. A personal external launcher may start it and
  provide phone access, but MyCard does not integrate with that tool.
- `--demo` runs are unmistakable: a persistent banner labels the run on every
  screen, demo activity uses a separate `demo-data` folder by default, My Cards
  is switched off in demo mode, and the guide explains the explicit
  `--data-dir` override. Tests prove default demo and normal runs point at
  different data folders.
- Non-secret linked child records (Priority Pass, lounge credentials,
  memberships, vouchers, companion credentials) are modeled in the encrypted
  vault with their own private UUID, parent card-instance UUID, kind, safe
  enum-derived display label, lifecycle (`active`/`expired`/`archived`), and
  optional local expiry date. The read-only browser boundary never returns the
  exact expiry date; it returns only a bounded `expiry_signal`. The vault
  format upgrade is additive and opens a pre-existing vault unchanged. The
  My Cards API nests each card's child records under the existing `no-store`,
  envelope-only boundary, and the card detail view renders clear empty,
  populated, expired, and archived states. No write path exists yet; that
  remains separate protected-flow work.
- The app itself, not only its docs, states its remote-access boundary: a
  Settings panel explains the loopback-only bind and that any external
  gateway or launcher is separate software, never part of MyCard's identity
  or configuration. A CLI test proves there is no `--host` flag, environment
  variable, or config field that could widen the bind.
- My Cards explains why the vault is unavailable instead of failing silently:
  each known cause (demo mode, no vault yet, passphrase-only vault, wrong data
  folder, keyring unavailable, locked vault) maps to a distinct safe API
  diagnostic and a distinct rendered message with an actionable fix, covered
  by deterministic API and UI tests and documented in the user guide.
- Discovery-only pilot source work for Tata Neu HDFC Infinity and HDFC Regalia
  Gold. No real benefit claim has been activated.
- User-first README and guide covering setup, daily use, privacy, Family Finance,
  mobile access, verification states, and maintainer-only audit files.
- Rendered desktop/mobile and dark/light checks for the public dashboard and
  companion flow; DeepSeek module reviews and a separate Terra companion
  follow-up report no unresolved High/Medium findings for completed public-data
  modules and the companion launcher.
- OpenCode DeepSeek V4 Flash independently reviewed the owned-catalog and
  protected My Cards slice after remediation. Its final verdict is
  `REVIEW_APPROVED`; Ruff, strict mypy, all 208 tests, package builds, repeated
  ordering checks, and deterministic 68-file catalog regeneration passed.
- Final Claude Sonnet core review and Claude Opus importer review report no
  unresolved High/Medium finding after remediation and live compatibility
  verification.
- The complete initial 120-question decision matrix, later owner revisions, and
  video/purchase-optimizer ideas are persisted in repository documentation.
- A dependency-cold clean clone of commit `c037ccf` passed locked setup without
  the optional keyring extra, Ruff, strict mypy, all 201 tests, and both package
  builds.
- The public MyCard repository is live at
  `https://github.com/ylnhari/mycard-benefits`; Family Finance companion commit
  `e90f073` is pushed and synchronized on its public `main` branch.

## Next planned slice

- Reconcile private owner aliases, exact product variants, expiry states, and
  old-to-replacement relationships through a previewed human confirmation flow.
- Add protected add/edit/archive/replace controls; the CLI remains the only
  real-card write surface until that review completes.
- Convert official-source pilot research into reviewable benefit candidates.
- Expose candidate review and research queue contracts through protected local
  API/UI surfaces.

## Not yet safe

- The browser is read-only. Do not enter card numbers or use it to add, edit,
  delete, reveal, or copy private fields; the reviewed local CLI is still the
  only supported private write path.
- Import status is provisional: 20 records are marked active and 60 archived,
  but archived does not mean expired. Seven variants need confirmation, no
  replacement link is established, owner aliases are not mapped to family
  roles, and many records remain unassigned.
- No live source adapter or scheduler is connected to the network. The queue is
  offline orchestration only. The active benefit catalog is empty until
  official-source findings are reviewed and approved; real pilot findings remain
  unapproved research candidates.
- The optimizer core is exposed only through the loopback API, never through
  the UI; it cannot open purchase or affiliate routes and it persists no
  scenario or result.
- Family Finance performs a privacy-preserving reachability check only; signed
  companion identity pinning remains a later gate.
- Family Finance one-time import and notifications are not implemented. The
  Drive-manifest import is local to MyCard Benefits and is not a continuous
  synchronization bridge.
- Initial publication and companion synchronization are complete. Future
  catalog publication, releases, and remote-access changes retain their own
  review gates.

## Next delivery gate

Build the previewed owner/variant/lifecycle/replacement reconciliation workflow
without enabling secret-field reveal or direct browser write actions.
