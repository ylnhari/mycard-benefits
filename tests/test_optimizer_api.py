"""Deterministic synthetic API tests for the ephemeral optimizer endpoint."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import pytest
from fastapi.testclient import TestClient

from mycard_benefits.app import create_app
from mycard_benefits.config import Settings
from mycard_benefits.optimizer.engine import optimize
from mycard_benefits.optimizer.model import (
    LinkClass,
    PurchaseScenario,
    RouteCandidate,
    RouteComponent,
    UserFee,
    canonical_https_origin,
)
from mycard_benefits.optimizer.router import (
    MAX_COMPONENTS_PER_ROUTE,
    MAX_REQUEST_BYTES,
    MAX_ROUTES,
    OptimizationResultResponse,
)

AS_OF = date(2026, 8, 6)
SYNTHETIC_ORIGIN = "https://example.invalid"
MARKER = "SYNTHETIC-ONLY-MUST-NOT-LEAK"


def _client(tmp_path: Path) -> TestClient:
    settings = Settings(data_dir=tmp_path / "data", catalog_dir=tmp_path / "catalog", port=8777)
    return TestClient(create_app(settings))


def _rule_id(value: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"{SYNTHETIC_ORIGIN}/synthetic-rule/{value}"))


def _component(
    component_id: str, value_class: str = "guaranteed", value: str = "1", **overrides: Any
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": component_id,
        "label": f"SYNTHETIC-ONLY-{component_id}",
        "benefit_rule_id": _rule_id(component_id),
        "value_class": value_class,
        "currency": "INR",
        "value_min": value,
        "value_max": value,
        "source_refs": [f"{SYNTHETIC_ORIGIN}/synthetic-source-{component_id}"],
        "evidence_tier": "medium",
        "freshness": "fresh",
        "verified_on": AS_OF.isoformat(),
        "reviewed": True,
    }
    payload.update(overrides)
    return payload


def _route(
    route_id: str,
    components: list[dict[str, Any]] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    if components is None:
        components = [_component("simple")]
    sibling_ids = [item["id"] for item in components]
    for item in components:
        item.setdefault("compatible_with", [other for other in sibling_ids if other != item["id"]])
    payload: dict[str, Any] = {
        "id": route_id,
        "label": route_id,
        "components": components,
        "instructions": ["SYNTHETIC-ONLY-FOLLOW-INSTRUCTIONS"],
        "link_class": "official",
        "official_reference": f"{SYNTHETIC_ORIGIN}/synthetic-official",
    }
    payload.update(overrides)
    return payload


def _scenario(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "amount": "100",
        "currency": "INR",
        "as_of": AS_OF.isoformat(),
        "user_fees": [],
        "allowed_link_classes": ["official", "third_party", "affiliate"],
        "approved_official_origins": [SYNTHETIC_ORIGIN],
    }
    payload.update(overrides)
    return payload


def _request(routes: list[dict[str, Any]] | None = None, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "scenario": _scenario(),
        "routes": routes if routes is not None else [_route("SYNTHETIC-ONLY-A")],
    }
    payload.update(overrides)
    return payload


def _engine_scenario(payload: dict[str, Any]) -> PurchaseScenario:
    scenario = payload["scenario"]
    return PurchaseScenario(
        amount=Decimal(str(scenario["amount"])),
        currency=scenario["currency"],
        as_of=AS_OF,
        user_fees=tuple(_engine_fee(fee) for fee in scenario["user_fees"]),
        allowed_link_classes=frozenset(
            LinkClass(value) for value in scenario["allowed_link_classes"]
        ),
        approved_official_origins=frozenset(
            canonical_https_origin(origin, "approved_official_origin", origin_entry=True)
            for origin in scenario["approved_official_origins"]
        ),
    )


def _engine_route(payload: dict[str, Any]) -> RouteCandidate:
    return RouteCandidate(
        id=payload["id"],
        label=payload["label"],
        components=tuple(_engine_component(item) for item in payload["components"]),
        instructions=tuple(payload["instructions"]),
        link_class=LinkClass(payload["link_class"]),
        official_reference=payload["official_reference"],
        route_fees=tuple(_engine_fee(fee) for fee in payload.get("route_fees", [])),
    )


def _engine_component(payload: dict[str, Any]) -> RouteComponent:
    return RouteComponent(
        id=payload["id"],
        label=payload["label"],
        benefit_rule_id=payload["benefit_rule_id"],
        value_class=payload["value_class"],
        currency=payload["currency"],
        value_min=Decimal(str(payload["value_min"])),
        value_max=Decimal(str(payload.get("value_max", payload["value_min"]))),
        source_refs=tuple(payload["source_refs"]),
        evidence_tier=payload["evidence_tier"],
        freshness=payload["freshness"],
        verified_on=date.fromisoformat(payload["verified_on"]),
        reviewed=payload["reviewed"],
        compatible_with=frozenset(payload.get("compatible_with", [])),
        conditions=tuple(payload.get("conditions", [])),
        assumptions=tuple(payload.get("assumptions", [])),
        expires_on=(
            date.fromisoformat(payload["expires_on"]) if payload.get("expires_on") else None
        ),
        per_transaction_cap=(
            Decimal(str(payload["per_transaction_cap"]))
            if payload.get("per_transaction_cap") is not None
            else None
        ),
        remaining_allowance=(
            Decimal(str(payload["remaining_allowance"]))
            if payload.get("remaining_allowance") is not None
            else None
        ),
        cap_group=payload.get("cap_group"),
        time_limited=payload.get("time_limited", False),
        valuation_name=payload.get("valuation_name"),
    )


def _engine_fee(payload: dict[str, Any]) -> UserFee:
    return UserFee(
        label=payload["label"], amount=Decimal(str(payload["amount"])), currency=payload["currency"]
    )


def _expected_engine_json(payload: dict[str, Any]) -> dict[str, Any]:
    result = optimize(
        _engine_scenario(payload),
        tuple(_engine_route(route) for route in payload["routes"]),
    )
    return OptimizationResultResponse.model_validate(result).model_dump(mode="json")


def _tree_snapshot(root: Path) -> dict[Path, bytes]:
    return {path: path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


def test_success_matches_engine_output_with_provenance_and_no_store(
    tmp_path: Path,
) -> None:
    routes = [
        _route(
            "SYNTHETIC-ONLY-BEST",
            [
                _component("best-a", "guaranteed", "40"),
                _component("best-b", "guaranteed", "40"),
            ],
        ),
        _route(
            "SYNTHETIC-ONLY-MID",
            [
                _component("mid-g", "guaranteed", "10"),
                _component("mid-c", "conditional", "20", value_max="30"),
                _component(
                    "mid-e",
                    "estimated",
                    "5",
                    value_max="10",
                    valuation_name="SYNTHETIC-ONLY-REDEMPTION-VALUATION",
                ),
            ],
        ),
        _route(
            "SYNTHETIC-ONLY-NEGATIVE",
            [_component("neg", "guaranteed", "1")],
            route_fees=[{"label": "SYNTHETIC-ONLY-FEE", "amount": "3", "currency": "INR"}],
        ),
        _route(
            "SYNTHETIC-ONLY-STALE",
            [_component("stale", "guaranteed", "1", freshness="stale")],
        ),
        _route(
            "SYNTHETIC-ONLY-UNREVIEWED",
            [_component("unreviewed", "guaranteed", "1", reviewed=False)],
        ),
    ]
    payload = _request(routes)

    with _client(tmp_path) as client:
        response = client.post("/api/v1/optimizer/routes", json=payload)
        second = client.post("/api/v1/optimizer/routes", json=payload)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-type"].startswith("application/json")
    assert second.status_code == 200
    assert response.content == second.content

    body = response.json()
    assert body == _expected_engine_json(payload)
    assert body["currency"] == "INR"
    assert body["as_of"] == AS_OF.isoformat()
    assert body["status"] == "verified_routes_available"
    assert [item["route_id"] for item in body["ranked_routes"]] == [
        "SYNTHETIC-ONLY-BEST",
        "SYNTHETIC-ONLY-MID",
        "SYNTHETIC-ONLY-NEGATIVE",
    ]
    assert [item["net_guaranteed"] for item in body["ranked_routes"]] == [
        "80.00",
        "10.00",
        "-2.00",
    ]
    mid = body["ranked_routes"][1]
    assert mid["conditional_min"] == "20.00"
    assert mid["conditional_max"] == "30.00"
    assert mid["estimated_min"] == "5.00"
    assert mid["estimated_max"] == "10.00"
    assert mid["value_class_totals_are_non_additive"] is True
    assert mid["components"][0]["value_class"] == "guaranteed"
    assert mid["components"][0]["source_refs"][0].startswith(SYNTHETIC_ORIGIN)
    assert mid["components"][1]["evidence_tier"] == "medium"
    assert mid["explanation"]
    rejected = {item["route_id"]: " ".join(item["reasons"]) for item in body["rejected_routes"]}
    assert "source freshness is stale" in rejected["SYNTHETIC-ONLY-STALE"]
    assert "source is not human reviewed" in rejected["SYNTHETIC-ONLY-UNREVIEWED"]


def test_every_fail_closed_drop_class_is_reported_with_reasons(
    tmp_path: Path,
) -> None:
    routes = [
        _route("SYNTHETIC-ONLY-STALE", [_component("stale", "guaranteed", "1", freshness="stale")]),
        _route(
            "SYNTHETIC-ONLY-UNKNOWN",
            [_component("unknown", "guaranteed", "1", freshness="unknown")],
        ),
        _route(
            "SYNTHETIC-ONLY-UNREVIEWED",
            [_component("unreviewed", "guaranteed", "1", reviewed=False)],
        ),
        _route(
            "SYNTHETIC-ONLY-EXPIRED",
            [
                _component(
                    "expired", "guaranteed", "1", expires_on=(AS_OF - timedelta(days=1)).isoformat()
                )
            ],
        ),
        _route(
            "SYNTHETIC-ONLY-OLD-EVIDENCE",
            [
                _component(
                    "old", "guaranteed", "1", verified_on=(AS_OF - timedelta(days=91)).isoformat()
                )
            ],
        ),
        _route(
            "SYNTHETIC-ONLY-FUTURE",
            [
                _component(
                    "future", "guaranteed", "1", verified_on=(AS_OF + timedelta(days=1)).isoformat()
                )
            ],
        ),
        _route(
            "SYNTHETIC-ONLY-INCOMPATIBLE",
            [
                _component("left", "guaranteed", "1", compatible_with=["right"]),
                _component("right", "guaranteed", "1", compatible_with=[]),
            ],
        ),
        _route(
            "SYNTHETIC-ONLY-AFFILIATE-HIDDEN",
            [_component("aff", "guaranteed", "1")],
            link_class="affiliate",
        ),
        _route(
            "SYNTHETIC-ONLY-UNAPPROVED-ORIGIN",
            [_component("unapproved", "guaranteed", "1")],
            official_reference="https://other.invalid/synthetic",
        ),
        _route(
            "SYNTHETIC-ONLY-SHARED-CAP",
            [
                _component("cap-a", "guaranteed", "1", cap_group="SYNTHETIC-ONLY-CAP"),
                _component("cap-b", "guaranteed", "1", cap_group="SYNTHETIC-ONLY-CAP"),
            ],
        ),
        _route("SYNTHETIC-ONLY-GOOD", [_component("good", "guaranteed", "10")]),
    ]
    payload = _request(routes, scenario=_scenario(allowed_link_classes=["official"]))

    with _client(tmp_path) as client:
        response = client.post("/api/v1/optimizer/routes", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert [item["route_id"] for item in body["ranked_routes"]] == ["SYNTHETIC-ONLY-GOOD"]
    reasons = {item["route_id"]: " ".join(item["reasons"]) for item in body["rejected_routes"]}
    assert "source freshness is stale" in reasons["SYNTHETIC-ONLY-STALE"]
    assert "source freshness is unknown" in reasons["SYNTHETIC-ONLY-UNKNOWN"]
    assert "source is not human reviewed" in reasons["SYNTHETIC-ONLY-UNREVIEWED"]
    assert "component expired before the scenario date" in reasons["SYNTHETIC-ONLY-EXPIRED"]
    assert "evidence is older than 90 days" in reasons["SYNTHETIC-ONLY-OLD-EVIDENCE"]
    assert "after the scenario date" in reasons["SYNTHETIC-ONLY-FUTURE"]
    assert (
        "stacking compatibility is not explicitly mutual" in reasons["SYNTHETIC-ONLY-INCOMPATIBLE"]
    )
    assert "affiliate routes are hidden by the user" in reasons["SYNTHETIC-ONLY-AFFILIATE-HIDDEN"]
    assert (
        "origin is not in the caller-approved origin set"
        in reasons["SYNTHETIC-ONLY-UNAPPROVED-ORIGIN"]
    )
    assert "shared cap allocation is not implemented" in reasons["SYNTHETIC-ONLY-SHARED-CAP"]
    assert (
        body["guidance"] == "Compare only the verified routes shown; no purchase action is taken."
    )


def test_no_verified_route_is_explicit(tmp_path: Path) -> None:
    payload = _request(
        [
            _route(
                "SYNTHETIC-ONLY-STALE", [_component("stale", "guaranteed", "1", freshness="stale")]
            )
        ]
    )

    with _client(tmp_path) as client:
        response = client.post("/api/v1/optimizer/routes", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["ranked_routes"] == []
    assert body["status"] == "no_verified_route"
    assert "do not infer or take a purchase action" in body["guidance"]


def test_malformed_inputs_are_rejected_without_echoing_values(
    tmp_path: Path,
) -> None:
    malformed: list[tuple[str, dict[str, Any]]] = [
        ("unsupported currency", _request(scenario=_scenario(currency="AUD"))),
        ("zero amount", _request(scenario=_scenario(amount="0"))),
        ("non-finite amount", _request(scenario=_scenario(amount="NaN"))),
        ("over-precise amount", _request(scenario=_scenario(amount="100.0000001"))),
        ("money as JSON number", _request(scenario=_scenario(amount=100.5))),
        ("empty allowed link classes", _request(scenario=_scenario(allowed_link_classes=[]))),
        ("empty approved origins", _request(scenario=_scenario(approved_official_origins=[]))),
        (
            "origin with path",
            _request(scenario=_scenario(approved_official_origins=[f"{SYNTHETIC_ORIGIN}/path"])),
        ),
        (
            "duplicate route ids",
            _request(routes=[_route("SYNTHETIC-ONLY-DUP"), _route("SYNTHETIC-ONLY-DUP")]),
        ),
        ("empty routes", _request(routes=[])),
        (
            "non-UUID benefit rule",
            _request(routes=[_route("X", [_component("x", benefit_rule_id="not-a-uuid")])]),
        ),
        (
            "insecure source ref",
            _request(
                routes=[_route("X", [_component("x", source_refs=["http://example.invalid/s"])])]
            ),
        ),
        (
            "invalid value class",
            _request(routes=[_route("X", [_component("x", value_class="bogus")])]),
        ),
        (
            "inverted values",
            _request(routes=[_route("X", [_component("x", value_min="10", value_max="5")])]),
        ),
        (
            "guaranteed spread",
            _request(routes=[_route("X", [_component("x", value_min="1", value_max="2")])]),
        ),
        (
            "estimated without valuation",
            _request(
                routes=[_route("X", [_component("x", "estimated", "5", valuation_name=None)])]
            ),
        ),
        (
            "fee currency mismatch",
            _request(
                scenario=_scenario(
                    user_fees=[{"label": "SYNTHETIC-ONLY-FEE", "amount": "1", "currency": "USD"}]
                )
            ),
        ),
        (
            "route fee currency mismatch",
            _request(
                routes=[
                    _route(
                        "X",
                        route_fees=[
                            {"label": "SYNTHETIC-ONLY-FEE", "amount": "1", "currency": "USD"}
                        ],
                    )
                ]
            ),
        ),
        (
            "fee label collision",
            _request(
                scenario=_scenario(
                    user_fees=[{"label": "SYNTHETIC-ONLY-FEE", "amount": "1", "currency": "INR"}]
                ),
                routes=[
                    _route(
                        "X",
                        route_fees=[
                            {"label": "synthetic-only-fee", "amount": "1", "currency": "INR"}
                        ],
                    )
                ],
            ),
        ),
        ("unknown top-level key", _request(extra_key=MARKER)),
    ]
    for label, payload in malformed:
        with _client(tmp_path) as client:
            response = client.post("/api/v1/optimizer/routes", json=payload)
        assert response.status_code == 422, label
        detail = response.json()["detail"]
        if isinstance(detail, list):
            assert detail, label
            for error in detail:
                assert set(error) == {"loc", "msg", "type"}, label
                assert MARKER not in str(error), label
        else:
            assert MARKER not in str(detail), label


def test_oversized_inputs_are_rejected_before_the_engine(tmp_path: Path) -> None:
    oversized: list[tuple[str, dict[str, Any]]] = [
        (
            "too many routes",
            _request(
                routes=[_route(f"SYNTHETIC-ONLY-R{index}") for index in range(MAX_ROUTES + 1)]
            ),
        ),
        (
            "too many components",
            _request(
                routes=[
                    _route(
                        "X",
                        [_component(f"c{index}") for index in range(MAX_COMPONENTS_PER_ROUTE + 1)],
                    )
                ]
            ),
        ),
        ("label too long", _request(routes=[_route("X", [_component("x", label="X" * 201)])])),
        (
            "too many source refs",
            _request(
                routes=[
                    _route(
                        "X",
                        [
                            _component(
                                "x",
                                source_refs=[f"{SYNTHETIC_ORIGIN}/{index}" for index in range(9)],
                            )
                        ],
                    )
                ]
            ),
        ),
        (
            "too many user fees",
            _request(
                scenario=_scenario(
                    user_fees=[
                        {"label": f"SYNTHETIC-ONLY-F{index}", "amount": "1", "currency": "INR"}
                        for index in range(6)
                    ]
                )
            ),
        ),
        (
            "too many route fees",
            _request(
                routes=[
                    _route(
                        "X",
                        route_fees=[
                            {"label": f"SYNTHETIC-ONLY-F{index}", "amount": "1", "currency": "INR"}
                            for index in range(6)
                        ],
                    )
                ]
            ),
        ),
    ]
    for label, payload in oversized:
        with _client(tmp_path) as client:
            response = client.post("/api/v1/optimizer/routes", json=payload)
        assert response.status_code == 422, label

    oversized_body = _request(
        routes=[_route("X", [_component("x", label="X" * (MAX_REQUEST_BYTES + 1))])]
    )
    with _client(tmp_path) as client:
        response = client.post("/api/v1/optimizer/routes", json=oversized_body)
    assert response.status_code == 413
    assert response.json()["detail"] == "request body exceeds the size limit"


def test_no_persistence_or_logging_of_request_values(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    payload = _request(
        [
            _route(
                "SYNTHETIC-ONLY-A",
                [_component("a", "guaranteed", "7", label=f"{MARKER}-COMPONENT")],
                label=f"{MARKER}-ROUTE",
            )
        ]
    )
    payload["scenario"]["amount"] = "42"
    payload["scenario"]["user_fees"] = [
        {"label": f"{MARKER}-FEE", "amount": "1", "currency": "INR"}
    ]

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


def test_response_bounds_for_maximal_input(tmp_path: Path) -> None:
    routes = []
    for route_index in range(MAX_ROUTES):
        components = [
            _component(
                f"c{route_index}-{component_index}",
                "conditional" if component_index % 3 == 0 else "guaranteed",
                "10",
                label="L" * 100,
                conditions=["C" * 100],
                assumptions=["A" * 100],
            )
            for component_index in range(MAX_COMPONENTS_PER_ROUTE)
        ]
        routes.append(
            _route(f"SYNTHETIC-ONLY-R{route_index}", components, instructions=["I" * 100])
        )
    payload = _request(routes)

    with _client(tmp_path) as client:
        response = client.post("/api/v1/optimizer/routes", json=payload)
        second = client.post("/api/v1/optimizer/routes", json=payload)

    assert response.status_code == 200
    assert len(response.content) < 500_000
    assert len(response.json()["ranked_routes"]) <= MAX_ROUTES
    assert len(response.json()["rejected_routes"]) <= MAX_ROUTES
    assert response.content == second.content


def test_optimizer_route_is_narrowly_scoped_and_loopback_served(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        assert client.get("/api/v1/optimizer/routes").status_code == 405
        assert client.get("/api/v1/optimizer/anything").status_code == 404
        assert client.post("/api/v1/optimizer/routes").status_code == 422
        assert (
            client.post(
                "/api/v1/optimizer/routes",
                content=b"",
                headers={"content-type": "application/json"},
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/v1/optimizer/routes",
                content=b"not json",
                headers={"content-type": "application/json"},
            ).status_code
            == 422
        )

    app = create_app(
        Settings(data_dir=tmp_path / "data", catalog_dir=tmp_path / "catalog", port=8777)
    )
    schema = app.openapi()
    optimizer_paths = [path for path in schema["paths"] if path.startswith("/api/v1/optimizer")]
    assert optimizer_paths == ["/api/v1/optimizer/routes"]
    assert "post" in schema["paths"]["/api/v1/optimizer/routes"]
    assert "get" not in schema["paths"]["/api/v1/optimizer/routes"]
