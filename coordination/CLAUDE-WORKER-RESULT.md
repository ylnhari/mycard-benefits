# Claude batch result — MC-024 and MC-177

Status: COMPLETE (corrected after manager review — see "Correction" below)
Task: MC-024, MC-177
Runner: Claude Code Sonnet 5
Branch: `agent/mc024-177-claude`
Base: `33a866c2c402b976cb59b03af2ae6c803df51d18`
Push authorized: no (not pushed)

**Read the "Correction — manager review" section near the end first.** It
supersedes the child-record `label` and `expiry_date` claims made in the
initial write-up below (kept for context, not accurate as final state).

## MC-024 — linked child records

### Architecture note

The private vault has no SQLAlchemy/Alembic layer despite `AGENTS.md`'s
architecture line — grep for `sqlalchemy`/`alembic` usage across `src/`
returns nothing beyond the unused `pyproject.toml` dependency declarations.
Card records are a single encrypted, AEAD-authenticated JSON envelope
(`src/mycard_benefits/vault/core.py`), not a database. Child records extend
that same pattern rather than introducing a new persistence layer.

### Model (`src/mycard_benefits/vault/core.py`)

- `ChildRecordKind` (`priority_pass`, `lounge_credential`, `membership`,
  `voucher`, `companion_credential`) and `ChildRecordLifecycle`
  (`active`/`expired`/`archived`) enums.
- `_ChildRecord` frozen dataclass: `child_id`, `parent_card_id`, `kind`,
  `lifecycle`, `created_at`, `updated_at`, `expiry_date` (optional). **No
  free-text `label` field** (removed after manager review — see
  "Correction" below); all fields are non-secret and none of the
  `_ALLOWED_SECRET_FIELDS` machinery was touched or extended.
- `VaultSession.add_child_record(...)` validates the parent card exists
  (`_get_record`), validates kind/lifecycle enum membership, and an optional
  `YYYY-MM-DD` `expiry_date` (`_validate_date`).
  `list_child_records(parent_card_id=None)` mirrors `list_cards()`'s
  envelope-projection pattern.
- Persistence: `child_records` is a new top-level envelope key, cleartext
  (no per-field secret to encrypt) but covered by the same whole-envelope
  HMAC (`_envelope_mac`) that already authenticates every other cleartext
  field — no new crypto primitive. `_persist`, `_serialize_envelope`, and
  `_validate_write_bounds` now take both the card map and the child-record
  map together so both stay in one atomic vault revision.
- **Backward compatibility**: `_parse_child_records` treats a missing
  `child_records` key as an empty list (`envelope.get("child_records", [])`),
  so a vault written before this change opens unchanged and silently
  upgrades to carry the new key on its next write. Verified with a
  reconstructed pre-existing-format envelope in
  `test_vault_without_a_child_records_key_opens_with_none_and_upgrades_on_next_write`.
  The on-disk format version constant (`_FORMAT_VERSION = 2`) was
  deliberately **not** bumped.
- Fail-closed parsing: unknown parent card id, unknown kind/lifecycle string,
  malformed date, or any tampered cleartext field (parent id, kind,
  lifecycle, timestamps) makes the whole vault refuse to open
  (`VaultAccessError`), matching the existing card-record invariants.
- `ChildRecordKind`/`ChildRecordLifecycle` exported from `vault/__init__.py`.

### API (`src/mycard_benefits/vault/router.py`)

- `PrivateChildRecordSummary` (new, `extra="forbid"`) nested as
  `PrivateCardSummary.child_records: list[...] = Field(default_factory=list)`
  — child records ride inside the existing `GET /api/v1/private/cards`
  response rather than a new endpoint, so the existing `no-store` header,
  `demo` gate, and `VaultUnavailable` → 503 mapping cover them automatically.
- `_read_keyring_cards` now also calls `session.list_child_records()` and
  groups by `parent_card_id` before returning each card row, so the real
  keyring-backed reader (not just injectable test readers) exercises the new
  grouping.
- `CardReader` type widened from `tuple[dict[str, str], ...]` to
  `tuple[dict[str, Any], ...]` to admit the nested list; strict mypy passes.

### UI (`templates/index.html`, `static/app.js`, `static/app.css`)

- `cardDetailSection` now appends a "Linked credentials" block
  (`childRecordsSection`) after the existing card-detail `<dl>`, before the
  unmatched-offering note.
- `CHILD_RECORD_KIND_LABELS` maps each kind to a human label; `childRecordBadge`
  reuses the existing `badge active`/`badge error`/`badge pending` classes
  (active → green, expired → red, archived → muted) — no new badge palette.
- Empty state: "No Priority Pass, lounge, membership, voucher, or companion
  credentials are linked to this card." (two-tier pattern matching the
  existing My Cards empty/filtered-empty convention).
