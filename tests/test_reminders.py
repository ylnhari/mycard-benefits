from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mycard_benefits.catalog.loader import load_catalog
from mycard_benefits.reminders import (
    NotificationKind,
    ReminderKind,
    ReminderPreferenceStore,
    build_calendar,
    catalog_conflict_notifications,
    create_reminders_router,
    derive_reminder_signals,
    notification_copy,
)

ROOT = Path(__file__).parents[1]


def _conflicting_catalog():
    catalog = load_catalog(ROOT / "tests" / "fixtures" / "synthetic_catalog")
    first, second = catalog.benefits
    return replace(catalog, benefits=(
        replace(first, conflicts_with=(second.id,)),
        replace(second, conflicts_with=(first.id,)),
    ))


def _cross_offering_catalog(
    *, target_status: str = "active", target_market: str = "IN",
    source_start: date | None = None, source_end: date | None = None,
    target_start: date | None = None, target_end: date | None = None,
    source_offering_start: date | None = None, source_offering_end: date | None = None,
    target_offering_start: date | None = None, target_offering_end: date | None = None,
):
    catalog = load_catalog(ROOT / "tests" / "fixtures" / "synthetic_catalog")
    local, target = catalog.benefits
    local_offering = next(item for item in catalog.offerings if item.id == local.offering_id)
    target_offering = next(item for item in catalog.offerings if item.id != local_offering.id)
    target = replace(
        target, offering_id=target_offering.id, status=target_status,
        effective_from=target_start, effective_to=target_end,
    )
    local = replace(
        local, status="active", effective_from=source_start, effective_to=source_end,
        conflicts_with=(target.id,),
    )
    local_offering = replace(
        local_offering, effective_from=source_offering_start, effective_to=source_offering_end,
    )
    target_offering = replace(
        target_offering, effective_from=target_offering_start, effective_to=target_offering_end,
    )
    if target_market != target_offering.market:
        target_offering = replace(target_offering, market=target_market)
    return replace(catalog, offerings=(local_offering, target_offering), benefits=(local, target))


def test_reminders_are_coarse_and_archived_cards_are_ignored() -> None:
    records = (
        {"lifecycle": "active", "expiry_date": "2026-08-20", "child_records": [{"kind": "voucher", "expiry_date": "2026-08-10"}]},
        {"lifecycle": "archived", "expiry_date": "2026-08-10", "child_records": []},
    )
    signals = derive_reminder_signals(records, today=date(2026, 8, 9))
    assert {item.kind for item in signals} == {ReminderKind.VOUCHER_EXPIRY, ReminderKind.CARD_EXPIRY}
    assert all("2026" not in item.model_dump_json() for item in signals)
    assert all("active" not in item.model_dump_json() for item in signals)


def test_education_reminders_are_opt_in_and_labeled() -> None:
    record = ({"due_date": "2026-08-20", "autopay_enabled": True},)
    assert derive_reminder_signals(record, today=date(2026, 8, 9)) == ()
    signals = derive_reminder_signals(record, today=date(2026, 8, 9), due_date_autopay=True)
    assert {item.kind for item in signals} == {ReminderKind.DUE_DATE_ALIGNMENT, ReminderKind.AUTOPAY_CHECK}
    assert all(item.education_only for item in signals)


def test_calendar_export_is_bounded_and_has_no_injection() -> None:
    content = build_calendar(({"expiry_date": "2026-08-20\r\nX-ALARM:bad"},), today=date(2026, 8, 9))
    text = content.decode()
    assert "DTSTART;VALUE=DATE:20260820" not in text
    assert "X-ALARM" not in text
    assert b"filename" not in content
    assert len(content) < 32_000


def test_archived_children_never_emit_signals_or_calendar_events() -> None:
    records = ({"card_id": "synthetic-card", "lifecycle": "active", "child_records": [
        {"child_id": "synthetic-child", "lifecycle": "archived", "kind": "voucher", "expiry_date": "2026-08-10"}
    ]}, {"lifecycle": "archived", "expiry_date": "2026-08-10", "child_records": []})
    assert derive_reminder_signals(records, today=date(2026, 8, 9)) == ()
    assert b"BEGIN:VEVENT" not in build_calendar(records, today=date(2026, 8, 9))


