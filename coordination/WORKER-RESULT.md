# Integrated worker results

Status: COMPLETE
Task: MC-008, MC-009
Runner: OpenCode
Provider/model: `opencode/deepseek-v4-flash-free`
Branch: `agent/mc008-009-opencode`
Manager branch: `manager/concurrent-integration`
Push authorized: no

## MC-002 — card record detail view

- Worker: OpenCode, `opencode/deepseek-v4-flash-free`
- Worker commits: `59bbebb`, `cc7ff1e`
- Manager integration: `d337811`
- Result: each My Cards row has a keyboard-reachable, envelope-only detail
  panel. It shows public offering data, lifecycle, dates, and safe replacement
  context; Escape returns focus to the trigger. No secret or raw identifier is
  rendered.
- Manager validation: Ruff, strict mypy, JavaScript syntax, package build,
  diff check, and 218 tests passed on the frozen integrated snapshot.

## MC-005 — neutral, self-contained MyCard wording

- Worker: Antigravity, Claude Opus 4.6 Thinking
- Worker commit: `f7bb1bd46bc800f112ea44b6af404be2b89aeb41`
- Result: active MyCard surfaces are checked for launcher-branded sign-in copy;
  regression coverage protects neutral local branding and loopback startup.
- Independent validation in the worker snapshot: Ruff, strict mypy, JavaScript
  syntax, package build, diff check, and 216 tests passed. Manager integration
  retains both MC-002 and MC-005 tests.

## MC-006 — unmatched offering variant state

Verdict: `MC-006_WORKER_PASS`

Cards whose offering identifier has no catalog match now render as a clear,
friendly **"Unmatched variant"** state in both the My Cards row and the
card-detail panel, with explicit guidance to correct the import or request the
supported variant. Raw offering identifiers, slugs, and card ids are never
rendered in rows, detail panels, or aria-labels; the private cards API stays
envelope-only and the raw slug appears exactly once (the envelope
`offering_id`). MC-002 and MC-005 behavior is preserved on the merged
snapshot.

### Implementation commits and files

- MC-006 implementation: `a0236b0` on `agent/mc006-opencode` (parent of the
  sync merge; base `cc7ff1e`).
- Sync merge with the canonical manager branch: `manager/concurrent-integration`
  (`532318f`) merged into `agent/mc006-opencode` at commit **`730ebba`**
  (MC-002 integration `d337811` + MC-005 integration `532318f`); conflicts
  were additive and resolved by retaining every section from both sides.
  Post-sync gates and the rendered harness ran on the merged snapshot
  `730ebba`.
- `src/mycard_benefits/static/app.js` — `UNMATCHED_CARD_LABEL` is now
  "Unmatched variant"; a shared `UNMATCHED_NOTE` constant (fix-the-import /
  request-the-variant guidance) is used by both the row and the detail panel;
  the View details `aria-label` for unmatched cards reads "View details for
  unmatched variant". Raw identifiers remain readable only for search
  (`cardSearchText`) and matching (`offeringForCard`, replacement lookups) —
  never for display.
- `tests/test_ui.py` — updated the stale label assertion; new
  `test_unmatched_variant_state_is_friendly_and_never_renders_raw_identifier`
  asserting the friendly label, guidance note used in both row and detail, safe
  aria-label, no legacy label, no text-node rendering of slug/offering_id/
  card_id/replacement_card_id, and exact read-only counts of
  `card.offering_id` (2), `offering?.slug` (1), `card.card_id` (3). The
  MC-005 test `test_active_surfaces_have_neutral_copy_and_self_contained_startup`
  is retained from the manager branch.
- `tests/test_private_cards_api.py` — new
  `test_unmatched_offering_response_is_envelope_only_and_never_repeats_slug`
  asserting an unmatched offering returns 200 with only the six envelope keys
  and `response.text.count("not-a-catalog-slug") == 1`.
- `docs/USER-GUIDE.md` — section 6 (import tip, per-card row description,
  detail panel paragraph) and the section 12 troubleshooting entry updated to
  "Unmatched variant" with no-raw-slug wording and the two fix paths; MC-005
  neutral-copy edits merged in from the manager branch.
- `README.md`, `PROJECT_STATUS.md`, `TASKS.md` — living artifacts updated with
  the new state wording; MC-006 marked done.
- `coordination/CURRENT-WORKER-TASK.md` — manager-owned integration trace
  retained from the canonical branch, with the MC-006 status line updated to
  record the completed synchronization.

### Commands and outcomes (post-sync, on the merged snapshot)

- `uv run ruff check .` — All checks passed.
- `uv run mypy src` — Success, no issues in 31 source files (strict).
- `node --check src/mycard_benefits/static/app.js` — ok.
- `uv run pytest` — full suite passed, exit 0: **221 passed**, including both
  the MC-005 neutral-wording tests and the MC-006 unmatched-variant tests.