- All DOM construction uses the existing `node()`/`textContent` helpers; no
  `innerHTML`/`insertAdjacentHTML` was introduced (enforced by test and
  `node --check`).
- No new interactive elements were added inside the child-records block, so
  it inherits the existing detail panel's keyboard reachability
  (View details → Enter/Space to open, Escape to close and return focus)
  without any change to that logic.
- CSS: `.child-records`, `.child-record-row`, `.child-record-list`,
  `.child-record-meta` — flex-wrap based, so it reflows at the existing
  850px mobile breakpoint without a new media-query entry; uses only
  existing CSS custom properties, so both themes are covered automatically.

### Browser verification

Verified live (not just via static string tests) with a scratch dev server
(`create_app(settings, private_card_reader=<synthetic fixture>)`, no real
vault or OS keyring touched) covering: all 5 child-record kinds, all 3
lifecycle badges (active/expired/archived), a card with zero child records
(empty state), an unmatched-offering card, desktop (1280×900) and mobile
(390×844) widths, and both dark and light themes. Screenshots were reviewed
inline during the session; the scratch server, its data directory, and the
temporary verification script were all removed afterward — nothing from
this pass is tracked or left running.

### Tests added

- `tests/test_vault.py`: round-trip + reopen, no-label-parameter-exists
  (signature introspection), parent-must-exist, invalid kind/lifecycle/date
  (parametrized, 4 cases), full tamper-each-field authentication
  (parametrized, 5 fields), dangling-parent and unknown-kind
  externally-tampered rejection, the backward-compatibility open test above,
  and a count-bound test.
- `tests/test_private_cards_api.py`: nested rendering with the full expected
  field set (post-correction shape), the exact-expiry-date-never-sent test
  (3 signal buckets), fail-closed on an unexpected nested field
  (`membership_number`) and on a `label` field specifically, fail-closed on
  unknown kind/unknown lifecycle/parent-mismatch/duplicate-id/invalid-uuid
  (5 dedicated tests), and an end-to-end test through the real
  `_read_keyring_cards` reader (via `VaultStore`/`StubKeyring`, no real
  keyring) proving per-card grouping.
- `tests/test_ui.py`: static-source assertions for the new render functions,
  kind labels, empty-state copy, and secret-field-name absence
  (`record.pan`, `record.cvv`, `record.pin`, `record.membership_number`, …).
- Two pre-existing exact-field-set assertions
  (`test_private_cards_rows_carry_only_the_five_envelope_fields`,
  `test_unmatched_offering_response_is_envelope_only_and_never_repeats_slug`)
  were updated to include the new `child_records` field — this is the field
  MC-024 intentionally adds, not a regression.

No secret child value (membership number, credential value, barcode) is
modeled, stored, or ever crosses the HTTP boundary. See "Correction" below:
after manager review, the field set that can reach the browser is exactly
`child_id`, `parent_card_id`, `kind`, `lifecycle`, `created_at`, `updated_at`,
and `expiry_signal` — no free-text label, no exact expiry date.

## MC-177 — self-contained, launcher-independent guidance

`README.md`, `docs/USER-GUIDE.md`, `docs/FAMILY-FINANCE-INTEGRATION.md`, and
`PRODUCT_REQUIREMENTS.md` "Family Finance and remote access" were already
compliant (verified by re-reading each in full and grepping for `Rover`,
`launcher`, `Companion Dashboard` — zero matches outside historical
append-only `coordination/` evidence, which the task brief allows to keep its
original wording). The remaining gap was that the **running app itself**
said nothing about this boundary — only the docs did.

- Added a "Remote access" row to the in-app Settings panel
  (`templates/index.html`), next to the existing Appearance row: states the
  app answers only on `127.0.0.1`, that phone/other-device access goes
  through "an authenticated gateway or launcher you control" (same phrase
  the docs already use), and that this tool is separate software that never
  shares MyCard's identity or configuration and can never widen MyCard's own
  bind. Deliberately avoids the literal phrase "external launcher" to stay
  consistent with the existing `test_dashboard_has_all_public_navigation_and_honest_vault_gate`
  assertion that phrase must not appear on the homepage.
- Extended `test_active_surfaces_have_neutral_copy_and_self_contained_startup`
  to assert this new Settings copy is present in the template and in the
  rendered homepage HTML (single-page app, so all panels are in one
  response).
