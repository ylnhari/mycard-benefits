# Codex Instructions — mycard-benefits

## Purpose

Build and maintain MyCard Benefits: an open-source, local-first card vault and
verified benefits intelligence companion. The public catalog is shareable;
personal card records are private, local, and encrypted.

## Non-negotiable boundaries

1. Never commit, log, transmit, screenshot, or place in agent prompts any real
   PAN, CVV, PIN, owner identity, boarding pass, credential, or private card
   record. Tests and demos use values prefixed `SYNTHETIC-ONLY-`; synthetic PAN
   fixtures must also be deliberately non-numeric and cannot be Luhn-valid.
2. CVV and PIN support is consumer-controlled and local-only. Do not claim PCI
   compliance and do not add hosted secret storage or cloud secret sync.
3. Background agents and LLMs never receive decrypted vault values. They may
   request a protected local UI action; only the human-facing UI may reveal or
   copy plaintext after reauthentication.
4. Do not bypass authentication, CAPTCHA, robots restrictions, access controls,
   rate limits, or source terms. Block and report instead.
5. Source agents create candidates only. Publishing a catalog change requires
   approval by a human reviewer; ambiguous or high-impact claims require two
   independent human reviewers. Agents may assist review but cannot approve.
6. No purchase, card application, booking, redemption, upload, paid model call,
   public remote, push, or publication without its explicit gate. A gate is a
   dated human approval naming the exact action, transcribed to
   `coordination/events.jsonl` before execution; absence means no approval.
7. Bind the app to `127.0.0.1`. Remote access goes through an authenticated
   gateway; never widen the app bind to make remote access work.

## Data boundaries

- `catalog/` contains reviewed, independently written structured facts, source
  URLs, hashes, effective dates, and synthetic fixtures only.
- Runtime databases, vaults, keys, attachments, raw source captures, logs,
  backups, imports, and generated evidence live under ignored local paths.
- The unencrypted card envelope may contain only local UUIDs, catalog offering
  ID, lifecycle status, schema version, and timestamps.
- Never hand-edit runtime vault/database state. Use supported application APIs,
  migrations, import/export tools, and verified backups.

## Source policy

Use, in order: specific administering-party terms; issuer documents; card
network rules; merchant fulfillment terms; regulatory context; discovery-only
aggregators/community reports. Every assertion must retain provenance,
effective dates, retrieval time, content hash, confidence, and review state.
Missing or changed evidence makes an assertion `needs_review`, not active by
default. Read `docs/SOURCE-POLICY.md` before adding a source or adapter.

## Agent coordination

- Read `PROJECT_STATUS.md`, `DECISIONS.md`, and the assigned file under
  `coordination/tasks/` before starting.
- For bounded public-code or public-research work, prefer the lowest-cost
  verified capable runner in this order: the owner's authenticated Claude Code
  subscription, the locally listed `opencode/deepseek-v4-flash-free` route,
  then smaller host workers. Reserve the primary agent for intent, security
  judgment, integration, and verification. Verify runner/model identity at
  each use; never use `--dangerously-skip-permissions`.
- Append honest job/event state. Do not leave resumable context only in chat.
- Work only in the assigned files and scope. Stop after 2–3 repeated failures.
- A worker cannot approve its own change. Provide tests and evidence with every
  handoff.
- Claude and other delegated runners receive public code/data only. Quota
  blocks use `deferred_quota`; resume from the on-disk task, not memory.

## Architecture

- Python 3.12, FastAPI, SQLite/SQLAlchemy/Alembic, Jinja, and browser JavaScript.
- `src/mycard_benefits/catalog/`: catalog loading, validation, rule evaluation.
- `src/mycard_benefits/vault/`: cryptography and private persistence boundary.
- `src/mycard_benefits/candidates/`: immutable public candidate review store.
- `src/mycard_benefits/research/`: offline admitted-source job orchestration.
- `src/mycard_benefits/optimizer/`: pure purchase-route ranking engine.
- `src/mycard_benefits/qa/`: deterministic public catalog question answering.
- `src/mycard_benefits/templates/` and `static/`: human-facing public dashboard.
- `catalog/`: public authoring sources and generated release inputs.
- `tests/`: no network, no real data, temporary runtime directories only.

## Local application and ports

Resolve the port in this order: `--port` → `MYCARD_BENEFITS_PORT` → nearest
`ports.json` entry → documented clone fallback. Never read `next_available` in
application code and never hunt for a free port. Verify the health endpoint's
signed installation identity rather than trusting a port or app name alone.

## Quality gates

- Format/lint: `uv run ruff check .`
- Tests: `uv run pytest`
- Type checks once enabled: `uv run mypy src`
- Every schema, migration, parser, API, vault behavior, and UI flow needs tests.
- A startup test must prove the default bind is loopback and cannot silently
  widen to `0.0.0.0` or another non-loopback address.
- Network adapters use committed synthetic fixtures in CI; live checks are
  separate and non-blocking.
- Before a commit, scan tracked changes for secrets, real identifiers, absolute
  user paths, raw source content, and generated/runtime files.
- Before reporting UI work complete, verify rendered blank/demo/populated states
  on desktop and mobile, in both themes, with keyboard navigation.

## Repository and publication

This repository must remain clone-self-contained. Private shared instructions,
machine paths, ports, identities, and credentials are never project
dependencies. Local commits are allowed within an approved implementation;
creating a public remote or pushing requires a separate publication review and
explicit approval that names the commit range and destination. The dated human
approval is recorded in `coordination/events.jsonl`; no agent may create the
remote or push without citing that record.

## Living artifacts

`PRODUCT_REQUIREMENTS.md`, `ROADMAP.md`, `PROJECT_STATUS.md`, `DECISIONS.md`,
`docs/DECISION-TRACE.md`, `docs/QUESTIONNAIRE-DECISIONS.md`,
`docs/IDEA-LOG.md`, and the append-only files under `coordination/` describe
the current project. Update them in the same change whenever implementation,
requirements, decisions, or resumable job state changes; leaving them stale is
a defect.
