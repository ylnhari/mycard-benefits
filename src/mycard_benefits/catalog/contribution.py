"""Validated schema for a public catalog contribution (pull request).

`CONTRIBUTING.md` already asks a human contributor for primary sources and
neutral wording; this module gives that request a machine-checkable shape so
a contribution missing a source or a conflict-of-interest answer fails
validation instead of silently reaching review. It validates the
contribution's *metadata* (who is proposing this, on what evidence, with
what disclosed interest) — the catalog record itself is validated by the
catalog loader and schema gates, which this does not duplicate or replace.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

MAX_SOURCES = 10
MAX_URL_LENGTH = 2048
MAX_DETAIL_LENGTH = 2000
MAX_SUMMARY_LENGTH = 500


class ContributionValidationError(ValueError):
    pass


def _anonymous_https(url: str, field: str) -> None:
    if not isinstance(url, str) or len(url) > MAX_URL_LENGTH:
        raise ContributionValidationError(f"{field} must be a bounded string")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ContributionValidationError(f"{field} must be an anonymous HTTPS URL")


@dataclass(frozen=True)
class ContributionDisclosure:
    """The conflict-of-interest and sourcing disclosure required on every contribution.

    `has_conflict_of_interest` must be answered explicitly (there is no
    default) — see `__post_init__`, which is the actual gate, since a
    dataclass field cannot itself express "no default value."
    """

    summary: str
    primary_sources: tuple[str, ...]
    has_conflict_of_interest: bool
    conflict_of_interest_detail: str | None
    uses_only_synthetic_or_public_fixtures: bool

    def __post_init__(self) -> None:
        if not self.summary or len(self.summary) > MAX_SUMMARY_LENGTH:
            raise ContributionValidationError(f"summary must be 1-{MAX_SUMMARY_LENGTH} characters")
        if not self.primary_sources or len(self.primary_sources) > MAX_SOURCES:
            raise ContributionValidationError(f"primary_sources must contain 1-{MAX_SOURCES} URLs")
        for url in self.primary_sources:
            _anonymous_https(url, "primary_sources entry")
        if len(self.primary_sources) != len(set(self.primary_sources)):
            raise ContributionValidationError("primary_sources must not contain duplicates")
        if not isinstance(self.has_conflict_of_interest, bool):
            raise ContributionValidationError("has_conflict_of_interest must be answered true or false")
        if self.has_conflict_of_interest:
            if not self.conflict_of_interest_detail or len(self.conflict_of_interest_detail) > MAX_DETAIL_LENGTH:
                raise ContributionValidationError(
                    "conflict_of_interest_detail is required and bounded when has_conflict_of_interest is true"
                )
        elif self.conflict_of_interest_detail:
            raise ContributionValidationError("conflict_of_interest_detail must be empty when there is no disclosed conflict")
        if not self.uses_only_synthetic_or_public_fixtures:
            raise ContributionValidationError(
                "a contribution must confirm it uses only synthetic or already-public fixtures, per AGENTS.md"
            )


def validate_contribution_disclosure(raw: dict[str, object]) -> ContributionDisclosure:
    """Validate a contribution's raw (for example, PR-template-parsed) disclosure fields.

    Raises `ContributionValidationError` naming exactly what is missing or
    invalid; never guesses a default for a required field.
    """
    required = {
        "summary",
        "primary_sources",
        "has_conflict_of_interest",
        "conflict_of_interest_detail",
        "uses_only_synthetic_or_public_fixtures",
    }
    missing = required - raw.keys()
    if missing:
        raise ContributionValidationError(f"missing required disclosure fields: {', '.join(sorted(missing))}")
    unexpected = raw.keys() - required
    if unexpected:
        raise ContributionValidationError(f"unexpected disclosure fields: {', '.join(sorted(unexpected))}")
    primary_sources = raw["primary_sources"]
    if not isinstance(primary_sources, (list, tuple)) or not all(isinstance(item, str) for item in primary_sources):
        raise ContributionValidationError("primary_sources must be a list of URL strings")
    summary = raw["summary"]
    detail = raw["conflict_of_interest_detail"]
    if not isinstance(summary, str):
        raise ContributionValidationError("summary must be a string")
    if detail is not None and not isinstance(detail, str):
        raise ContributionValidationError("conflict_of_interest_detail must be a string or null")
    has_conflict = raw["has_conflict_of_interest"]
    uses_fixtures = raw["uses_only_synthetic_or_public_fixtures"]
    if not isinstance(has_conflict, bool) or not isinstance(uses_fixtures, bool):
        raise ContributionValidationError("has_conflict_of_interest and uses_only_synthetic_or_public_fixtures must be booleans")
    return ContributionDisclosure(
        summary=summary,
        primary_sources=tuple(primary_sources),
        has_conflict_of_interest=has_conflict,
        conflict_of_interest_detail=detail,
        uses_only_synthetic_or_public_fixtures=uses_fixtures,
    )
