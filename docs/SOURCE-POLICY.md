# Source Policy

Governs which sources may back a catalog assertion, in what order they are
preferred, and what automation is permitted against them. Read this before
adding a source, writing a parser adapter, or admitting a new source for
unattended work. This document elaborates `AGENTS.md`; it does not override
it. Any change here that would relax a boundary in `AGENTS.md` or
`DECISIONS.md` is out of scope and must go back to those files instead.

## Source tiers, most preferred first

1. Specific administering-party terms (the exact issuer/network/program page
   or document that governs the benefit in question).
2. Issuer documents (card terms, fee schedules, program guides).
3. Card network rules (Visa/Mastercard/Rupay/Amex program rules).
4. Merchant fulfillment terms (the merchant or partner honoring the benefit).
5. Regulatory context (central bank or regulator guidance affecting terms).
6. Discovery-only aggregators and community reports.

Tier 6 sources may only surface leads for a human or agent to chase down a
tier 1–5 source. A tier 6 source can never itself verify or justify an
`approved` assertion.

When two admitted sources disagree, prefer the higher tier. Record the
conflict rather than silently discarding the lower-tier source — see
`CATALOG-GOVERNANCE.md`.

## Source admission

A source must have an **admission record** before any adapter automates
requests against it. The admission record is authored and reviewed like a
catalog change (see `CATALOG-GOVERNANCE.md`) and states, at minimum:

- The source's tier (1–6 above) and the administering party it represents.
- The exact URL scope the adapter may request.
- Confirmation that the source's `robots.txt` and published terms permit the
  intended automated access, and any rate limit the source publishes or
  implies.
- The retrieval cadence the adapter will use.
- A maximum re-check interval no longer than 90 days. Time-limited promotions
  use 30 days or their remaining lifetime, whichever is shorter.
- The human reviewer who approved the admission and when. One dated human
  approval is sufficient; additional review may be recommended for high-impact
  or ambiguous sources but is not mandatory.

Until a source has an admission record, work against it is manual and
non-automated, or the source is left as a discovery-only lead per tier 6.

## Provenance requirements

Every catalog assertion must retain, for its lifetime:

- Source URL and tier.
- Effective date(s) the terms describe.
- Retrieval timestamp.
- Content hash of the retrieved material (see `EVIDENCE.md`).
- Confidence level.
- Review state.

Missing or changed evidence moves an assertion to `needs_review`. Assertions
are never active by default while in that state; see `CATALOG-GOVERNANCE.md`
for how review states progress.

## No reproduction of source content

Do not copy source prose, screenshots, PDFs, logos, or bulk catalogs into this
repository, an evidence record, an agent prompt, a commit, or an issue.
Catalog assertions are independently written structured facts plus a pointer
(URL + hash) to the source, not a copy of it. A short, clearly attributed
factual quote used only to justify an ambiguous assertion during review is
the only exception, and it still may not be committed verbatim into
`catalog/`.

## Permitted unattended work vs. forbidden bypass

Source work — including scheduled or agent-driven work — may run unattended
when it stays inside these boundaries:

**Permitted:**
- Fetching pages or documents that are publicly reachable without logging in.
- Parsing content the source has published for public consumption.
- Respecting the source's own rate limits, and backing off further on any
  ambiguity.
- Re-checking a previously admitted source on the cadence its admission
  record allows.

**Forbidden, always, with no exception:**
- Bypassing authentication (using credentials, sessions, or tokens the agent
  was not given specifically and knowingly for this purpose).
- Solving, working around, or automating past CAPTCHA challenges.
- Ignoring or evading `robots.txt` disallow rules.
- Bypassing access controls (paywalls, IP allowlists, geofencing, login
  walls) by any technical means.
- Exceeding a source's stated or implied rate limit, including by rotating
  identities, IPs, or user agents to evade detection.
- Violating a source's published terms of service.

If automation hits any of the forbidden conditions above, it must stop and
report the block — see `AGENT-OPERATIONS.md`
— never route around it.

## Related documents

- `EVIDENCE.md` — the structure and storage of retrieved evidence.
- `CATALOG-GOVERNANCE.md` — how a candidate assertion becomes a published fact.
- `AGENT-OPERATIONS.md` — what background agents may and may not do.
