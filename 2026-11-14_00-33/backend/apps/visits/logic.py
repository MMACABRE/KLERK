"""Visit rules (legacy src/lib/visits.js): validation, ranges, overlap, day bar, overdue flags.

Booking and changes run under the named lock 'visit_slots' (one doctor = one calendar), then the transaction
locks the patient row, then the visit row (SPEC §4.3)."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.core.audit import audit
from apps.core.errors import Conflict, Invalid
from apps.core.jalali import TEHRAN, add_days, jalali_month, parse_jalali
from apps.core.locks import get_for_update, named_lock
from apps.core.text import normalize_text, to_ascii_digits
from apps.patients.models import Patient
from apps.visits.models import Visit

VISIT_STATUSES = ["scheduled", "done", "cancelled"]
STATUS_LABEL_FA = {"scheduled": "برنامه‌ریزی‌شده", "done": "انجام‌شده", "cancelled": "لغو‌شده"}
DURATIONS = [*(i * 5 for i in range(1, 13)), 75, 90]
DEFAULT_DURATION = 15
LEADS = {"none": "بدون یادآوری", "now": "همین الان", "h2": "۲ ساعت قبل", "d1": "۱ روز قبل", "d2": "۲ روز قبل"}
LEAD_KEYS = list(LEADS)
RANGES = {
    "today": "امروز", "tomorrow": "فردا", "week": "۷ روز آینده", "month": "این ماه", "nextmonth": "ماه آینده",
    "past": "گذشته", "all": "همه",
}
ARCHIVED_MESSAGE = "پرونده بایگانی‌شده است. برای ثبت ویزیت جدید، نخست آن را از بایگانی خارج کنید."
FA_DIGIT = "۰۱۲۳۴۵۶۷۸۹"


class OverlapClash(Invalid):
    """The new slot overlaps another visit (the form shows it under the time field)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = self.message_fa = message


class VisitRefused(Conflict):
    """A visit change refused with a Persian message and a fixed code (409)."""

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.message_fa, self.code = message, code


def parse_time(value: Any) -> str | None:
    m = re.fullmatch(r"(\d{1,2})[:.](\d{2})", to_ascii_digits("" if value is None else str(value)).strip(), re.ASCII)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    return None if h > 23 or mi > 59 else f"{h:02d}:{m.group(2)}"


def _text(body: dict[str, Any], key: str) -> str:
    v = body.get(key)
    return "" if v is None or isinstance(v, (list, dict)) else str(v)


