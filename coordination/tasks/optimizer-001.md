# Task optimizer-001 — Deterministic purchase-route optimizer

Read `AGENTS.md`, `PRODUCT_REQUIREMENTS.md`,
`docs/PURCHASE-OPTIMIZER.md`, and `docs/IDEA-LOG.md` first.

Implement and review a pure engine that ranks complete purchase routes without
making or encouraging a purchase. Keep guaranteed, conditional, and estimated
value separate; subtract user-entered fees; reject stale or unreviewed inputs;
require explicit pairwise stackability; disclose affiliates without allowing
affiliate status to improve rank; retain source references, assumptions, and
freshness. Tests use synthetic values only.

The first implementation is worker-owned. Claude or another independent
runner performs a read-only review; the primary integrates fixes and runs all
quality gates. No real offer claim, private card value, persistence, network
call, purchase, or publication is permitted.

## Status — 2026-08-07

Pure engine implementation, 24 focused tests, and independent re-review are
complete with no High/Medium findings. It remains intentionally unexposed to
the application UI/API. See `coordination/evidence/optimizer-review.md`.
