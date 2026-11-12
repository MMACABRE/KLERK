"""Finance API (SPEC §5.6; legacy src/routes/finance.js). Charts: the server returns numbers; the SPA draws."""

from __future__ import annotations

from typing import Any, cast

from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from apps.billing.models import BillLine, Payment
from apps.billing.ops import bill_for, visit_number
from apps.billing.views import KIND_LABEL, bill_json
from apps.core import present
from apps.core.audit import audit
from apps.core.codes import is_code
from apps.core.http import (
    body,
    conflict,
    id_of,
    invalid,
    not_found,
    ok,
    page_args,
    paginate,
    raw_field,
    route,
    text,
    user_of,
)
from apps.core.jalali import (
    JALALI_MONTHS,
    add_days,
    fa_digits,
    format_jalali,
    jalali_month,
    parse_jalali,
    to_jalali_input,
    week_start,
)
from apps.core.money import format_money, parse_money
from apps.core.perms import can
from apps.core.qty import parse_qty
from apps.core.settings_store import get_settings, set_settings
from apps.core.text import fa_key, normalize_text
from apps.finance import services as fin
from apps.finance.models import Account, Catalog, PayMethod
from apps.patients.models import Patient
from apps.storage.models import Lot
from apps.storage.views import read_item_form
from apps.visits.logic import hhmm
from apps.visits.models import Visit

PAGE_SIZE = 50
KINDS = ["payment", "refund", "move_out", "move_in"]


def _cur() -> str:
    return str(get_settings()["currency"])


def overview(request: HttpRequest) -> HttpResponse:
    me = user_of(request)
    cur = _cur()
    today = timezone.localdate()
    month = jalali_month(today)
    wk = week_start(today)
    figures: dict[str, Any] = {
        "today": fin.income_between(today, today),
        "week": fin.income_between(wk, today),
        "month": fin.income_between(month.start, today),
        **fin.outstanding(),
    }
    def m(r: int | None) -> dict[str, Any] | None:
        return present.money(r, cur)

    def units(v: int) -> Any:
        return cast(dict[str, Any], present.qty(v))["text"]

    days = list(reversed(fin.income_by_day(add_days(today, -29), today)))
    daily = [
        {"label": fa_digits(format_jalali(d["day"], "short")[-2:]), "value": d["total"],
         "title": f"{format_jalali(d['day'])}: {format_money(d['total'], cur)}", "highlight": d["day"] == today,
         "day": present.d(d["day"]), "money": m(d["total"])}
        for d in days
    ]
    months = []
    for i in range(6):
        jm = jalali_month(today, -i)
        inc = fin.income_between(jm.start, today if i == 0 else jm.end)["total"]
        name = JALALI_MONTHS[jm.jm - 1]
        months.append({
            "label": name, "value": inc,
            "title": f"{name} {fa_digits(str(jm.jy))}: {format_money(inc, cur)}",
            "highlight": i == 0, "money": m(inc),
        })
    source = fin.revenue_by_source(month.start, month.end)
    source_rows = [
        {"label": "خدمات", "value": source["byKind"]["service"], "money": m(source["byKind"]["service"])},
        {"label": "کالاها", "value": source["byKind"]["item"], "money": m(source["byKind"]["item"])},
    ]
    top = [{**r, "money": m(r["value"])} for r in source["top"][:8]]
    usage = None
    if can(me, "storage"):
        usage = [
            {"label": fa_digits(format_jalali(d["day"], "short")[-2:]), "value": d["total"],
             "title": f"{format_jalali(d['day'])}: {fa_digits(units(d['total']))} عدد",
             "day": present.d(d["day"])}
            for d in reversed(fin.usage_by_day(add_days(today, -29), today))
        ]
    return ok({
        "figures": {
            "today": {"total": m(figures["today"]["total"]), "count": figures["today"]["count"]},
            "week": {"total": m(figures["week"]["total"]), "count": figures["week"]["count"]},
            "month": {"total": m(figures["month"]["total"]), "count": figures["month"]["count"]},
            "remaining": m(figures["remaining"]), "credit": m(figures["credit"]),
        },
        "monthName": f"{JALALI_MONTHS[month.jm - 1]} {fa_digits(str(month.jy))}",
        "currency": cur,
        "charts": {"daily": daily, "monthly": months, "source": source_rows, "top": top, "usage": usage},
        "billDisc": m(source["billDisc"]),
    })