def test_calendar_is_deterministic_and_interoperable() -> None:
    records = ({"card_id": "synthetic-card", "expiry_date": "2026-08-20"},)
    first = build_calendar(records, today=date(2026, 8, 9))
    assert first == build_calendar(records, today=date(2026, 8, 9))
    text = first.decode("utf-8")
    assert "DTSTAMP:20260809T000000Z" in text
    assert "\r\n" in text and "\n" not in text.replace("\r\n", "")
    assert text.endswith("END:VCALENDAR\r\n")


def test_invalid_private_dates_fail_closed_and_bounds_apply() -> None:
    assert derive_reminder_signals(({"expiry_date": "2026-99-99"},), today=date(2026, 8, 9)) == ()
    with pytest.raises(ValueError, match="too many"):
        derive_reminder_signals(tuple({} for _ in range(101)))


def test_update_notification_copy_is_fixed_and_private_value_free() -> None:
    for kind in (NotificationKind.FAILURE, NotificationKind.CONFLICT):
        text = notification_copy(kind)
        assert text
        assert "owner" not in text.lower()
        assert "card" not in text.lower()


def test_catalog_conflict_notification_is_fixed_unresolved_and_idempotent() -> None:
    catalog = _conflicting_catalog()
    records = (
        {"offering_id": "synthetic-example-in-visa", "lifecycle": "active", "child_records": []},
        {"offering_id": "synthetic-example-in-visa", "lifecycle": "active", "child_records": []},
    )
    first = catalog_conflict_notifications(records, catalog)
    second = catalog_conflict_notifications(records, catalog)
    assert first == second
    assert len(first) == 1
    assert first[0].kind is NotificationKind.CONFLICT
    assert first[0].message == notification_copy(NotificationKind.CONFLICT)
    assert first[0].review_state == "needs_review"
    assert first[0].offering_id == "synthetic-example-in-visa"
    assert first[0].conflict_ids == tuple(sorted(item.id for item in catalog.benefits))
    assert "SYNTHETIC-ONLY" not in first[0].message
    assert "Synthetic" not in first[0].message


def test_archived_cards_do_not_plan_catalog_conflict_notifications() -> None:
    catalog = _conflicting_catalog()
    records = ({"offering_id": "synthetic-example-in-visa", "lifecycle": "archived", "child_records": []},)
    assert catalog_conflict_notifications(records, catalog) == ()


def test_cross_offering_active_conflict_is_fixed_public_and_idempotent() -> None:
    catalog = _cross_offering_catalog()
    records = (
        {"offering_id": "synthetic-example-in-visa", "lifecycle": "active", "child_records": []},
        {"offering_id": "synthetic-example-in-visa", "lifecycle": "active", "child_records": [
            {"lifecycle": "archived", "kind": "voucher"},
        ]},
    )
    plans = catalog_conflict_notifications(records, catalog)
    assert plans == catalog_conflict_notifications(tuple(reversed(records)), catalog)
    assert len(plans) == 1
    assert plans[0].conflict_ids == tuple(sorted(item.id for item in catalog.benefits))
    assert plans[0].message == notification_copy(NotificationKind.CONFLICT)
    assert plans[0].review_state == "unresolved"


def test_cross_offering_needs_review_conflict_is_review_only() -> None:
    catalog = _cross_offering_catalog(target_status="needs_review")
    reference = catalog.conflict_references_for(catalog.benefits[0].offering_id)[0]
    assert reference.resolution == "needs_review"
    plans = catalog_conflict_notifications(({"offering_id": "synthetic-example-in-visa", "lifecycle": "active"},), catalog)
    assert len(plans) == 1
    assert plans[0].review_state == "needs_review"


@pytest.mark.parametrize("target_status", ["historical", "superseded"])
def test_target_rule_status_and_interval_never_resolve(target_status: str) -> None:
    catalog = _cross_offering_catalog(target_status=target_status, target_end=date(2026, 8, 8))
    local_id = catalog.benefits[0].offering_id
    reference = catalog.conflict_references_for(local_id, as_of=date(2026, 8, 9))[0]
    assert reference.resolution == "inactive"
    assert catalog.conflicts_for(local_id, as_of=date(2026, 8, 9)) == ()


