# Final Claude Sonnet vault review

Review date: 2026-08-07

Claude Code 2.1.220 ran with model `sonnet`, read/search tools only, and the
scope in `coordination/tasks/vault-claude-final-001.md`. It reported that the
scope was respected, no file was edited, and no ignored/runtime path was read.

## Result

**No High or Medium finding remains.** The review independently verified:

- Argon2id KEK wrapping, random AES-GCM DEK use, and HKDF domain separation;
- full canonical-envelope authentication before record parsing;
- KDF, file, record, digest, copy, and backup resource bounds;
- atomic persistence, backup rotation, and tested rollback behavior;
- a protected single-user Windows DACL with read-back verification;
- in-process and bounded cross-process locks;
- generic unlock/reauthentication failures;
- idle and absolute expiry plus one-use, passphrase-reauthenticated reveal;
- exact secret-field allow-list enforcement on write and open; and
- absence of logging/print/traceback paths in the vault package.

## Low findings resolved in this checkpoint

1. The envelope-MAC key is now the mutable buffer that is actually scrubbed in
   `core.py` (`_envelope_mac`, current lines 556-567), rather than scrubbing a
   throwaway copy.
2. The unused per-session identifier was removed.
3. Unwrapped DEKs must now be exactly 32 bytes (`core.py`, current lines 576-585),
   backed by `test_unwrapped_dek_must_be_256_bits`.

## Accepted limits / future gate

- Directory-entry fsync remains a no-op on Windows and relies on NTFS metadata
  journaling; this is a platform durability limit, not a confidentiality bypass.
- Whole-file rollback still requires an external monotonic anchor, and plaintext
  zeroization in Python remains best effort.
- The reveal method performs cheap card/field validation before Argon2id. This
  is not externally observable because no vault API/UI exists; timing behavior
  must be revisited before exposing that boundary.

Post-cleanup verification: 49 focused vault tests and 189 complete repository
tests passed, together with Ruff, strict mypy, dependency, JavaScript syntax,
diff, and package-build gates.
