"""Visit page with its bill and payments (SPEC §5.5; legacy src/routes/bill.js)."""

from __future__ import annotations

from typing import Any, cast

from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from apps.billing import ops
from apps.billing.models import BillLine, Payment
from apps.billing.services import lock_visits
from apps.core import present
from apps.core.audit import audit
from apps.core.http import body, conflict, id_of, invalid, not_found, ok, raw_field, text, user_of
from apps.core.jalali import parse_jalali, to_jalali_input
from apps.core.money import describe_discount, line_too_large, parse_discount, parse_money
from apps.core.perms import EDIT, can
from apps.core.qty import parse_qty
from apps.core.settings_store import get_settings
from apps.core.text import fa_key, normalize_text
from apps.finance.models import Account, Catalog, PayMethod
from apps.storage.services import available, to_qty
from apps.visits.logic import end_time, flags, hhmm
from apps.visits.models import Visit

KIND_LABEL = {
    "payment": "پرداخت",
    "refund": "بازپرداخت",
    "move_out": "انتقال به ویزیت دیگر",
    "move_in": "انتقال از ویزیت دیگر",
}


def _cur() -> str:
    return str(get_settings()["currency"])


def _user(me: Any) -> Any:
    from apps.accounts.models import User

    return User.objects.filter(pk=me.id).first()


def bill_json(b: dict[str, Any], cur: str) -> dict[str, Any]:
    def m(r: int | None) -> dict[str, Any] | None:
        return present.money(r, cur)

    return {
        "lines": [
            {
                "id": x["line"].pk, "kind": x["line"].kind, "name": x["line"].name, "qty": present.qty(x["line"].qty),
                "unitPrice": m(x["line"].unit_price),
                "overridePrice": m(x["line"].override_price) if x["line"].override_price is not None else None,
                "discKind": x["line"].disc_kind, "discValue": x["line"].disc_value,
                "discText": describe_discount(x["line"].disc_kind, x["line"].disc_value, cur),
                "gross": m(x["gross"]), "disc": m(x["disc"]), "net": m(x["net"]),
            }
            for x in b["lines"]
        ],
        "payments": [
            {
                "id": p.pk, "amount": m(p.amount), "kind": p.kind, "kindLabel": KIND_LABEL.get(p.kind, p.kind),
                "paidOn": present.d(p.paid_on), "method": p.method.name if p.method else None,
                "methodId": p.method_id, "accountId": p.account_id,
                "account": p.account.name if p.account else None, "note": p.note,
                "who": p.created_by.display_name if p.created_by else None, "moveId": p.move_id,
                "otherDate": present.d(b["other_dates"].get(p.pk)),
            }
            for p in b["payments"]
        ],
        "cancelled": b["cancelled"],
        **{
            k: m(b[k])
            for k in ("gross", "lineDisc", "subtotal", "billDisc", "discount", "owed", "paid", "remaining", "credit")
        },
    }


def _catalog_choices() -> list[dict[str, Any]]:
    cur = _cur()
    today = timezone.localdate()
    rows = Catalog.objects.filter(active=True, deleted_at__isnull=True).order_by("-fixed", "-kind", "name")
    out = []
    for r in rows:
        item = {"id": r.pk, "kind": r.kind, "name": r.name, "price": present.money(r.sale_price, cur), "fixed": r.fixed}
        if r.kind == "item":
            item["usable"] = present.qty(available(r.pk, today))
        out.append(item)
    return out


def visit_page(request: HttpRequest, v: Visit, notice: str | None = None) -> HttpResponse:
    me = user_of(request)
    cur = _cur()
    f = flags(v)
    p = v.patient
    out: dict[str, Any] = {
        "visit": {
            "id": v.pk, "date": present.d(v.visit_date), "time": hhmm(v.visit_time),
            "until": end_time(v.visit_time, v.duration_min), "durationMin": v.duration_min, "reason": v.reason,
            "notes": v.notes, "status": v.status, "doctorNote": v.doctor_note, "reminderLead": v.reminder_lead,
            "discKind": v.disc_kind, "discValue": v.disc_value,
            "discText": describe_discount(v.disc_kind, v.disc_value, cur),
            "overdue": f["overdue"], "ongoing": f["ongoing"],
        },
        "patient": {"code": p.code, "firstName": p.first_name, "lastName": p.last_name, "status": p.status,
                    "discKind": p.disc_kind, "discValue": p.disc_value},
        "number": ops.visit_number(v),
        "today": to_jalali_input(timezone.localdate()),
        "notice": notice,
    }
    if can(me, "finance"):
        out["bill"] = bill_json(ops.bill_for(v), cur)
        out["targets"] = [
            {"id": t.pk, "date": present.d(t.visit_date), "time": hhmm(t.visit_time)}
            for t in Visit.objects.filter(patient_id=v.patient_id).exclude(pk=v.pk).exclude(status="cancelled")
            .order_by("-visit_date", "-visit_time")[:30]
        ]
        out["methods"] = [{"id": m.pk, "name": m.name, "defaultAccount": m.default_account_id}
                          for m in PayMethod.objects.filter(active=True).order_by("id")]
        out["accounts"] = [{"id": a.pk, "name": a.name} for a in Account.objects.filter(active=True).order_by("id")]
    if can(me, "finance", EDIT):
        out["catalog"] = _catalog_choices()
    return ok(out)


