"""Printable documents (SPEC §5.12; legacy src/routes/print.js). Server-rendered HTML on print.css; the browser's
Print / Save as PDF makes the PDF. The pdf area is checked by the gate; each document also checks every area whose
data it shows, here. Values are prepared as display text in Python; templates only place them (auto-escaped)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from apps.billing.models import BillLine, Payment
from apps.billing.ops import bill_for, visit_number
from apps.core.audit import audit
from apps.core.codes import is_code
from apps.core.http import id_of, user_of
from apps.core.jalali import fa_digits, format_jalali, format_jalali_datetime, jalali_month, parse_jalali
from apps.core.labels import CATEGORY, SEX, STATUS
from apps.core.money import discount_of, format_money
from apps.core.perms import can
from apps.core.settings_store import get_settings
from apps.documents.services import documents_for
from apps.patients.models import Medication, Patient
from apps.storage.models import Lot
from apps.storage.services import days_until, expiry_level, items_with_stock, qty_text
from apps.visits.logic import hhmm
from apps.visits.models import Visit

PAY = {"payment": "پرداخت", "refund": "بازپرداخت", "move_in": "انتقال از ویزیت", "move_out": "انتقال به ویزیت"}
BILL_KIND = {
    "payment": "پرداخت",
    "refund": "بازپرداخت",
    "move_out": "انتقال به ویزیت دیگر",
    "move_in": "انتقال از ویزیت دیگر",
}
STATE = {"expired": "منقضی شده", "crit": "انقضای نزدیک", "warn": "انقضا در ۳۰ روز"}


class _Stop(Exception):
    def __init__(self, response: HttpResponse) -> None:
        self.response = response


def _error(request: HttpRequest, status: int, message: str) -> HttpResponse:
    return render(request, "print/error.html", {"status": status, "message": message}, status=status)


def _day(request: HttpRequest, key: str, fallback: date) -> date:
    raw = request.GET.get(key, "").strip()
    if not raw:
        return fallback
    d = parse_jalali(raw)
    if d is None:
        raise _Stop(_error(request, 422, "تاریخ نامعتبر است. نمونه: ۱۴۰۵/۰۸/۰۱"))
    return d


def _needs(request: HttpRequest, *areas: str) -> None:
    me = user_of(request)
    if not all(can(me, a) for a in areas):
        raise _Stop(_error(request, 403, "شما اجازه‌ی دسترسی به این بخش را ندارید."))


def _show(
    request: HttpRequest, template: str, data: dict[str, Any], doc: str, patient_id: int | None = None
) -> HttpResponse:
    me = user_of(request)
    audit(me.id, "print", patient_id, doc)
    s = get_settings()
    return render(request, f"print/{template}.html", {
        **data, "clinic": s, "generated": format_jalali_datetime(timezone.now()), "by": me.display_name,
    })


def guarded(fn: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
    def view(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if request.method not in ("GET", "HEAD"):
            return HttpResponse(status=405)
        try:
            return fn(request, *args, **kwargs)
        except _Stop as stop:
            return stop.response

    return view


def _m(cur: str) -> Callable[[Any], str]:
    def fmt(r: Any) -> str:
        return format_money(int(r), cur)

    return fmt


def _cur() -> str:
    return str(get_settings()["currency"])


def _q(v: Any) -> str:
    return fa_digits(qty_text(v))


@guarded
def finance_day(request: HttpRequest) -> HttpResponse:
    _needs(request, "finance", "patients")
    m = _m(_cur())
    day = _day(request, "d", timezone.localdate())
    pays = list(
        Payment.objects.filter(paid_on=day, kind__in=["payment", "refund"])
        .select_related("visit__patient", "method", "account")
        .order_by("created_at", "id")
    )
    rows = []
    by_method: dict[str, int] = {}
    by_account: dict[str, int] = {}
    for i, p in enumerate(pays):
        v = p.visit
        kind = "بازپرداخت" if p.kind == "refund" else ("پیش‌پرداخت" if v.visit_date > day else "پرداخت")
        rows.append({
            "n": fa_digits(str(i + 1)),
            "name": f"{v.patient.first_name} {v.patient.last_name}",
            "code": v.patient.code,
            "visit": format_jalali(v.visit_date, "short"),
            "kind": kind,
            "method": p.method.name if p.method else "—",
            "account": p.account.name if p.account else "—",
            "amount": m(p.amount),
            "neg": p.amount < 0,
        })
        km = p.method.name if p.method else "—"
        ka = p.account.name if p.account else "—"
        by_method[km] = by_method.get(km, 0) + p.amount
        by_account[ka] = by_account.get(ka, 0) + p.amount
    total = sum(p.amount for p in pays)
    return _show(request, "finance_day", {
        "title": "گزارش مالی روزانه", "params": [format_jalali(day), "درآمد بر اساس روز پرداخت"], "size": "a4",
        "back": "/finance", "rows": rows, "total": m(total), "count": len(rows),
        "by_method": [(k, m(v)) for k, v in by_method.items()],
        "by_account": [(k, m(v)) for k, v in by_account.items()],
    }, f"finance_day {day.isoformat()}")


def _day_visits(day: date) -> list[Visit]:
    return list(Visit.objects.select_related("patient").filter(visit_date=day).exclude(status="cancelled")
                .order_by("visit_time", "id"))


@guarded
def visits_day(request: HttpRequest) -> HttpResponse:
    _needs(request, "visits", "patients", "finance")
    m = _m(_cur())
    day = _day(request, "d", timezone.localdate())
    rows = []
    tot = {"owed": 0, "paid": 0, "remaining": 0}
    for v in _day_visits(day):
        b = bill_for(v)
        for k in tot:
            tot[k] += b[k]

        def uniq(attr: str, b: dict[str, Any] = b) -> str:
            seen: list[str] = []
            for p in b["payments"]:
                name = getattr(getattr(p, attr), "name", None) if getattr(p, attr) else None
                if name and name not in seen:
                    seen.append(name)
            return "، ".join(seen)

        rows.append({
            "time": hhmm(v.visit_time), "code": v.patient.code,
            "name": f"{v.patient.first_name} {v.patient.last_name}",
            "number": fa_digits(str(visit_number(v) or "")), "owed": m(b["owed"]), "paid": m(b["paid"]),
            "methods": uniq("method") or "—", "accounts": uniq("account") or "—",
            "rest": ("بستانکار " + m(b["credit"])) if b["credit"] else m(b["remaining"]),
        })
    return _show(request, "visits_day", {
        "title": "فهرست ویزیت‌های روز",
        "params": [format_jalali(day), fa_digits(str(len(rows))) + " ویزیت"],
        "size": "a4",
        "back": "/visits", "rows": rows, "totals": {k: m(v) for k, v in tot.items()},
    }, f"visits_day {day.isoformat()}")


@guarded
def visits_report(request: HttpRequest) -> HttpResponse:
    _needs(request, "visits", "patients", "finance")
    m = _m(_cur())
    day = _day(request, "d", timezone.localdate())
    blocks = []
    by_account: dict[str, int] = {}
    tot = {"owed": 0, "paid": 0, "remaining": 0, "credit": 0}
    for i, v in enumerate(_day_visits(day)):
        b = bill_for(v)
        for k in tot:
            tot[k] += b[k]
        lines = []
        for x in b["lines"]:
            ln = x["line"]
            price = ln.override_price if ln.override_price is not None else ln.unit_price
            lines.append({
                "name": ln.name, "item": ln.kind == "item",
                "kind": "کالا" if ln.kind == "item" else "خدمت",
                "disc": m(x["disc"]) if x["disc"] else "", "qty": _q(ln.qty), "price": m(price),
                "net": m(x["net"]),
            })
        pays = []
        for p in b["payments"]:
            if p.kind in ("move_in", "move_out"):
                od = b["other_dates"].get(p.pk)
                detail = " " + format_jalali(od, "short") if od else ""
            else:
                detail = f" · {p.method.name if p.method else '—'} · {p.account.name if p.account else '—'}"
                key = p.account.name if p.account else "—"
                by_account[key] = by_account.get(key, 0) + p.amount
            pays.append({
                "label": PAY[p.kind] + detail,
                "date": format_jalali(p.paid_on, "short") if p.paid_on != day else "",
                "amount": m(p.amount), "neg": p.amount < 0,
            })
        blocks.append({
            "n": fa_digits(str(i + 1)), "code": v.patient.code, "name": f"{v.patient.first_name} {v.patient.last_name}",
            "time": hhmm(v.visit_time), "reason": v.reason or "—", "lines": lines,
            "bill_disc": m(-b["billDisc"]) if b["billDisc"] else "", "pays": pays, "owed": m(b["owed"]),
            "rest_label": "بستانکار" if b["credit"] else "مانده" if b["remaining"] else "",
            "rest": m(b["credit"] or b["remaining"]),
        })
    return _show(request, "visits_report", {
        "title": "گزارش کامل روزانه",
        "params": [format_jalali(day), "بر اساس روز ویزیت", fa_digits(str(len(blocks))) + " ویزیت"],
        "size": "a4", "body_class": "print-report", "back": "/print", "blocks": blocks,
        "by_account": [(k, m(v), v < 0) for k, v in by_account.items()], "account_total": m(sum(by_account.values())),
        "totals": {k: m(v) for k, v in tot.items()}, "has_credit": tot["credit"] > 0,
    }, f"visits_report {day.isoformat()}")


def _net(ln: BillLine) -> int:
    from apps.core.money import line_gross

    price = ln.override_price if ln.override_price is not None else ln.unit_price
    g = line_gross(int(price), float(ln.qty))
    return g - discount_of(g, ln.disc_kind, ln.disc_value)


@guarded
def stock_usage(request: HttpRequest) -> HttpResponse:
    _needs(request, "storage")
    me = user_of(request)
    by_patient = request.GET.get("by") == "patient"
    if by_patient:
        _needs(request, "patients")
    show_money = can(me, "finance")
    cur = _cur()
    m: Callable[[Any], str] = _m(cur) if show_money else (lambda r: "—")
    today = timezone.localdate()
    start = _day(request, "from", jalali_month(today).start)
    end = _day(request, "to", today)
    qs = (
        BillLine.objects.filter(kind="item", visit__visit_date__range=(start, end))
        .exclude(visit__status="cancelled")
        .select_related("visit__patient")
    )
    order = (
        ["visit__patient__last_name", "visit__patient__first_name", "visit__patient__code", "name"]
        if by_patient else ["name"]
    )
    lines = list(qs.order_by(*order))
    rows: list[dict[str, Any]] = []
    total_qty = Decimal("0")
    total_amount = 0
    if by_patient:
        for ln in lines:
            p = ln.visit.patient
            rows.append({
                "name": f"{p.first_name} {p.last_name}", "code": p.code,
                "day": format_jalali(ln.visit.visit_date, "short"),
                "item": ln.name, "qty": _q(ln.qty), "amount": m(_net(ln)),
            })
            total_qty += ln.qty
            total_amount += _net(ln)
    else:
        agg: dict[str, list[Any]] = {}
        for ln in lines:
            r = agg.setdefault(ln.name, [Decimal("0"), 0])
            r[0] += ln.qty
            r[1] += _net(ln)
        for name, (q, a) in agg.items():
            rows.append({"item": name, "qty": _q(q), "amount": m(a)})
            total_qty += q
            total_amount += a
    return _show(request, "stock_usage", {
        "title": "کالاهای مصرف‌شده",
        "params": [
            format_jalali(start, "short") + " تا " + format_jalali(end, "short"),
            "به تفکیک بیمار" if by_patient else "به تفکیک کالا",
        ],
        "size": "a4", "back": "/storage", "by_patient": by_patient, "rows": rows, "total_qty": _q(total_qty),
        "total_amount": m(total_amount),
    }, f"stock_usage {start.isoformat()} {end.isoformat()} {'patient' if by_patient else 'item'}")


@guarded
def stock_day(request: HttpRequest) -> HttpResponse:
    _needs(request, "storage", "patients", "visits")
    me = user_of(request)
    cur = _cur()
    finance = can(me, "finance")
    m: Callable[[Any], str] = _m(cur) if finance else (lambda r: "—")
    day = _day(request, "d", timezone.localdate())
    blocks: list[dict[str, Any]] = []
    by_item: dict[str, dict[str, Any]] = {}
    patients: set[int] = set()
    for v in _day_visits(day):
        b = bill_for(v)
        items = [x for x in b["lines"] if x["line"].kind == "item"]
        if not items:
            continue
        patients.add(v.patient_id)
        lines = []
        for x in items:
            ln = x["line"]
            price = ln.override_price if ln.override_price is not None else ln.unit_price
            lines.append({
                "name": ln.name, "disc": m(x["disc"]) if finance and x["disc"] else "", "qty": _q(ln.qty),
                "price": m(price), "net": m(x["net"]),
            })
            r = by_item.setdefault(ln.name, {"qty": Decimal("0"), "amount": 0, "patients": set()})
            r["qty"] += ln.qty
            r["amount"] += x["net"]
            r["patients"].add(v.patient_id)
        blocks.append({"n": fa_digits(str(len(blocks) + 1)), "code": v.patient.code,
                       "name": f"{v.patient.first_name} {v.patient.last_name}", "time": hhmm(v.visit_time),
                       "reason": v.reason or "—", "lines": lines})
    items_rows = [
        {"item": k, "patients": fa_digits(str(len(r["patients"]))), "qty": _q(r["qty"]), "amount": m(r["amount"])}
        for k, r in sorted(by_item.items())
    ]
    return _show(request, "stock_day", {
        "title": "گزارش روزانه‌ی مصرف کالا",
        "params": [
            format_jalali(day), fa_digits(str(len(patients))) + " بیمار", fa_digits(str(len(items_rows))) + " کالا",
        ],
        "size": "a4", "back": "/print", "blocks": blocks, "items": items_rows,
        "patient_count": fa_digits(str(len(patients))),
        "total_amount": m(sum(r["amount"] for r in by_item.values())),
    }, f"stock_day {day.isoformat()}")


@guarded
def stock_inventory(request: HttpRequest) -> HttpResponse:
    _needs(request, "storage")
    s = get_settings()
    today = timezone.localdate()
    lots = sorted(
        Lot.objects.filter(remaining__gt=0),
        key=lambda lot: (lot.expires_on is None, lot.expires_on or today, lot.pk),
    )
    items: list[dict[str, Any]] = []
    alert_count = 0
    for row in items_with_stock(s, today):
        it = row["item"]
        if row["low"] or row["expiry"]:
            alert_count += 1
        mine = []
        for lot in lots:
            if lot.item_id != it.pk:
                continue
            lvl = expiry_level(lot, today)
            d = days_until(lot.expires_on, today) if lot.expires_on else None
            left = "" if d is None else (
                fa_digits(str(-d)) + " روز گذشته" if d < 0 else "امروز" if d == 0 else fa_digits(str(d)) + " روز مانده"
            )
            mine.append({
                "received": format_jalali(lot.received_on, "short"), "qty_in": _q(lot.qty_in),
                "remaining": _q(lot.remaining),
                "expires": format_jalali(lot.expires_on, "short") if lot.expires_on else "بدون تاریخ انقضا",
                "left": left, "level": lvl or "", "state": STATE.get(lvl or "", "سالم"),
            })
        items.append({
            "n": fa_digits(str(len(items) + 1)), "name": it.name, "usable": _q(row["usable"]),
            "low": row["low"] or "",
            "low_text": ("موجودی بحرانی" if row["low"] == "crit" else "موجودی کم") if row["low"] else "",
            "lots": mine,
        })
    return _show(request, "stock_inventory", {
        "title": "موجودی انبار",
        "params": [format_jalali(today), fa_digits(str(len(items))) + " کالا", fa_digits(str(alert_count)) + " هشدار"],
        "size": "a4", "back": "/storage", "items": items,
    }, "stock_inventory")


@guarded
def bill(request: HttpRequest, vid: str) -> HttpResponse:
    _needs(request, "finance", "patients")
    m = _m(_cur())
    v = Visit.objects.select_related("patient").filter(pk=id_of(vid)).first()
    if v is None:
        return _error(request, 404, "ویزیت مورد نظر پیدا نشد.")
    b = bill_for(v)
    number = visit_number(v)
    lines = []
    for x in b["lines"]:
        ln = x["line"]
        price = ln.override_price if ln.override_price is not None else ln.unit_price
        lines.append({
            "name": ln.name, "qty": _q(ln.qty), "price": m(price),
            "disc": m(x["disc"]) if x["disc"] else "—", "net": m(x["net"]),
        })
    pays = [
        {
            "date": format_jalali(p.paid_on, "short"), "kind": BILL_KIND[p.kind],
            "method": p.method.name if p.method else "", "amount": m(p.amount),
        }
        for p in b["payments"]
    ]
    return _show(request, "bill", {
        "title": "صورتحساب ویزیت",
        "params": [format_jalali(v.visit_date), ("ویزیت " + fa_digits(str(number))) if number else "لغوشده"],
        "size": "a5", "back": f"/visits/{v.pk}",
        "name": f"{v.patient.first_name} {v.patient.last_name}", "code": v.patient.code,
        "time": hhmm(v.visit_time), "lines": lines, "pays": pays, "gross": m(b["gross"]),
        "discount": m(b["discount"]),
        "paid": m(b["paid"]), "rest_label": "بستانکار" if b["credit"] else "مانده",
        "rest": m(b["credit"] or b["remaining"]),
        "cancelled": b["cancelled"],
    }, f"bill visit={v.pk}", v.patient_id)


@guarded
def patient(request: HttpRequest, code: str) -> HttpResponse:
    _needs(request, "patients")
    me = user_of(request)
    m = _m(_cur())
    p = Patient.objects.filter(code=code).first() if is_code(code) else None
    if p is None:
        return _error(request, 404, "پرونده‌ی مورد نظر پیدا نشد.")
    finance = can(me, "finance")
    dash = "—"

    def num(v: Any, unit: str) -> str | None:
        if v is None:
            return None
        s = format(v.normalize(), "f")
        return fa_digits(s) + " " + unit

    kv = [
        ("کد بیمار", p.code, True), ("نام پدر", p.father_name, False), ("کد ملی", p.national_id, True),
        ("تاریخ تولد", format_jalali(p.birth_date) if p.birth_date else None, False),
        ("جنسیت", SEX.get(p.sex or "") if p.sex else None, False), ("تلفن", p.phone, True), ("شهر", p.city, False),
        ("گروه خونی", p.blood_type, True), ("قد", num(p.height_cm, "سانتی‌متر"), False),
        ("وزن", num(p.weight_kg, "کیلوگرم"), False), ("فشار خون", p.blood_pressure, True),
        ("بیمه", p.insurance_name, False), ("وضعیت", STATUS[p.status]["label"], False),
    ]
    visits = None
    if can(me, "visits"):
        visits = []
        for v in Visit.objects.filter(patient=p).order_by("visit_date", "visit_time"):
            n = visit_number(v)
            b = bill_for(v) if finance else None
            visits.append({
                "label": ("ویزیت " + fa_digits(str(n))) if n else "ویزیت لغوشده", "date": format_jalali(v.visit_date),
                "time": hhmm(v.visit_time), "reason": v.reason, "note": v.doctor_note,
                "lines": (
                    [{"name": x["line"].name, "qty": _q(x["line"].qty), "net": m(x["net"])} for x in b["lines"]]
                    if b else []
                ),
                "has_bill": bool(b and (b["lines"] or b["payments"])),
                "owed": m(b["owed"]) if b else "", "paid": m(b["paid"]) if b else "",
            })
    files = None
    if can(me, "documents"):
        from datetime import datetime

        files = []
        for f in documents_for(p):
            row = f["row"]
            when = row.doc_date if row and row.doc_date else (
                timezone.localtime(datetime.fromisoformat(f["modified"].replace("Z", "+00:00"))).date()
            )
            files.append({
                "title": (row.title if row and row.title else f["filename"]),
                "filename": f["filename"] if row and row.title else "",
                "category": CATEGORY[row.category] if row else "طبقه‌بندی نشده",
                "date": format_jalali(when, "short"),
            })
    return _show(request, "patient", {
        "title": "پرونده‌ی کامل بیمار", "params": [f"{p.first_name} {p.last_name}", p.code], "size": "a4",
        "back": f"/patients/{p.code}", "kv": [(k, v or dash, mono) for k, v, mono in kv], "p": p,
        "medications": Medication.objects.filter(patient=p).order_by("id"), "visits": visits,
        "visit_count": fa_digits(str(len(visits))) if visits is not None else "", "files": files,
        "file_count": fa_digits(str(len(files))) if files is not None else "",
    }, f"patient {p.code}", p.pk)
