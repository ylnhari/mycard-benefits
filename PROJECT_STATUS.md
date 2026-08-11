# Project status

Last updated: 2026-08-11

## Fresh-vault device-action session fix

The first-run device-held add path now reuses the active browser vault session
when My Cards has already opened it. Previously, add opened a second session,
persisted successfully, and locked it while the list continued reading the
first session's stale in-memory snapshot. The vault path, device key, atomic
commit, encryption, and reauthentication contracts remain unchanged; only
session ownership was corrected. Full validation collected 687 tests and
finished with 684 passed, 0 failed, and 3 skipped; Ruff passed; the live
loopback card list still reports 18 cards. No commit, push, card deletion, or
live-record mutation was performed.

## Latest reveal-flow assessment

The reveal reference cannot yet be wired safely. The existing
`/api/v1/private/cards/{card_id}/reveal-authorize` route accepts an existing
12-character-or-longer vault passphrase and a field name, then always returns
HTTP 410 with `plaintext reveal is disabled`. It does not create the design's
first-use PIN/passphrase, return a one-use browser authorization, or expose a
reviewed field/clipboard bridge. The core reveal methods remain an in-process
boundary.

No client-only modal or parallel endpoint was added because it would render a
false working flow and bypass the stated contract. The missing backend
contract must define create-once detail-credential storage with the existing
Argon2id work factor, escalating delay, and lockout, plus a session-bound
short-lived reveal/clipboard path that does not place plaintext in ordinary API
responses. No vault code, cryptography, persistence, private record,
credential, or passphrase was touched. The repository Ruff binary, JavaScript
syntax, and diff checks pass; the requested `uv run --no-sync ruff check .`
wrapper is blocked by the machine's unset pyenv version.

## Latest onboarding and regression checkpoint

Onboarding now filters the 72 public offerings by one or more issuer chips,
keeps multiple product selections, and submits them through one dynamic
`Add N cards` action. Last 4 is offered only in the post-add optional
follow-up. A synthetic-only browser-logic harness verified `Add 3 cards`,
three additions alongside eighteen synthetic existing summaries, and no
credential in the add payload. No vault code or real private record was
touched.

The five requested tracked files are sanitized of machine-specific paths, and
the path scan plus `coordination/events.jsonl` JSONL validation pass. On the
rendered public page at `127.0.0.1:8808`, Lounge 8, Movie 12, and Rewards 8
each render the label's row count; all 72 public offerings render; issuer and
network filters work; and public card detail shows the allowed benefit states.
The private My Cards surface reports that cards could not be opened, so an
archived-card rendered check and live add against the owner's vault were not
performed.

The repository Ruff binary, JavaScript syntax, diff checks, focused tests, and
synthetic harness pass. The exact `uv run --no-sync ruff check .` and
`uv run --no-sync pytest -q` wrappers are blocked by the machine's unset pyenv
version. The real full fallback run collected 687 tests and finished with 682
passed, 2 failed, and 3 skipped; the remaining failures are the pre-existing
catalog response-shape drift and missing `autocomplete="current-password"`
expectation. Codex did not commit or push; a workspace process created local
commit `3fe2183` during verification.

## Latest benefits filter and public catalog checkpoint

Benefits category chips now count the active scope, so each selected chip's
label agrees with its rendered rows. The row is compact and grouped rather
than a flat alphabetic wall: featured categories lead, remaining categories
are under More categories, and owned matches lead every group. Connected
browser checks matched Lounge 8/8, Movie 12/12, and Rewards 8/8.

The public catalog browser renders all 72 offerings, filters by issuer and
network, searches by card text, and opens a shared cardface-style product
detail with the three consumer benefit states. It is available without a
private card endpoint or credential. The browser passed 320/375/414 light and
dark checks with no horizontal overflow, no undersized interactive targets,
and no console errors or warnings. Focused tests passed (56 passed, 2
skipped), JavaScript syntax and diff checks passed, and the repository Ruff
binary passed. The requested `uv run --no-sync ruff check .` command remains
blocked by the machine's unset pyenv version.

The owner-only live scope was not independently rechecked because that private
endpoint was unavailable in the connected session; no private record,
credential, or passphrase was read or handled.

## Latest device-held vault checkpoint

My Cards now follows the decided device-held-key design. A fresh normal load
silently creates an empty encrypted vault with an internally generated key,
stores that key through the OS keyring, and uses the guarded ignored local
`<data-dir>/private/device-key` fallback when keyring support is unavailable.
The default setup/unlock controls and card-management password fields are gone;
the existing vault create/open and Argon2id paths remain unchanged, and
`reveal-authorize` remains the future full-detail credential boundary. A fresh
browser run created the empty vault, rendered My Cards without a credential
form, and reported no console errors or warnings.

## Latest cardface port checkpoint

The verified card-face reference is now wired into My Cards. Card faces use
issuer-derived gradients, catalog-joined benefit counts, archived-last sorting,
the reference desaturation treatment, and an `Add last 4` affordance. The
twelve prior My Cards dropdowns are replaced by the six required filter chips
plus one chip per issuer present. Empty local card state renders onboarding
instead of a blank grid. Synthetic-only browser checks covered populated and
empty states, chip filtering, both themes, and 320/375/414-pixel widths.

