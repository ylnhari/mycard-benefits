# Public catalog releases

`mycard_benefits.release.export_snapshot` validates the catalog, creates a
versioned directory, and writes SHA-256 checksums for every JSON file. A
verified install stages the new tree, records a durable journal, and commits
it into a content-addressed `.catalog.verified` store before switching the live
tree and `.catalog.active` pointer. Verified snapshots are immutable; an
interruption never replaces the last-known-good copy with an unverified active
tree. Recovery validates manifests and hashes, quarantines incomplete/corrupt
trees, and fails closed if no verified snapshot remains. The legacy
`.catalog.previous` path is retained only as a validated compatibility LKG, and
`rollback_catalog` prefers that validated immediate predecessor, then falls
back to another verified snapshot without consuming it. The install lock file
is restart evidence only; an exclusive OS-held lock is the sole ownership
authority, so a crash-surviving artifact cannot block a later process or let a
PID/clock claim take over a live owner. Accepted file and directory transitions
use platform-aware durability barriers and fail closed when a parent-directory
barrier is unavailable.
Invalid, incomplete, or checksum-mismatched snapshots are rejected.

The current mechanism is checksum/integrity based and offline. It is not a
cryptographic signature or proof of publisher identity; no signed release is
claimed in this batch.
