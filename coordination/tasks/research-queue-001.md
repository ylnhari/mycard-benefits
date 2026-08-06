# Task research-queue-001 — Resumable public-source job queue

Read `AGENTS.md`, `PROJECT_STATUS.md`, `docs/SOURCE-POLICY.md`,
`docs/SOURCE-ADAPTER-RUNBOOK.md`, and
`src/mycard_benefits/sources/policy.py` first.

Implement a local SQLite queue for public-source retrieval orchestration only.
It performs no network I/O. Jobs store an admitted source ID, canonical public
URL, cadence/next-run time, bounded attempt count, state, lease, and safe
machine-readable outcome code. Never store raw response bodies, exception text,
headers, credentials, cookies, private data, or card values.

Required behavior: idempotent enqueue, atomic single-worker claim with an
expiring lease, honest transitions (`queued`, `running`, `review_pending`,
`blocked`, `failed`, `completed`), maximum three attempts, no automatic retry
after policy/access/CAPTCHA/rate-limit blocks, stale-lease recovery, deterministic
time injection, and bounded listing. Multiple queue instances must not claim the
same job. Tests use synthetic admissions/URLs and temporary databases only.

Scope: `src/mycard_benefits/research/` and `tests/test_research_queue.py` only.
No app/API/catalog/vault/docs changes, no fetcher, no real source, no remote,
no commit. A different agent reviews before integration.

## Status — 2026-08-07

Offline queue implementation, 24 focused tests, and independent re-review are
complete with no High/Medium findings. It remains disconnected from any
network fetcher, scheduler, or application route. See
`coordination/evidence/research-queue-review.md`.