Focused UI tests, JavaScript syntax, `git diff --check`, and the repository Ruff
binary pass. The required `uv run --no-sync ruff check .` wrapper remains blocked
by the machine's unset pyenv version; no vault internals, private card record,
or passphrase was touched.

## Latest rebuild checkpoint

The Benefits consumer view is now the primary public-catalog screen: it loads
all 60 visible records without hiding two thirds behind discovery pagination,
groups them across 17 categories with owned matches first, exposes only the
Verified / Check before use / Sources differ labels, and carries source links,
as-of metadata, plain-language detail fields, and not-claimed disclosures.
The design palette, semantic state pills, row layout, scope/category controls,
and mobile overflow rules are implemented. The dead candidate-store refresh
helper and candidate migration CLI/module were removed; vault migration code
remains separate. Focused UI/rendered/lint gates and fresh connected-Chrome UAT
pass, including the serif heading treatment, exact consumer summary, selected
detail labels, mobile widths, and clean console. Post-rebuild triage updated
obsolete UI contracts and the synthetic harness while preserving the protected
card flow. The complete suite is 651 passed, 2 failed, 1 skipped; the two
failures are the known HEAD pre-existing catalog response-shape drift and
tracked-source machine-path finding.

## Current milestone

MyCard Benefits is an integrated local alpha undergoing consumer-product
correction. Its security, vault, catalog, research, and testing foundations are
substantial, but the owner's latest walkthrough did not accept the normal-user
experience as finished. Do not describe the product as release-ready yet.

## Repository consolidation

- `<repo>` is the only physical MyCard repository under the Projects directory.
- Forty-four linked worktrees were removed after their committed work was
  preserved as Git refs. Uncommitted Claude and OpenCode product changes were
  first saved as local WIP commits `6bd07e0` and `8937bf1`.
- A separate detached verification clone was sent to the Windows Recycle Bin.
- The canonical checkout now uses `agent/luna-final-integration`; ignored local
  vault/runtime data stayed in the canonical directory and was not inspected.
- Superseded coordination Markdown, task briefs, and review reports were
  removed from the working tree. Git history preserves them. Only append-only
  `coordination/events.jsonl` and `coordination/jobs.jsonl` remain live.

## Consumer-visible capability

- First-run device-held vault bootstrap, card add and lifecycle APIs, public
  catalog, benefit discovery, comparison, and purchase guidance are integrated.
  Legacy manual setup/unlock routes remain for compatibility, but are not part
  of the default My Cards path.
- Normal navigation is limited to the four consumer views: My Cards, Benefits,
  Which card?, and Settings. Maintainer/research operations are not consumer
  dashboard surfaces.
- Public offering tiles open details, and the owner-approved Tata Neu Infinity
  HDFC RuPay Select domestic lounge claim is active.
- The Tata detail now carries the structured allowance of two vouchers per
  qualifying calendar quarter, the issuer/GyFTR claim route, and the approved
  official HDFC source through to the rendered UI.

## Current product gaps

- My Cards still needs the first-reveal PIN/passphrase flow and a recovery path
  for legacy passphrase-only or unavailable local storage, verified against the
  owner's existing encrypted vault.
- Home must show the Tata allowance honestly. When local qualification or usage
  is unknown, it shows the ₹50,000 eligible net posted spend condition for the
  calendar quarter and a "Check eligibility and terms" action, never a
  remaining-visit claim. A definite remaining count requires supporting local
  state.
- The owner-approved local review library shows all 61 seeded public benefit
  references in the served Benefits screen: one is the reviewed active Tata
  rule, 55 are source-reference items to check against current terms, and five
  preserve source conflicts. Only the reviewed active rule is used by catalog
  search, Compare, Which Card, or purchase guidance.
- Compare, Which Card, and Travel need more reviewed active content and final
  rendered owner acceptance before they can be called complete.

## Verification state

- The pre-redesign integrated baseline passed 973 tests with two expected
  browser-environment skips plus Ruff, strict mypy, JavaScript syntax, build,
  clean-clone, release-policy, and scanner gates.
- The subsequent Tata source-to-pixel correction passed 12 focused tests, its
  dependency-free rendered DOM harness, JavaScript syntax, Python lint, and
  diff checks.
- The 2026-08-11 device-held bootstrap slice passed the focused vault/UI route
  suite, JavaScript syntax, Python lint, and a fresh served-page check with an
  empty vault. The Python Playwright rendered test remains skipped because its
  browser dependency is not installed; the connected browser check covered the
  exact My Cards page and console state.
- One final complete offline suite and real rendered desktop/mobile acceptance
  remain required after the consumer correction stabilizes; avoid repeated
  full-suite runs during active UI iteration.

## Boundaries still closed

No live provider execution, purchase, application, booking, redemption,
boarding-pass upload, remote push, or public publication is implied by this
status. Those actions retain their explicit gates. Private card values remain
local and encrypted and must never enter model prompts or tracked files.

## Resume point

Use `CONTINUE-HERE.md` for the short execution order and `TASKS.md` for the
complete requirements ledger. Use Git history when an old implementation or
review artifact is needed; do not recreate per-worker worktrees or reports.
