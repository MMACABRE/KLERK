"""Visits API (SPEC §5.5; legacy src/routes/visits.js)."""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models import F, Q
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from apps.core import present
from apps.core.audit import audit
from apps.core.http import (
    MSG_400,
    ApiError,
    body,
    id_of,
    invalid,
    not_found,
    ok,
    page_args,
    paginate,
    route,
    text,
    user_of,
)
from apps.core.jalali import add_days, parse_jalali, to_jalali_input
from apps.core.settings_store import get_settings
from apps.core.text import fa_key, normalize_text
from apps.patients.models import Patient
from apps.patients.views import find_patient, visit_item
from apps.visits import logic
from apps.visits.models import Visit

PAGE_SIZE = 50
DAY_LIMIT = 400
NOT_FOUND = "ویزیت مورد نظر پیدا نشد."


def find_visit(vid: str) -> Visit:
    v = Visit.objects.select_related("patient").filter(pk=id_of(vid)).first()
    if v is None:
        raise not_found(NOT_FOUND)
    return v


def day(request: HttpRequest) -> HttpResponse:
    d = parse_jalali(request.GET.get("d"))
    if d is None:
        raise ApiError(400, "تاریخ نامعتبر است.")
    exclude = id_of(request.GET.get("exclude", ""))
    bookings = logic.day_bookings(d, exclude)[:DAY_LIMIT]
    for b in bookings:
        b.pop("id", None)
    return ok({
        "date": d.isoformat(), "input": to_jalali_input(d), "today": d == timezone.localdate(),
        "bookings": bookings,
    })


def list_visits(request: HttpRequest) -> HttpResponse:
    me = user_of(request)
    today = timezone.localdate()
    d = parse_jalali(request.GET.get("d"))
    rng: dict[str, Any] = (
        {"name": "", "from": d, "to": d, "desc": False} if d else logic.range_for(request.GET.get("range", ""), today)
    )
    status = request.GET.get("status", "")
    status = status if status in logic.VISIT_STATUSES else ""
    rows = Visit.objects.select_related("patient")
    if rng["from"]:
        rows = rows.filter(visit_date__gte=rng["from"])
    if rng["to"]:
        rows = rows.filter(visit_date__lte=rng["to"])
    if status:
        rows = rows.filter(status=status)
    if rng["desc"]:
        rows = rows.order_by("-visit_date", "-visit_time", "id")
    else:
        rows = rows.order_by("visit_date", "visit_time", "id")
    total = rows.count()
    page, size = page_args(request, PAGE_SIZE)
    pg = paginate(total, page, size)
    start = (pg["page"] - 1) * size
    sms_on = get_settings()["sms_enabled"] == "1"
    bar_day = d or (rng["from"] if rng["from"] and rng["from"] == rng["to"] else today)
    return ok({
        "data": [visit_item(v, me, sms_on, with_patient=True) for v in rows[start : start + size]],
        "pagination": pg,
        "status": status,
        "ranges": logic.RANGES,
        "rangeName": "" if d else rng["name"],
        "dayInput": to_jalali_input(d) if d else "",
        "today": present.d(today),
        "bar": {
            "date": bar_day.isoformat(), "long": present.d(bar_day)["long"],  # type: ignore[index]
            "input": to_jalali_input(bar_day), "prev": to_jalali_input(add_days(bar_day, -1)),
            "next": to_jalali_input(add_days(bar_day, 1)), "isToday": bar_day == today,
            "bookings": logic.day_bookings(bar_day),
        },
    })


def patient_search(request: HttpRequest) -> HttpResponse:
    term = normalize_text(request.GET.get("q", "")[:100])
    found = []
    if term:
        digits = term.replace(" ", "").replace("-", "")
        found = [
            {"code": p.code, "firstName": p.first_name, "lastName": p.last_name}
            for p in Patient.objects.exclude(status="archived")
            .filter(Q(name_key__contains=fa_key(term)) | Q(code__contains=term) | Q(phone__contains=digits))
            .order_by("last_name_sort", "first_name_sort")[:20]
        ]
    return ok({"q": term, "found": found})


def _values_or_422(data: dict[str, Any]) -> dict[str, Any]:
    values, errors = logic.validate_visit(data)
    if errors:
        raise invalid("لطفاً خطاهای مشخص‌شده را برطرف کنید.", errors)
    return values


def create(request: HttpRequest, code: str) -> HttpResponse:
    me = user_of(request)
    p = find_patient(code)
    if p.status == "archived":
        raise ApiError(409, logic.ARCHIVED_MESSAGE, code="ARCHIVED")
    values = _values_or_422(body(request))
    try:
        v = logic.book(p.pk, values, _user(me))
    except logic.OverlapClash as clash:
        raise invalid(clash.message, {"visitTime": clash.message}) from None
    audit(me.id, "visit_add", p.pk)
    return ok({"id": v.pk, "dateInput": to_jalali_input(values["visit_date"])}, 201)


def _user(me: Any) -> Any:  # the User row for created_by / stock moves
    from apps.accounts.models import User

    return User.objects.filter(pk=me.id).first()


def show(request: HttpRequest, vid: str) -> HttpResponse:
    from apps.billing.views import visit_page

    return visit_page(request, find_visit(vid))


def edit(request: HttpRequest, vid: str) -> HttpResponse:
    me = user_of(request)
    v = find_visit(vid)
    values = _values_or_422(body(request))
    try:
        logic.update(v.pk, values, _user(me))
    except logic.OverlapClash as clash:
        raise invalid(clash.message, {"visitTime": clash.message}) from None
    audit(me.id, "visit_edit", v.patient_id)
    return ok({"id": v.pk, "code": v.patient.code})


def set_status(request: HttpRequest, vid: str) -> HttpResponse:
    me = user_of(request)
    v = find_visit(vid)
    status = text(body(request), "status")
    if status not in logic.VISIT_STATUSES:
        raise invalid(MSG_400, {"status": MSG_400})
    logic.set_status(v.pk, status, _user(me))
    audit(me.id, "visit_status", v.patient_id, status)
    return ok({"id": v.pk, "status": status})


def delete(request: HttpRequest, vid: str) -> HttpResponse:
    me = user_of(request)
    v = find_visit(vid)
    logic.delete(v.pk, _user(me))
    audit(me.id, "visit_delete", v.patient_id)
    return ok({"code": v.patient.code})


def note(request: HttpRequest, vid: str) -> HttpResponse:
    import unicodedata

    me = user_of(request)
    v = find_visit(vid)
    raw = text(body(request), "doctorNote") or text(body(request), "doctor_note")
    value = unicodedata.normalize("NFC", raw.replace("\r\n", "\n")).strip()[:5000]
    with transaction.atomic():
        Visit.objects.filter(pk=v.pk).update(doctor_note=value or None, updated_at=timezone.now())
        audit(me.id, "visit_note", v.patient_id, f"visit={v.pk}")
    return ok()


visits_view = route(GET=list_visits)
visit_view = route(GET=show, PATCH=edit, DELETE=delete)
_ = F