def payments(request: HttpRequest) -> HttpResponse:
    cur = _cur()
    q = request.GET
    today = timezone.localdate()
    start = parse_jalali(q.get("from")) or jalali_month(today).start
    end = parse_jalali(q.get("to")) or today
    method = id_of(q.get("method", ""))
    account = id_of(q.get("account", ""))
    kind = q.get("kind", "")
    kind = kind if kind in KINDS else ""
    rows = Payment.objects.filter(paid_on__range=(start, end))
    if method:
        rows = rows.filter(method_id=method)
    if account:
        rows = rows.filter(account_id=account)
    if kind:
        rows = rows.filter(kind=kind)
    from apps.core.aggregates import sum_rial

    total = sum_rial(rows, "amount")
    income = sum_rial(rows.filter(kind__in=["payment", "refund"]), "amount")
    n = rows.count()
    page, size = page_args(request, PAGE_SIZE)
    pg = paginate(n, page, size)
    s = (pg["page"] - 1) * size
    chunk = rows.select_related("visit__patient", "method", "account").order_by("-paid_on", "-id")[s : s + size]
    return ok({
        "data": [
            {
                "id": p.pk, "amount": present.money(p.amount, cur), "kind": p.kind, "kindLabel": KIND_LABEL[p.kind],
                "paidOn": present.d(p.paid_on), "method": p.method.name if p.method else None,
                "account": p.account.name if p.account else None, "note": p.note, "visitId": p.visit_id,
                "visitDate": present.d(p.visit.visit_date),
                "patient": {"code": p.visit.patient.code, "firstName": p.visit.patient.first_name,
                            "lastName": p.visit.patient.last_name},
            }
            for p in chunk
        ],
        "pagination": pg,
        "sum": {"n": n, "total": present.money(total, cur), "income": present.money(income, cur)},
        "filters": {"from": to_jalali_input(start), "to": to_jalali_input(end), "method": method or "",
                    "account": account or "", "kind": kind},
        "methods": [{"id": x.pk, "name": x.name} for x in PayMethod.objects.order_by("id")],
        "accounts": [{"id": x.pk, "name": x.name} for x in Account.objects.order_by("id")],
        "kinds": KIND_LABEL,
    })


def pay(request: HttpRequest) -> HttpResponse:
    cur = _cur()
    q = request.GET
    patient = None
    chosen = id_of(q.get("visit", ""))
    if chosen:
        pid = Visit.objects.filter(pk=chosen).values_list("patient_id", flat=True).first()
        patient = Patient.objects.filter(pk=pid).first() if pid else None
    elif is_code(q.get("patient", "")):
        patient = Patient.objects.filter(code=q.get("patient")).first()
    term = normalize_text(q.get("q", "")[:100])
    found = []
    if patient is None and term:
        found = [
            {"code": p.code, "firstName": p.first_name, "lastName": p.last_name, "phone": p.phone}
            for p in Patient.objects.filter(
                Q(name_key__contains=fa_key(term)) | Q(code__contains=term) | Q(phone__contains=term)
            )
            .order_by("last_name_sort", "first_name_sort")[:20]
        ]
    visits = []
    if patient:
        visit_rows = Visit.objects.filter(patient=patient).exclude(status="cancelled")
        for v in visit_rows.order_by("-visit_date", "-visit_time"):
            b = bill_for(v)
            if b["remaining"] > 0 or v.status == "scheduled" or v.pk == chosen:
                visits.append({
                    "id": v.pk, "date": present.d(v.visit_date), "time": hhmm(v.visit_time),
                    "status": v.status, "number": visit_number(v), "bill": bill_json(b, cur),
                })
    return ok({
        "q": term, "found": found,
        "patient": (
            {"code": patient.code, "firstName": patient.first_name, "lastName": patient.last_name}
            if patient else None
        ),
        "visits": visits, "chosen": chosen,
        "methods": [{"id": x.pk, "name": x.name, "defaultAccount": x.default_account_id}
                    for x in PayMethod.objects.filter(active=True).order_by("id")],
        "accounts": [{"id": x.pk, "name": x.name} for x in Account.objects.filter(active=True).order_by("id")],
        "today": to_jalali_input(timezone.localdate()),
    })


