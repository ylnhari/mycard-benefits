# Vault review evidence

Review date: 2026-08-06 to 2026-08-07

Scope: synthetic-only local vault implementation and tests. The dashboard still
rejects real-card entry and exposes no vault API.

## Claude review

Claude Code's read-only security review identified:

- a transient Windows null-DACL window during permission setup;
- no authentication of the complete envelope, allowing record removal,
  reordering, or splicing despite per-record AEAD;
- deny-list field validation and unknown-field compatibility concerns;
- passive listing extending the idle session lifetime;
- missing in-process locking and a potentially indefinite POSIX lock wait; and
- smaller backup-creation and bounded-read issues.

## Resolution

- Windows permissions are now applied once with a protected, single-user DACL,
  read back, and tested on Windows.
- Backup partial-file cleanup is tested.
- Passive listing no longer refreshes activity and sessions have an absolute
  lifetime.
- The pre-release vault format is now v2 only. It adds a DEK-derived MAC over
  the complete canonical envelope; v1 is rejected rather than silently
  migrated. Delete, reorder, metadata mutation, and cross-vault splice tests
  were added.
- Persisted secrets now use an exact field allow-list. Unknown fields fail
  closed on both write and open.
- All state and mutations use an in-process reentrant lock plus bounded
  cross-process locks on Windows and POSIX.
- Reads, digests, copies, and backup/restore paths are bounded and chunked;
  staged backup failures roll back safely.
- Passphrase and KDF inputs are bounded, failures are generic, and reveal grants
  are one-use, reauthenticated, and time-limited.

The final DeepSeek V4 Flash read-only audit reported no High or Medium findings.
A subsequent bounded Claude Sonnet review independently reached the same result.
Its three Low cleanup suggestions were applied: real-buffer MAC-key scrubbing,
removal of an unused session identifier, and an explicit 32-byte unwrapped-DEK
check with regression coverage. See `vault-claude-final.md`.

Forty-nine focused vault tests, 189 complete repository tests, repository lint,
and strict mypy passed after those changes. Accepted threat-model limits are
whole-file rollback without an external monotonic anchor, best-effort plaintext
zeroization in Python, Windows directory-entry durability, and the requirement
for a trustworthy local filesystem/OS account. Real-card controls remain
disabled until a separately reviewed protected API/UI exists.
