# Claude batch — MC-024 and MC-177

Status: integrated after independent manager review
Worker: Claude Code Sonnet with Chrome integration
Branch: `agent/mc024-177-claude`
Base: `33a866c2c402b976cb59b03af2ae6c803df51d18`
Push authorized: only under the repository publication gate

Read `AGENTS.md`, `PRODUCT_REQUIREMENTS.md`, `DECISIONS.md`, `PROJECT_STATUS.md`,
`TASKS.md`, `docs/USER-GUIDE.md`, and
`docs/FAMILY-FINANCE-INTEGRATION.md` before editing. Work only in this
worktree. Do not read ignored private data, vault contents, imports, Drive,
credentials, browser identity data, or cardholder information. Use synthetic
fixtures only.

Implement both tasks end to end:

## MC-024 — linked child records

Model non-secret child records for Priority Pass, lounge credentials,
memberships, vouchers, and companion credentials. Each child record must have
its own stable private UUID, parent card-instance UUID, kind, safe display
label, lifecycle state, optional expiry signal/date representation consistent
with the existing browser privacy boundary, and created/updated timestamps.
Do not add PAN, membership number, credential secret, barcode, PIN, CVV, or
other revealable value to the browser envelope.

Render child records in the existing card detail view with clear empty,
populated, expired, archived, and unavailable states. Preserve the read-only
browser boundary and `Cache-Control: no-store`. Unknown fields and invalid
parent/lifecycle values must fail closed. Add deterministic API/model/UI tests
using synthetic values only. Verify keyboard navigation, focus behavior,
desktop/mobile layouts, and dark/light themes in Chrome. Do not add protected
write controls; those remain separate tasks.

Acceptance is the exact MC-024 entry in `TASKS.md`, plus proof that no secret
child value can cross the HTTP boundary or appear in rendered text, labels,
logs, URLs, screenshots, or test artifacts.

## MC-177 — self-contained launcher-independent guidance

Make README, user guide, Family Finance integration guide, and active app copy
clear to a non-technical user: MyCard runs independently and binds to
`127.0.0.1`; an external personal launcher may optionally start/stop or proxy
it for remote/mobile access, but is never part of MyCard, its identity, its
configuration, or its authentication. Keep Rover references only where needed
to explain that it is the owner's optional external project; do not integrate
or configure Rover. No launcher secret, identity, port, or browser storage may
enter MyCard source or docs.

Add tests for loopback-only startup and neutral active copy. Browser-verify the
rendered guidance at desktop/mobile widths and in dark/light themes. Historical
append-only coordination evidence may retain its original wording.

Acceptance is the exact MC-177 entry in `TASKS.md` and the applicable Family
Finance/remote-access requirements.

## Delivery and verification

- Preserve all already-integrated behavior and tests.
- Update living artifacts (`TASKS.md`, `PROJECT_STATUS.md`, relevant docs) in
  the same change. Do not edit `coordination/CURRENT-WORKER-TASK.md`.
- Write `coordination/CLAUDE-WORKER-RESULT.md` with files changed, design and
  privacy decisions, browser evidence, commands/results, risks, and exact
  commit hash(es).
- Run Ruff, strict mypy, full pytest, JavaScript syntax check, `uv build`, and
  `git diff --check`. Fix failures and rerun the complete gates.
- Inspect the final diff for secrets, private paths, generated artifacts, and
  production-visible `.invalid` URLs.
- Commit the completed batch locally with a clear message. Do not merge,
  rebase, push, publish, modify another worktree, or access private data.
- End with the exact token `CLAUDE_MC024_177_COMPLETE` only after every gate
  passes and the worktree is clean. If blocked, write the blocker and evidence
  to `coordination/CLAUDE-WORKER-RESULT.md` and end with
  `CLAUDE_MC024_177_BLOCKED`.
