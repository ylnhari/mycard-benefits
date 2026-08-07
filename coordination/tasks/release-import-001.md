# Initial release and private card import

Status: ready for publication
Owner: primary orchestrator
Approved: 2026-08-07

## Scope

- Inventory the owner-authorized Google Drive family card folders.
- Derive a private, deduplicated card manifest without copying card scans or
  payment credentials into the repository.
- Add a supported local-only import path, import records into the encrypted
  ignored vault, and validate counts without revealing secret fields.
- Run complete quality, privacy, packaging, and rendered-product gates.
- Obtain independent public-code reviews from authenticated Claude Opus and
  OpenCode DeepSeek V4 Flash.
- Create and push the initial public MyCard Benefits repository, then push the
  already approved Family Finance companion commit.

## Boundaries

- Drive document contents, owner names, PANs, expiry values, CVVs, PINs, and
  account identifiers never enter tracked files, agent prompts, logs, or Git.
- Delegated runners receive tracked public code only.
- The private manifest, import evidence, vault, recovery material, and backups
  stay under ignored local paths with restrictive permissions.
- Public benefit claims remain synthetic until separately reviewed.

## Routing decision

- Primary: private Drive discovery, security decisions, integration, import,
  push authorization recording, and final verification.
- Claude Opus: bounded read-only public-code/security review.
- OpenCode `opencode/deepseek-v4-flash-free`: bounded mechanical release audit.
- Smaller host workers: fallback only if one of the preferred runners is
  unavailable or fails repeatedly.

This minimizes premium context while avoiding the rework and privacy risk of
delegating financial documents or decrypted vault data.

## Checkpoint result

- Private import completed and count-only verification passed.
- Claude Opus approved the remediated tracked importer slice; no unresolved
  High/Medium finding remains after the live compatibility condition passed.
- OpenCode's bounded whole-repository audit timed out without output or edits.
- Complete deterministic gates passed: 201 MyCard tests, Ruff, strict mypy,
  dependency checks, build, package privacy checks, 207 Family Finance Python
  tests, and 51 Family Finance Node tests.
