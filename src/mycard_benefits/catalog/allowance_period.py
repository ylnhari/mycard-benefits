"""Deterministic reset-boundary arithmetic for allowance/counter periods.

`BenefitRule.allowance` already carries a free-form `period` string (see
`benefit.allowance.period` in `static/app.js`). This module gives that string
a closed, testable set of values and a pure function that answers "what
period is `as_of` in, and when does it reset?" — no persistence, no counting
of actual usage, which stays out of scope (usage counting is private,
per-card state, not a public catalog concern).
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum


class AllowancePeriod(StrEnum):
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNIVERSARY = "anniversary"
    CALENDAR_YEAR = "calendar_year"


@dataclass(frozen=True)
class PeriodBounds:
    """The inclusive [start, end] window `as_of` falls in, and its reset date.

    `resets_on` is the first day of the *next* window — the day the counter
    becomes usable again — so a caller never has to add a day to `end` to
    find it.
    """

    start: date
    end: date
    resets_on: date

    def __post_init__(self) -> None:
        if not self.start <= self.end < self.resets_on:
            raise ValueError("period bounds must satisfy start <= end < resets_on")


def _last_day_of_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def _clamped_date(year: int, month: int, day: int) -> date:
    """A date in (year, month) clamped to that month's real last day (handles Feb 29)."""
    return date(year, month, min(day, _last_day_of_month(year, month)))


def period_bounds(
    period: AllowancePeriod,
    as_of: date,
    *,
    anniversary_month: int | None = None,
    anniversary_day: int | None = None,
) -> PeriodBounds:
    """Return the reset-boundary window `as_of` falls in for `period`.

    `anniversary_month`/`anniversary_day` are required only for
    `AllowancePeriod.ANNIVERSARY` (for example, a card's account-open date);
    they are rejected for every other period so a caller cannot silently pass
    them to the wrong period type.
    """
    if not isinstance(period, AllowancePeriod):
        raise ValueError("period must be an AllowancePeriod")
    if period is not AllowancePeriod.ANNIVERSARY and (anniversary_month is not None or anniversary_day is not None):
        raise ValueError("anniversary_month/anniversary_day only apply to AllowancePeriod.ANNIVERSARY")
    if period is AllowancePeriod.MONTHLY:
        start = date(as_of.year, as_of.month, 1)
        end = date(as_of.year, as_of.month, _last_day_of_month(as_of.year, as_of.month))
        resets_on = end + timedelta(days=1)
        return PeriodBounds(start, end, resets_on)
    if period is AllowancePeriod.QUARTERLY:
        quarter_index = (as_of.month - 1) // 3
        start_month = quarter_index * 3 + 1
        end_month = start_month + 2
        start = date(as_of.year, start_month, 1)
        end = date(as_of.year, end_month, _last_day_of_month(as_of.year, end_month))
        resets_on = end + timedelta(days=1)
        return PeriodBounds(start, end, resets_on)
    if period is AllowancePeriod.CALENDAR_YEAR:
        start = date(as_of.year, 1, 1)
        end = date(as_of.year, 12, 31)
        resets_on = date(as_of.year + 1, 1, 1)
        return PeriodBounds(start, end, resets_on)
    if anniversary_month is None or anniversary_day is None:
        raise ValueError("AllowancePeriod.ANNIVERSARY requires anniversary_month and anniversary_day")
    if not 1 <= anniversary_month <= 12:
        raise ValueError("anniversary_month must be 1-12")
    if not 1 <= anniversary_day <= 31:
        raise ValueError("anniversary_day must be 1-31")
    this_year_anniversary = _clamped_date(as_of.year, anniversary_month, anniversary_day)
    if this_year_anniversary <= as_of:
        start = this_year_anniversary
        resets_on = _clamped_date(as_of.year + 1, anniversary_month, anniversary_day)
    else:
        start = _clamped_date(as_of.year - 1, anniversary_month, anniversary_day)
        resets_on = this_year_anniversary
    return PeriodBounds(start, resets_on - timedelta(days=1), resets_on)