- `uv build` — source distribution and wheel built successfully, exit 0.
- `git diff --check` — clean.
- Rendered harness rerun on the merged snapshot: 24/24 checks passed
  (identical to the pre-merge run), confirming MC-006 behavior and the MC-002
  detail view survive the MC-005 integration.
- Pre-commit scan of the change — only `SYNTHETIC-ONLY-`/UUID fixture values;
  no real identifiers, secrets, absolute user paths, or generated/runtime files.

### Rendered evidence

Browser-verified with system Chrome headless over CDP against three
loopback-only harness servers (ports 8791-8793, injected synthetic card reader,
temp data dirs, harness outside the repo). 24/24 checks passed:

- 4 rows render; both unmatched rows show the "Unmatched variant" heading and
  the full import-fix/request-variant guidance; the legacy "Unmatched card
  variant" label is gone.
- No raw offering slug (`hdfc-regalia-gold-credit`, `hdfc-millennia-credit`,
  `no-such-catalog-slug`, `synthetic-example-in-visa`) and no card id
  (`018f47f2...`) appears anywhere in the row text, detail text, or the whole
  DOM.
- Unmatched detail is honest ("Not matched in the public catalog") with the
  guidance sentence and no slug; the archived unmatched card still shows its
  replacement link ("Replaced by HDFC Bank Regalia Gold Credit Card").
- Matched cards render exactly as before (Regalia, Millennia) and their detail
  panels never print their own offering slug.
- API returns only the six envelope fields with `Cache-Control: no-store`.
- Keyboard preserved: Tab reaches a toggle, Enter opens and focuses the detail
  heading, Escape closes and returns focus.
- Desktop dark and light, and mobile: no horizontal overflow; the unmatched
  detail opens on mobile with the guidance visible.
- Empty and unavailable states unchanged and explicit; zero console errors or
  404s.
- Screenshots saved under the temp harness directory
  (`mc006-unmatched-desktop-dark.png`, `mc006-unmatched-desktop-light.png`,
  `mc006-unmatched-mobile-dark.png`).

### Risks

- Rendered verification used an injected synthetic reader rather than the real
  OS-keyring path (no keyring writes performed); keyring behavior is covered by
  the existing test suite.
- Two unmatched cards in the populated fixture share the same label by design
  (the synthetic offering was removed from the served public catalog in
  MC-003); they remain distinguishable by lifecycle badge and dates, and
  neither leaks an identifier.
- The MC-005 neutral-wording integration (`532318f`) was merged as-is from the
  manager branch; its functional changes are covered by the retained MC-005
  tests on the merged snapshot.
- Harness and servers run from the temp directory only; nothing was added to
  the repository.

### Commit

- Implementation: `a0236b0` (MC-006).
- Sync merge with the canonical manager branch: **`730ebba`** (final commit on
  `agent/mc006-opencode`).
- Coordination follow-up: this file.
- All local to `agent/mc006-opencode`; nothing was pushed.

## MC-008 — demo versus real-data boundary

Verdict: `MC_008_WORKER_PASS`

`--demo` runs are now unmistakable: a persistent banner labels the run on every
screen (desktop and mobile, both themes), demo activity stays in the separate
`demo-data` folder, and My Cards is switched off in demo mode — the private
cards endpoint returns a fixed 503 and no vault is ever opened, even if a
reader were injected. The user guide explains the boundary and the explicit
`--data-dir` interaction.

### Implementation commits and files

- Implementation: `d5405ff` on `agent/mc008-009-opencode` (branched from the
  manager checkpoint `4eeb303`, fast-forwarded via
  `git merge manager/concurrent-integration` with no conflicts).
- `src/mycard_benefits/templates/index.html` — persistent `#demoBanner`
  (`role="note"`, "Synthetic demo run", demo-data / `--demo` copy) rendered for
  every view when `demo` is set.
- `src/mycard_benefits/static/app.css` — `.demo-banner` using the existing
  theme variables (works in dark and light).
- `src/mycard_benefits/vault/router.py` — `create_private_cards_router` gained
  a `demo` flag; in demo mode the endpoint short-circuits before any reader
  runs with `503 "Private card list is switched off in demo mode"`.
- `src/mycard_benefits/app.py` — passes `settings.demo` into the router.
- `tests/test_config.py` — demo vs non-demo `from_environment` point at
  `demo-data` vs `data` (differing folders) and explicit `--data-dir` still
  wins.
- `tests/test_ui.py` —
  `test_demo_run_shows_persistent_banner_and_switches_off_my_cards` (banner in
  demo, absent otherwise, demo API 503, health unchanged).
- `docs/USER-GUIDE.md` section 3, `README.md`, `PROJECT_STATUS.md`, `TASKS.md`
  (MC-008 marked done) updated in the same commit.

## MC-009 — vault unavailable diagnostics

Verdict: `MC_009_WORKER_PASS`

