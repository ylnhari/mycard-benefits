"""Deterministic tests for batch 3 of the Claude 30-task run.

Covers MC-059 (spend condition state shape), MC-062 (allowance reset-period
structure), and MC-064 (personalized/login-only evidence cannot be approved).
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date

import pytest

from mycard_benefits.catalog.allowance_period import AllowancePeriod, period_bounds
from mycard_benefits.catalog.condition_state import (
    SpendConditionAnswer,
    SpendConditionState,
    assert_no_transaction_shaped_fields,
)
from mycard_benefits.catalog.loader import CatalogLoadError, _assertion

EVIDENCE_ID = "40000000-0000-4000-8000-000000000000"


# ---- MC-059: spend condition state shape ----------------------------------


def test_spend_condition_state_is_closed_to_exactly_three_values() -> None:
    assert {member.value for member in SpendConditionState} == {"met", "not_met", "unknown"}


def test_spend_condition_answer_defaults_to_unknown_never_guessed() -> None:
    answer = SpendConditionAnswer(condition_id="SYNTHETIC-ONLY-min-spend")
    assert answer.state is SpendConditionState.UNKNOWN


def test_spend_condition_answer_is_immutable_and_rejects_invalid_state() -> None:
    answer = SpendConditionAnswer(condition_id="SYNTHETIC-ONLY-min-spend", state=SpendConditionState.MET)
    with pytest.raises(FrozenInstanceError):
        answer.state = SpendConditionState.NOT_MET  # type: ignore[misc]
    with pytest.raises(ValueError, match="condition_id"):
        SpendConditionAnswer(condition_id="")


def test_spend_condition_answer_shape_never_grows_a_transaction_field() -> None:
    assert_no_transaction_shaped_fields()


# ---- MC-062: monthly/quarterly/anniversary/calendar reset counters --------


def test_monthly_period_resets_on_the_first_of_the_next_month() -> None:
    bounds = period_bounds(AllowancePeriod.MONTHLY, date(2026, 2, 15))
    assert (bounds.start, bounds.end, bounds.resets_on) == (date(2026, 2, 1), date(2026, 2, 28), date(2026, 3, 1))


def test_quarterly_period_covers_three_calendar_months() -> None:
    bounds = period_bounds(AllowancePeriod.QUARTERLY, date(2026, 8, 9))
    assert (bounds.start, bounds.end, bounds.resets_on) == (date(2026, 7, 1), date(2026, 9, 30), date(2026, 10, 1))


def test_calendar_year_period_spans_january_to_december() -> None:
    bounds = period_bounds(AllowancePeriod.CALENDAR_YEAR, date(2026, 8, 9))
    assert (bounds.start, bounds.end, bounds.resets_on) == (date(2026, 1, 1), date(2026, 12, 31), date(2027, 1, 1))


def test_anniversary_period_window_and_reset_boundary_day_before_and_of() -> None:
    day_before = period_bounds(AllowancePeriod.ANNIVERSARY, date(2026, 3, 14), anniversary_month=3, anniversary_day=15)
    assert day_before.start == date(2025, 3, 15)
    assert day_before.resets_on == date(2026, 3, 15)

    day_of = period_bounds(AllowancePeriod.ANNIVERSARY, date(2026, 3, 15), anniversary_month=3, anniversary_day=15)
    assert day_of.start == date(2026, 3, 15)
    assert day_of.resets_on == date(2027, 3, 15)


def test_anniversary_period_clamps_feb_29_in_a_non_leap_year() -> None:
    bounds = period_bounds(AllowancePeriod.ANNIVERSARY, date(2026, 6, 1), anniversary_month=2, anniversary_day=29)
    assert bounds.start == date(2026, 2, 28)


def test_anniversary_fields_are_rejected_for_non_anniversary_periods() -> None:
    with pytest.raises(ValueError, match="only apply to AllowancePeriod.ANNIVERSARY"):
        period_bounds(AllowancePeriod.MONTHLY, date(2026, 1, 1), anniversary_month=1, anniversary_day=1)


# ---- MC-064: personalized/login-only offers cannot become public facts ---


def _raw_assertion(*, review_state: str, personalized: bool, with_review: bool = True) -> dict:
    reviews = (
        [{"id": "50000000-0000-4000-8000-000000000000", "reviewer_id": "SYNTHETIC-ONLY-reviewer", "reviewed_at": "2026-08-08T00:00:00Z", "decision": "approved"}]
        if with_review
        else []
    )
    raw: dict = {
        "id": EVIDENCE_ID,
        "source_policy_class": "issuer_document",
        "url": "https://example.invalid/synthetic-terms",
        "content_sha256": "a" * 64,
        "retrieved_at": "2026-08-07T00:00:00Z",
        "confidence": "high",
        "review_state": review_state,
        "reviews": reviews,
    }
    if personalized:
        raw["personalized"] = True
    return raw


def test_personalized_evidence_cannot_be_approved() -> None:
    with pytest.raises(CatalogLoadError, match="personalized or login-only evidence cannot be approved"):
        _assertion(_raw_assertion(review_state="approved", personalized=True), "test-path")


def test_personalized_evidence_may_still_be_needs_review() -> None:
    assertion = _assertion(_raw_assertion(review_state="needs_review", personalized=True, with_review=False), "test-path")
    assert assertion.personalized is True
    assert assertion.review_state == "needs_review"


def test_personalized_defaults_to_false_for_existing_records() -> None:
    assertion = _assertion(_raw_assertion(review_state="approved", personalized=False), "test-path")
    assert assertion.personalized is False


def test_personalized_field_must_be_boolean() -> None:
    raw = _raw_assertion(review_state="needs_review", personalized=False, with_review=False)
    raw["personalized"] = "yes"
    with pytest.raises(CatalogLoadError, match="personalized must be a boolean"):
        _assertion(raw, "test-path")