# ---- settings -----------------------------------------------------------------------------------

def _used_catalog(cid: int) -> bool:
    return BillLine.objects.filter(catalog_id=cid).exists() or Lot.objects.filter(item_id=cid).exists()


def get_finance_settings(request: HttpRequest) -> HttpResponse:
    cur = _cur()
    s = get_settings()
    return ok({
        "settings": {
            "currency": s["currency"], "lowWarn": present.qty(s["low_warn"]), "lowCrit": present.qty(s["low_crit"]),
            "clinicName": s["clinic_name"], "clinicAddress": s["clinic_address"], "clinicPhone": s["clinic_phone"],
        },
        "catalog": [
            {"id": c.pk, "kind": c.kind, "name": c.name, "salePrice": present.money(c.sale_price, cur),
             "purchaseCost": present.money(c.purchase_cost, cur), "fixed": c.fixed, "active": c.active,
             "lowWarn": present.qty(c.low_warn), "lowCrit": present.qty(c.low_crit), "used": _used_catalog(c.pk)}
            for c in Catalog.objects.filter(deleted_at__isnull=True).order_by("-fixed", "-kind", "-active", "name")
        ],
        "methods": [
            {"id": x.pk, "name": x.name, "defaultAccount": x.default_account_id, "active": x.active,
             "used": Payment.objects.filter(method=x).exists()}
            for x in PayMethod.objects.order_by("id")
        ],
        "accounts": [
            {"id": x.pk, "name": x.name, "active": x.active,
             "used": Payment.objects.filter(account=x).exists() or PayMethod.objects.filter(default_account=x).exists()}
            for x in Account.objects.order_by("id")
        ],
    })


def put_finance_settings(request: HttpRequest) -> HttpResponse:
    me = user_of(request)
    data = body(request)
    errors: dict[str, str] = {}
    currency = "R" if text(data, "currency") == "R" else "T"
    warn = parse_qty(raw_field(data, "lowWarn"), allow_zero=True)
    crit = parse_qty(raw_field(data, "lowCrit"), allow_zero=True)
    if warn is None or warn != warn:
        errors["lowWarn"] = "یک عدد وارد کنید (تا دو رقم اعشار)."
    if crit is None or crit != crit:
        errors["lowCrit"] = "یک عدد وارد کنید (تا دو رقم اعشار)."
    if not errors and crit > warn:  # type: ignore[operator]
        errors["lowCrit"] = "حد بحرانی نباید از حد هشدار بیشتر باشد."
    name = normalize_text(text(data, "clinicName"))[:120]
    if not name:
        errors["clinicName"] = "نام کلینیک را وارد کنید."
    if errors:
        raise invalid("لطفاً خطاهای مشخص‌شده را برطرف کنید.", errors)
    wt, ct = present.qty(warn)["text"], present.qty(crit)["text"]  # type: ignore[index]
    with transaction.atomic():
        set_settings({
            "currency": currency, "low_warn": wt, "low_crit": ct, "clinic_name": name,
            "clinic_address": normalize_text(text(data, "clinicAddress"))[:300],
            "clinic_phone": normalize_text(text(data, "clinicPhone"))[:60],
        })
        audit(me.id, "finance_settings", None, f"currency={currency} warn={wt} crit={ct}")
    return ok({"notice": "تنظیمات ذخیره شد."})


def add_catalog(request: HttpRequest) -> HttpResponse:
    me = user_of(request)
    data = body(request)
    kind = "item" if text(data, "kind") == "item" else "service"
    errors, row = read_item_form(data, _cur())
    if errors:
        raise invalid(next(iter(errors.values())), {"catalog": next(iter(errors.values())), **errors})
    with transaction.atomic():
        c = Catalog.objects.create(
            kind=kind, name=row["name"], sale_price=row["sale_price"],
            purchase_cost=row["purchase_cost"] if kind == "item" else None,
            low_warn=row["low_warn"] if kind == "item" else None, low_crit=row["low_crit"] if kind == "item" else None,
        )
        audit(me.id, "catalog_add", None, f"{kind}={c.pk} price={row['sale_price']}")
    return ok({"id": c.pk}, 201)


def _entry(cid: str) -> Catalog:
    c = Catalog.objects.filter(pk=id_of(cid), deleted_at__isnull=True).first()
    if c is None:
        raise not_found("این مورد پیدا نشد.")
    return c


