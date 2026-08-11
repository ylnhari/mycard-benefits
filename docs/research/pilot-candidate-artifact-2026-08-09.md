# Pilot candidate artifact — 2026-08-09

This is an offline conversion of the two recorded pilot evidence documents.
No network request, source refresh, or source adapter ran in this batch.

## Deterministic reconciliation

- Candidate artifacts: **4**, all `needs_review` — Tata Neu Infinity RuPay Select **2** and
  Regalia Gold **2**.
- Evidence rows: **8** — `official_candidate` **4**, `blocked` **2**,
  `not_found` **1**, and unattached `needs_mapping` **1**.
- The blocked rows are RuPay Select concierge (HTTP 403, no reproducible
  content hash) and Regalia Gold Travel Edge (recorded hash, blocked by the
  internal classification label).
- Visa Meet & Assist remains unattached `not_found` for these pilots because the
  recorded Visa Infinite issuer-linkage requirement is unproven. Its complete
  international face-to-face spend predicate and exact retrieval timestamp
  (`2026-08-07T10:46:30Z`) are retained.
- The Visa-specific Tata Neu Priority Pass row remains unattached
  `needs_mapping`; no exact Visa Tata Neu offering exists in the catalog, so it
  is not a candidate and cannot be inferred onto the RuPay Select offering.
- Travel Edge's boarding-pass trigger, quarterly allowance, effective range,
  rule owner, source tier, retrieval time, locator, and content hash remain in
  the immutable manifest. The earlier statement-credit ambiguity is preserved
  as unresolved metadata; neither disputed value is selected or reproduced.

The candidate store contains only the four exact-offering supported rows. It cannot
approve, activate, or write catalog records, and the seeding author cannot
review its own candidates. No raw PDF/API body or internal document text is
copied into public catalog output.
