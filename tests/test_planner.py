"""Deterministic contract tests for the planner UI's documented adapter mapping.

The browser planner builds one bounded payload shape from user-entered
assumptions and posts it to the existing loopback optimizer endpoint. These
tests replay that exact payload shape (the same percent-to-money rule, the
same synthetic provenance, the same fail-closed review markers) to prove the
endpoint's response stays within the contract the UI renders: every
user-entered route is rejected with verbatim reasons, nothing is persisted,
and ``Cache-Control: no-store`` is preserved on every path.
"""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from mycard_benefits.app import create_app
from mycard_benefits.config import Settings

PLANNER_ORIGIN = "https://planner-user-entered.invalid"
PLANNER_SOURCE = "https://planner-user-entered.invalid/synthetic-user-entered-source"
INSTRUCTION = (
    "User-entered assumption — verify the card's current official terms "
    "before relying on this route."
)
MARKER = "SYNTHETIC-ONLY-PLANNER"
AS_OF = "2026-08-09"


def _client(tmp_path: Path) -> TestClient:
    settings = Settings(data_dir=tmp_path / "data", catalog_dir=tmp_path / "catalog", port=8777)
    return TestClient(create_app(settings))


def _percent_to_money(amount: str, percent: str) -> str:
    """Mirror the browser adapter's exact BigInt half-even rule.

    The browser computes ``amount * percent / 100`` with BigInt decimals,
    quantized to 6 decimal places using round-half-even.
    """
    product = Decimal(amount) * Decimal(percent) / Decimal(100)
    value = product.quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _planner_component(
    *,
    label: str,
    value_class: str,
    amount: str,
    percent_min: str,
    percent_max: str | None = None,
    condition: str | None = None,
) -> dict[str, object]:
    if percent_max is None:
        percent_max = percent_min
    return {
        "id": "layer-1",
        "label": label,
        "benefit_rule_id": str(uuid4()),
        "value_class": value_class,
        "currency": "INR",
        "value_min": _percent_to_money(amount, percent_min),
        "value_max": _percent_to_money(amount, percent_max),
        "source_refs": [PLANNER_SOURCE],
        "evidence_tier": "low",
        "freshness": "unknown",
        "verified_on": AS_OF,
        "reviewed": False,
        "compatible_with": [],
        "conditions": [condition] if condition else [],
        "assumptions": [
            f"User-entered assumption: {percent_min}% of the planned {amount} INR purchase"
        ],
        "expires_on": None,
        "per_transaction_cap": None,
        "remaining_allowance": None,
        "cap_group": None,
        "time_limited": False,
        "valuation_name": "user-entered redemption valuation"
        if value_class == "estimated"
        else None,
    }


def _planner_payload(
    *,
    amount: str = "5000",
    channels: list[str] | None = None,
    cards: list[dict[str, object]] | None = None,
    currency: str = "INR",
) -> dict[str, object]:
    if channels is None:
        channels = ["official", "third_party"]
    if cards is None:
        cards = [
            {
                "id": "card-1",
                "label": f"{MARKER}-CARD-A",
                "components": [
                    _planner_component(
                        label=f"{MARKER}-ASSUMPTION-A",
                        value_class="guaranteed",
                        amount=amount,
                        percent_min="5",
                    )
                ],
                "instructions": [INSTRUCTION],
                "link_class": "official",
                "official_reference": f"{PLANNER_ORIGIN}/route-1",
                "action_link_review_state": "approved",
                "route_fees": [],
            },
            {
                "id": "card-2",
                "label": f"{MARKER}-CARD-B",
                "components": [
                    _planner_component(
                        label=f"{MARKER}-ASSUMPTION-B",
                        value_class="conditional",
                        amount=amount,
                        percent_min="2",
                        percent_max="10",
                        condition="valid once per day",
                    )
                ],
                "instructions": [INSTRUCTION],
                "link_class": "third_party",
                "official_reference": f"{PLANNER_ORIGIN}/route-2",
                "action_link_review_state": "approved",
                "route_fees": [],
            },
        ]
    return {
        "scenario": {
            "amount": amount,
            "currency": currency,
            "as_of": AS_OF,
            "user_fees": [],
            "allowed_link_classes": channels,
            "admitted_action_origins": [PLANNER_ORIGIN],
        },
        "routes": cards,
    }