def edit_catalog(request: HttpRequest, cid: str) -> HttpResponse:
    me = user_of(request)
    c = _entry(cid)
    data = body(request)
    name = normalize_text(text(data, "name"))[:120]
    price = parse_money(raw_field(data, "salePrice"), _cur())
    if not name or price is None:
        raise invalid("نام و قیمت فروش را درست وارد کنید.", {f"c{c.pk}": "نام و قیمت فروش را درست وارد کنید."})
    active = data.get("active") in (True, "1", 1)
    with transaction.atomic():
        old = c.sale_price
        c.name, c.sale_price, c.active = name, price, active
        c.save()
        audit(me.id, "catalog_edit", None, f"catalog={c.pk} price={old}->{price} active={1 if active else 0}")
    return ok()


def delete_catalog(request: HttpRequest, cid: str) -> HttpResponse:
    me = user_of(request)
    c = _entry(cid)
    if _used_catalog(c.pk):
        raise conflict("این مورد در صورتحساب یا انبار به کار رفته است؛ فقط می‌توان آن را غیرفعال کرد.")
    with transaction.atomic():
        c.delete()
        audit(me.id, "catalog_delete", None, f"catalog={cid}")
    return ok()


def _list_views(kind: str) -> tuple[Any, Any, Any]:
    model: Any = PayMethod if kind == "method" else Account

    def used(row: Any) -> bool:
        if kind == "method":
            return Payment.objects.filter(method=row).exists()
        return Payment.objects.filter(account=row).exists() or PayMethod.objects.filter(default_account=row).exists()

    def account_of(v: str) -> int | None:
        i = id_of(v)
        return i if i and Account.objects.filter(pk=i).exists() else None

    def add(request: HttpRequest) -> HttpResponse:
        me = user_of(request)
        data = body(request)
        name = normalize_text(text(data, "name"))[:80]
        if not name:
            raise invalid("نام را وارد کنید.", {kind: "نام را وارد کنید."})
        with transaction.atomic():
            if kind == "method":
                row: Any = PayMethod.objects.create(
                    name=name, default_account_id=account_of(text(data, "defaultAccount")),
                )
            else:
                row = Account.objects.create(name=name)
            audit(me.id, "finance_settings", None, f"{kind}_add={row.pk}")
        return ok({"id": row.pk}, 201)

    def edit(request: HttpRequest, rid: str) -> HttpResponse:
        me = user_of(request)
        row = model.objects.filter(pk=id_of(rid)).first()
        if row is None:
            raise not_found("این مورد پیدا نشد.")
        data = body(request)
        name = normalize_text(text(data, "name"))[:80]
        if not name:
            raise invalid("نام را وارد کنید.", {kind: "نام را وارد کنید."})
        active = data.get("active") in (True, "1", 1)
        with transaction.atomic():
            row.name, row.active = name, active
            if kind == "method":
                row.default_account_id = account_of(text(data, "defaultAccount"))
            row.save()
            audit(me.id, "finance_settings", None, f"{kind}_edit={row.pk} active={1 if active else 0}")
        return ok()

    def delete(request: HttpRequest, rid: str) -> HttpResponse:
        me = user_of(request)
        row = model.objects.filter(pk=id_of(rid)).first()
        if row is None:
            raise not_found("این مورد پیدا نشد.")
        if used(row):
            raise conflict("این مورد به کار رفته است؛ فقط می‌توان آن را غیرفعال کرد.")
        with transaction.atomic():
            pk = row.pk
            row.delete()
            audit(me.id, "finance_settings", None, f"{kind}_delete={pk}")
        return ok()

    return add, edit, delete


_m_add, _m_edit, _m_delete = _list_views("method")
_a_add, _a_edit, _a_delete = _list_views("account")

settings_view = route(GET=get_finance_settings, PUT=put_finance_settings)
catalog_view = route(POST=add_catalog)
catalog_item_view = route(PATCH=edit_catalog, DELETE=delete_catalog)
methods_view = route(POST=_m_add)
method_view = route(PATCH=_m_edit, DELETE=_m_delete)
accounts_view = route(POST=_a_add)
account_view = route(PATCH=_a_edit, DELETE=_a_delete)
