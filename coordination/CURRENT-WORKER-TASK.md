# Current worker task

Status: READY
Task: MC-006
Assigned runner: OpenCode
Required provider/model: `opencode/deepseek-v4-flash-free`
Branch: `agent/mc006-opencode`
Manager review required: yes
Commit authorized: local task-branch commit after every gate passes
Push authorized: no

Read this file and `AGENTS.md` completely. Execute **only MC-006** in this
worktree. The branch base is the reviewed, integrated MC-002 branch
(`cc7ff1e`). Do not access any other worktree or private data directory.

## Outcome

Cards whose offering identifier cannot be matched to the public catalog must
never display a raw slug/identifier. In both My Cards rows and the card-detail
view, show a clear, friendly "Unmatched variant" state with guidance to correct
the import or request a supported variant. Do not expose private card data or
raw internal identifiers.

## Scope and boundaries

- Use only `SYNTHETIC-ONLY-` fixtures and temporary test data. Never read
  `data/`, `imports/`, vaults, backups, `.env`, browser profiles, or real cards.
- Preserve the loopback-only and no-store read-only boundary. Do not implement
  protected writes, reveal/copy, lifecycle editing, MC-005 wording work, or any
  other task.
- Change only objectively necessary app/static/template/API-test/UI-test files,
  user docs/living status if behavior changes, and this result file.
- Preserve existing MC-002 behavior: matched rows, keyboard-reachable detail
  panel, Escape focus return, replacement naming, empty/unavailable states.

## Required evidence

1. No rendered row, detail panel, or aria-label ever shows the raw offering
   identifier or card id; unmatched cards show a friendly "Unmatched variant"
   state with import-fix and request-a-variant guidance in both row and detail.
2. The private cards API stays envelope-only for unmatched offerings; the raw
   slug appears exactly once (as the envelope `offering_id`), never repeated in
   extra fields or messages.
3. Focused UI tests assert the friendly label, the guidance strings, and the
   absence of any text-node rendering of slug/offering_id/card_id.
4. Browser-verify desktop/mobile and dark/light for matched and unmatched rows,
   including the detail panel; record keyboard behavior and console findings.
5. Run Ruff, strict mypy, full pytest, package build, JavaScript syntax check,
   and `git diff --check`.

Overwrite `coordination/WORKER-RESULT.md` with actual model, exact files,
commands/outcomes, rendered evidence, risks, commit ID, and final verdict
`MC-006_WORKER_PASS` or `MC-006_WORKER_BLOCKED`. Commit locally only after all
gates pass; never push.
