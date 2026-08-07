# Vault import release review

Date: 2026-08-07
Scope: tracked public importer/vault code only

## Claude Opus

Authenticated Claude Code 2.1.220 with Opus reviewed the complete importer
slice. The first pass found one High and five Medium issues. The implementation
was changed before commit to:

- pin vault storage to the app-owned `<data-dir>/private/vault.json` path;
- create the vault before writing the OS keyring credential, eliminating the
  concurrent overwrite/delete race;
- preserve the key after any completed creation so a failed batch can be
  retried without `--create`;
- validate the plaintext offering identifier and encrypted field contract
  before side effects and again in the vault core;
- remove exception chaining that could retain private manifest text;
- add parser, concurrency, keyring-failure, interactive-prompt, existing-vault,
  atomicity, and direct-core regression tests.

The final closure pass reported no unresolved High findings. Its only Medium
was conditional compatibility risk from enforcing the offering identifier on
read. The condition was closed by successfully opening the existing local
vault after the change and verifying its non-secret count. Opus therefore
approved the exact tracked slice for commit. Remaining observations were Low
documentation/test-quality notes and were either fixed in the reviewed slice
or explicitly non-blocking.

Private paths, `data/`, `imports/`, `.env`, credentials, and card records were
excluded from every Claude prompt and read scope.

## OpenCode DeepSeek V4 Flash

The authenticated local OpenCode server accepted the whole-repository release
audit with model `opencode/deepseek-v4-flash-free`. The bounded five-minute run
ended without output or file changes. It is recorded as a timeout, not an
approval. Deterministic release gates remain owned and verified by the primary.

## Direct gates at review checkpoint

- `uv run ruff check .`: passed.
- `uv run mypy src`: passed for 29 source files.
- Focused vault/import tests: 61 passed.
- Existing OS-keyring vault verification: passed with the expected count.
- Complete MyCard suite: 201 passed with one upstream deprecation warning.
- Locked dependency and installed-package checks: passed.
- Wheel and sdist builds: passed; neither contains private runtime paths.
- Family Finance regression suite: 207 Python and 51 Node tests passed.

The first dependency-cold clone then exposed one optional-keyring strict-mypy
failure hidden by the installed extra. An explicit cast to the already-defined
keyring protocol was added; the clean-clone gate must be repeated before push.

The repeated clean clone at commit `c037ccf` passed locked setup without the
keyring extra, Ruff, strict mypy, all 201 tests, and both package builds.

Post-push verification found public MyCard `main` at `657bcc8` and public
Family Finance `main` at `e90f073`, each matching its local branch.
