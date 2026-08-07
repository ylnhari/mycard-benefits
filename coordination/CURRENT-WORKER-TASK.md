# Current worker task

Status: READY
Task: MC-001
Assigned runner: OpenCode
Required provider/model: `opencode/deepseek-v4-flash-free`
Manager review required: yes
Commit authorized: local task-branch commit after all gates pass
Push authorized: no

## Worker start instruction

Read this file completely and execute only MC-001 in this worktree. When finished, overwrite `coordination/WORKER-RESULT.md` with `COMPLETE` or `BLOCKED`, then create one local commit on the current `agent/mc001-opencode` branch only if every acceptance item passes. Never push.

Record the actual harness, provider, and model. Read `AGENTS.md` and directly required instructions, the MC-001 entry in `TASKS.md`, current branch/status, and only relevant public source/tests/docs.

## MC-001 outcome

Make the imported private-card list immediately understandable. The My Cards view must show each card as a readable row with its matched public catalog product, issuer/bank, network, lifecycle status, and non-secret record dates. It must not expose PAN, expiry, CVV, PIN, cardholder name, private notes, owner identity, or any other secret.

This worktree is isolated for concurrency. Work only here. Do not access or edit the integration, Antigravity, or future Claude worktrees.

## Privacy and scope

- Never read real `data/`, imports, vaults, backups, `.env`, browser profiles, or personal card records.
- Use only `SYNTHETIC-ONLY-` fixtures and temporary test data.
- Preserve the MC-004 launcher-independent, loopback-only boundary.
- Do not add private fields to API responses. Prefer joining existing envelope `offering_id` values to the public catalog in the browser/server without expanding the private envelope.
- Do not implement MC-002 card details, MC-003 synthetic catalog separation, protected writes, reveal/copy, or another backlog item.
- Do not modify global configuration, another repository/worktree, `TASKS.md`, or `dashboard.html`.

## Permitted implementation area

Change only files objectively necessary within:

- `src/mycard_benefits/static/app.js`
- `src/mycard_benefits/static/app.css`
- `src/mycard_benefits/templates/index.html`
- `src/mycard_benefits/vault/router.py` only if required without widening the envelope
- relevant catalog lookup code only if necessary for public metadata joining
- `tests/test_private_cards_api.py`, `tests/test_ui.py`, and narrowly relevant new tests
- `README.md`, `docs/USER-GUIDE.md`, `PROJECT_STATUS.md`, `ROADMAP.md` only for changed user behavior/living status
- `coordination/WORKER-RESULT.md`

## Required acceptance evidence

1. Populated My Cards renders one readable row per envelope record with public catalog product name, issuer/bank, network, lifecycle, created date, and updated date.
2. No secret/private value is returned or rendered. The private response remains `Cache-Control: no-store` and envelope-only.
3. Search matches visible product, issuer, network, lifecycle, and safe identifiers; lifecycle/status filtering returns exact subsets.
4. Empty, vault-unavailable, and unmatched-offering states are explicit and actionable, without dumping an unexplained raw slug. Do not expand into MC-006 beyond a clear label.
5. Rendered verification passes at desktop and mobile widths, in light and dark themes, for populated, empty, and unavailable states.
6. Keyboard navigation, visible focus, labels, and status announcements remain accessible.
7. Add deterministic API/UI regression tests for rows, public metadata joining, search/filter, empty/unavailable states, `no-store`, and absence of secret fields.
8. Run Ruff, strict mypy, full pytest, package build, and `git diff --check`.
9. Confirm only this worktree/branch changed and no path outside the permitted area was created.

## Result rule

Overwrite `coordination/WORKER-RESULT.md`; do not only answer in chat.

- `Status: COMPLETE` only when all acceptance items pass; otherwise `BLOCKED`.
- Include exact changed files, commands/outcomes, rendered evidence, remaining risks, branch name and commit ID.
- Final verdict: `MC-001_WORKER_PASS` or `MC-001_WORKER_BLOCKED`.
