# OpenCode worker result - MC-098 optimizer API

Status: COMPLETE
Task: MC-098 (expose the reviewed pure purchase-route optimizer through a
narrowly scoped loopback API)
Runner: OpenCode free route, `opencode/deepseek-v4-flash-free`
Branch: `agent/mc098-opencode`
Base: `33a866c2c402b976cb59b03af2ae6c803df51d18`
Push authorized: no (local commit only)
Date: 2026-08-07

## Files

- `src/mycard_benefits/optimizer/router.py` (new) - the API adapter: request
  and response pydantic models mirroring the engine dataclasses, bounded
  ephemeral `POST /api/v1/optimizer/routes`, sanitized errors, `no-store`.
- `src/mycard_benefits/app.py` - registers `create_optimizer_router()`.
- `tests/test_optimizer_api.py` (new) - 8 deterministic synthetic API tests.
- `TASKS.md` - MC-098 marked `[x]`.
- `PROJECT_STATUS.md` - Completed bullet added; "Next planned slice" and
  "Not yet safe" wording updated for the loopback-only surface.
- `docs/PURCHASE-OPTIMIZER.md` - new "Loopback API" section.
- `docs/README.md`, `README.md` - exposure wording updated.
- `coordination/tasks/opencode-mc098.md` - worker-result section appended.

## Design decisions

- Single endpoint `POST /api/v1/optimizer/routes`; no state, no other
  optimizer routes (asserted via the OpenAPI path set). GET/unknown paths
  return 405/404.
- The body is parsed manually after a hard size check (128 KiB -> 413) so an
  oversized request is rejected before validation or the engine runs.
- Pydantic enforces only structural bounds (route/component/fee/ref counts,
  text lengths, money as decimal strings or integers; JSON floats rejected
  for exactness). All semantic rules (currency, UUID, URL origin, freshness,
  review, expiry, evidence age, stacking, fees, caps) stay in the reviewed
  engine unchanged; engine `ValueError` maps to 422 with its value-free
  message. Ranking rules were not reimplemented.
- Validation errors are sanitized to `loc`/`msg`/`type` only - request values
  are never echoed back, logged, or persisted.
- Stale/unreviewed/inactive/incompatible/ineligible routes are first-class
  output: the engine drops them into `rejected_routes` with reasons and the
  response carries them; status `no_verified_route` plus guidance when
  nothing ranks.
- Response models are explicit pydantic mirrors of the engine dataclasses
  (`from_attributes`), so Decimal -> string, date -> ISO, enum -> value in a
  deterministic JSON contract. A test asserts byte-identical responses for
  repeated calls and equality with the engine's own serialized output built
  independently in the test.
- Ephemerality is enforced by construction (no file/network I/O in the
  router) and proven by tests: no filesystem change under the data dir, no
  log record containing request values, no marker in error bodies.

## Exact commands and results

- `uv run ruff check .` -> All checks passed
- `uv run mypy src` -> Success: no issues found in 32 source files
- `uv run pytest` -> 254 passed, 1 warning (pre-existing httpx deprecation)
- `node --check src/mycard_benefits/static/app.js` -> OK (no JS changes)
- `uv build` -> both sdist and wheel built successfully
- `git diff --check` -> clean

## Final diff inspection

No secrets, credentials, machine paths, real identifiers, or generated
artifacts. `dist/` output is ignored. The only `.invalid` hosts are
SYNTHETIC-only fixtures in tests and documentation, never in production code
or response paths.

## Risks / notes for review

- The endpoint intentionally documents no request-body schema in OpenAPI
  (manual parsing for the 413 cap); the contract is documented in
  `docs/PURCHASE-OPTIMIZER.md` "Loopback API".
- Bounds: 128 KiB body, 20 routes, 8 components/route, 5+5 fees, 8 source
  refs, 8 origins, text caps 200/300/2048. Increase only with a documented
  reason and tests.
- The response is capped by the request bounds; maximal-input test asserts
  < 500 KB and determinism.
- No browser verification was performed: MC-098 deliberately adds no UI.
- Manager should independently review and integrate; worker did not merge,
  rebase, or push.

## Commit

Local commit on `agent/mc098-opencode` (hash recorded in the task file and
by the commit message); no push.