@pytest.mark.parametrize("field", ["source_offering", "source_rule", "target_offering", "target_rule"])
@pytest.mark.parametrize(
    ("boundary", "in_scope"),
    [(date(2026, 8, 10), False), (date(2026, 8, 11), True),
     (date(2026, 8, 12), True), (date(2026, 8, 13), True),
     (date(2026, 8, 14), False)],
)
def test_source_and_target_date_boundaries_fail_closed(
    field: str, boundary: date, in_scope: bool
) -> None:
    field_arguments = {
        "source_offering": "source_offering",
        "source_rule": "source",
        "target_offering": "target_offering",
        "target_rule": "target",
    }
    argument_prefix = field_arguments[field]
    kwargs = {f"{argument_prefix}_start": date(2026, 8, 11),
              f"{argument_prefix}_end": date(2026, 8, 13)}
    catalog = _cross_offering_catalog(**kwargs)
    references = catalog.conflict_references_for(catalog.benefits[0].offering_id, as_of=boundary)
    if field in {"source_offering", "source_rule"} and not in_scope:
        assert references == ()
    elif not in_scope:
        assert references[0].resolution in {"offering_out_of_scope", "inactive"}
        assert catalog.conflicts_for(catalog.benefits[0].offering_id, as_of=boundary) == ()
    else:
        assert references[0].resolution == "resolved"


def test_target_offering_date_scope_is_explicit_and_review_only() -> None:
    catalog = _cross_offering_catalog(target_offering_end=date(2026, 8, 8))
    reference = catalog.conflict_references_for(catalog.benefits[0].offering_id, as_of=date(2026, 8, 9))[0]
    assert reference.resolution == "offering_out_of_scope"
    assert catalog.conflicts_for(catalog.benefits[0].offering_id, as_of=date(2026, 8, 9)) == ()
    plans = catalog_conflict_notifications(
        ({"offering_id": "synthetic-example-in-visa", "lifecycle": "active"},), catalog,
        as_of=date(2026, 8, 9),
    )
    assert len(plans) == 1
    assert plans[0].review_state == "needs_review"
    assert plans[0].message == notification_copy(NotificationKind.CONFLICT)


def test_missing_target_offering_stays_explicit() -> None:
    catalog = _cross_offering_catalog()
    target = catalog.benefits[1]
    catalog = replace(catalog, offerings=(catalog.offerings[0],), benefits=(catalog.benefits[0], target))
    reference = catalog.conflict_references_for(catalog.benefits[0].offering_id)[0]
    assert reference.resolution == "missing_offering"
    assert catalog.conflicts_for(catalog.benefits[0].offering_id) == ()


def test_route_keeps_out_of_scope_target_as_review_only_fixed_copy() -> None:
    catalog = _cross_offering_catalog(target_offering_end=date(2026, 8, 5))
    app = FastAPI()
    app.include_router(create_reminders_router(
        lambda: ({"offering_id": "synthetic-example-in-visa", "lifecycle": "active"},),
        catalog_reader=lambda: catalog,
    ))
    with TestClient(app) as client:
        payload = client.get("/api/v1/private/reminders").json()
    assert payload["notification_count"] == 1
    notice = payload["notifications"][0]
    assert notice["review_state"] == "needs_review"
    assert notice["message"] == notification_copy(NotificationKind.CONFLICT)
    assert "out_of_scope" not in str(payload)


@pytest.mark.parametrize("target_status", ["historical", "superseded"])
def test_expired_or_inactive_cross_offering_target_stays_explicit(target_status: str) -> None:
    catalog = _cross_offering_catalog(target_status=target_status, target_end=date(2026, 8, 8))
    local_id = next(item for item in catalog.offerings if item.id == catalog.benefits[0].offering_id).id
    references = catalog.conflict_references_for(local_id)
    assert len(references) == 1
    assert references[0].resolution == "inactive"
    plans = catalog_conflict_notifications(({"offering_id": "synthetic-example-in-visa", "lifecycle": "active"},), catalog)
    assert plans[0].review_state == "needs_review"
    assert plans[0].conflict_ids == tuple(sorted(item.id for item in catalog.benefits))


