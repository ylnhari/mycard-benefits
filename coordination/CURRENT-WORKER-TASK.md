# Current worker task

Status: READY
Task: MC-002
Assigned runner: OpenCode
Required provider/model: `opencode/deepseek-v4-flash-free`
Branch: `agent/mc002-opencode`
Manager review required: yes
Commit authorized: local task-branch commit after every gate passes
Push authorized: no

Read this file and `AGENTS.md` completely. Execute **only MC-002** in this
worktree. MC-001 and MC-003 are already integrated at the branch base. Do not
access any other worktree or private data directory.

## Outcome

Selecting an imported My Cards row must open a keyboard-reachable, read-only
detail view that shows only the matched public offering name, issuer/bank,
network, lifecycle, created and updated dates, and replacement relationship.
Do not reveal or return PAN, CVV, PIN, expiry, cardholder, nickname, notes,
owner data, raw vault fields, or an unmatched raw offering identifier.

## Scope and boundaries

- Use only `SYNTHETIC-ONLY-` fixtures and temporary test data. Never read
  `data/`, `imports/`, vaults, backups, `.env`, browser profiles, or real cards.
- Preserve the loopback-only and no-store read-only boundary. Do not implement
  protected writes, reveal/copy, lifecycle editing, MC-005 wording work, or any
  other task.
- Change only objectively necessary app/static/template/API-test/UI-test files,
  user docs/living status if behavior changes, and this result file.
- A detail route or client-side panel is acceptable; choose the smallest design
  that stays envelope-only and usable on desktop/mobile, dark/light, keyboard.

## Required evidence

1. Every matched card row has a clear, keyboard-reachable detail action.
2. The detail view contains only public-catalog data plus the existing safe
   envelope fields; test the exact response/rendered DOM for secret absence.
3. Replacement links are shown safely. An unmatched card has an honest, safe
   detail/unavailable state with no raw slug dump.
4. Test normal, empty, unavailable, unmatched, and replacement cases.
5. Browser-verify desktop/mobile and dark/light; record keyboard behavior and
   console findings.
6. Run Ruff, strict mypy, full pytest, package build, JavaScript syntax check,
   and `git diff --check`.

Overwrite `coordination/WORKER-RESULT.md` with actual model, exact files,
commands/outcomes, rendered evidence, risks, commit ID, and final verdict
`MC-002_WORKER_PASS` or `MC-002_WORKER_BLOCKED`. Commit locally only after all
gates pass; never push.
