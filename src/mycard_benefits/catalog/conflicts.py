"""Explain which side of a recorded conflict is more authoritative, without deleting either.

`BenefitRule.conflicts_with` already names other benefits a rule's evidence
disagrees with (validated as a required, now-symmetric graph edge by the
loader). This module answers "which one wins" using only
`docs/SOURCE-POLICY.md`'s existing source-tier ordering (numerically lower
`source_tier` is more authoritative) — it never deletes, hides, or silently
prefers a rule; both sides of a conflict remain stored and this only labels
one of them.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import BenefitRule


@dataclass(frozen=True)
class ConflictExplanation:
    benefit_id: str
    conflicting_benefit_id: str
    benefit_best_tier: int
    conflicting_best_tier: int
    more_authoritative_benefit_id: str | None

    def __post_init__(self) -> None:
        if self.benefit_id == self.conflicting_benefit_id:
            raise ValueError("a benefit cannot conflict with itself")


def _best_tier(rule: BenefitRule) -> int:
    """The lowest (most authoritative) source_tier among a rule's evidence; 6 if it has none."""
    if not rule.evidence:
        return 6
    return min(assertion.source_tier for assertion in rule.evidence)


def explain_conflict(benefit: BenefitRule, conflicting: BenefitRule) -> ConflictExplanation:
    """Explain the authority relationship between two benefits recorded as conflicting.

    Raises `ValueError` if `conflicting.id` is not actually listed in
    `benefit.conflicts_with` — this function only explains a conflict that
    was already reviewed and recorded, it never infers one.
    """
    if conflicting.id not in benefit.conflicts_with:
        raise ValueError(f"{conflicting.id} is not recorded in {benefit.id}'s conflicts_with")
    benefit_tier = _best_tier(benefit)
    conflicting_tier = _best_tier(conflicting)
    if benefit_tier == conflicting_tier:
        winner = None
    elif benefit_tier < conflicting_tier:
        winner = benefit.id
    else:
        winner = conflicting.id
    return ConflictExplanation(
        benefit_id=benefit.id,
        conflicting_benefit_id=conflicting.id,
        benefit_best_tier=benefit_tier,
        conflicting_best_tier=conflicting_tier,
        more_authoritative_benefit_id=winner,
    )


def explain_all_conflicts(benefit: BenefitRule, benefits_by_id: dict[str, BenefitRule]) -> tuple[ConflictExplanation, ...]:
    """Explain every conflict recorded against `benefit`, preserving each one."""
    return tuple(
        explain_conflict(benefit, benefits_by_id[other_id])
        for other_id in benefit.conflicts_with
    )
