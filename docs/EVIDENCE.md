# Evidence

Describes what an evidence record is, what it must contain, and where it
lives. Read `SOURCE-POLICY.md` first for the source tiers and admission
rules an evidence record depends on.

## What evidence is

Evidence is the retrieved material that backs one or more catalog assertions,
plus the structured metadata that makes the retrieval verifiable later.
Evidence is not the assertion itself: the assertion is the independently
written structured fact in `catalog/`; the evidence is what justifies it.

## Evidence record fields

Every evidence record carries:

- **Source URL** — the exact address retrieved.
- **Source tier** — one of the six tiers in `SOURCE-POLICY.md`.
- **Administering party** — who the source represents (issuer, network,
  merchant, regulator, aggregator).
- **Effective date(s)** — the date range the retrieved terms describe.
- **Retrieval timestamp** — when the content was fetched.
- **Content hash** — a hash (e.g. SHA-256) of the retrieved content, computed
  at retrieval time.
- **Confidence** — the reviewer's or adapter's confidence that the content
  supports the linked assertion(s).
- **Review state** — see below.
- **Linked assertion IDs** — the catalog assertion(s) this evidence supports.

## Review states

- `needs_review` — default state for anything new, or for anything whose
  hash no longer matches the last-approved retrieval. Not eligible to back
  an active catalog assertion.
- `reviewed` — a reviewer has read the evidence and the linked assertion, and
  has not yet recorded the approval needed by `CATALOG-GOVERNANCE.md`.
- `approved` — the evidence is sufficient to back its linked assertion(s).
- `rejected` — the evidence does not support the linked assertion; the
  assertion must be revised or removed.
- `superseded` — a newer evidence record has replaced this one for the same
  assertion; kept for history, not for active backing.

An assertion is only `active` in the published catalog while it has at least
one `approved` evidence record with a current (unchanged) content hash and one
dated human approval. Additional review may be recommended by risk tier but is
not required for activation.

## Immutability and audit trail

An evidence record's source URL, tier, effective dates, content hash, and
linked assertion IDs are immutable once created. Only its review state may
transition in place. Every retrieval or re-check appends a separate audit-log
entry with the timestamp, observed hash, and match/mismatch outcome; a
same-hash check never erases the prior retrieval history. Changed content
always creates a new evidence record in `needs_review` state.

## Storage boundary

Raw retrieved content (full page captures, downloaded documents, screenshots)
is private and local only. It lives under an ignored path — this repository
uses `evidence-private/` — and is never committed. `catalog/` and any
document in `docs/` may contain only the structured evidence record fields
above: URL, tier, party, dates, hash, confidence, review state, and linked
assertion IDs. See `SOURCE-POLICY.md` for why source prose is never
reproduced into tracked files.

## Canonical graph boundary

MC-215 adds `mycard_benefits.evidence_graph` as the lossless public interchange
form. Its immutable nodes bind an assertion to an admitted source document,
observation, and exact extraction span. The graph stores hashes and bounded
coordinates only, never raw source text or private values. Unknown fields and
future schema versions fail closed; its canonical hash is the candidate/release
binding.

Legacy records may be wrapped for migration, but a migrated record remains
`needs_review` and is not promotion-eligible until each current document,
observation, span, review, effective-state, and payload binding is revalidated.

## Change detection

Re-retrieving an admitted source and comparing the new content hash against
the last `approved` hash is how staleness is detected:

- Same hash — evidence stays `approved`; append a successful re-check entry.
- Different hash — the evidence record moves to `needs_review` and a new
  record is created for the new retrieval. The linked assertion is
  `needs_review` until the new evidence is reviewed.

## Freshness and retention

Every source admission record defines a maximum re-check interval. It may not
exceed 90 days; time-limited promotions must be checked at least every 30 days
and again before their stated end date. Missing the interval automatically
moves linked assertions to `needs_review`. Superseded raw evidence retention is
still a deployment-owner choice, but deleting it never changes the immutable
public hash/history record.

## Related documents

- `SOURCE-POLICY.md` — source tiers, admission, and automation boundaries.
- `CATALOG-GOVERNANCE.md` — how evidence review states gate publication.
