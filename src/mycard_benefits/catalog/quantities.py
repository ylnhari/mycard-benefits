"""Closed-vocabulary projections of source-shaped benefit allowances.

The catalog's ``allowance`` remains authoritative and source-shaped.  This
module only creates a second, explicitly conservative representation for
numbers that can be compared without guessing what a source key means.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

# These values are the smallest vocabularies needed by the current catalog.
# Adding a new value is a schema change, not an authoring-time fallback.
QUANTITY_METRICS = frozenset(
    {
        "rate_percent",
        "discount_percent",
        "fee_percent",
        "cap",
        "count",
        "coverage",
        "fee",
        "value",
        "duration",
    }
)
QUANTITY_UNITS = frozenset(
    {"percent", "inr", "points", "visits", "tickets", "multiple", "days"}
)
QUANTITY_BASES = frozenset({"spend", "transaction", "statement", "year"})
QUANTITY_PERIODS = frozenset(
    {
        "transaction",
        "month",
        "quarter",
        "half_year",
        "year",
        "financial_year",
        "statement_cycle",
        "qualifying_calendar_quarter",
        "one_time",
        "total",
        "issuance_window",
        "qualification_window",
        "claim_window",
        "validity",
    }
)
QUANTITY_SCOPES = frozenset(
    {
        "amazon.in",
        "BookMyShow",
        "Swiggy Dineout partner restaurants",
        "Visa APAC airport dining",
        "fuel",
        "travel_booking",
        "UPI",
        "Tata Neu",
    }
)

_PLAIN_NUMBER = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")


@dataclass(frozen=True)
class QuantityProjection:
    """The derived quantities plus an audit trail for every source key."""

    quantities: tuple[dict[str, Any], ...]
    mapped_keys: frozenset[str]
    unmapped: tuple[tuple[str, str], ...]


def project_benefit_record(record: dict[str, Any]) -> QuantityProjection:
    """Project one catalog record and preserve reasons for omitted fields."""

    allowance = record.get("allowance")
    if not isinstance(allowance, dict):
        allowance = {}
    result = _project_allowance(
        allowance,
        benefit_type=str(record.get("benefit_type", "")),
        category=str(record.get("category", "")),
        title=str(record.get("title", "")),
    )
    unmapped = list(result.unmapped)
    if "not_claimed" in record and not any(key == "not_claimed" for key, _ in unmapped):
        unmapped.append(
            (
                "not_claimed",
                "an evidence gap is not a numeric quantity",
            )
        )
    return QuantityProjection(result.quantities, result.mapped_keys, tuple(unmapped))


def _project_allowance(
    allowance: dict[str, Any], *, benefit_type: str, category: str, title: str
) -> QuantityProjection:
    mapped: set[str] = set()
    reasons: dict[str, str] = {}
    quantities: list[dict[str, Any]] = []

    def mark(*keys: str) -> None:
        mapped.update(key for key in keys if key in allowance)

    def omit(key: str, reason: str) -> None:
        if key in allowance and key not in mapped:
            reasons[key] = reason

    def add(
        *,
        metric: str,
        key: str,
        unit: str,
        basis: str,
        period: str,
        scope: str | None,
        used: tuple[str, ...] = (),
        cap: dict[str, Any] | None = None,
    ) -> None:
        value = _number(allowance.get(key))
        if value is None:
            omit(key, "the value is not a plain numeric quantity")
            return
        quantities.append(
            {
                "metric": metric,
                "value": value,
                "unit": unit,
                "basis": basis,
                "scope": scope,
                "period": period,
                "cap": cap,
            }
        )
        mark(key, *used)
        if scope is not None:
            mark("channel", "india_only")

    def period_for(fallback: str) -> tuple[str, tuple[str, ...]]:
        source_period = allowance.get("period")
        if isinstance(source_period, str) and source_period in QUANTITY_PERIODS:
            return source_period, ("period",)
        if allowance.get("uses_per_month") is not None:
            return "month", ("uses_per_month",)
        if allowance.get("uses_total") is not None:
            return "one_time", ("uses_total",)
        if allowance.get("uses_per_financial_year") is not None:
            return "financial_year", ("uses_per_financial_year",)
        if allowance.get("visits_per_quarter") is not None:
            return "quarter", ("visits_per_quarter",)
        if allowance.get("visits_per_year") is not None:
            return "year", ("visits_per_year",)
        return fallback, ()

    def cap_for(*candidate_keys: str) -> tuple[dict[str, Any] | None, tuple[str, ...]]:
        for cap_key in candidate_keys:
            if cap_key not in allowance:
                continue
            cap_value = _number(allowance[cap_key])
            if cap_value is None:
                omit(cap_key, "the cap is not a plain numeric quantity")
                return None, ()
            if cap_key == "monthly_cap_inr":
                return {"value": cap_value, "unit": "inr", "period": "month"}, (cap_key,)
            if cap_key == "statement_cycle_cap_inr":
                return {
                    "value": cap_value,
                    "unit": "inr",
                    "period": "statement_cycle",
                }, (cap_key,)
            if cap_key in {"cap_inr", "second_ticket_cap_inr", "ticket_cap_inr"}:
                cap_period, period_keys = period_for("transaction")
                return {"value": cap_value, "unit": "inr", "period": cap_period}, (
                    cap_key,
                    *period_keys,
                )
        return None, ()

    def scope_for(key: str = "") -> str | None:
        text = f"{title} {category} {allowance.get('channel', '')}".casefold()
        if "bookmyshow" in text:
            return "BookMyShow"
        if "amazon" in text:
            return "amazon.in"
        if "swiggy dineout" in text or "swiggy" in text:
            return "Swiggy Dineout partner restaurants"
        if "airport dining" in text:
            return "Visa APAC airport dining"
        if key in {"travel_booking_redemption_percent_cap"}:
            return "travel_booking"
        if category == "fuel" or "fuel" in text:
            return "fuel"
        if "tata neu" in text or "neucoins" in text or "upi" in key.casefold():
            return "Tata Neu" if "tata neu" in text else "UPI"
        return None

    reward_reason = (
        "reward-point earning, conversion, or valuation belongs in catalog/rewards"
    )
    reward_keys = {
        "any_upi_percent",
        "calendar_month_cap",
        "cashpoints",
        "cashpoints_percent",
        "grocery_monthly_cap_neucoins",
        "hotel_and_flight_multiplier",
        "incremental_points_cap_per_month",
        "inr_per_cashpoint",
        "instant_voucher_multiplier",
        "insurance_monthly_cap_neucoins",
        "maximum_airmiles_per_reward_point",
        "merchant_emi_percent",
        "monthly_cap_neucoins",
        "monthly_flight_hotel_points_cap",
        "monthly_statement_balance_points_cap",
        "neucoins_per_inr",
        "other_non_emi_percent",
        "partner_tata_non_emi_percent",
        "redemption_fee_inr",
        "reward_point_expiry",
        "reward_redemption_fee_inr",
        "selected_brand_multiplier",
        "statement_cycle_cap",
        "tata_neu_upi_increment_percent",
        "telecom_cable_monthly_cap_neucoins",
        "utility_monthly_cap_neucoins",
        "welcome_neucoins",
    }
    if benefit_type == "reward_points":
        reward_keys.update(allowance)
    for key in allowance:
        if key in reward_keys:
            omit(key, reward_reason)

    # Percentage rates whose unit and basis are clear from the key itself.
    for key, metric, basis in (
        ("cashback_percent", "rate_percent", "spend"),
        ("discount_percent", "discount_percent", "transaction"),
        ("maximum_discount_percent", "discount_percent", "transaction"),
        ("surcharge_percent", "fee_percent", "transaction"),
        ("foreign_currency_markup_percent", "fee_percent", "transaction"),
        ("foreign_exchange_markup_percent", "fee_percent", "transaction"),
        ("dynamic_currency_conversion_markup_percent", "fee_percent", "transaction"),
    ):
        if key not in allowance or key in reward_keys:
            continue
        cap, cap_keys = cap_for("monthly_cap_inr", "statement_cycle_cap_inr", "cap_inr")
        period, period_keys = period_for("transaction")
        if cap is not None:
            period = str(cap["period"])
        add(
            metric=metric,
            key=key,
            unit="percent",
            basis=basis,
            period=period,
            scope=scope_for(key),
            used=(*cap_keys, *period_keys),
            cap=cap,
        )

    if "travel_booking_redemption_percent_cap" in allowance and "travel_booking_redemption_percent_cap" not in reward_keys:
        add(
            metric="cap",
            key="travel_booking_redemption_percent_cap",
            unit="percent",
            basis="transaction",
            period="transaction",
            scope="travel_booking",
        )

    # Clear monetary coverage limits are comparable as limits, not as rewards.
    coverage_keys = {
        "accident_inr",
        "accidental_air_death_cover_inr",
        "air_accident_inr",
        "baggage_inr",
        "credit_liability_cover_inr",
        "emergency_overseas_hospitalization_cover_inr",
        "purchase_inr",
        "unauthorized_use_inr",
    }
    for key in sorted(coverage_keys & allowance.keys() - reward_keys):
        add(
            metric="coverage",
            key=key,
            unit="inr",
            basis="transaction",
            period="total",
            scope=None,
        )

    # Movie and other ticket counts have a supported ticket unit.
    for key in ("complimentary_tickets", "complimentary_or_discounted_tickets"):
        if key not in allowance:
            continue
        period, period_keys = period_for("transaction")
        cap, cap_keys = cap_for("second_ticket_cap_inr", "ticket_cap_inr")
        add(
            metric="count",
            key=key,
            unit="tickets",
            basis="transaction",
            period=period,
            scope=scope_for(key),
            used=(*period_keys, *cap_keys),
            cap=cap,
        )

    # Standalone INR caps still carry useful information when no rate/count
    # quantity exists to hold them.
    standalone_caps = (
        "monthly_cap_inr",
        "statement_cycle_cap_inr",
        "cap_inr",
        "movie_ticket_cap_each_inr",
        "food_and_beverage_cap_inr",
        "transaction_cap_inr",
        "ticket_cap_inr",
    )
    for key in standalone_caps:
        if key not in allowance or key in mapped or key in reward_keys:
            continue
        period, period_keys = period_for("transaction")
        if key == "monthly_cap_inr":
            period, period_keys = "month", ()
        elif key == "statement_cycle_cap_inr":
            period, period_keys = "statement_cycle", ()
        add(
            metric="cap",
            key=key,
            unit="inr",
            basis="transaction",
            period=period,
            scope=scope_for(key),
            used=period_keys,
        )

    # Lounge caps use the source's singular "visit" spelling, normalized to
    # the closed consumer unit "visits".
    if "cap" in allowance and "cap" not in reward_keys:
        raw_unit = allowance.get("unit")
        unit = "visits" if raw_unit in {"visit", "visits"} else None
        if unit is None:
            omit("unit", "the source unit is not in the closed quantity vocabulary")
        else:
            period, period_keys = period_for("transaction")
            add(
                metric="cap",
                key="cap",
                unit=unit,
                basis="transaction",
                period=period,
                scope=scope_for("cap"),
                used=("unit", *period_keys),
            )
    elif "visits" in allowance and "visits" not in reward_keys:
        period, period_keys = period_for("transaction")
        add(
            metric="count",
            key="visits",
            unit="visits",
            basis="transaction",
            period=period,
            scope=scope_for("visits"),
            used=period_keys,
        )

    for key, period, basis in (
        ("visits_per_quarter", "quarter", "transaction"),
        ("visits_per_year", "year", "transaction"),
    ):
        if key in allowance and key not in reward_keys:
            add(
                metric="count",
                key=key,
                unit="visits",
                basis=basis,
                period=period,
                scope=scope_for(key),
            )

    # Time windows are durations, so their own period describes the window's
    # purpose rather than pretending that a number of days is a reset period.
    durations = {
        "bank_transfer_target_days_after_statement": ("statement", "statement_cycle"),
        "bookmyshow_issuance_window_days": ("transaction", "issuance_window"),
        "claim_window_days": ("transaction", "claim_window"),
        "claim_window_days_from_quarter_end": ("transaction", "claim_window"),
        "download_window_days": ("transaction", "issuance_window"),
        "extended_claim_visibility_days_from_statement": ("statement", "claim_window"),
        "initial_claim_window_days": ("transaction", "claim_window"),
        "issuer_first_statement_window_days": ("statement", "statement_cycle"),
        "qualification_window_days": ("transaction", "qualification_window"),
        "welcome_validity_days_from_claim": ("transaction", "validity"),
    }
    for key, (basis, period) in durations.items():
        if key in allowance and key not in reward_keys:
            add(
                metric="duration",
                key=key,
                unit="days",
                basis=basis,
                period=period,
                scope=scope_for(key),
            )

    for key, metric, period in (
        ("joining_fee_inr", "fee", "transaction"),
        ("renewal_fee_inr", "fee", "year"),
        ("waived_fee_inr", "fee", "year"),
        ("voucher_value_inr", "value", "one_time"),
    ):
        if key in allowance and key not in reward_keys:
            add(
                metric=metric,
                key=key,
                unit="inr",
                basis="transaction" if period != "year" else "year",
                period=period,
                scope=None,
            )

    for key in (
        "cap_basis",
        "cap_inr_by_subtype",
        "choice",
        "conditions",
        "daily_inventory_blocks",
        "exclusions",
        "india_only",
        "participating_locations",
        "partner_and_transfer_terms",
        "post_purchase_emi",
        "taxes",
        "not_claimed",
        "validation_fee_reversed",
        "waived_fee",
    ):
        if key not in allowance or key in mapped:
            continue
        reason = {
            "cap_inr_by_subtype": "nested subtype map is not modelled",
            "not_claimed": "an evidence gap is not a numeric quantity",
            "partner_and_transfer_terms": "prose terms are not a numeric quantity",
            "india_only": "a boolean scope restriction has no standalone quantity",
            "cap_basis": "cap selection semantics are not represented in the quantity shape",
        }.get(key, "the source field is not a comparable numeric quantity")
        omit(key, reason)

    for key in (
        "daily_inventory_blocks",
        "expiry_years",
        "interest_free_period",
        "maximum_airmiles_per_reward_point",
        "reward_redemption_fee_inr",
        "stated_brand_count",
        "uses_per_financial_year",
        "uses_per_month",
        "uses_total",
        "validation_swipe_inr",
        "validation_fee_usd",
        "voucher_validity_months",
    ):
        if key not in allowance or key in mapped or key in reward_keys:
            continue
        reason = "the source unit is not in the closed quantity vocabulary"
        if key in {"uses_per_financial_year", "uses_per_month", "uses_total"}:
            reason = "a count of uses has no supported normalized unit"
        elif key == "validation_fee_usd":
            reason = "the closed unit vocabulary has INR but no USD unit"
        elif key in {"interest_free_period", "maximum_airmiles_per_reward_point"}:
            reason = "the source value is qualified prose rather than a plain number"
        elif key == "validation_swipe_inr":
            reason = "a qualifying validation transaction is a condition, not a benefit quantity"
        omit(key, reason)

    for key in sorted(allowance):
        if key in mapped or key in reasons:
            continue
        omit(key, "no unambiguous projection exists in the current closed vocabulary")

    return QuantityProjection(
        tuple(quantities),
        frozenset(mapped),
        tuple(sorted(reasons.items())),
    )


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if not isinstance(value, (str, Decimal)):
        return None
    text = str(value)
    if not _PLAIN_NUMBER.fullmatch(text):
        return None
    try:
        parsed = Decimal(text)
    except InvalidOperation:
        return None
    if not parsed.is_finite() or parsed < 0:
        return None
    if parsed == parsed.to_integral_value():
        return int(parsed)
    return float(parsed)
