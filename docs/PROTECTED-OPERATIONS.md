# Protected local operations

The protected services are local Python seams, not browser endpoints. Audit
records contain an opaque event UUID, UTC timestamp, allowlisted action, and
success flag only. The default retention is 365 days; callers may choose a
bounded value and invoke purge. Audit files, backup files, recovery exports,
and attachment ciphertext stay under the selected local data directory.

Recovery creates a new authenticated vault envelope under a randomly generated
user-held recovery key. The key is returned once and is never persisted by the
application. Losing it is unrecoverable; there is no server-side reset. A
human must record it in an appropriate offline location and validate a restore
before relying on it.

Restore is a capability handoff, not a detached path-success result. The
restore caller receives a one-use `VerifiedRestoreLease`, keeps it open, and
calls `consume()` to activate the authenticated vault bytes before releasing
it. The lease retains the exact destination handle, reparse checks, and the
destination lock through that first consumption; on Windows its handle also
denies replacement/deletion sharing. A later path reopen is unverified and
must not be presented as the restore result.

Attachments use opaque UUID filenames and authenticated encryption. Agents may
receive the allowlisted metadata object but never attachment bytes, paths, or
plaintext. Supported purposes are boarding passes, vouchers, enrollment
confirmations, and membership documents. Expiry and retention are explicit and
bounded.

The current UI remains read-only. A future human-facing protected-flow UI must
perform reauthentication and the recovery-key ceremony before calling these
seams; no OS keyring or remote gateway is silently widened by this batch.
