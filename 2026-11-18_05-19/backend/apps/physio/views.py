"""Physiotherapy API (SPEC §15.3-15.5): courses, ticked sessions and the list of unfinished courses.

Every write locks the patient row, then the course row (the lock order in apps.core.locks), and checks the rules
under those locks, so a double click or a second user can never leave a gap or a second unfinished course."""

from __future__ import annotations

from datetime import date
from typing import Any

from django.db import transaction
from django.db.models import Count, F, Q, QuerySet
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from apps.core import present
from apps.core.audit import audit
from apps.core.http import (
    MSG_400,
    ApiError,
    body,
    conflict,
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
from apps.core.jalali import parse_jalali
from apps.core.locks import get_for_update
from apps.core.perms import EDIT, can
from apps.core.text import fa_key, normalize_text, to_ascii_digits
from apps.patients.models import Patient
from apps.patients.views import find_patient
from apps.physio.models import MAX_SESSIONS, PhysioCourse, PhysioSession

PAGE_SIZE = 50
IDLE_DAYS = 7  # a last session older than this is shown in terracotta (SPEC §15.6)

NOT_FOUND = "دوره‌ی فیزیوتراپی پیدا نشد."
SESSION_NOT_FOUND = "جلسه‌ی مورد نظر پیدا نشد."
COUNT_ERROR = "تعداد جلسه‌ها باید عددی از ۱ تا ۵۰ باشد."  # MAX_SESSIONS
ARCHIVED = "پرونده بایگانی‌شده است. برای تغییر فیزیوتراپی، نخست آن را از بایگانی خارج کنید."
OPEN_EXISTS = "این بیمار یک دوره‌ی فیزیوتراپی ناتمام دارد."
BELOW_DONE = "تعداد جلسه‌ها نمی‌تواند از جلسه‌های ثبت‌شده کمتر باشد."
HAS_TICKS = "این دوره جلسه‌ی ثبت‌شده دارد. نخست جلسه‌ها را بردارید."
STALE = "این دوره در این فاصله تغییر کرده است. دوباره نگاه کنید."
FULL = "همه‌ی جلسه‌های این دوره ثبت شده است."
NOT_LAST = "فقط آخرین جلسه‌ی ثبت‌شده برداشته می‌شود."
DATE_BAD = "تاریخ نامعتبر است."
DATE_FUTURE = "تاریخ جلسه نمی‌تواند در آینده باشد."
DATE_BEFORE = "تاریخ جلسه نمی‌تواند پیش از جلسه‌ی قبلی باشد."
DATE_AFTER = "تاریخ جلسه نمی‌تواند پس از جلسه‌ی بعدی باشد."


# ---- reading ----------------------------------------------------------------------------------------

def unfinished(qs: QuerySet[PhysioCourse]) -> QuerySet[PhysioCourse]:
    return qs.annotate(done=Count("ticks")).filter(done__lt=F("sessions"))


def _dates(course: PhysioCourse) -> list[date]:
    return [s.date for s in sorted(course.ticks.all(), key=lambda s: s.number)]


def course_item(c: PhysioCourse) -> dict[str, Any]:
    dates = _dates(c)
    return {
        "id": c.pk, "sessions": c.sessions, "done": len(dates), "finished": len(dates) >= c.sessions,
        "createdAt": present.dt(c.created_at), "createdDay": present.d(timezone.localtime(c.created_at).date()),
        "dates": [present.d(x) for x in dates],
    }


def patient_courses(patient_id: int) -> list[dict[str, Any]]:
    """Every course of a patient, newest first, for the profile box."""
    rows = PhysioCourse.objects.filter(patient_id=patient_id).prefetch_related("ticks").order_by("-created_at", "-id")
    return [course_item(c) for c in rows]


def _since(c: PhysioCourse, dates: list[date]) -> date:
    return dates[-1] if dates else timezone.localtime(c.created_at).date()


def unfinished_rows(term: str = "") -> list[dict[str, Any]]:
    """One row per patient with an unfinished course; the longest wait first (SPEC §15.6). Archived patients are
    left out: their record is read only."""
    qs = unfinished(PhysioCourse.objects.exclude(patient__status="archived")).select_related("patient")
    if term:
        qs = qs.filter(Q(patient__name_key__contains=fa_key(term)) | Q(patient__code__contains=term))
    today = timezone.localdate()
    keyed: list[tuple[date, int, dict[str, Any]]] = []
    # ponytail: sorted in Python; unfinished courses at one clinic are a few hundred at most.
    for c in qs.prefetch_related("ticks"):
        dates = _dates(c)
        since = _since(c, dates)
        p = c.patient
        keyed.append((since, c.pk, {
            "code": p.code, "firstName": p.first_name, "lastName": p.last_name, "courseId": c.pk,
            "sessions": c.sessions, "done": len(dates), "dates": [present.d(x) for x in dates],
            "last": present.d(dates[-1]) if dates else None, "since": present.d(since),
            "idle": (today - since).days > IDLE_DAYS,
        }))
    keyed.sort(key=lambda k: (k[0], k[1]))
    return [row for _, _, row in keyed]


def list_unfinished(request: HttpRequest) -> HttpResponse:
    term = normalize_text(request.GET.get("q", "")[:100])
    rows = unfinished_rows(term)
    page, size = page_args(request, PAGE_SIZE)
    pg = paginate(len(rows), page, size)
    start = (pg["page"] - 1) * size
    return ok({"data": rows[start : start + size], "pagination": pg, "q": term,
               "canEdit": can(user_of(request), "physio", EDIT)})


# ---- input ------------------------------------------------------------------------------------------

def _int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        s = to_ascii_digits(value.strip())
        if s.isascii() and s.isdigit() and len(s) <= 4:
            return int(s)
    return None


def _count(data: dict[str, Any]) -> int:
    n = _int(data.get("sessions"))
    if n is None or not 1 <= n <= MAX_SESSIONS:
        raise invalid(COUNT_ERROR, {"sessions": COUNT_ERROR})
    return n


def _date(data: dict[str, Any], default_today: bool) -> date:
    raw = text(data, "date", 40).strip()
    if not raw and default_today:
        return timezone.localdate()
    d = parse_jalali(raw)
    if d is None:
        raise invalid(DATE_BAD, {"date": DATE_BAD})
    return d


def _check_order(d: date, before: date | None, after: date | None) -> None:
    for wrong, message in ((d > timezone.localdate(), DATE_FUTURE),
                           (before is not None and d < before, DATE_BEFORE),
                           (after is not None and d > after, DATE_AFTER)):
        if wrong:
            raise invalid(message, {"date": message})


# ---- locking ----------------------------------------------------------------------------------------

def _locked(cid: str) -> tuple[Patient, PhysioCourse]:
    """Inside a transaction: the patient row, then the course row, both locked. Archived patients are refused."""
    row = PhysioCourse.objects.filter(pk=id_of(cid)).values("patient_id").first()
    if row is None:
        raise not_found(NOT_FOUND)
    p = get_for_update(Patient.objects.all(), row["patient_id"], "patient")
    c = get_for_update(PhysioCourse.objects.all(), id_of(cid), "physio course")
    if p.status == "archived":
        raise conflict(ARCHIVED, "ARCHIVED")
    return p, c


def _has_other_unfinished(p: Patient, exclude: int | None = None) -> bool:
    qs = PhysioCourse.objects.filter(patient=p)
    if exclude is not None:
        qs = qs.exclude(pk=exclude)
    return unfinished(qs).exists()


def _fresh(cid: int) -> dict[str, Any]:
    return course_item(PhysioCourse.objects.prefetch_related("ticks").get(pk=cid))


def _detail(p: Patient, c: PhysioCourse, n: int | None = None) -> str:
    return f"{p.code} course={c.pk}" + (f" session={n}" if n is not None else "")


def _stale(cid: int) -> ApiError:
    return conflict(STALE, "PHYSIO_STALE", course=_fresh(cid))


# ---- writes -----------------------------------------------------------------------------------------

def create(request: HttpRequest, code: str) -> HttpResponse:
    me = user_of(request)
    n = _count(body(request))
    pid = find_patient(code).pk
    with transaction.atomic():
        p = get_for_update(Patient.objects.all(), pid, "patient")
        if p.status == "archived":
            raise conflict(ARCHIVED, "ARCHIVED")
        if _has_other_unfinished(p):
            raise conflict(OPEN_EXISTS, "PHYSIO_OPEN")
        c = PhysioCourse.objects.create(patient=p, sessions=n, created_by_id=me.id)
        audit(me.id, "physio_create", p.pk, _detail(p, c))
    return ok(_fresh(c.pk), 201)


def edit(request: HttpRequest, cid: str) -> HttpResponse:
    me = user_of(request)
    n = _count(body(request))
    with transaction.atomic():
        p, c = _locked(cid)
        done = c.ticks.count()
        if n < done:
            raise invalid(BELOW_DONE, {"sessions": BELOW_DONE})
        if n > done and done >= c.sessions and _has_other_unfinished(p, exclude=c.pk):
            raise conflict(OPEN_EXISTS, "PHYSIO_OPEN")
        if n != c.sessions:
            PhysioCourse.objects.filter(pk=c.pk).update(sessions=n)
            audit(me.id, "physio_count", p.pk, _detail(p, c))
    return ok(_fresh(c.pk))


def delete(request: HttpRequest, cid: str) -> HttpResponse:
    me = user_of(request)
    with transaction.atomic():
        p, c = _locked(cid)
        if c.ticks.exists():
            raise conflict(HAS_TICKS, "PHYSIO_HAS_TICKS")
        detail = _detail(p, c)
        c.delete()
        audit(me.id, "physio_delete", p.pk, detail)
    return ok({"code": p.code})


def tick(request: HttpRequest, cid: str) -> HttpResponse:
    me = user_of(request)
    data = body(request)
    number = _int(data.get("number"))
    if number is None:
        raise ApiError(400, MSG_400)
    d = _date(data, default_today=True)
    with transaction.atomic():
        p, c = _locked(cid)
        done = c.ticks.count()
        if number != done + 1:
            raise _stale(c.pk)
        if number > c.sessions:
            raise conflict(FULL, "PHYSIO_FULL", course=_fresh(c.pk))
        last = c.ticks.filter(number=done).values_list("date", flat=True).first()
        _check_order(d, last, None)
        PhysioSession.objects.create(course=c, number=number, date=d, ticked_by_id=me.id)
        audit(me.id, "physio_tick", p.pk, _detail(p, c, number))
    return ok(_fresh(c.pk), 201)


def _session_number(c: PhysioCourse, n: str) -> tuple[int, int]:
    num, done = id_of(n), c.ticks.count()
    if not 1 <= num <= done:
        raise not_found(SESSION_NOT_FOUND)
    return num, done


def edit_date(request: HttpRequest, cid: str, n: str) -> HttpResponse:
    me = user_of(request)
    data = body(request)
    with transaction.atomic():
        p, c = _locked(cid)
        num, _done = _session_number(c, n)
        d = _date(data, default_today=False)
        near = dict(c.ticks.filter(number__in=[num - 1, num + 1]).values_list("number", "date"))
        _check_order(d, near.get(num - 1), near.get(num + 1))
        PhysioSession.objects.filter(course=c, number=num).update(date=d)
        audit(me.id, "physio_date", p.pk, _detail(p, c, num))
    return ok(_fresh(c.pk))


def untick(request: HttpRequest, cid: str, n: str) -> HttpResponse:
    me = user_of(request)
    with transaction.atomic():
        p, c = _locked(cid)
        num, done = _session_number(c, n)
        if num != done:
            raise conflict(NOT_LAST, "PHYSIO_NOT_LAST", course=_fresh(c.pk))
        PhysioSession.objects.filter(course=c, number=num).delete()
        audit(me.id, "physio_untick", p.pk, _detail(p, c, num))
    return ok(_fresh(c.pk))


list_view = route(GET=list_unfinished)
patient_view = route(POST=create)
course_view = route(PATCH=edit, DELETE=delete)
sessions_view = route(POST=tick)
session_view = route(PATCH=edit_date, DELETE=untick)