- Strengthened the loopback-only guarantee: `tests/test_cli.py` already had
  `test_cli_always_binds_loopback` proving the current call passes
  `host="127.0.0.1"`. Added
  `test_cli_has_no_way_to_configure_a_non_loopback_bind`, which additionally
  proves there is no `--host` (or any `*host*`) argparse option, no `host`
  field on `Settings`, and no `os.environ`/`MYCARD_BENEFITS_HOST` read
  anywhere in `cli.py` — i.e. the bind cannot be silently widened by any
  currently-reachable code path, not just that today's one call happens to
  pass the right string.
- Browser-verified the new Settings copy with `uv run mycard-benefits --demo`
  at desktop and mobile widths, in both themes (see screenshots reviewed
  inline during the session); the demo server and its `demo-data/`
  directory (gitignored, untracked) were stopped and removed afterward.

No launcher secret, identity, or configuration value exists in MyCard source,
browser storage, or docs — none was added, and the grep sweep above confirms
none was already present.

## Delivery and verification

- Living artifacts updated in this change: `TASKS.md` (MC-024, MC-177
  checked off), `PROJECT_STATUS.md` ("Completed" section), `DECISIONS.md`
  (new "Linked child records and remote-access UI copy — 2026-08-07"
  section recording the no-SQLAlchemy architecture decision and the
  in-app-copy decision).
- Quality gates, all green on the final (corrected) tree:
  - `uv run ruff check .` — all checks passed.
  - `uv run mypy src` — success, no issues found in 31 source files.
  - `uv run pytest -q` — 272 passed (254 before this batch; 281 after the
    initial MC-024/MC-177 submission; 272 after the correction — several
    label/expiry-specific tests were removed or consolidated into shared
    `_child_record()`/`_card_with_children()` helpers as the child-record
    contract changed, and new fail-closed tests were added).
  - `node --check src/mycard_benefits/static/app.js` — passed.
  - `uv build` — both sdist and wheel built successfully.
  - `git diff --check` — clean (no whitespace errors).
- Diff inspected for secrets, real identifiers, absolute user paths, and
  generated/runtime files: none found. `dist/` and `demo-data/` remain
  gitignored and were not committed.
- No behavior outside MC-024/MC-177 scope was changed. Existing tests were
  only touched where the new `child_records` field intentionally changed an
  exact-field-set assertion, and where internal helper signatures
  (`_serialize_envelope`, `_persist`) changed and their direct unit-test
  call sites needed the new parameter.

## Correction — manager review

The manager rejected the initial commit (`d988f0c` at review time) with three
blocking findings. All three are fixed in a follow-up local commit; nothing
was pushed in between.

1. **Free-text child-record label could carry a secret.** `add_child_record`
   took an arbitrary `label: str`, stored it as cleartext envelope metadata,
   and the API/UI rendered it verbatim — a real membership number typed into
   that field would have leaked. Fix: the `label` field is removed entirely
   from `_ChildRecord`, `add_child_record`, envelope
   serialization/parsing, `PrivateChildRecordSummary`, and the UI. There is
   no code path left that accepts free text for a child record; the
   displayed name is always looked up from the allowlisted `ChildRecordKind`
   (`CHILD_RECORD_KIND_LABELS` in `app.js`, already a static, non-user-
   controlled map). Any reader that still supplies a `label` key is rejected
   by `extra="forbid"` (`test_private_cards_fail_closed_on_free_text_child_label`,
   `test_private_cards_fail_closed_on_unexpected_child_record_fields`), and
   `test_child_record_has_no_free_text_label_field` asserts the vault-session
   method signature itself has no such parameter.
2. **API boundary didn't independently fail closed.** `PrivateChildRecordSummary`
   typed `kind`/`lifecycle` as plain `str` and never checked that a nested
   child's `parent_card_id` matched its containing card, so only the vault's
   disk-parsing layer — not the HTTP boundary itself — enforced those
   invariants; a bug in a future reader implementation would have slipped
   through unvalidated. Fix: `kind: ChildRecordKind` and
   `lifecycle: ChildRecordLifecycle` (real enums, so an unknown string is a
   422/503 `ValidationError`, not a passthrough string); `child_id`/
   `parent_card_id`/`card_id` are uuid-format-validated
   (`field_validator`); and a `model_validator(mode="after")` on
   `PrivateCardSummary` rejects any child record whose `parent_card_id`
   differs from the card's own `card_id`, and rejects duplicate `child_id`
   values within one card's list. Covered by
   `test_private_cards_fail_closed_on_unknown_child_kind_or_lifecycle`,
   `test_private_cards_fail_closed_on_child_parent_mismatch`,
   `test_private_cards_fail_closed_on_duplicate_child_record_ids`,
   `test_private_cards_fail_closed_on_invalid_child_identifiers`.
