<!--
Read CONTRIBUTING.md and AGENTS.md before opening a catalog-affecting PR.
Fill in every field below in the disclosure block; a maintainer will not
review a PR with an incomplete disclosure. The field names and rules here
match `src/mycard_benefits/catalog/contribution.py::validate_contribution_disclosure`.
-->

## Summary

<!-- What does this change, and why? -->

## Contribution disclosure (sources and conflict of interest)

```yaml
summary: ""                                   # 1-500 chars, plain-language summary of the change
primary_sources:                              # 1-10 anonymous HTTPS URLs backing every catalog assertion changed
  - "https://"
has_conflict_of_interest: false               # true if you or your employer is the issuer/network/merchant this PR concerns
conflict_of_interest_detail: null             # required, non-empty string when has_conflict_of_interest is true; must stay null otherwise
uses_only_synthetic_or_public_fixtures: true  # must be true — no real card numbers, credentials, or private records
```

## Checklist

- [ ] I read `AGENTS.md` and `docs/SOURCE-POLICY.md`.
- [ ] Every catalog assertion I added or changed carries a primary-source URL, effective date, retrieval date, and content hash.
- [ ] I did not copy source prose, screenshots, PDFs, logos, or bulk catalog content.
- [ ] I did not automate a source that lacks an admission record.
- [ ] I added or updated tests for this change.
- [ ] I updated the relevant durable task/status record (`TASKS.md`, `PROJECT_STATUS.md`, etc.).
- [ ] This PR contains no credentials, private records, raw evidence captures, local machine paths, or generated runtime state.
- [ ] I am not approving my own catalog assertion or candidate.
