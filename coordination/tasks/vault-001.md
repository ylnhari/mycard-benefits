# Task vault-001 — Encrypted vault boundary

Owner: primary. Independent reviewer required.

Implement the cryptographic design in `DECISIONS.md` and the approved plan using
maintained libraries. The unencrypted envelope contains only allowed fields.
No plaintext secret may enter logs, URLs, exceptions, notifications, agents, or
test artifacts. Use only synthetic markers and temporary directories.

Required gates: key wrapping/recovery, tamper failure, auto-lock, reauth,
one-use reveal/copy actions, redacted logs, encrypted backup/restore, and a
fresh-machine recovery test. Do not accept real data before approval.

## Status — 2026-08-07

Core implementation and 49 focused tests are complete. DeepSeek and final
Claude Sonnet counterpart reviews found no High/Medium issues; all three Sonnet
Low cleanup suggestions were applied and retested. No vault API/UI is enabled,
so the real-data prohibition remains in force. See
`coordination/evidence/vault-review.md` and `vault-claude-final.md`.
