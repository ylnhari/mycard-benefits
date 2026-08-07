# Worker result

Status: COMPLETE
Task: MC-006
Runner: OpenCode
Provider/model: `opencode/deepseek-v4-flash-free`
Branch: `agent/mc006-opencode`

## Result

Verdict: `MC-006_WORKER_PASS`

Cards whose offering identifier has no catalog match now render as a clear,
friendly **"Unmatched variant"** state in both the My Cards row and the
card-detail panel, with explicit guidance to correct the import or request the
supported variant. Raw offering identifiers, slugs, and card ids are never
rendered in rows, detail panels, or aria-labels; the private cards API stays
envelope-only and the raw slug appears exactly once (the envelope
`offering_id`). MC-002 behavior (matched rows, detail panel, keyboard/Escape
focus handling, empty/unavailable states) is preserved and re-verified.

## Files changed

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
  `card.offering_id` (2), `offering?.slug` (1), `card.card_id` (3).
- `tests/test_private_cards_api.py` — new
  `test_unmatched_offering_response_is_envelope_only_and_never_repeats_slug`
  asserting an unmatched offering returns 200 with only the six envelope keys
  and `response.text.count("not-a-catalog-slug") == 1`.
- `docs/USER-GUIDE.md` — section 6 (import tip, per-card row description,
  detail panel paragraph) and the section 12 troubleshooting entry updated to
  "Unmatched variant" with no-raw-slug wording and the two fix paths.
- `README.md`, `PROJECT_STATUS.md`, `TASKS.md` — living artifacts updated with
  the new state wording; MC-006 marked done.
- `coordination/CURRENT-WORKER-TASK.md` — rewritten for MC-006 (living task
  record).

## Commands and outcomes

- `uv run ruff check .` — All checks passed.
- `uv run mypy src` — Success, no issues in 31 source files (strict).
- `node --check src/mycard_benefits/static/app.js` — ok.
- `uv run pytest` — full suite passed, exit 0 (focused UI/API subset 20/20).
- `uv build` — source distribution and wheel built successfully, exit 0.
- `git diff --check` — clean.
- Pre-commit scan of the change — only `SYNTHETIC-ONLY-`/UUID fixture values;
  no real identifiers, secrets, absolute user paths, or generated/runtime files.

## Rendered evidence

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

## Risks

- Rendered verification used an injected synthetic reader rather than the real
  OS-keyring path (no keyring writes performed); keyring behavior is covered by
  the existing test suite.
- Two unmatched cards in the populated fixture share the same label by design
  (the synthetic offering was removed from the served public catalog in
  MC-003); they remain distinguishable by lifecycle badge and dates, and
  neither leaks an identifier.
- Harness and servers run from the temp directory only; nothing was added to
  the repository.

## Commit

Local commit on `agent/mc006-opencode` only; nothing was pushed.
