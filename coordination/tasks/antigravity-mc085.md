# Antigravity task — MC-085 lounge and meet-and-greet verification

Status: assigned
Worker: Antigravity with Chrome/browser verification
Branch: `agent/mc085-antigravity`
Base: `33a866c2c402b976cb59b03af2ae6c803df51d18`
Push authorized: no

Read `AGENTS.md`, `PRODUCT_REQUIREMENTS.md`, `TASKS.md`,
`docs/SOURCE-POLICY.md`, `docs/EVIDENCE.md`,
`coordination/tasks/pilot-benefit-research-002.md`, and
`docs/research/pilot-benefit-source-map-2026-08-07.md` before working.

Implement MC-085 only. Re-verify every lounge, airport-service,
meet-and-greet, and relevant network-level candidate for the Tata Neu Infinity
HDFC Bank RuPay Select and HDFC Regalia Gold pilots against current official
issuer, RuPay/Visa, Priority Pass, DreamFolks, airport-service administrator,
or merchant terms. Use Chrome when needed. Discovery sites may identify leads
but can never support a verified claim. Do not bypass login, CAPTCHA, robots,
terms, geofencing, rate limits, or access controls.

Create a dated reviewable evidence artifact under `docs/research/` containing
independently worded candidate facts, exact official URL, source tier,
retrieval time, content hash, effective dates/unknown-end-date status,
eligibility/spend conditions, page/section locator, conflicts, and current
status (`official_candidate`, `conflict`, `not_found`, or `blocked`). Preserve
unknowns and conflicting official assertions; never infer stacking. No item
becomes active catalog truth and the worker cannot approve its own research.
Do not read private card data, Drive, vaults, ignored paths, credentials, or
browser identity details.

Add or update deterministic documentation/schema checks if the evidence
format requires them. Update `TASKS.md` and `PROJECT_STATUS.md` only if the
acceptance criteria are objectively met. Run all repository quality gates and
`git diff --check`, inspect for copied source prose, secrets, private paths,
generated artifacts, and production `.invalid` URLs, then commit locally.
Write `coordination/ANTIGRAVITY-WORKER-RESULT.md` with sources checked, evidence
counts, blocked/conflicting items, commands/results, risks, and commit hash.
Do not merge, rebase, push, publish, or edit another worktree. End with
`ANTIGRAVITY_MC085_COMPLETE` only after all gates pass and the worktree is
clean; otherwise record evidence and end with `ANTIGRAVITY_MC085_BLOCKED`.