My Cards no longer fails with one generic message. The private cards API
classifies every known cause into a safe, structured detail
(`detail: {code, message}`) and the UI renders a distinct title, badge, status,
explanation, and fix step for each: `demo`, `vault_missing`, `passphrase_only`,
`wrong_data_dir`, `locked`, `keyring_unavailable`, and `generic`. No path,
secret, identifier, or decrypted value ever appears in the diagnostic copy.

### Implementation commits and files

- Implementation: `8fc9e2c` on `agent/mc008-009-opencode`.
- `src/mycard_benefits/vault/router.py` — `VaultUnavailable` exception with a
  machine-readable code; `VAULT_DIAGNOSTIC_MESSAGES` (safe one-line summaries);
  `_read_keyring_cards` now classifies: missing file + no keyring entry →
  `vault_missing`; missing file + keyring entry for this exact vault path →
  `wrong_data_dir`; existing file + no keyring entry → `passphrase_only`;
  keyring backend failure → `keyring_unavailable`; open failure with stored
  passphrase → `locked` (VaultError) or `generic` (OSError/ValueError).
- `src/mycard_benefits/static/app.js` — `VAULT_DIAGNOSTICS` map with distinct
  title/text/badge/status/note/fix per code; `setPrivateUnavailable` renders
  the note and fix into `#myCardList`; the fetch error path parses the
  structured detail code and falls back to `generic`.
- `src/mycard_benefits/static/app.css` — `.diagnostic-fix`.
- `tests/test_private_cards_api.py` — structured-detail test for all seven
  codes via injected readers (plus tmp-path non-leak), and deterministic real
  reader classification tests for `vault_missing`, `wrong_data_dir`,
  `passphrase_only`, and `locked` using a stub keyring (no real keyring
  writes); the reader-raises test now asserts the `generic` code.
- `tests/test_ui.py` — per-code UI copy assertions, structured demo API detail,
  and the neutral-copy startup test now stubs the keyring so its
  `vault_missing` assertion is deterministic on any host.
- `docs/USER-GUIDE.md` section 12 rewritten per cause with fix steps;
  `PROJECT_STATUS.md`, `TASKS.md` (MC-009 marked done) updated in the same
  commit.

### Commands and outcomes (final snapshot `8fc9e2c`)

- `uv run ruff check .` — All checks passed.
- `uv run mypy src` — Success, no issues in 31 source files (strict).
- `node --check src/mycard_benefits/static/app.js` — ok.
- `uv run pytest` — full suite passed, exit 0: **229 passed**, including the
  MC-002/005/006 tests plus the new MC-008 and MC-009 tests.
- `uv build` — source distribution and wheel built successfully, exit 0.
- `git diff --check` — clean.
- Pre-commit scan of both changes — only `SYNTHETIC-ONLY-`/UUID fixture
  values; no real identifiers, secrets, absolute user paths, or
  generated/runtime files.

### Rendered evidence

Browser-verified with system Chrome headless over CDP against nine
loopback-only harness servers (ports 8791-8799, injected synthetic readers and
temp data dirs, harness outside the repo). No repository changes were made by
the harness.

- MC-009 suite (`verify4.js`): 15/15 passed — all seven diagnostics render
  distinct titles/badges/fix steps with the "no fallback data was used" status
  and no raw ids/paths/ports in any diagnostic; light theme on two states;
  mobile (demo + passphrase-only) with no horizontal overflow; same-origin API
  checks confirm the seven structured 503 codes; populated and empty
  regressions intact; zero console errors or 404s. Screenshots
  `mc009-*.png` (all states desktop dark, two light, two mobile).
- MC-008 suite (`verify-demo.js`): 13/13 passed — banner persistent across
  views on desktop dark/light and mobile with no overflow; catalog loads in
  demo (68 variants); demo API 503 with the switch-off detail; non-demo run
  has no banner and still serves 4 envelope rows with `no-store`.
  Screenshots `mc008-demo-*.png`.
- MC-006 regression (`verify3.js`): 24/24 passed on the MC-009 snapshot
  (updated only for the intentional new generic-diagnostic copy).
- MC-002/005 behavior retained: matched/unmatched detail panels, keyboard
  flow, neutral wording all re-verified.

### Risks

- Rendered verification used injected synthetic readers and a stub keyring
  rather than the real OS-keyring path (no keyring writes performed); the real
  classification path is covered by the deterministic API tests with
  monkeypatched keyring functions.
- `wrong_data_dir` is only positively detectable when the OS keyring still
  holds a passphrase for this exact vault path; the `vault_missing` copy also
  mentions the `--data-dir` possibility for the other case.
- Harness and servers run from the temp directory only; nothing was added to
  the repository.

### Commit

- MC-008: `d5405ff` — "Complete MC-008 demo and real-data boundary".
- MC-009: `8fc9e2c` — "Complete MC-009 vault unavailable diagnostics".
- Coordination follow-up: this file.
- All local to `agent/mc008-009-opencode` (base: manager checkpoint
  `4eeb303`); nothing was pushed.
