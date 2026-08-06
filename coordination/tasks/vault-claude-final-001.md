# Task vault-claude-final-001 — Final Sonnet vault security review

Run after the owner's Claude subscription resets. Use the normal authenticated
Claude Code CLI with Sonnet, read-only tools, and no dangerous permission flag.

Read only:

- `AGENTS.md`
- `SECURITY.md`
- `DECISIONS.md`
- `src/mycard_benefits/vault/`
- `tests/test_vault.py`
- `coordination/evidence/vault-review.md`

Do not access ignored runtime directories, `.env`, data, backups, logs, browser
state, or anything outside this public/synthetic repository. Do not edit files.

Review cryptographic construction and key separation; authenticated envelope
coverage; KDF bounds; parsing/resource limits; atomic persistence, rollback,
and backup behavior; Windows/POSIX permissions and locking; concurrency;
generic errors; lifecycle, reauthentication, auto-lock, and one-use reveal;
unknown-field rejection; and accidental plaintext/logging paths. Separate
High/Medium findings from Low/accepted threat-model limitations. Cite exact
file and line numbers and propose concrete fixes. Explicitly state when no
High/Medium finding remains.

The dashboard has no vault API or real-card controls. No real data is in scope.

## Status — 2026-08-07

Completed with Claude Code 2.1.220 using Sonnet and read/search tools only. No
High or Medium finding remained. Three Low cleanups were applied by the primary
and passed 49 focused and 189 complete tests. See
`coordination/evidence/vault-claude-final.md`.
