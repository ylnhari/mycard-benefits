# Catalog Governance

How a candidate catalog assertion becomes a published fact, and how the
catalog stays trustworthy afterward. Read `SOURCE-POLICY.md` and
`EVIDENCE.md` first.

## What the catalog is

The public catalog (`catalog/`) is a set of independently written structured
facts about card offerings and their benefits — never a copy of source
prose. It is human-authored YAML, compiled to deterministic JSON snapshots
for release. Each offering has a stable public slug plus an immutable UUID;
private card instances (in the vault, not the catalog) get their own
UUIDv7 and are never mixed into catalog identifiers.

## Roles

- **Source agent / contributor** — proposes. Produces candidate assertions
  and evidence records (see `SOURCE-ADAPTER-RUNBOOK.md` for automated
  sources; a human contributor follows the same shape manually).
- **Independent reviewer** — a human who approves or rejects and whose recorded
  identity differs from the candidate author's identity.
- **Second reviewer** — a different human, required in addition to the first
  for ambiguous or high-impact claims (see below).

A worker or contributor can never approve its own catalog change. Agents may
draft review notes but cannot hold either reviewer role. Reviewer identity and
the approval timestamp are part of the approval record.

## Review workflow

1. A candidate assertion arrives with one or more evidence records in
   `needs_review` state (see `EVIDENCE.md`).
2. A reviewer who did not author the candidate checks the assertion against
   the evidence: correct source tier, correct effective dates, neutral
   wording, no reproduced source prose, hash matches what was actually
   retrieved.
3. If it holds up, the reviewer moves the evidence to `reviewed` (or
   `approved` if only one reviewer is required — see below) and either
   approves or requests changes on the assertion.
4. Ambiguous claims (terms that could be read more than one way, or that
   depend on eligibility conditions not clearly stated in the source) and
   high-impact claims (benefits likely to be relied on for a real financial
   decision, or affecting many offerings at once) require a **second**,
   independent reviewer before the assertion can become `active`.
5. Once all required reviewers have approved, the evidence state becomes
   `approved` and the assertion is eligible for the next release snapshot.

## Conflicts between sources

When two admitted sources disagree on the same benefit:

- Prefer the higher-tier source per `SOURCE-POLICY.md`'s ordering.
- Do not silently drop the lower-tier source's evidence — keep it linked and
  note the conflict in review notes so a future change is not surprised by
  it.
- If the sources are the same tier and still disagree, the assertion stays
  `needs_review` until a reviewer can resolve or escalate the conflict; it
  does not default to either source's claim.

## Expired and historical benefits

Benefits that have expired remain in the catalog as clearly historical
structured facts — they are not deleted. This preserves the accepted
decision in `DECISIONS.md`; do not remove expired assertions during routine
maintenance.

## Release process

Approved, active assertions compile to a deterministic JSON snapshot as the
release artifact. The YAML source of truth stays human-authored and
reviewable; the JSON snapshot is generated, not hand-edited.

## Related documents

- `SOURCE-POLICY.md` — where an assertion's backing evidence is allowed to
  come from.
- `EVIDENCE.md` — the record structure and review states referenced above.
- `SOURCE-ADAPTER-RUNBOOK.md` — how automated candidates are produced.
- `AGENT-OPERATIONS.md` — the boundaries an agent operates under while
  proposing candidates.
