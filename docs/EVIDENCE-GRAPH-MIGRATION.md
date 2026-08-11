# Evidence-graph migration

The canonical evidence graph is an additive compatibility boundary for public
catalog and candidate records. It stores immutable hashes, dates, identifiers,
and extraction coordinates only; raw retrievals remain ignored local evidence.

Existing candidate rows are not guessed into graph nodes. A future guarded
store migration may attach a row only after resolving every exact source,
observation, span, review, effective-state, and payload binding. Until then,
legacy and incomplete rows remain `needs_review` and are ineligible for human
promotion. Applying a migration must create a validated backup and an
append-only lineage event before switching the application-owned store.

The effective promotion boundary is similarly additive: it reads the fixed
`candidates.sqlite3` store, checks the canonical graph and catalog fingerprint,
requires durable reviewer authorization, and records an integrity-bound audit
receipt. No candidate is activated by this release or by an import of this
document.