def _tree_snapshot(root: Path) -> dict[Path, bytes]:
    return {path: path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


def test_planner_percent_to_money_regression() -> None:
    """Lock the adapter's percent-to-money rule to exact BigInt arithmetic.

    The browser computes ``amount * percent / 100`` with BigInt decimals
    quantized to 6 places using round-half-even. These known values pin that
    rule so a regression (for example the previous ``/ 10**6`` divisor that
    turned ``5% of 5000`` into billions) fails loudly.
    """
    assert _percent_to_money("5000", "5") == "250"
    assert _percent_to_money("5000", "5.5") == "275"
    assert _percent_to_money("100", "5") == "5"
    assert _percent_to_money("200", "2.5") == "5"
    assert _percent_to_money("1000", "3.125") == "31.25"
    assert _percent_to_money("5000.50", "5") == "250.025"
    assert _percent_to_money("1000", "0.5") == "5"
    assert _percent_to_money("999999999", "10") == "99999999.9"
    assert _percent_to_money("3", "33.333333") == "1"
    assert _percent_to_money("100", "1") == "1"


def test_planner_payload_is_rejected_honestly_with_no_verified_route(
    tmp_path: Path,
) -> None:
    payload = _planner_payload()

    with _client(tmp_path) as client:
        response = client.post("/api/v1/optimizer/routes", json=payload)
        second = client.post("/api/v1/optimizer/routes", json=payload)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.content == second.content

    body = response.json()
    assert body["status"] == "no_verified_route"
    assert body["currency"] == "INR"
    assert body["as_of"] == AS_OF
    assert body["ranked_routes"] == []
    assert "do not infer or take a purchase action" in body["guidance"]

    assert [item["route_id"] for item in body["rejected_routes"]] == ["card-1", "card-2"]
    reasons_by_id = {
        item["route_id"]: " ".join(item["reasons"]) for item in body["rejected_routes"]
    }
    assert "source is not human reviewed" in reasons_by_id["card-1"]
    assert "source freshness is unknown" in reasons_by_id["card-1"]
    assert "layer-1: source is not human reviewed" in reasons_by_id["card-2"]
    assert [item["label"] for item in body["rejected_routes"]] == [
        f"{MARKER}-CARD-A",
        f"{MARKER}-CARD-B",
    ]
    serialized = response.text
    assert PLANNER_ORIGIN not in serialized
    assert all(
        fragment not in serialized for fragment in ("https://cashkaro", "https://amazon", "http://")
    )


def test_planner_hidden_channels_are_rejected_by_the_engine(
    tmp_path: Path,
) -> None:
    payload = _planner_payload(channels=["official"])
    route = payload["routes"][1]
    assert isinstance(route, dict)
    route["link_class"] = "affiliate"
    route["official_reference"] = f"{PLANNER_ORIGIN}/route-2"

    with _client(tmp_path) as client:
        response = client.post("/api/v1/optimizer/routes", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "no_verified_route"
    reasons_by_id = {
        item["route_id"]: " ".join(item["reasons"]) for item in body["rejected_routes"]
    }
    assert "affiliate routes are hidden by the user" in reasons_by_id["card-2"]
    assert response.headers["cache-control"] == "no-store"


def test_planner_maximum_cards_stay_within_api_bounds(tmp_path: Path) -> None:
    cards = []
    for index in range(8):
        cards.append(
            {
                "id": f"card-{index + 1}",
                "label": f"{MARKER}-CARD-{index}",
                "components": [
                    _planner_component(
                        label=f"{MARKER}-ASSUMPTION-{index}",
                        value_class="guaranteed",
                        amount="100",
                        percent_min="1",
                    )
                ],
                "instructions": [INSTRUCTION],
                "link_class": "official",
                "official_reference": f"{PLANNER_ORIGIN}/route-{index + 1}",
                "action_link_review_state": "approved",
                "route_fees": [],
            }
        )

    with _client(tmp_path) as client:
        response = client.post(
            "/api/v1/optimizer/routes", json=_planner_payload(amount="100", cards=cards)
        )

    assert response.status_code == 200
    assert len(response.json()["rejected_routes"]) == 8


def test_planner_requests_persist_and_log_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    payload = _planner_payload()

    with _client(tmp_path) as client:
        before = _tree_snapshot(tmp_path)
        response = client.post("/api/v1/optimizer/routes", json=payload)
        after = _tree_snapshot(tmp_path)

    assert response.status_code == 200
    assert before == after
    for _path, content in after.items():
        assert MARKER not in content.decode("utf-8", errors="ignore")

    with caplog.at_level(logging.DEBUG):
        with _client(tmp_path) as client:
            client.post("/api/v1/optimizer/routes", json=payload)
        records = list(caplog.records)
    assert not any(MARKER in record.getMessage() for record in records)