def _visit(vid: str) -> Visit:
    v = Visit.objects.select_related("patient").filter(pk=id_of(vid)).first()
    if v is None:
        raise not_found("ویزیت مورد نظر پیدا نشد.")
    return v


def _line(v: Visit, lid: str) -> BillLine:
    line = BillLine.objects.filter(pk=id_of(lid), visit=v).first()
    if line is None:
        raise not_found("این ردیف پیدا نشد.")
    return line


def add_line(request: HttpRequest, vid: str) -> HttpResponse:
    me = user_of(request)
    v = _visit(vid)
    data = body(request)
    typed = normalize_text(text(data, "entry"))[:120]
    if typed:
        key = fa_key(typed)
        found = list(Catalog.objects.filter(active=True, deleted_at__isnull=True, name_key=key)[:2])
    else:
        found = list(Catalog.objects.filter(pk=id_of(text(data, "catalogId")), active=True, deleted_at__isnull=True))
    entry = found[0] if len(found) == 1 else None
    raw_qty = raw_field(data, "qty") or "1"
    qty = parse_qty(raw_qty)
    if len(found) > 1:
        m = f"چند مورد با نام «{typed}» در فهرست قیمت هست؛ نام یکی را در تنظیمات مالی عوض کنید."
        raise invalid(m, {"line": m})
    if entry is None:
        m = (f"«{typed}» در فهرست خدمات و کالاها پیدا نشد؛ از پیشنهادهای فهرست انتخاب کنید." if typed
             else "یک خدمت یا کالا انتخاب کنید.")
        raise invalid(m, {"line": m})
    if not qty or qty != qty:
        m = "تعداد را به عدد وارد کنید (تا دو رقم اعشار، مثل ۰٫۵)."
        raise invalid(m, {"line": m})
    q = to_qty(qty)
    qty_text = cast(dict[str, Any], present.qty(q))["text"]
    with transaction.atomic():  # C5: the audit row commits with the change or not at all
        line_id = ops.add_line(v.pk, entry.pk, q, _user(me))
        audit(me.id, "bill_line_add", v.patient_id, f"visit={v.pk} line={line_id} catalog={entry.pk} qty={qty_text}")
    return ok({"id": line_id}, 201)


def delete_line(request: HttpRequest, vid: str, lid: str) -> HttpResponse:
    me = user_of(request)
    v = _visit(vid)
    line = _line(v, lid)
    qty_text = cast(dict[str, Any], present.qty(line.qty))["text"]
    with transaction.atomic():
        ops.delete_line(v.pk, line.pk, _user(me))
        audit(me.id, "bill_line_delete", v.patient_id, f"visit={v.pk} line={line.pk} qty={qty_text}")
    return ok()


def line_discount(request: HttpRequest, vid: str, lid: str) -> HttpResponse:
    me = user_of(request)
    v = _visit(vid)
    line = _line(v, lid)
    data = body(request)
    d = parse_discount(text(data, "discKind"), raw_field(data, "discValue"), _cur())
    if d and "error" in d:
        raise invalid(str(d["error"]), {f"line{line.pk}": str(d["error"])})
    with transaction.atomic():
        lock_visits([v.pk])
        BillLine.objects.filter(pk=line.pk).update(
            disc_kind=d["kind"] if d else None, disc_value=d["value"] if d else 0
        )
        audit(
            me.id, "bill_discount", v.patient_id,
            f"line={line.pk} {d['kind']}={d['value']}" if d else f"line={line.pk} none",
        )
    return ok()


