# Local release governance

The repository provides local evidence checks; they do not create or imply
GitHub branch protection, pull-request approval, publication, signing, legal
acceptance, or deployment authorization.

## Required local sequence

1. Validate every JSON contribution under the supported
   `catalog/contributions/` and `coordination/contributions/` paths with
   `uv run --offline python scripts/validate_contribution.py --schema catalog/schema/contribution.schema.json --all`.
2. Inspect the exact unpushed range with
   `uv run --offline python scripts/release_candidate_check.py --base <local-base-sha>`.
   The command uses local Git objects and never fetches, pushes, or changes refs.
3. Check same-change living-artifact consistency with
   `uv run --offline python scripts/check_living_artifacts.py --base <local-base-sha>`.
4. Run `uv run python scripts/generate_compliance_checklist.py` and attach the
   resulting review input to the local handoff. It is not an approval record.
5. Run Ruff, mypy, pytest, JavaScript syntax checks, package build, and
   `git diff --check`.

Future pushes require a dated human approval naming the exact commit range and
destination in `coordination/events.jsonl` before execution. Force-pushes and
history rewrites remain prohibited. A reviewer must be independent of the
author; silence is not approval.

The PR governance job is defined with `pull_request_target`, so its workflow and
scanner come from the trusted base branch. It fetches the event's full
`pull_request.head.sha` directly, requires the fetched object to resolve to that
exact SHA, and scans it only as an unexecuted Git object. It never trusts a
mutable pull or branch ref. For an all-zero new-branch `before`, the exact range
starts at Git's empty-tree object so every initial commit and path is included.
It has only
`contents: read` permission, invokes no live-source checks, and uploads no
private artifacts. Hosted checkout/action setup and frozen dependency
acquisition may use the network; every project check then uses offline uv mode.
The separate manual live-source workflow is opt-in and non-blocking. Local
offline mode means no fetch, network, or dependency resolution is attempted;
hosted CI cannot by itself attest that a pinned third-party SHA still denotes
the intended upstream source or that repository branch protection is enabled.
