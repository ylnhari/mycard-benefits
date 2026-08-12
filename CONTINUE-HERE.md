# Continue MyCard Benefits here

This repository is the single source of truth. Start from this file instead of
old chat transcripts, task briefs, review reports, or former worktrees.

## Derived catalog index — 2026-08-12

- Added `src/mycard_benefits/catalog/index.py` with the single SQLite write boundary
  `build_catalog_index`. It rebuilds the ignored runtime
  `<data-dir>/derived/catalog.sqlite3` from offerings, benefits, quantities,
  and reward records, and atomically replaces only a complete build.
- The index stores a source-file fingerprint and every read rechecks it. JSON
  remains authoritative; a changed catalog raises a stale-index error rather
  than serving old rows. Query connections are immutable and read-only.
- Quantity comparisons require category, metric, and unit, with optional scope.
  Missing quantities, missing rates, and null reward valuations stay SQL NULL
  or absent and are returned as excluded-unknown counts, never as zero.
- The production catalog smoke build contains 72 offerings, 61 benefits, 73
  quantities, and one reward record. Synthetic integration tests cover byte-
  deterministic rebuilds, real quantity and valuation arithmetic, unknown
  values, read-only enforcement, and stale-source rejection.
- No vault path, cryptography, private record, credential, commit, or push was
  involved.

## Fresh-vault device-action session fix — 2026-08-11

- Fixed the fresh device-held vault regression where `POST
  /api/v1/private/cards/add` committed a card through a second unlocked
  session while the browser list retained the first session's stale empty
  records. The add/list routes already resolved the same vault path and device
  key; the defect was session ownership, not cryptographic persistence.
- Device-held mutations now reuse the active browser vault session when one is
  present and retain the existing device-key reauthentication. Action-only
  sessions are still locked after the request; the vault core's atomic commit
  and encryption paths were not changed.
- Validation: the full suite collected 687 tests and finished with 684 passed,
  0 failed, and 3 skipped; `uv run --no-sync ruff check .` passed; the live
  loopback list endpoint returned 18 cards. The installed `uv` binary was
  selected ahead of the machine's unset pyenv shim and test application data
  was isolated from the live vault.
- No commit or push was made. No live card record was changed or deleted.

## Reveal-flow assessment — 2026-08-11

- The design reference was inspected, but no reveal UI was added because the
  existing browser route cannot perform the required operation safely. `POST
  /api/v1/private/cards/{card_id}/reveal-authorize` accepts an existing
  12-character-or-longer vault passphrase and a field name, then currently
  returns HTTP 410 with `plaintext reveal is disabled`.
- The route has no create-once PIN/passphrase mode, confirmation, first-use
  state, reusable session authorization, one-use browser token, or field
  response. The core's in-process reveal authorization is not exposed through
  this route. Adding a parallel endpoint or a fake client-only reveal would
  violate the task's security boundary.
- The missing contract must be supplied before the reference can be ported:
  create and persist the separate detail credential with the existing Argon2id
  work factor/backoff/lockout, then expose a reviewed session-bound reveal and
  clipboard bridge that never returns plaintext in ordinary API responses.
  No vault code, cryptography, persistence, private record, credential, or
  passphrase was touched; no commit or push was made.
- The repository Ruff binary passed, JavaScript syntax and diff checks passed,
  and the requested `uv run --no-sync ruff check .` wrapper remains blocked by
  the machine's unset pyenv version.

## Onboarding batch and public regression checkpoint — 2026-08-11

- Replaced the one-card picker with issuer-filter chips, multi-select product
  cards, one dynamic submit (`Add N cards`), and an optional last-4 follow-up
  after adding. No passphrase or other credential is requested; the
  synthetic-only batch harness verified `Add 3 cards`, three adds alongside
  eighteen synthetic existing summaries, and no credential in the request.
- Sanitized the five requested tracked documents: `CONTINUE-HERE.md`,
  `PROJECT_STATUS.md`, `coordination/events.jsonl`,
  `docs/CLAUDE-FINAL-PRODUCT-REVIEW-2026-08-10.md`, and
  `docs/REBUILD-BRIEF-2026-08-10.md`. The path scan and JSONL parse passed.
