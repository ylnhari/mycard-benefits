# Research queue review evidence

Review date: 2026-08-07

Scope: offline SQLite orchestration only. No fetcher, response content, headers,
credentials, or real source was involved.

The first independent review found that expired leases could still finish,
third-attempt jobs could be requeued into a constraint failure, URL query
strings could be retained, sub-second lease precision was lost, and the tests
did not cover the requested lifecycle matrix.

The implementation now rejects expired tokens inside the finishing
transaction, filters claims below three attempts, fails exhausted stale leases,
resets attempts for a new cadence cycle, rejects query and fragment URLs, and
keeps microsecond timestamps. It also provides explicit operator-only retry for
failed jobs, cadence-consistent idempotent admission, atomic claims, bounded
lists/stats, and safe machine-readable outcomes without raw payloads or errors.

The final DeepSeek V4 Flash read-only audit reported no High or Medium findings;
24 focused queue tests, lint, and strict mypy passed. The queue remains offline
orchestration only: it is not connected to the app, scheduler, or any network
fetcher.
