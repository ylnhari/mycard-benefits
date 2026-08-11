# Testing and network boundaries

## Required fixture-only gate

The required quality gate is deliberately fixture-only. It runs strict mypy,
Ruff, deterministic pytest, JavaScript syntax validation, and the package build
without a source adapter, browser profile, vault, candidate approval, or live
request:

```powershell
$env:MYCARD_BENEFITS_NO_DOTENV = "1"
uv run ruff check .
uv run mypy src
uv run pytest -q -m "not rendered_ui"
node --check src/mycard_benefits/static/app.js
uv build
```

`.github/workflows/fixture-quality.yml` is the corresponding required CI job.
It must remain independent of live-source checks.

## Clean-clone offline verification

After committing a clean worktree, run:

```powershell
python scripts/verify_clean_clone_offline.py
```

The verifier uses `git clone --local` and `uv sync --offline --frozen` before
running the same quality gates inside the clone. It neither reads `.env` nor
uses runtime data. This verifies an offline clone only when the machine already
has the required uv packages cached; it intentionally fails on a cold cache and
does not claim to bootstrap dependencies without a network.

## Opt-in live checks

There is no live source adapter at present. Fixture CI therefore makes no live
request. The separate `live-source-checks.yml` workflow is manual-only, requires
an explicit input, and is non-blocking. Its current harness reports that no
adapter is registered and makes no network request. A future adapter must retain
that explicit opt-in boundary and must not be added to fixture CI.