def validate_visit(body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    errors: dict[str, str] = {}
    d = parse_jalali(_text(body, "visitDate") or _text(body, "visit_date"))
    if d is None:
        errors["visitDate"] = "تاریخ را به صورت ۱۴۰۳/۰۵/۱۲ وارد کنید."
    t = parse_time(_text(body, "visitTime") or _text(body, "visit_time"))
    if t is None:
        errors["visitTime"] = "ساعت را به صورت ۰۹:۳۰ وارد کنید."
    asked = to_ascii_digits(_text(body, "durationMin") or _text(body, "duration_min")).strip()
    duration = DEFAULT_DURATION if asked == "" else int(asked) if re.fullmatch(r"\d{1,2}", asked) else -1
    if duration not in DURATIONS:
        errors["durationMin"] = "مدت ویزیت را از فهرست انتخاب کنید (۵ تا ۶۰ دقیقه، ۷۵ یا ۹۰ دقیقه)."
    status = _text(body, "status")
    status = status if status in VISIT_STATUSES else "scheduled"
    values: dict[str, Any] = {
        "visit_date": d, "visit_time": t, "duration_min": duration, "status": status,
        "reason": normalize_text(_text(body, "reason"))[:200] or None,
        "notes": normalize_text(_text(body, "notes"))[:1000] or None,
    }
    if "reminderLead" in body or "reminder_lead" in body:
        lead = _text(body, "reminderLead") or _text(body, "reminder_lead")
        values["reminder_lead"] = lead if lead in LEAD_KEYS else None
    return values, errors


def range_for(name: str, today: date) -> dict[str, Any]:
    if name == "tomorrow":
        d = add_days(today, 1)
        return {"name": name, "from": d, "to": d, "desc": False}
    if name == "week":
        return {"name": name, "from": today, "to": add_days(today, 6), "desc": False}
    if name == "month":
        m = jalali_month(today)
        return {"name": name, "from": m.start, "to": m.end, "desc": False}
    if name == "nextmonth":
        m = jalali_month(today, 1)
        return {"name": name, "from": m.start, "to": m.end, "desc": False}
    if name == "past":
        return {"name": name, "from": None, "to": add_days(today, -1), "desc": True}
    if name == "all":
        return {"name": name, "from": None, "to": None, "desc": False}
    return {"name": "today", "from": today, "to": today, "desc": False}


def hhmm(t: time | str) -> str:
    return t if isinstance(t, str) else f"{t.hour:02d}:{t.minute:02d}"


def _minutes(t: time | str) -> int:
    s = hhmm(t)
    return int(s[:2]) * 60 + int(s[3:5])


def end_time(t: time | str, duration: int) -> str:
    m = (_minutes(t) + duration) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def _abs(d: date, t: time | str) -> int:
    return (d - date(1970, 1, 1)).days * 1440 + _minutes(t)


def find_overlap(d: date, t: str, duration: int, exclude_id: int = 0) -> Visit | None:
    start = _abs(d, t)
    end = start + duration
    rows = (
        Visit.objects.select_related("patient")
        .filter(visit_date__range=(add_days(d, -1), add_days(d, 1)))
        .exclude(status="cancelled")
        .exclude(pk=exclude_id)
        .order_by("visit_date", "visit_time")
    )
    for o in rows:
        s = _abs(o.visit_date, o.visit_time)
        if s < end and start < s + o.duration_min:
            return o
    return None


def overlap_message(o: Visit) -> str:
    t = hhmm(o.visit_time)
    text = (
        f"این بازه با ویزیت {o.patient.first_name} {o.patient.last_name} (ساعت {t} تا "
        f"{end_time(t, o.duration_min)}) هم‌پوشانی دارد."
    )
    return re.sub(r"\d", lambda m: FA_DIGIT[int(m.group(0))], text, flags=re.ASCII)


def day_bookings(d: date, exclude_id: int = 0) -> list[dict[str, Any]]:
    midnight = _abs(d, "00:00")
    rows = (
        Visit.objects.select_related("patient")
        .filter(visit_date__range=(add_days(d, -1), d))
        .exclude(status="cancelled")
        .exclude(pk=exclude_id)
        .order_by("visit_date", "visit_time", "id")
    )
    out = []
    for o in rows:
        s = _abs(o.visit_date, o.visit_time) - midnight
        b: dict[str, Any] = {
            "id": o.pk, "status": o.status, "name": f"{o.patient.first_name} {o.patient.last_name}",
            "time": hhmm(o.visit_time), "until": end_time(o.visit_time, o.duration_min),
            "start": max(0, s), "end": min(1440, s + o.duration_min), "fromYesterday": s < 0,
        }
        if b["end"] > b["start"]:
            out.append(b)
    return out


def flags(v: Visit, now: datetime | None = None) -> dict[str, bool]:
    now = now or timezone.now()
    start = datetime.combine(v.visit_date, v.visit_time if isinstance(v.visit_time, time) else time(0), tzinfo=TEHRAN)
    end = start + timedelta(minutes=v.duration_min)
    planned = v.status == "scheduled"
    return {"overdue": planned and end <= now, "ongoing": planned and start <= now < end}


def todays_visits() -> list[Visit]:
    today = timezone.localdate()
    return list(
        Visit.objects.select_related("patient")
        .filter(visit_date=today)
        .exclude(status="cancelled")
        .order_by("visit_time", "id")
    )


def visits_for(patient_id: int) -> dict[str, Any]:
    rows = list(Visit.objects.filter(patient_id=patient_id).order_by("-visit_date", "-visit_time"))
    now = timezone.now()
    upcoming = [v for v in rows if v.status == "scheduled" and not flags(v, now)["overdue"]][::-1]
    rest = [v for v in rows if v not in upcoming]
    return {"next": upcoming[0] if upcoming else None, "upcoming": upcoming, "rest": rest}


def replans_archived(visit: Visit, patient_status: str, status: str) -> bool:
    return patient_status == "archived" and status == "scheduled" and visit.status != "scheduled"


# ---- writes -----------------------------------------------------------------------------------------

def book(patient_id: int, values: dict[str, Any], user: Any) -> Visit:
    with named_lock("visit_slots"), transaction.atomic():
        patient = get_for_update(Patient.objects.all(), patient_id, "patient")
        if patient.status == "archived":
            raise VisitRefused(ARCHIVED_MESSAGE, "ARCHIVED")
        if values["status"] != "cancelled":
            clash = find_overlap(values["visit_date"], values["visit_time"], values["duration_min"])
            if clash:
                raise OverlapClash(overlap_message(clash))
        visit = Visit.objects.create(
            patient=patient, visit_date=values["visit_date"], visit_time=values["visit_time"],
            duration_min=values["duration_min"], reason=values["reason"], notes=values["notes"],
            status=values["status"], reminder_lead=values.get("reminder_lead"), created_by=user,
        )
        audit(_uid(user), "visit_add", patient.pk)
        return visit


def _uid(user: Any) -> int | None:
    return user.pk if user is not None else None


def lock_visit(visit_id: int) -> tuple[Patient, Visit]:
    """Inside a transaction: lock the patient row, then the visit row."""
    pid = Visit.objects.filter(pk=visit_id).values_list("patient_id", flat=True).first()
    if pid is None:
        from apps.core.errors import NotFound

        raise NotFound("visit")
    patient = get_for_update(Patient.objects.all(), pid, "patient")
    visit = get_for_update(Visit.objects.all(), visit_id, "visit")
    return patient, visit


def update(visit_id: int, values: dict[str, Any], user: Any) -> Visit:
    from apps.billing.ops import sync_stock_for_status

    with named_lock("visit_slots"), transaction.atomic():
        patient, visit = lock_visit(visit_id)
        if replans_archived(visit, patient.status, values["status"]):
            raise VisitRefused(ARCHIVED_MESSAGE, "ARCHIVED")
        if values["status"] != "cancelled":
            clash = find_overlap(values["visit_date"], values["visit_time"], values["duration_min"], visit.pk)
            if clash:
                raise OverlapClash(overlap_message(clash))
        sync_stock_for_status(visit, values["status"], user)
        for k in ("visit_date", "visit_time", "duration_min", "reason", "notes", "status"):
            setattr(visit, k, values[k])
        if "reminder_lead" in values:
            visit.reminder_lead = values["reminder_lead"]
        visit.save()
        audit(_uid(user), "visit_edit", visit.patient_id)
        return visit


def set_status(visit_id: int, status: str, user: Any) -> Visit:
    from apps.billing.ops import sync_stock_for_status

    with named_lock("visit_slots"), transaction.atomic():
        patient, visit = lock_visit(visit_id)
        if replans_archived(visit, patient.status, status):
            raise VisitRefused(ARCHIVED_MESSAGE, "ARCHIVED")
        if status != "cancelled" and visit.status == "cancelled":
            clash = find_overlap(visit.visit_date, hhmm(visit.visit_time), visit.duration_min, visit.pk)
            if clash:
                raise VisitRefused(overlap_message(clash), "OVERLAP")
        sync_stock_for_status(visit, status, user)
        visit.status = status
        visit.save()
        audit(_uid(user), "visit_status", visit.patient_id, status)
        return visit


def delete(visit_id: int, user: Any) -> Visit:
    from apps.billing.ops import PAYMENTS_BLOCK, release_stock, visit_has_payments

    with transaction.atomic():
        _, visit = lock_visit(visit_id)
        if visit_has_payments(visit.pk):
            raise VisitRefused(PAYMENTS_BLOCK, "PAYMENTS_BLOCK")
        release_stock([visit.pk], user)
        patient_id = visit.patient_id
        visit.delete()
        audit(_uid(user), "visit_delete", patient_id)
        return visit
