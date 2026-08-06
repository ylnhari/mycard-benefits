# Task candidate-review-001 — Immutable catalog candidates and diffs

Read `AGENTS.md`, `PRODUCT_REQUIREMENTS.md`, `docs/CATALOG-GOVERNANCE.md`,
`docs/EVIDENCE.md`, and the catalog loader before working.

Design and implement a local, public-data-only candidate store. Every proposal
is immutable, starts in `needs_review`, names its author separately from human
reviewers, binds to a base catalog release and target record, and carries a
content hash. Generate deterministic field-level diffs without copying source
prose or raw evidence. Review decisions are append-only, require a distinct
human reviewer identity, and may not activate or rewrite the catalog directly.

Fail closed on unknown fields, invalid state transitions, base-release drift,
duplicate reviewers, changed candidate hashes, or high-impact claims without
two distinct approvals. Bound all text, lists, and stored records. Tests use
synthetic public facts only. No network, fetcher, vault, real offer, publication,
or automatic catalog edit is in scope.

## Status — 2026-08-07

Implementation, 26 focused tests, and independent re-review are complete with
no High/Medium findings. No candidate can activate catalog data directly. See
`coordination/evidence/candidate-review.md`.
