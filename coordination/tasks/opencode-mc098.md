# OpenCode task — MC-098 optimizer API

Status: assigned
Worker: OpenCode free route
Branch: `agent/mc098-opencode`
Base: `33a866c2c402b976cb59b03af2ae6c803df51d18`
Push authorized: no

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
