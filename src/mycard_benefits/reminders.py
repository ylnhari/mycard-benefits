"""Bounded, local reminder signals and safe calendar export.

The reader passed to this module may see decrypted vault data, but this module
never returns that data.  It emits coarse signals for the UI and fixed copy
for notifications.  ICS is an explicit local export and is the only path
that may contain a derived private date.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from . import data_location
from .catalog.loader import Catalog, CatalogLoadError
from .vault.core import VaultError
from .vault.router import CardReader, VaultUnavailable

_MAX_REMINDERS = 100
_MAX_ICS_BYTES = 32_000
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}
_PREFERENCE_FILE = "reminder-preferences.json"


class ReminderKind(StrEnum):
    ENROLLMENT = "enrollment"
    BENEFIT_EXPIRY = "benefit_expiry"
    VOUCHER_EXPIRY = "voucher_expiry"
    ALLOWANCE_RESET = "allowance_reset"
    RENEWAL = "renewal"
    FEE_WAIVER_CHECKPOINT = "fee_waiver_checkpoint"
    CARD_EXPIRY = "card_expiry"
    EARN_BURN_EXPIRY = "earn_burn_expiry"
    EARN_BURN_DEVALUATION = "earn_burn_devaluation"
    DUE_DATE_ALIGNMENT = "due_date_alignment"
    AUTOPAY_CHECK = "autopay_check"


_COPY: dict[ReminderKind, tuple[str, str]] = {
    ReminderKind.ENROLLMENT: ("Enrollment check", "Review enrollment steps in the official terms."),
    ReminderKind.BENEFIT_EXPIRY: ("Benefit expiry check", "Review the benefit before its private expiry signal changes."),
    ReminderKind.VOUCHER_EXPIRY: ("Voucher expiry check", "Review the voucher before its private expiry signal changes."),
    ReminderKind.ALLOWANCE_RESET: ("Allowance reset check", "Review the allowance period and current official terms."),
    ReminderKind.RENEWAL: ("Renewal check", "Review renewal terms and the current official source."),
    ReminderKind.FEE_WAIVER_CHECKPOINT: ("Fee-waiver checkpoint", "Review the fee-waiver conditions; this is not a spend tracker."),
    ReminderKind.CARD_EXPIRY: ("Card expiry check", "Review your local card record and issuer instructions."),
    ReminderKind.EARN_BURN_EXPIRY: ("Rewards expiry check", "Review the current rewards terms; future value is not promised."),
    ReminderKind.EARN_BURN_DEVALUATION: ("Rewards terms check", "Review current rewards terms; future value is not promised."),
    ReminderKind.DUE_DATE_ALIGNMENT: ("Payment-date education", "Review whether your chosen payment date aligns with the issuer due date."),
    ReminderKind.AUTOPAY_CHECK: ("Autopay education", "Review your autopay instruction and issuer due-date guidance."),
}


class ReminderSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: ReminderKind
    priority: int = Field(ge=1, le=3)
    title: str = Field(max_length=80)
    message: str = Field(max_length=240)
    status: str = Field(pattern=r"^(expired|expiring_soon|scheduled|education)$")
    education_only: bool


class NotificationKind(StrEnum):
    """Bounded notification categories for the local reminder surface."""

    CADENCE_CLAMPED = "cadence_clamped"
    RATE_LIMITED = "rate_limited"
    SOURCE_BLOCKED = "source_blocked"
    FAILURE = "failure"
    CONFLICT = "conflict"


_GENERIC_NOTIFICATION_COPY: dict[NotificationKind, str] = {
    NotificationKind.CADENCE_CLAMPED: "A public source schedule was adjusted for safety.",
    NotificationKind.RATE_LIMITED: "A public source asked the app to slow down. Review is required.",
    NotificationKind.SOURCE_BLOCKED: "A public source was blocked and needs review.",
    NotificationKind.FAILURE: "A public update could not be completed. Review is required.",
    NotificationKind.CONFLICT: "A public update contains conflicting information. Review is required.",
}


def notification_copy(kind: NotificationKind) -> str:
    """Return fixed copy; never interpolate owner, card, or record values."""
    if not isinstance(kind, NotificationKind):
        raise ValueError("notification kind is invalid")
    return _GENERIC_NOTIFICATION_COPY[kind]


class NotificationState(StrEnum):
    """Planning is not delivery; this is intentionally the only state."""

    PLANNED = "planned"


@dataclass(frozen=True)
class NotificationSignal:
    """Safe input to deterministic notification planning."""

    admission_id: str
    source_url: str
    kind: NotificationKind


@dataclass(frozen=True)
class NotificationPlan:
    """A fixed-copy notification that awaits a local review action."""

    id: str
    admission_id: str
    source_url: str
    kind: NotificationKind
    state: NotificationState
    message: str
    catalog_release_id: str | None = None
    offering_id: str | None = None
    conflict_ids: tuple[str, ...] = ()
    review_state: str | None = None


def plan_notifications(signals: tuple[NotificationSignal, ...]) -> tuple[NotificationPlan, ...]:
    """Produce de-duplicated, reproducible local notification plans."""
    keys: set[tuple[str, str, NotificationKind]] = set()
    for signal in signals:
        if not isinstance(signal, NotificationSignal):
            raise ValueError("notification signal is invalid")
        if not isinstance(signal.admission_id, str) or not signal.admission_id:
            raise ValueError("admission id is invalid")
        if not isinstance(signal.source_url, str) or not signal.source_url:
            raise ValueError("notification source URL is invalid")
        if not isinstance(signal.kind, NotificationKind):
            raise ValueError("notification kind is invalid")
        keys.add((signal.admission_id, signal.source_url, signal.kind))
    plans: list[NotificationPlan] = []
    for admission_id, source_url, kind in sorted(
        keys, key=lambda item: (item[0], item[1], item[2].value)
    ):
        material = json.dumps(
            {"admission_id": admission_id, "kind": kind.value, "source_url": source_url},
            sort_keys=True,
            separators=(",", ":"),
        )
        plans.append(
            NotificationPlan(
                id=hashlib.sha256(material.encode("utf-8")).hexdigest(),
                admission_id=admission_id,
                source_url=source_url,
                kind=kind,
                state=NotificationState.PLANNED,
                message=notification_copy(kind),
            )
        )
    return tuple(plans)


def catalog_conflict_notification(
    release_id: str,
    offering_id: str,
    conflict_ids: tuple[str, ...],
    review_state: str,
) -> NotificationPlan:
    """Build one deterministic, fixed-copy plan for a catalog conflict."""
    base = plan_notifications((
        NotificationSignal(release_id, f"catalog://{release_id}/{offering_id}", NotificationKind.CONFLICT),
    ))[0]
    material = json.dumps(
        {"conflict_ids": sorted(conflict_ids), "offering_id": offering_id, "release_id": release_id},
        sort_keys=True,
        separators=(",", ":"),
    )
    return NotificationPlan(
        id=hashlib.sha256(material.encode("utf-8")).hexdigest(),
        admission_id=base.admission_id,
        source_url=base.source_url,
        kind=base.kind,
        state=base.state,
        message=base.message,
        catalog_release_id=release_id,
        offering_id=offering_id,
        conflict_ids=tuple(sorted(conflict_ids)),
        review_state=review_state,
    )


def catalog_conflict_notifications(
    records: tuple[dict[str, Any], ...], catalog: Catalog, *, as_of: date | None = None
) -> tuple[NotificationPlan, ...]:
    """Plan fixed-copy conflict notices for non-archived public offerings.

    Only catalog release/rule/offering identifiers cross this boundary.  The
    result is deterministic and independent of the number or identity of
    local card instances, so restart reads cannot duplicate a notice.
    """
    signals: list[NotificationPlan] = []
    for card in records:
        if not isinstance(card, dict) or card.get("lifecycle") == "archived":
            continue
        offering_id = card.get("offering_id")
        if not isinstance(offering_id, str):
            continue
        offering = catalog.offering_by_slug(offering_id)
        if offering is None:
            continue
        for reference in catalog.conflict_references_for(offering.id, as_of):
            left = reference.source
            right = reference.target
            review_state = (
                "needs_review"
                if reference.resolution != "resolved"
                or "needs_review" in {left.status, right.status if right is not None else None}
                else "unresolved"
            )
            conflict_ids = (left.id, reference.target_id) if right is None else (left.id, right.id)
            signals.append(catalog_conflict_notification(
                catalog.release.release_id, offering_id, conflict_ids, review_state
            ))
    unique = {item.id: item for item in signals}
    return tuple(unique[key] for key in sorted(unique))


def _private_date(value: Any) -> date | None:
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _signal(kind: ReminderKind, due: date | None, today: date, index: int) -> ReminderSignal:
    if kind in {ReminderKind.DUE_DATE_ALIGNMENT, ReminderKind.AUTOPAY_CHECK}:
        status = "education"
        priority = 3
    elif due is None:
        status = "scheduled"
        priority = 3
    elif due < today:
        status = "expired"
        priority = 1
    elif due <= today + timedelta(days=30):
        status = "expiring_soon"
        priority = 2
    else:
        status = "scheduled"
        priority = 3
    title, message = _COPY[kind]
    material = f"{kind.value}:{status}:{index}".encode("ascii")
    return ReminderSignal(
        id=hashlib.sha256(material).hexdigest()[:24],
        kind=kind,
        priority=priority,
        title=title,
        message=message,
        status=status,
        education_only=kind in {ReminderKind.DUE_DATE_ALIGNMENT, ReminderKind.AUTOPAY_CHECK},
    )


def derive_reminder_signals(
    records: tuple[dict[str, Any], ...], *, today: date | None = None, due_date_autopay: bool = False
) -> tuple[ReminderSignal, ...]:
    """Derive bounded signals from private records without reflecting values."""
    if len(records) > _MAX_REMINDERS:
        raise ValueError("too many private records")
    current = today or date.today()
    planned: list[tuple[ReminderKind, date | None]] = []
    for card in records:
        if not isinstance(card, dict):
            raise ValueError("private record is invalid")
        card_due = _private_date(card.get("expiry_date"))
        if card_due is not None and card.get("lifecycle") != "archived":
            planned.append((ReminderKind.CARD_EXPIRY, card_due))
        if card.get("lifecycle") == "archived":
            continue
        for child in card.get("child_records", ()):
            if not isinstance(child, dict):
                raise ValueError("private child record is invalid")
            if child.get("lifecycle") == "archived":
                continue
            child_due = _private_date(child.get("expiry_date"))
            if child_due is None:
                continue
            kind = ReminderKind.VOUCHER_EXPIRY if child.get("kind") == "voucher" else ReminderKind.BENEFIT_EXPIRY
            planned.append((kind, child_due))
        for item in card.get("reminders", ()):
            if not isinstance(item, dict):
                raise ValueError("private reminder is invalid")
            raw_kind = item.get("kind")
            if not isinstance(raw_kind, str):
                continue
            try:
                kind = ReminderKind(raw_kind)
            except ValueError:
                continue
            due = _private_date(item.get("due_date"))
            planned.append((kind, due))
        if due_date_autopay:
            if _private_date(card.get("due_date")) is not None:
                planned.append((ReminderKind.DUE_DATE_ALIGNMENT, None))
            if card.get("autopay_enabled") is True:
                planned.append((ReminderKind.AUTOPAY_CHECK, None))
    signals = [_signal(kind, due, current, index) for index, (kind, due) in enumerate(planned)]
    return tuple(sorted(signals, key=lambda item: (item.priority, item.kind.value, item.id))[:_MAX_REMINDERS])


def _ics_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r", "").replace("\n", "")


def _fold_ics_line(line: str) -> str:
    chunks: list[str] = []
    while len(line.encode("utf-8")) > 75:
        cut = 75
        while len(line[:cut].encode("utf-8")) > 75:
            cut -= 1
        chunks.append(line[:cut])
        line = " " + line[cut:]
    chunks.append(line)
    return "\r\n".join(chunks)


def build_calendar(records: tuple[dict[str, Any], ...], *, today: date | None = None) -> bytes:
    """Build a bounded RFC5545 export; raw values never become filenames or IDs."""
    events: list[str] = []
    dtstamp = (today or date.today()).strftime("%Y%m%dT000000Z")
    for index, card in enumerate(records[:_MAX_REMINDERS]):
        if not isinstance(card, dict) or card.get("lifecycle") == "archived":
            continue
        raw_dates = [(ReminderKind.CARD_EXPIRY, card.get("expiry_date"))]
        raw_dates.extend(
            (ReminderKind.VOUCHER_EXPIRY if child.get("kind") == "voucher" else ReminderKind.BENEFIT_EXPIRY, child.get("expiry_date"))
            for child in card.get("child_records", ())
            if isinstance(child, dict) and child.get("lifecycle") != "archived"
        )
        for kind, raw in raw_dates:
            due = _private_date(raw)
            if due is None:
                continue
            identity = card.get("card_id", str(index))
            uid = hashlib.sha256(f"{identity}:{kind.value}:{due.isoformat()}".encode()).hexdigest()[:24]
            start = due.strftime("%Y%m%d")
            end = (due + timedelta(days=1)).strftime("%Y%m%d")
            title = _COPY[kind][0]
            events.append("\r\n".join(_fold_ics_line(line) for line in (
                "BEGIN:VEVENT", f"UID:{uid}@mycard-benefits.invalid", f"DTSTAMP:{dtstamp}",
                f"DTSTART;VALUE=DATE:{start}", f"DTEND;VALUE=DATE:{end}",
                f"SUMMARY:{_ics_escape(title)}", "END:VEVENT")))
    body = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//MyCard Benefits//Reminders//EN\r\nCALSCALE:GREGORIAN\r\n" + "\r\n".join(events) + "\r\nEND:VCALENDAR\r\n"
    encoded = body.encode("utf-8")
    if len(encoded) > _MAX_ICS_BYTES:
        raise ValueError("calendar export is too large")
    return encoded


class ReminderPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    due_date_autopay: bool = False


class ReminderPreferenceStore:
    """Small, bounded, local-only preference store; invalid state fails closed."""

    def __init__(self, data_dir: Path) -> None:
        root = data_location.validate_data_root(data_dir)
        self.path = root / "private" / _PREFERENCE_FILE
        data_location.reject_reparse(self.path, allow_missing=True)

    def load(self) -> ReminderPreferences:
        try:
            if not data_location.existing_regular_file(self.path):
                return ReminderPreferences()
            raw = json.loads(data_location.read_guarded_bytes(self.path, maximum=64 * 1024).decode("utf-8"))
            return ReminderPreferences.model_validate(raw)
        except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError, data_location.DataLocationError):
            return ReminderPreferences()

    def save(self, value: ReminderPreferences) -> None:
        private = self.path.parent
        data_location.reject_reparse(private, allow_missing=True)
        data_location.data_location_checkpoint("before-preference-directory-create", private)
        private.mkdir(parents=True, exist_ok=True)
        data_location.reject_reparse(private)
        encoded = json.dumps(value.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode("utf-8")
        temporary = self.path.with_suffix(".tmp")
        data_location.reject_reparse(temporary, allow_missing=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(temporary, flags, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                descriptor = -1
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        data_location.data_location_checkpoint("before-preference-replace", self.path)
        data_location.reject_reparse(private)
        data_location.reject_reparse(self.path, allow_missing=True)
        os.replace(temporary, self.path)
        if os.name != "nt":
            os.chmod(self.path, 0o600)


def create_reminders_router(
    reader: CardReader, *, ntfy_enabled: bool = False, preference_store: ReminderPreferenceStore | None = None,
    authorize_mutation: Any | None = None, catalog_reader: Any | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/private/reminders", tags=["private reminders"])
    store = preference_store
    preferences = store.load() if store is not None else ReminderPreferences()

    @router.get("")
    def list_reminders(response: Response) -> dict[str, object]:
        response.headers.update(_NO_STORE)
        try:
            records = reader()
            signals = derive_reminder_signals(records, due_date_autopay=preferences.due_date_autopay)
            notifications = catalog_conflict_notifications(records, catalog_reader()) if catalog_reader is not None else ()
        except (OSError, ValueError, VaultError, VaultUnavailable):
            raise HTTPException(status_code=503, detail="Reminder data unavailable", headers=_NO_STORE) from None
        return {
            "reminders": [item.model_dump(mode="json") for item in signals],
            "notifications": [
                {"id": item.id, "kind": item.kind.value, "state": item.state.value,
                 "message": item.message, "offering_id": item.offering_id,
                 "conflict_ids": list(item.conflict_ids), "review_state": item.review_state}
                for item in notifications
            ],
            "count": len(signals), "notification_count": len(notifications), "ntfy_enabled": ntfy_enabled,
        }

    @router.get("/calendar.ics")
    def calendar_export() -> Response:
        try:
            content = build_calendar(reader())
        except (OSError, ValueError, VaultError, VaultUnavailable, CatalogLoadError):
            raise HTTPException(status_code=503, detail="Calendar export unavailable", headers=_NO_STORE) from None
        return Response(content=content, media_type="text/calendar", headers={**_NO_STORE, "Content-Disposition": 'attachment; filename="mycard-reminders.ics"'})

    @router.get("/preferences")
    def get_preferences(response: Response) -> dict[str, bool]:
        response.headers.update(_NO_STORE)
        return preferences.model_dump(mode="json")

    @router.post("/preferences")
    def set_preferences(payload: ReminderPreferences, response: Response) -> dict[str, bool]:
        nonlocal preferences
        if authorize_mutation is not None:
            try:
                authorize_mutation()
            except Exception:
                raise HTTPException(status_code=503, detail="Reminder preferences unavailable", headers=_NO_STORE) from None
        if store is not None:
            try:
                store.save(payload)
            except (OSError, ValueError):
                raise HTTPException(status_code=503, detail="Reminder preferences unavailable", headers=_NO_STORE) from None
        preferences = payload
        response.headers.update(_NO_STORE)
        return {"due_date_autopay": preferences.due_date_autopay}

    @router.post("/ntfy/test")
    def ntfy_test(response: Response) -> dict[str, object]:
        response.headers.update(_NO_STORE)
        return {"enabled": ntfy_enabled, "delivered": False, "mode": "disabled" if not ntfy_enabled else "mocked"}

    return router
