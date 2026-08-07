# OpenCode task — MC-098 optimizer API

Status: integrated after independent manager review
Worker: OpenCode free route
Branch: `agent/mc098-opencode`
Base: `33a866c2c402b976cb59b03af2ae6c803df51d18`
Push authorized: only under the repository publication gate

Read `AGENTS.md`, `PRODUCT_REQUIREMENTS.md`, `PROJECT_STATUS.md`, `TASKS.md`,
`docs/PURCHASE-OPTIMIZER.md`, the complete reviewed optimizer package, and its
tests before editing.

Implement MC-098 only: expose the reviewed pure purchase-route optimizer
through a narrowly scoped loopback API. The request is ephemeral and bounded;
it accepts a synthetic/general planned-purchase scenario and returns ranked
routes with the engine's provenance, assumptions, value classes, and rejection
reasons. It must reject stale, unreviewed, inactive, malformed, oversized, or
ineligible inputs and must not persist the request or response. Do not read the
vault, private card inventory, ignored paths, browser state, or user data. Do
not add UI, affiliate navigation, network calls, source fetching, purchases,
or real offer claims.

Add deterministic synthetic API tests covering success, every fail-closed
boundary, no persistence/logging of request values, response bounds,
`Cache-Control: no-store`, and loopback-only startup. Preserve the existing
optimizer behavior rather than reimplementing its ranking rules. Update
`TASKS.md`, `PROJECT_STATUS.md`, and relevant API/user documentation in the
same change.

Run Ruff, strict mypy, full pytest, JavaScript syntax, `uv build`, and
`git diff --check`. Inspect the final diff for secrets, private paths,
generated artifacts, and production `.invalid` URLs. Commit locally and write
`coordination/OPENCODE-WORKER-RESULT.md` with files, design decisions, exact
commands/results, risks, and commit hash. Do not merge, rebase, push, publish,
or edit another worktree. End with `OPENCODE_MC098_COMPLETE` only when the full
suite passes and the worktree is clean; otherwise record evidence and end with
`OPENCODE_MC098_BLOCKED`.

## Worker result (2026-08-07)

Status: COMPLETE
Runner: OpenCode free route (opencode/deepseek-v4-flash-free)
Branch: agent/mc098-opencode
Push: none (local commit only)
Result: implemented MC-098. New module src/mycard_benefits/optimizer/router.py exposes a single bounded ephemeral endpoint POST /api/v1/optimizer/routes registered in src/mycard_benefits/app.py; returns engine-ranked routes with provenance, assumptions, value classes, and rejection reasons; rejects malformed (422), oversized (413/422), stale, unreviewed, inactive, ineligible inputs; persists/logs nothing; Cache-Control: no-store. 8 new deterministic API tests in tests/test_optimizer_api.py. Gates: ruff clean, strict mypy 32 files, 254 tests passed, JS syntax OK, uv build OK, git diff --check OK. Commit: 098503a. Record: coordination/OPENCODE-WORKER-RESULT.md.

## Correction (manager review, 2026-08-07)

Addresses the four review blockers with commit `cb7d08f`:

1. **128 KiB bound enforced without buffering** - `_read_bounded_body()`
   rejects `Content-Length > 128 KiB` before reading and aborts immediately
   mid-stream on chunked bodies (bounded streaming). Tests:
   `test_oversized_content_length_is_rejected_without_reading` and
   `test_chunked_body_is_bounded_while_streaming` (proves the cap is enforced
   while streaming and the app stops reading).
2. **OpenAPI documents request/response schemas** - explicit pydantic request
   and response models with `$ref` rewrites into `components/schemas`;
   `POST /api/v1/optimizer/routes` now documents `requestBody` (required) and
   `200`/`413`/`422` responses. Money is documented as decimal-string/integer
   (floats rejected) via `WithJsonSchema`; responses serialize as strings.
3. **`Cache-Control: no-store` on all error paths** - `_error()` adds no-store
   to every 413 and 422 response; tests assert it on oversize, structural
   (malformed JSON), and semantic (duplicate route ids) errors.
4. **Collections fail closed instead of silently deduping** - pydantic
   validators reject duplicate link classes, duplicate approved origins (after
   canonicalization via `canonical_https_origin`), duplicate stacking refs,
   and duplicate component ids; engine still rejects duplicate route ids and
   duplicate fee labels. `test_duplicate_collection_entries_fail_closed`
   covers five cases.

Gates on the corrected tree: `uv run ruff check src tests` -> All checks
passed; `uv run ruff format --check` on the three changed files -> formatted
(pre-existing unrelated files remain unformatted and were not touched);
`uv run mypy src` -> no issues in 32 files; full `uv run pytest` -> passed
(exit 0); `node --check` on static JS -> OK; `uv build` -> OK;
`git diff --check` -> clean. Commit: `cb7d08f`.