- Rendered public-page evidence on `127.0.0.1:8808`: Lounge 8/8, Movie
  12/12, Rewards 8/8; 72 public offerings; issuer/network filtering and
  public product detail worked; no public regression was observed for the
  not-claimed entitlement, decimal, machine-language, headline, failing
  control, or remaining-count checks. The private My Cards surface reported
  that cards could not be opened, so archived-card rendering and a live add
  against the owner's vault were not exercised.
- The repository Ruff binary, JavaScript syntax, diff checks, focused tests,
  and synthetic onboarding harness passed. The requested `uv run --no-sync`
  wrappers were blocked by the machine's unset pyenv version. The real full
  fallback suite collected 687 tests and finished with 682 passed, 2 failed,
  and 3 skipped; the two failures are the pre-existing catalog contract drift
  and missing `autocomplete="current-password"` expectation.
- Codex issued no commit or push. A workspace process nevertheless created
  local commit `3fe2183` during verification; its contents match this task.

## Benefits filter and public catalog checkpoint — 2026-08-11

- Fixed category filtering so chip labels and rendered rows use the current
  card scope. The compact category row leads with Lounge, Movie, Rewards,
  Dining, Cashback, and Vouchers; remaining categories are grouped under
  More categories, and owned matches lead each group.
- Added a public card browser that is independent of private card storage. All
  72 catalog offerings render with issuer, network, and text filters; selecting
  a cardface opens its recorded benefits with only Verified, Check before use,
  or Sources differ state labels. No credential or vault path was added.
- Connected-browser checks matched Lounge 8/8 rows, Movie 12/12, and Rewards
  8/8; 320, 375, and 414 pixel light/dark checks had no horizontal overflow or
  undersized interactive targets, and the browser console was clean. Focused
  tests passed (56 passed, 2 skipped), as did JavaScript syntax, diff checks,
  and the repository Ruff binary. The requested `uv run --no-sync ruff check .`
  wrapper remains blocked by the machine's unset pyenv version.
- The connected session's owner-only endpoint was not available for an
  independent live My cards-only row-count check. No private card record,
  credential, or passphrase was read or handled; no commit or push was made.

## Rebuild checkpoint — 2026-08-11

- Implemented the decided device-held vault bootstrap. On the first normal My
  Cards load, the app generates its high-entropy vault key internally, stores
  it through the OS-keyring boundary, and calls the existing encrypted vault
  create/open path without showing a credential form. If keyring support is
  unavailable, the guarded fallback is the ignored local
  `<data-dir>/private/device-key` file with restrictive local permissions.
- Removed the default setup/unlock sidebar and panels, the access badge, and
  the remaining card-management password fields. Device-held actions continue
  to use the existing vault reauthentication and Argon2id envelope; the
  reveal-authorize endpoint remains the separate credential gate for future
  full-detail reveal work.
- Fresh browser verification started with no vault: the empty vault and local
  fallback were created, My Cards rendered without onboarding/password UI, and
  the browser reported no console errors or warnings. Focused vault/UI routes,
  JavaScript syntax, and `uv run --no-sync ruff check .` pass. No existing card
  record was read, modified, or deleted; no commit or push was made.
- Reviewed checkpoint paths: `src/mycard_benefits/vault/`,
  `src/mycard_benefits/data_location.py`, `src/mycard_benefits/static/`,
  `src/mycard_benefits/templates/index.html`, focused vault/UI tests, and
  these handoff/status files.

## Cardface port checkpoint — 2026-08-11

- Ported the verified card-face reference into `static/app.css`,
  `static/app.js`, and the My Cards template. The My Cards grid now joins
  private card summaries to public catalog offerings and counts benefits by
  canonical offering ID; archived cards sort last and use the reference
  desaturation treatment.
- Replaced the twelve My Cards dropdowns with the reference filter chips plus
  issuer chips, added the exact count header, and kept the empty-wallet
  onboarding entry point. Missing last-four values render only as `Add last 4`.
- Focused UI tests, JavaScript syntax, `git diff --check`, and the repository
  Ruff binary pass. Connected browser verification used synthetic-only card
  summaries and confirmed populated/empty states, light/dark themes, chip
  filtering, and 320/375/414-pixel overflow behavior. No real card record or
  passphrase was read or handled; no commit or push was made.

## Rebuild checkpoint — 2026-08-10