def line_price(request: HttpRequest, vid: str, lid: str) -> HttpResponse:
    me = user_of(request)
    v = _visit(vid)
    line = _line(v, lid)
    raw = text(body(request), "price").strip()
    price = parse_money(raw, _cur()) if raw else None
    if raw and price is None:
        raise invalid("قیمت تازه را به عدد وارد کنید.", {f"line{line.pk}": "قیمت تازه را به عدد وارد کنید."})
    if price is not None and line_too_large(price, float(line.qty)):
        raise invalid(ops.TOO_LARGE, {f"line{line.pk}": ops.TOO_LARGE})
    with transaction.atomic():
        lock_visits([v.pk])
        line = _line(v, lid)  # read again under the lock: the audit row names the price it replaced
        nxt = None if price == line.unit_price else price
        BillLine.objects.filter(pk=line.pk).update(override_price=nxt)
        frm = line.override_price if line.override_price is not None else line.unit_price
        to = nxt if nxt is not None else line.unit_price
        audit(me.id, "price_override", v.patient_id, f"line={line.pk} from={frm} to={to}")
    return ok()


def visit_discount(request: HttpRequest, vid: str) -> HttpResponse:
    me = user_of(request)
    v = _visit(vid)
    data = body(request)
    d = parse_discount(text(data, "discKind"), raw_field(data, "discValue"), _cur())
    if d and "error" in d:
        raise invalid(str(d["error"]), {"billDisc": str(d["error"])})
    with transaction.atomic():
        lock_visits([v.pk])
        Visit.objects.filter(pk=v.pk).update(disc_kind=d["kind"] if d else None, disc_value=d["value"] if d else 0)
        audit(
            me.id, "bill_discount", v.patient_id,
            f"visit={v.pk} {d['kind']}={d['value']}" if d else f"visit={v.pk} none",
        )
    return ok()


def read_payment(data: dict[str, Any], cur: str, need_method: bool = True) -> tuple[dict[str, Any], dict[str, str]]:
    errors: dict[str, str] = {}
    amount = parse_money(raw_field(data, "amount"), cur)
    if not amount:
        errors["amount"] = "مبلغ را به عدد و بیشتر از صفر وارد کنید."
    raw_day = text(data, "paidOn", 20)
    today = timezone.localdate()
    paid_on = parse_jalali(raw_day) if raw_day.strip() else today
    if paid_on is None:
        errors["paidOn"] = "تاریخ را به شکل ۱۴۰۵/۰۸/۰۱ وارد کنید."
    elif paid_on > today:
        errors["paidOn"] = "تاریخ پرداخت نمی‌تواند بعد از امروز باشد."
    method = PayMethod.objects.filter(pk=id_of(text(data, "methodId")), active=True).first()
    acc_id = id_of(text(data, "accountId")) or (method.default_account_id if method else 0) or 0
    account = Account.objects.filter(pk=acc_id, active=True).first()
    if need_method and method is None:
        errors["methodId"] = "روش پرداخت را انتخاب کنید."
    if need_method and account is None:
        errors["accountId"] = "حساب را انتخاب کنید."
    return {
        "amount": amount, "paid_on": paid_on, "method_id": method.pk if method else None,
        "account_id": account.pk if account else None, "note": normalize_text(text(data, "note"))[:200],
    }, errors


def add_payment(request: HttpRequest, vid: str) -> HttpResponse:
    me = user_of(request)
    v = _visit(vid)
    data = dict(body(request))
    cur = _cur()
    full = data.get("full") in ("1", True, 1)
    if full:
        remaining = ops.bill_for(v)["remaining"]
        if not remaining:
            raise invalid(ops.NOTHING_LEFT, {"pay": ops.NOTHING_LEFT})
        data["amount"] = f"{remaining}R"
    row, errors = read_payment(data, cur)
    if errors:
        raise invalid(next(iter(errors.values())), {"pay": next(iter(errors.values())), **errors})
    with transaction.atomic():
        pid = ops.record_payment(
            v.pk, row["amount"], row["paid_on"], row["method_id"], row["account_id"], row["note"], _user(me),
            full=full,
        )
        amount = Payment.objects.filter(pk=pid).values_list("amount", flat=True).first()
        audit(me.id, "payment_add", v.patient_id,
              f"visit={v.pk} payment={pid} amount={amount} method={row['method_id']} account={row['account_id']}")
    return ok({"id": pid}, 201)


def refund(request: HttpRequest, vid: str) -> HttpResponse:
    me = user_of(request)
    v = _visit(vid)
    row, errors = read_payment(body(request), _cur())
    if not errors.get("amount") and row["amount"] and row["amount"] > ops.bill_for(v)["credit"]:
        errors["amount"] = "مبلغ بازپرداخت از بستانکاری بیشتر است."
    if errors:
        raise invalid(next(iter(errors.values())), {"refund": next(iter(errors.values()))})
    with transaction.atomic():
        pid = ops.record_payment(
            v.pk, row["amount"], row["paid_on"], row["method_id"], row["account_id"], row["note"], _user(me),
            kind="refund",
        )
        audit(me.id, "payment_refund", v.patient_id, f"visit={v.pk} payment={pid} amount={row['amount']}")
    return ok({"id": pid}, 201)


