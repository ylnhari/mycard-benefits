# Current worker task

Status: READY
Task: MC-003
Assigned runner: Antigravity
Manager review required: yes
Commit or push authorized: no

## Worker start instruction

Read this entire file and execute only MC-003. Work directly in this repository. Do not start another backlog item. When finished, overwrite `coordination/WORKER-RESULT.md` using the required format below and set its status to `COMPLETE` or `BLOCKED`.

Before working, record the actual agent harness, provider, and model in the result. Read `AGENTS.md` and the instruction files it directly requires, the MC-003 entry in `TASKS.md`, current Git status/diff, and only the public source/tests/docs relevant to this task.

## MC-003 outcome

Remove production-visible synthetic `example.invalid` links and synthetic catalog records. A normal non-demo MyCard launch must never return or render the synthetic offering, synthetic benefit, or any `.invalid` URL. Synthetic fixtures may remain only in isolated tests or an unmistakably labeled demo mode.

The worktree contains an approved but uncommitted MC-004 change set. Preserve it exactly. Do not revert or reformat those files unless this task objectively requires a small overlap; report any overlap explicitly.

## Privacy and boundaries

- Do not read private card data, `data/`, `imports/`, vaults, backups, `.env`, browser profiles, or personal records.
- Do not use real user/card data in tests. Synthetic fixtures must retain the `SYNTHETIC-ONLY-` convention.
- Do not research the internet; this task is separation of existing fixture data from production surfaces.
- Do not change Rover, Family Finance, shared-agent repositories, global configuration, or another repository.
- Do not commit, push, tag, publish, rewrite history, or edit `TASKS.md`, `dashboard.html`, or `coordination/MC-004-ANTIGRAVITY-REVIEW.md`.
- Do not begin MC-001, MC-005, MC-177, or another task.

## Permitted implementation area

Change only files objectively necessary within these areas, plus the result file:

- `catalog/offerings/synthetic-example-in.json`
- `catalog/benefits/synthetic-example-reward.json`
- `src/mycard_benefits/catalog/`
- `src/mycard_benefits/app.py`
- `src/mycard_benefits/config.py`
- `src/mycard_benefits/cli.py`
- `src/mycard_benefits/templates/index.html`
- `src/mycard_benefits/static/app.js`
- relevant catalog, API, QA, app, and UI tests under `tests/`
- new isolated synthetic fixtures under `tests/fixtures/` when needed
- `README.md`, `docs/USER-GUIDE.md`, `PROJECT_STATUS.md`, and `ROADMAP.md` only when user-visible behavior or living status changes
- `coordination/WORKER-RESULT.md`

Do not broadly rewrite production catalog architecture. Prefer the smallest design that creates an explicit production-versus-test/demo boundary and remains easy for maintainers to understand.

## Required acceptance evidence

1. A normal non-demo production catalog API list contains no synthetic offering or benefit.
2. The synthetic offering detail route is unavailable in non-demo mode, and no non-demo API response or rendered DOM contains `example.invalid`.
3. Real production offering records remain available and deterministic.
4. Synthetic catalog coverage remains in isolated test fixtures; tests do not depend on a synthetic record living in the production `catalog/` directory.
5. If demo mode exposes any fixture, the UI labels the entire view as demo and production mode cannot access it. Removing the fixture from runtime entirely is acceptable if simpler.
6. Add a regression test that fails if a production catalog record contains an `.invalid` URL or a synthetic-only identifier.
7. Browser-verify normal non-demo catalog/dashboard behavior at desktop and mobile widths. Record the absence of synthetic offering/link text and console errors.
8. Run Ruff, strict mypy, full pytest, package build, and `git diff --check` using the repository's established commands.
9. Confirm no worker-created path exists outside the permitted implementation area. Manager-owned task/dashboard/review files and the approved MC-004 diff are pre-existing.

## Result rule

Do not merely answer in chat. Overwrite `coordination/WORKER-RESULT.md`.

- Use `Status: COMPLETE` only when every acceptance item passes.
- Use `Status: BLOCKED` otherwise.
- Include exact files changed during this task, exact commands and outcomes, browser evidence, remaining risks, and the final verdict `MC-003_WORKER_PASS` or `MC-003_WORKER_BLOCKED`.
