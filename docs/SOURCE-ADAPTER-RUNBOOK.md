# Source Adapter Runbook

How to build and operate a parser adapter for an admitted source. Read
`SOURCE-POLICY.md` and `EVIDENCE.md` first; this document assumes both.

## Before writing any adapter code

1. Confirm the source has an admission record (`SOURCE-POLICY.md`). If it
   does not, do not automate it. Either work the source manually and produce
   a single evidence record by hand, or leave it as a tier 6 discovery lead.
2. Read the admission record's URL scope, retrieval cadence, and any rate
   limit. The adapter must not exceed what the admission record authorizes,
   even if the source would technically allow more.

## What an adapter may do

- Request pages/documents inside the admitted URL scope, at or below the
  admitted cadence.
- Parse and normalize retrieved content into candidate catalog assertions
  plus an evidence record per `EVIDENCE.md`.
- Compute and store the content hash at retrieval time.
- Write candidates to the review queue described in `CATALOG-GOVERNANCE.md`.
- Run on a schedule, unattended, within the above limits.

## What an adapter must never do

Restating `SOURCE-POLICY.md`'s forbidden list, because an adapter is where
these boundaries are actually enforced in code:

- Never send credentials, session tokens, or cookies to bypass a login wall.
  Authenticated sources are outside automated-adapter scope. A human may use
  such a source manually without giving its secrets or captured content to an
  agent, and any resulting candidate still follows the normal review gates.
- Never solve, proxy, or automate past a CAPTCHA.
- Never fetch a path disallowed by the source's `robots.txt`.
- Never rotate IP addresses, user agents, or identities to get around a
  block, rate limit, or access control.
- Never exceed the admitted cadence, even to "catch up" after downtime.
- Never treat a blocked, CAPTCHA-gated, or authentication-required response
  as a signal to try harder — treat it as a stop signal.

## On a block

If a request is blocked, rate-limited, CAPTCHA-gated, or returns an
authentication challenge:

1. Stop requesting that source immediately.
2. Record the block in the adapter's job/event log (honest state, not a
   silent retry) with what was observed and when.
3. Report the block for human review. Do not attempt a workaround.
4. Resuming requires either a source-side change (confirmed by a human) or an
   updated admission record — not a code change that routes around the
   block.

## Output is candidate-only

An adapter never writes directly to the published catalog. It writes:

- One or more candidate catalog assertions.
- One evidence record per retrieval, in `needs_review` state.

Both go through the independent review described in `CATALOG-GOVERNANCE.md`
before anything becomes `active`.

## Testing

- Adapters are tested in CI against committed synthetic fixtures (fake pages,
  not real retrieved content) — no network access in CI, and no real source
  data in fixtures.
- Live checks against the real source are a separate, non-blocking job. A
  live check failing must not fail CI; it should raise a candidate-review or
  operations signal instead.
- Every adapter needs a test for: successful parse, malformed/changed page
  shape (should produce `needs_review`, not a wrong assertion), and a
  simulated block/rate-limit response (should stop and report, not retry).

## Logging and secrets

- Never log raw retrieved source content, credentials, cookies, or session
  tokens.
- Logs may contain the URL, timestamp, hash, and outcome (success, block,
  parse failure) — nothing else from the response body.

## Related documents

- `SOURCE-POLICY.md` — tiers, admission, and the permitted/forbidden line.
- `EVIDENCE.md` — the record an adapter must produce.
- `CATALOG-GOVERNANCE.md` — what happens to a candidate after the adapter
  hands it off.
- `AGENT-OPERATIONS.md` — boundaries for the agent, if any, driving the
  adapter.
