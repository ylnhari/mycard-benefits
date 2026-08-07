# Documentation Index

Public documentation for how source data enters this project's catalog, how
it is reviewed, and how agents (human-delegated or automated) are allowed to
operate. `AGENTS.md` and `DECISIONS.md` at the repository root remain the
canonical policy; the documents here elaborate them and must not contradict
them. If following a document here would require relaxing a boundary in
`AGENTS.md` or `DECISIONS.md`, that is a policy question for the repository
owner, not a documentation change — see each document's own notes on
unresolved questions.

- [SOURCE-POLICY.md](SOURCE-POLICY.md) — which sources may back a catalog
  assertion, in what preference order, how a source gets admitted for
  automation, and the exact line between permitted unattended work and
  forbidden bypass of authentication/CAPTCHA/robots/access-control/rate
  limits.
- [EVIDENCE.md](EVIDENCE.md) — the structured record every piece of evidence
  must carry, its review states, and where raw retrieved content is (and is
  not) allowed to live.
- [SOURCE-ADAPTER-RUNBOOK.md](SOURCE-ADAPTER-RUNBOOK.md) — how to build and
  operate a parser adapter for an admitted source, including what to do when
  a request is blocked.
- [CATALOG-GOVERNANCE.md](CATALOG-GOVERNANCE.md) — how a candidate assertion
  becomes a published catalog fact, independent review, the two-reviewer
  rule for ambiguous/high-impact claims, and conflict handling.
- [AGENT-OPERATIONS.md](AGENT-OPERATIONS.md) — what any background agent or
  delegated runner may and may not do, including the unattended-work
  boundary restated for agent operators specifically.
- [PURCHASE-OPTIMIZER.md](PURCHASE-OPTIMIZER.md) — deterministic whole-route
  ranking, value classes, stacking, and affiliate neutrality.
- [FAMILY-FINANCE-INTEGRATION.md](FAMILY-FINANCE-INTEGRATION.md) — optional
  companion setup, privacy boundary, failure behavior, and removal.
- [VAULT-IMPORT.md](VAULT-IMPORT.md) — bounded one-time private manifest import,
  interactive/keyring unlock, recovery warning, and verification command.
- [IDEA-LOG.md](IDEA-LOG.md) — durable owner ideas and discovery leads that are
  not approved catalog facts.
- [DECISION-TRACE.md](DECISION-TRACE.md) — concise trace from the initial
  questionnaire and subsequent owner choices into the current contract.
- [QUESTIONNAIRE-DECISIONS.md](QUESTIONNAIRE-DECISIONS.md) — numbered record of
  all 120 accepted defaults and the later revisions that supersede them.
- [`research/pilot-official-source-leads.md`](research/pilot-official-source-leads.md)
  — discovery-only official leads for the first two pilot offerings.

## One-line summary of the hardest rule

Source work, including scheduled and agent-driven work, may run unattended —
but it may never bypass authentication, CAPTCHA, robots restrictions, access
controls, rate limits, or a source's terms. When automation hits one of
those, it stops and reports; it does not route around it. This line is
restated in full, with what counts as "fine" vs. "forbidden," in
[SOURCE-POLICY.md](SOURCE-POLICY.md#permitted-unattended-work-vs-forbidden-bypass)
and [AGENT-OPERATIONS.md](AGENT-OPERATIONS.md#unattended-work-what-is-fine-vs-what-is-not).

## See also

- [`../AGENTS.md`](../AGENTS.md) — canonical project instructions.
- [`../DECISIONS.md`](../DECISIONS.md) — accepted product and technical
  decisions.
- [`../CONTRIBUTING.md`](../CONTRIBUTING.md) — contribution workflow for
  human contributors.
- [`../SECURITY.md`](../SECURITY.md) — vault threat model and reporting.