- The Benefits view now renders all 60 public records locally in 17 category
  groups, with owned-card rows first when local matching is available.
- The view uses the three consumer states only: Verified, Check before use, and
  Sources differ. It includes visible scope/category controls, source links,
  as-of metadata, plain-language detail fields, and an explicit not-claimed
  treatment.
- The Benefits CSS uses the design artifact's paper/surface tokens, serif
  headings, mono metadata, semantic state pills, compact rows, and mobile
  overflow rules.
- Dead candidate-store refresh/migration surfaces were removed; vault
  migration remains under `src/mycard_benefits/vault/`.
- Focused UI, rendered harness, public-experience, conditional-benefit, and
  lint gates pass. Fresh connected-Chrome UAT on demo port 8793 passed with
  60 rows, 17 categories, the exact consumer summary, selected-detail labels,
  serif h1/h2/brand/category headings, no forbidden vocabulary, no mobile
  overflow, and no console errors or warnings. Post-rebuild triage aligned the
  removed Which-card, planner, travel/contributor, and old-copy contracts with
  the four-screen UI; the isolated private-card harness now
  models the rebuilt helper dependencies. The complete suite is 651 passed,
  2 failed, 1 skipped: the two failures are the known HEAD pre-existing
  catalog response-shape drift and tracked-source machine-path finding.
  `ruff check .`, JavaScript syntax, and `git diff --check` pass.
- This checkpoint is the end of Codex's current repository-writer scope:
  commit only the reviewed rebuild paths below, do not push or publish, and
  leave Stage 2b vault deletion and Stage 3 credential work untouched.
- Reviewed checkpoint paths: `src/mycard_benefits/static/`,
  `src/mycard_benefits/templates/index.html`, the Benefits UI tests/harness,
  the dead candidate refresh/migration removals, `docs/design/mycard-design.html`,
  and these handoff/status files.

## Canonical checkout

- Path: `<repo>`
- Branch: `agent/luna-final-integration`
- Integrated product baseline before repository cleanup: `fedf1cf`
- `coordination/` contains only append-only event and job ledgers. Superseded
  coordination Markdown remains recoverable from Git history.

## What works

- Local-only encrypted card storage, setup, unlock, and card lifecycle
  operations are integrated with the public catalog, benefit search,
  comparison, purchase guidance, and deterministic tests.
- The owner-approved Tata Neu Infinity HDFC RuPay Select domestic lounge rule
  is the first active public benefit.
- Its consumer detail now shows two quarterly vouchers, the approved claim
  route, and the official HDFC source.
- Existing encrypted runtime data remains under the ignored local `data/`
  directory and was not moved or inspected during repository cleanup.

## Product work still open

1. Finish the plain-language My Cards experience: simple add-card flow,
  first-reveal credential/PIN flow, and recovery for legacy passphrase-only or
  unavailable local storage states.
2. For the active Tata lounge rule, never imply that a visit remains when
   qualification or usage is not proven. Show the ₹50,000 eligible quarterly
   spend condition beside the allowance and use a plain "Check eligibility and
   terms" action; show a definite remaining count only when local records
   support it.
3. Finish the four consumer views (My Cards, Benefits, Which card?, and
   Settings) with owned-card ranking and reviewed benefit data. Maintainer and
   research operations remain outside the consumer dashboard.
4. The owner-approved local review library exposes all 61 seeded public
   benefit references in the served app. It keeps 55 source-reference records
   separate from the reviewed catalog and calls out five source conflicts; it
   does not affect comparison, ranking, or purchase guidance. Refresh and
   promote individual claims only after their current official terms are
   checked.
5. Run one final focused-plus-rendered acceptance pass, then the complete
   offline release gate. Remote push/publication is a separate owner decision.

## Working rules

- Read `AGENTS.md`, `PROJECT_STATUS.md`, `TASKS.md`, and `DECISIONS.md`.
- Never expose decrypted card values to agents, logs, screenshots, prompts, or
  tracked files. The owner enters secrets only in the protected local UI.
- Preserve one physical checkout. Use short-lived branches without additional
  worktree directories unless the owner explicitly requests otherwise.
- Record durable status in this file, `PROJECT_STATUS.md`, `TASKS.md`, and the
  append-only coordination ledgers—not in per-worker Markdown reports.