3. **Exact expiry dates reached the browser.** `expiry_date` was sent
   verbatim in the API response and rendered as a formatted date in the UI.
   Fix: `PrivateChildRecordSummary` has no `expiry_date` field at all. A
   `model_validator(mode="before")` strips any incoming `expiry_date` and
   replaces it with a bounded `expiry_signal` —
   `"expired" | "expiring_soon" | "active" | null` — computed server-side by
   `_expiry_signal_from_date()` against the real current date (`expiring_soon`
   = within 30 days). The exact date string never appears in the model, the
   JSON response, or the rendered page; the UI shows only
   `CHILD_RECORD_EXPIRY_SIGNAL_TEXT[record.expiry_signal]` ("Expired" /
   "Expiring soon" / "Not expiring soon"). The vault itself still stores the
   precise `expiry_date` locally (that's local disk state, not the HTTP/UI
   boundary the finding was about, and it's what the signal is computed
   from) — nothing in the finding asked for the value to disappear from the
   user's own encrypted vault, only for it to stop crossing into the
   browser. Covered by `test_private_cards_never_send_the_exact_child_expiry_date`
   (three buckets, asserts every exact date string and the literal token
   `expiry_date` are absent from the response body) and a direct pydantic
   unit check in the fix-verification pass.

Also removed as dead code once `label` was gone: `_validate_label` and
`_MAX_LABEL_CHARS` in `core.py`.

**Follow-up fix caught by the tracked-diff privacy/secret scan**: the new
`test_private_cards_fail_closed_on_free_text_child_label` fixture originally
embedded a well-known 16-digit Visa test-card number (Luhn-valid, purely
numeric) inside a rejected `label` value. `git diff | grep -oE
"[0-9]{13,19}"` caught it. `AGENTS.md` boundary 1 requires synthetic
PAN-shaped fixtures to be "deliberately non-numeric and cannot be
Luhn-valid" even though this string was never a `pan` field and never
reaches a response body (the whole point of the test is that it's
rejected) — replaced with a non-numeric placeholder,
`SYNTHETIC-ONLY-secret-membership-number-ALPHA-NOT-A-REAL-PAN`, which reads
the same in the test's intent but cannot be mistaken for a real or
Luhn-valid card number. Re-ran `git diff | grep -oE "[0-9]{13,19}"` after
the fix: no matches anywhere in the tracked diff.

Re-verification: re-ran the full gate set on the corrected tree (all green,
see updated counts above) and did a genuine live browser pass in Chrome
(desktop 1280×900 and a true ~390px-wide mobile viewport, both dark and
light themes) against a scratch dev server (`browser_verify_server2.py`,
`create_app(settings, private_card_reader=<synthetic fixture>)`, no real
vault/keyring) seeded with all 5 child-record kinds across all 3
`expiry_signal` buckets plus a no-expiry case. Confirmed visually and via
`curl`'d JSON: each child row shows only its `kind` label (e.g. "PRIORITY
PASS") with no free-text name, a lifecycle badge, and — only when
`expiry_signal` is non-null — one of "Expired" / "Expiring soon" / "Not
expiring soon"; no exact date, and no `label` key, appears anywhere in the
DOM or the API response at any width or theme. (This session's
`resize_window` call reported success but did not actually narrow the
underlying Chrome window's rendered viewport for this browser instance;
genuine narrow-viewport rendering was instead confirmed by loading the same
page in a same-origin `<iframe>` sized to 390px, which gets its own CSS
viewport for `@media` purposes regardless of the outer window's actual
size — `window.innerWidth` inside that iframe read 386.) The scratch
server, its process, and its `data`/`demo-data` directories were all
stopped and removed afterward.

## Risks / follow-ups for later tasks

- MC-024 explicitly excludes write controls (add/edit/archive a child
  record from the browser) — `add_child_record` exists at the vault-session
  level only, with no HTTP write endpoint, matching the same boundary as
  `add_card`/`replace_card` today. A future protected-write task (MC-028/
  MC-029-adjacent) would wire a reauthenticated endpoint to it.
- MC-159 (encrypted attachments) depends on MC-024 per `TASKS.md` and can
  now build on the `parent_card_id` linkage pattern established here.
- The CLI-widen guard test added for MC-177 will need a matching update if
  a future task legitimately adds a `--host`-style override; that would be
  an explicit, reviewed change to `AGENTS.md` boundary 7, not an incidental
  one.

## Commit

Committed locally on `agent/mc024-177-claude`:

- Initial submission: `d0c76f1537a0e59ced135256a808e100077edb55` (plus
  `d988f0c` recording that hash in this file).
- Manager-review correction: `50991a6` — removes the child-record `label`
  field, adds fail-closed enum/uuid/parent-match/duplicate-id validation at
  the API boundary, and replaces the exact `expiry_date` with a bounded
  `expiry_signal`.

Not merged, rebased, pushed, or published.
