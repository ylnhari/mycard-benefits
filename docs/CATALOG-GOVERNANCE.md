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

- **Source contributor** — proposes. Produces candidate assertions and
  evidence records; automated source execution is not part of this local
  consumer release.
- **Independent reviewer** — a human who approves or rejects and whose recorded
  identity differs from the candidate author's identity.
- **Second reviewer** — a different human who may be recommended in addition
  to the first for enhanced, ambiguous, or high-impact claims. This is risk
  context, not a mandatory activation gate.

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
3. If it holds up, the reviewer moves the evidence to `approved` and either
   approves or requests changes on the assertion. One dated human approval is
   sufficient at every review tier.
4. Enhanced, ambiguous, and high-impact claims should surface a recommendation
   for a second independent human review when one is available. The recommendation
   does not block activation; the reviewer must still resolve conflicts and
   preserve uncertainty in the structured claim.
5. Once the human approval is recorded, the evidence state becomes `approved`
   and the assertion is eligible for the next release snapshot. Agents still
   cannot approve candidates, and authors cannot approve their own work.

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

## Movie and ticket benefits

Movie rules use the common `eligibility` predicates for conditions and the
common `allowance` object for caps or usage windows. A `benefit_type: movie`
record additionally carries a bounded `provider`, an anonymous HTTPS
`official_reference`, ordered `redemption_steps`, and explicit `exclusions`.
These fields describe how a user can verify and use a ticket or voucher offer;
they do not authorize checkout, redemption, affiliate routing, or a claim that
an issuer or merchant currently offers it. Missing or changed evidence keeps
the rule in `needs_review`, which is never treated as an active benefit.

## Release process

Approved, active assertions compile to a deterministic JSON snapshot as the
release artifact. The YAML source of truth stays human-authored and
reviewable; the JSON snapshot is generated, not hand-edited.

## Related documents

- `SOURCE-POLICY.md` — where an assertion's backing evidence is allowed to
  come from.
- `EVIDENCE.md` — the record structure and review states referenced above.
- `AGENT-OPERATIONS.md` — the boundaries an agent operates under while
  proposing candidates.