def test_missing_and_incompatible_cross_offering_targets_stay_explicit() -> None:
    catalog = load_catalog(ROOT / "tests" / "fixtures" / "synthetic_catalog")
    local, target = catalog.benefits
    local = replace(local, conflicts_with=(target.id, "SYNTHETIC-ONLY-MISSING-RULE"))
    local_offering = next(item for item in catalog.offerings if item.id == local.offering_id)
    target_offering = next(item for item in catalog.offerings if item.id == target.offering_id)
    incompatible = replace(target_offering, market="US")
    catalog = replace(catalog, offerings=(local_offering, incompatible), benefits=(local, target))
    references = catalog.conflict_references_for(local_offering.id)
    assert [(item.target_id, item.resolution) for item in references] == [
        (target.id, "incompatible"),
        ("SYNTHETIC-ONLY-MISSING-RULE", "missing"),
    ]
    plans = catalog_conflict_notifications(({"offering_id": "synthetic-example-in-visa", "lifecycle": "active"},), catalog)
    assert len(plans) == 2
    assert all(item.review_state == "needs_review" for item in plans)


def test_cross_offering_conflicts_respect_as_of_and_ordering() -> None:
    catalog = _cross_offering_catalog(target_end=date(2026, 8, 8))
    local_id = next(item for item in catalog.offerings if item.id == catalog.benefits[0].offering_id).id
    assert catalog.conflicts_for(local_id, as_of=date(2026, 8, 7))
    assert catalog.conflicts_for(local_id, as_of=date(2026, 8, 9)) == ()
    first = replace(catalog.benefits[0], conflicts_with=(catalog.benefits[1].id,))
    second = replace(catalog.benefits[1], conflicts_with=(first.id,))
    ordered = replace(catalog, benefits=(second, first))
    assert [tuple(item.id for item in pair) for pair in ordered.conflicts_for(local_id, as_of=date(2026, 8, 7))] == [
        tuple(sorted((first.id, second.id)))
    ]


def test_conflict_notification_route_is_public_safe_and_fixed() -> None:
    catalog = _cross_offering_catalog()
    app = FastAPI()
    app.include_router(create_reminders_router(
        lambda: ({"offering_id": "synthetic-example-in-visa", "lifecycle": "active", "child_records": []},),
        catalog_reader=lambda: catalog,
    ))
    with TestClient(app) as client:
        response = client.get("/api/v1/private/reminders")
    assert response.status_code == 200
    payload = response.json()
    assert payload["notification_count"] == 1
    notice = payload["notifications"][0]
    assert notice["kind"] == "conflict"
    assert notice["message"] == notification_copy(NotificationKind.CONFLICT)
    assert notice["offering_id"] == "synthetic-example-in-visa"
    assert "SYNTHETIC-ONLY" not in response.text
    assert "Synthetic" not in response.text
    assert "lifecycle" not in response.text


def test_local_api_returns_signals_and_never_raw_dates(tmp_path) -> None:
    app = FastAPI()
    app.include_router(create_reminders_router(lambda: ({"expiry_date": "2026-08-20"},)))
    with TestClient(app) as client:
        response = client.get("/api/v1/private/reminders")
        calendar = client.get("/api/v1/private/reminders/calendar.ics")
    assert response.status_code == 200
    assert "2026-08-20" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert calendar.status_code == 200
    assert b"DTSTART;VALUE=DATE:20260820" in calendar.content
    assert tmp_path.name not in response.text


def test_preferences_persist_and_corrupt_state_fails_closed(tmp_path) -> None:
    store = ReminderPreferenceStore(tmp_path)
    app = FastAPI()
    app.include_router(create_reminders_router(lambda: ({"due_date": "2026-08-20"},), preference_store=store))
    with TestClient(app) as client:
        assert client.get("/api/v1/private/reminders/preferences").json() == {"due_date_autopay": False}
        assert client.post("/api/v1/private/reminders/preferences", json={"due_date_autopay": True}).status_code == 200
    app = FastAPI()
    app.include_router(create_reminders_router(lambda: ({"due_date": "2026-08-20", "autopay_enabled": True},), preference_store=store))
    with TestClient(app) as client:
        assert client.get("/api/v1/private/reminders/preferences").json() == {"due_date_autopay": True}
    store.path.write_text("{not-json", encoding="utf-8")
    assert ReminderPreferenceStore(tmp_path).load().due_date_autopay is False