def move(request: HttpRequest, vid: str) -> HttpResponse:
    me = user_of(request)
    v = _visit(vid)
    data = body(request)
    to = (
        Visit.objects.filter(pk=id_of(text(data, "to")), patient_id=v.patient_id)
        .exclude(pk=v.pk)
        .exclude(status="cancelled")
        .first()
    )
    amount = parse_money(raw_field(data, "amount"), _cur())
    error = None
    if to is None:
        error = "ویزیت مقصد را از ویزیت‌های همین بیمار انتخاب کنید."
    elif not amount:
        error = "مبلغ را به عدد و بیشتر از صفر وارد کنید."
    elif amount > ops.bill_for(v)["credit"]:
        error = "مبلغ انتقال از بستانکاری بیشتر است."
    if error:
        raise invalid(error, {"move": error})
    assert to is not None and amount
    with transaction.atomic():
        move_id = ops.move_credit(v.pk, to.pk, amount, timezone.localdate(), _user(me))
        audit(me.id, "payment_move", v.patient_id, f"from={v.pk} to={to.pk} amount={amount} move={move_id}")
    return ok({"moveId": move_id}, 201)


def _payment(v: Visit, pid: str) -> Payment:
    p = Payment.objects.filter(pk=id_of(pid), visit=v).first()
    if p is None:
        raise not_found("این پرداخت پیدا نشد.")
    return p


def get_payment(request: HttpRequest, vid: str, pid: str) -> HttpResponse:
    v = _visit(vid)
    p = _payment(v, pid)
    if p.move_id:
        raise not_found("این پرداخت پیدا نشد یا قابل ویرایش نیست.")
    cur = _cur()
    return ok({"payment": {
        "id": p.pk, "kind": p.kind, "amount": present.money(abs(p.amount), cur), "paidOn": present.d(p.paid_on),
        "methodId": p.method_id, "accountId": p.account_id, "note": p.note,
    }})


def edit_payment(request: HttpRequest, vid: str, pid: str) -> HttpResponse:
    me = user_of(request)
    v = _visit(vid)
    p = _payment(v, pid)
    if p.move_id:
        raise not_found("این پرداخت پیدا نشد یا قابل ویرایش نیست.")
    row, errors = read_payment(body(request), _cur())
    if not errors.get("amount") and p.kind == "refund":
        b = ops.bill_for(v)
        if row["amount"] > max(b["paid"] - p.amount - b["owed"], 0):
            errors["amount"] = "مبلغ بازپرداخت از بستانکاری بیشتر است."
    if errors:
        raise invalid(next(iter(errors.values())), {"edit": next(iter(errors.values()))})
    if v.status == "cancelled" and p.kind == "payment" and row["amount"] > p.amount:
        raise conflict("ویزیت لغو شده است؛ پرداخت آن را نمی‌توان بیشتر کرد.")
    signed = -row["amount"] if p.kind == "refund" else row["amount"]
    day = row["paid_on"].isoformat()
    try:
        with transaction.atomic():
            ops.edit_payment(p.pk, row["amount"], row["paid_on"], row["method_id"], row["account_id"], row["note"])
            audit(me.id, "payment_edit", v.patient_id, f"payment={p.pk} from={p.amount} to={signed} day={day}")
    except ops.BillError as err:
        raise invalid(err.message_fa, {"edit": err.message_fa}) from None
    return ok()


def delete_payment(request: HttpRequest, vid: str, pid: str) -> HttpResponse:
    me = user_of(request)
    v = _visit(vid)
    p = _payment(v, pid)
    move = f" move={p.move_id}" if p.move_id else ""
    with transaction.atomic():
        ops.remove_payment(p.pk)
        audit(me.id, "payment_delete", v.patient_id, f"payment={p.pk} amount={p.amount} kind={p.kind}{move}")
    return ok()


from apps.core.http import route  # noqa: E402

lines_view = route(POST=add_line)
line_view = route(DELETE=delete_line)
line_discount_view = route(PUT=line_discount)
line_price_view = route(PUT=line_price)
visit_discount_view = route(PUT=visit_discount)
payments_view = route(POST=add_payment)
payment_view = route(GET=get_payment, PATCH=edit_payment, DELETE=delete_payment)
refund_view = route(POST=refund)
move_view = route(POST=move)
