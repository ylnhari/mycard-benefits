# Current worker task

Status: READY
Task: MC-005
Assigned runner: Antigravity
Branch: `agent/mc005-antigravity`
Manager review required: yes
Commit authorized: local task-branch commit after every gate passes
Push authorized: no

Read this file and `AGENTS.md` completely. Execute **only MC-005** in this
worktree, which begins at integrated MC-001 and MC-003. Do not access other
worktrees or private data.

## Outcome

Make all active MyCard surfaces use neutral, self-contained MyCard-local copy.
Rover is the owner's optional personal start/stop/mobile-access tool, never a
MyCard identity, sign-in, requirement, setting, or “Companion Dashboard.”
Remove active Rover-branded and Companion-Dashboard-branded sign-in language
from templates, static assets, API errors, README, and user guide. Preserve
historical coordination evidence unchanged.

## Scope and boundaries

- Do not read `data/`, `imports/`, vaults, backups, `.env`, browser profiles,
  or real cards. Do not use real user data.
- Do not change external Rover, Family Finance, shared-agent projects, global
  configuration, task dashboard, or historical `coordination/events.jsonl`.
- Do not implement MC-002 detail views, private writes/reveals, source research,
  or another backlog item.
- Change only active MyCard app/docs/tests necessary for neutral wording, plus
  this result file. Keep optional external-launcher copy factual and generic.

## Required evidence

1. Targeted grep finds no active “Rover sign-in”, “Rover login”, “Companion
   Dashboard”, or launcher-coupled wording in templates/static/README/user guide.
2. Render desktop/mobile and dark/light states and record neutral visible copy
   plus console findings.
3. Add focused regressions for active copy and self-contained startup.
4. Run Ruff, strict mypy, full pytest, package build, JavaScript syntax check,
   and `git diff --check`.

Overwrite `coordination/WORKER-RESULT.md` with actual model, exact files,
commands/outcomes, rendered evidence, risks, commit ID, and final verdict
`MC-005_WORKER_PASS` or `MC-005_WORKER_BLOCKED`. Commit locally only after all
gates pass; never push.
