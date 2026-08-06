# Local alpha checkpoint verification

Date: 2026-08-07

## MyCard Benefits

- `uv run pytest`: 189 passed, including the final CLI loopback-bind and
  malformed-DEK regressions.
- `uv run ruff check .`: passed.
- `uv run mypy src`: passed for 27 source files in strict mode.
- `node --check src/mycard_benefits/static/app.js`: passed.
- `uv lock --check` and `uv pip check`: passed.
- `git diff --check`: passed after all intended untracked files were marked
  intent-to-add for complete coverage.
- `uv build`: source distribution and wheel built successfully.
- Isolated `uv run --no-project --with <wheel>` smoke: packaged synthetic
  catalog loaded; dashboard, catalog API, and Q&A returned success. The
  generated temporary signing identity was deleted after the check.
- Live listener: loopback-only; ordinary and nonce-signed health responses
  returned the expected MyCard identity fields after restart.
- Coverage checkpoint: 92% overall and 90% for the vault core.
- Final Claude Sonnet review reported no High/Medium vault finding. Its three
  Low cleanups were applied; 49 focused vault tests passed afterward.

## Rendered MyCard checks

- Desktop and responsive mobile geometry without horizontal document overflow.
- Dark and light themes.
- Ask navigation, Enter submission, button submission, Escape clear, result
  focus, synthetic examples, unsupported-question guidance, and safe external
  citation attributes.
- Add/reveal private controls remain disabled.
- No browser console warning/error entries.

## Family Finance companion

- 207 Python tests and 51 Node tests passed, including the extracted pure URL
  policy boundary cases; JavaScript syntax and diff checks passed.
- Rendered Cards-page controls, bundled-guide fallback, invalid and valid URL
  setup, successful local launch, responsive stacked actions, accessible dialog
  semantics, setting cleanup, and no new console errors were verified.
- DeepSeek V4 Flash policy review and a separate Terra popup-flow follow-up
  reported no unresolved High/Medium findings.
- Rover compatibility was checked against its local documentation: the
  launcher now unit-tests literal Tailscale `100.64.0.0/10` HTTP proxy URLs
  while continuing to reject other remote HTTP destinations.

## Remaining product gates

Real-card UI/API, network source fetching, catalog publication, remote identity
pinning, public remote creation, and push remain disabled or unperformed.
