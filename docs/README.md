# Documentation Index

## Start here if you just want to use the app

- **[USER-GUIDE.md](USER-GUIDE.md)** — the complete guide for a normal user:
  what the app does and does not do, what actually works today, five-minute
  Windows PowerShell setup, getting around the dashboard, searching the 69-variant
  card catalog, importing your own cards and viewing them in the read-only **My
  Cards** list, the optional Family Finance button, using it from your phone
  through an authenticated gateway, what stays private, how to read verified
  versus needs-review, troubleshooting, and removal.
- [FAMILY-FINANCE-INTEGRATION.md](FAMILY-FINANCE-INTEGRATION.md) — the optional
  companion button: setup, the privacy boundary, what happens when the app is
  not running, and how to remove the link.
- [VAULT-IMPORT.md](VAULT-IMPORT.md) — the supported one-time private card
  import: manifest fields, interactive or OS-keyring unlock, the recovery
  warning, and the count-only verification command. The CLI is still the only
  write path; the browser **My Cards** view is read-only and needs the
  keyring-backed vault plus a gateway-authenticated browser.
- [`../SECURITY.md`](../SECURITY.md) — what the vault protects against, what it
  cannot protect against, and how to report a problem safely.

Everything below this point is for people maintaining or contributing to the
project. You do not need any of it to use the app.

## Three things worth knowing even as a user

**How a claim earns trust.** Every catalog statement keeps its source and source
tier, a content fingerprint, a retrieval time, effective dates, a confidence
level, and a review state — for its whole lifetime. A human must approve it;
ambiguous or high-impact claims need two independent reviewers; no agent can
approve anything. If evidence is missing or has changed, the statement moves to
`needs_review` and is not treated as active. Expired benefits are kept as
history rather than deleted. This is why the catalog currently lists far more card
variants than benefits: a variant is a public product identity, while a benefit is
a claim that must first pass official-source review.

**Private cards stay private even when the browser shows them.** The read-only
**My Cards** view requires a current signed browser session from the
authenticated gateway, fails closed without one, opens the OS-keyring-encrypted
vault server-side, and returns envelope metadata only — card UUID, catalog
offering, lifecycle, timestamps, and any linked replacement record — with
`no-store`. PAN, CVV, PIN, nickname, notes, cardholder name, and expiry are never
sent to the browser. Add, edit, delete, reveal/copy, and owner/expiry/replacement
reconciliation remain future protected work.

**The hardest rule.** Source work, including scheduled and agent-driven work,
may run unattended — but it may never bypass authentication, CAPTCHA, robots
restrictions, access controls, rate limits, or a source's terms. When automation
hits one of those, it stops and reports; it does not route around it. This is
stated in full, with what counts as fine versus forbidden, in
[SOURCE-POLICY.md](SOURCE-POLICY.md#permitted-unattended-work-vs-forbidden-bypass)
and [AGENT-OPERATIONS.md](AGENT-OPERATIONS.md#unattended-work-what-is-fine-vs-what-is-not).

## Contributor and policy documents

`AGENTS.md` and `DECISIONS.md` at the repository root remain the canonical
policy; the documents here elaborate them and must not contradict them. If
following a document here would require relaxing a boundary in `AGENTS.md` or
`DECISIONS.md`, that is a policy question for the repository owner, not a
documentation change — see each document's own notes on unresolved questions.

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
  ranking, value classes, stacking, affiliate neutrality, and the ephemeral
  loopback API. The engine is exposed only through that loopback API in this
  release, not through the UI.
- [IDEA-LOG.md](IDEA-LOG.md) — durable owner ideas and discovery leads that are
  not approved catalog facts.
- [DECISION-TRACE.md](DECISION-TRACE.md) — concise trace from the initial
  questionnaire and subsequent owner choices into the current contract.
- [QUESTIONNAIRE-DECISIONS.md](QUESTIONNAIRE-DECISIONS.md) — numbered record of
  all 120 accepted defaults and the later revisions that supersede them.
- [`research/pilot-official-source-leads.md`](research/pilot-official-source-leads.md)
  — discovery-only official leads for the first two pilot offerings.
- [`research/pilot-benefit-source-map-2026-08-07.md`](research/pilot-benefit-source-map-2026-08-07.md)
  — current issuer/network candidates, evidence gaps, and conflicts for Tata
  Neu Infinity and Regalia Gold; none is active merely because it appears here.

## Maintainer audit trail — not documentation

`coordination/` outside this folder is the maintainers' audit and resume
evidence, not guidance for anyone. It holds task briefs under
`coordination/tasks/`, append-only `jobs.jsonl` and `events.jsonl` records, and
code-review results under `coordination/evidence/`. Two reasons it is committed:
sensitive actions in this project require a dated written human approval that
can be audited afterwards rather than taken on trust, and work spans sessions
and delegated runners, so resumable state must live on disk instead of in a
transcript. Files named like `*-review-001.md` are review records. Regular users
can ignore all of it; nothing there changes how the app behaves.

## See also

- [`../README.md`](../README.md) — project overview and quick start.
- [`../AGENTS.md`](../AGENTS.md) — canonical project instructions.
- [`../DECISIONS.md`](../DECISIONS.md) — accepted product and technical
  decisions.
- [`../PROJECT_STATUS.md`](../PROJECT_STATUS.md) — current milestone, what is
  complete, and what is explicitly not yet safe.
- [`../ROADMAP.md`](../ROADMAP.md) — planned slices and their gates.
- [`../CONTRIBUTING.md`](../CONTRIBUTING.md) — contribution workflow for
  human contributors.
- [`../SECURITY.md`](../SECURITY.md) — vault threat model and reporting.
