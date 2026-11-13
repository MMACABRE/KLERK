"""The bill of a visit and every change to it (legacy src/lib/bill.js).

Every change locks the visit row first (lock order: patient -> visits -> catalog -> lots), then reads.
Totals are computed from the rows, never stored."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.billing.models import BillLine, Payment
from apps.billing.services import _group, _payment, lock_visits
from apps.core.aggregates import sum_rial
from apps.core.errors import Conflict, NotFound
from apps.core.money import discount_of, line_gross, line_too_large
from apps.visits.models import Visit

PAYMENTS_BLOCK = "این ویزیت پرداخت ثبت‌شده دارد. ابتدا پرداخت‌ها را بازپرداخت یا به ویزیت دیگری منتقل کنید."
PATIENT_PAYMENTS_BLOCK = (
    "این بیمار پرداخت ثبت‌شده دارد و سوابق مالی نباید پاک شود. به‌جای حذف، پرونده را بایگانی کنید."
)
OVERDRAWN_BLOCK = (
    "پس از این تغییر، بازپرداخت یا انتقال این ویزیت از پولی که دریافت کرده بیشتر می‌شود. "
    "ابتدا آن بازپرداخت یا انتقال را حذف یا اصلاح کنید."
)
TOO_LARGE = "مبلغ این ردیف بیش از حد مجاز است؛ تعداد یا قیمت را درست وارد کنید."


NOTHING_LEFT = "مانده‌ای برای پرداخت نیست."


class BillError(Conflict):
    """A refused bill change with its Persian message and HTTP status (legacy BillError)."""

    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.message_fa = message
        self.status = status


def line_amounts(line: BillLine) -> tuple[int, int]:
    price = line.override_price if line.override_price is not None else line.unit_price
    gross = line_gross(int(price), float(line.qty))
    return gross, discount_of(gross, line.disc_kind, line.disc_value)


def bill_for(visit: Visit) -> dict[str, Any]:
    lines: list[dict[str, Any]] = []
    for line in BillLine.objects.filter(visit=visit).order_by("id"):
        gross, disc = line_amounts(line)
        lines.append({"line": line, "gross": gross, "disc": disc, "net": gross - disc})
    payments = list(
        Payment.objects.filter(visit=visit).select_related("method", "account", "created_by").order_by("paid_on", "id")
    )
    other_dates: dict[int, date] = {}
    move_ids = [p.move_id for p in payments if p.move_id]
    if move_ids:
        moved = Payment.objects.filter(move_id__in=move_ids).values_list("move_id", "id", "visit__visit_date")
        for mid, pid, vdate in moved:
            for p in payments:
                if p.move_id == mid and p.pk != pid:
                    other_dates[p.pk] = vdate
    subtotal = sum(x["net"] for x in lines)
    bill_disc = discount_of(subtotal, visit.disc_kind, visit.disc_value)
    cancelled = visit.status == "cancelled"
    owed = 0 if cancelled else subtotal - bill_disc
    paid = sum(int(p.amount) for p in payments)
    line_disc = sum(x["disc"] for x in lines)
    return {
        "lines": lines, "payments": payments, "other_dates": other_dates, "cancelled": cancelled,
        "gross": sum(x["gross"] for x in lines), "lineDisc": line_disc, "subtotal": subtotal, "billDisc": bill_disc,
        "discount": line_disc + bill_disc, "owed": owed, "paid": paid,
        "remaining": max(owed - paid, 0), "credit": max(paid - owed, 0),
    }


def patient_balance(patient_id: int) -> dict[str, int]:
    remaining = credit = 0
    for v in Visit.objects.filter(patient_id=patient_id):
        b = bill_for(v)
        remaining += b["remaining"]
        credit += b["credit"]
    return {"remaining": remaining, "credit": credit}


def visit_number(visit: Visit) -> int | None:
    if visit.status == "cancelled":
        return None
    return (
        Visit.objects.filter(patient_id=visit.patient_id)
        .exclude(status="cancelled")
        .filter(
            Q(visit_date__lt=visit.visit_date)
            | Q(visit_date=visit.visit_date, visit_time__lt=visit.visit_time)
            | Q(visit_date=visit.visit_date, visit_time=visit.visit_time, id__lte=visit.pk)
        )
        .count()
    )


def visit_has_payments(visit_id: int) -> bool:
    return Payment.objects.filter(visit_id=visit_id).exists()


def patient_has_payments(patient_id: int) -> bool:
    return Payment.objects.filter(visit__patient_id=patient_id).exists()


def add_line(visit_id: int, entry_id: int, qty: Any, user: Any) -> int:
    """Add a catalog entry at today's price; an item takes its stock now. The patient's standing discount is
    copied with the first line. Returns the line id."""
    from apps.finance.models import Catalog
    from apps.patients.models import Patient
    from apps.storage.services import ShortError, available, short_message, take_stock

    with transaction.atomic():
        (visit,) = lock_visits([visit_id])
        if visit.status == "cancelled":
            raise BillError("ویزیت لغو شده است؛ به صورتحساب آن چیزی اضافه نمی‌شود.", 409)
        entry = Catalog.objects.filter(pk=entry_id, deleted_at__isnull=True).first()
        if entry is None or not entry.active:
            raise BillError("این مورد در فهرست قیمت‌ها نیست یا غیرفعال است.")
        if line_too_large(int(entry.sale_price), float(qty)):
            raise BillError(TOO_LARGE)
        line = BillLine.objects.create(
            visit=visit, catalog=entry, kind=entry.kind, name=entry.name, qty=qty, unit_price=entry.sale_price,
            created_by=user,
        )
        if entry.kind == "item":
            try:
                take_stock(entry.pk, qty, user=user, line_id=line.pk)
            except ShortError:
                raise BillError(short_message(entry.name, available(entry.pk)), 409) from None
        if BillLine.objects.filter(visit=visit).count() == 1 and not visit.disc_kind:
            p = Patient.objects.filter(pk=visit.patient_id).values("disc_kind", "disc_value").first()
            if p and p["disc_kind"] and p["disc_value"]:
                Visit.objects.filter(pk=visit.pk).update(disc_kind=p["disc_kind"], disc_value=p["disc_value"])
        return int(line.pk)


def delete_line(visit_id: int, line_id: int, user: Any) -> BillLine:
    from apps.storage.services import return_stock

    with transaction.atomic():
        lock_visits([visit_id])
        line = BillLine.objects.filter(pk=line_id, visit_id=visit_id).first()
        if line is None:
            raise NotFound(f"line {line_id}")
        if line.kind == "item":
            return_stock(line.pk, user=user)
        line.delete()
        return line


def sync_stock_for_status(visit: Visit, status: str, user: Any) -> None:
    """Cancelling returns every item line's pieces; bringing a cancelled visit back takes them again.
    Call inside the status change's transaction, with the visit row locked."""
    from apps.storage.services import ShortError, return_stock, take_stock

    if visit.status == status:
        return
    items = list(BillLine.objects.filter(visit=visit, kind="item").order_by("catalog_id", "id"))
    if status == "cancelled":
        for line in items:
            return_stock(line.pk, user=user)
    elif visit.status == "cancelled":
        for line in items:
            try:
                take_stock(line.catalog_id, line.qty, user=user, line_id=line.pk)
            except ShortError:
                raise BillError(
                    f"برای برگرداندن این ویزیت، «{line.name}» به اندازه‌ی کافی در انبار نیست.", 409
                ) from None


def release_stock(visit_ids: list[int], user: Any) -> None:
    from apps.storage.services import return_stock

    lines = BillLine.objects.filter(kind="item", visit_id__in=visit_ids).order_by("catalog_id", "id")
    for line_id in lines.values_list("id", flat=True):
        return_stock(line_id, user=user)


def assert_not_overdrawn(visit_ids: Iterable[int]) -> None:
    for vid in visit_ids:
        if sum_rial(Payment.objects.filter(visit_id=vid), "amount") < 0:
            raise BillError(OVERDRAWN_BLOCK, 409)


def record_payment(
    visit_id: int, amount: int, paid_on: date, method_id: int | None, account_id: int | None, note: str | None,
    user: Any, kind: str = "payment", full: bool = False,
) -> int:
    """A payment, or a refund given as a positive amount (stored negative, at most the visit's credit).
    `full` pays what remains, read after the visit is locked (two "pay full" clicks pay it once)."""
    with transaction.atomic():
        (visit,) = lock_visits([visit_id])
        if kind == "payment" and visit.status == "cancelled":
            raise BillError("ویزیت لغو شده است؛ فقط بازپرداخت یا انتقال ممکن است.", 409)
        if full:
            amount = bill_for(visit)["remaining"]
            if not amount:
                raise BillError(NOTHING_LEFT)
        if paid_on > timezone.localdate():
            raise BillError("تاریخ پرداخت نمی‌تواند بعد از امروز باشد.")
        if kind == "refund" and amount > bill_for(visit)["credit"]:
            raise BillError("مبلغ بازپرداخت از بستانکاری بیشتر است.")
        p = Payment.objects.create(
            visit=visit, amount=-amount if kind == "refund" else amount, kind=kind, paid_on=paid_on,
            method_id=method_id, account_id=account_id, note=note or None, created_by=user,
        )
        return int(p.pk)


def move_credit(from_id: int, to_id: int, amount: int, paid_on: date, user: Any) -> int:
    with transaction.atomic():
        rows = {v.pk: v for v in lock_visits([from_id, to_id])}
        if amount > bill_for(rows[from_id])["credit"]:
            raise BillError("مبلغ انتقال از بستانکاری بیشتر است.")
        out = Payment.objects.create(
            visit=rows[from_id], amount=-amount, kind="move_out", paid_on=paid_on, created_by=user
        )
        Payment.objects.filter(pk=out.pk).update(move_id=out.pk)
        Payment.objects.create(
            visit=rows[to_id], amount=amount, kind="move_in", paid_on=paid_on, move_id=out.pk, created_by=user
        )
        return int(out.pk)


def remove_payment(payment_id: int) -> Payment:
    with transaction.atomic():
        first = _payment(payment_id)
        visit_ids = set(_group(first).values_list("visit_id", flat=True))
        lock_visits(visit_ids)
        current = _payment(payment_id)
        _group(current).delete()
        assert_not_overdrawn(visit_ids)
        return current


def edit_payment(
    payment_id: int, amount: int, paid_on: date, method_id: int | None, account_id: int | None, note: str | None
) -> Payment:
    with transaction.atomic():
        first = _payment(payment_id)
        lock_visits([first.visit_id])
        p = _payment(payment_id)
        if p.kind not in ("payment", "refund"):
            raise BillError("انتقال اعتبار ویرایش نمی‌شود؛ آن را حذف و دوباره ثبت کنید.", 409)
        if paid_on > timezone.localdate():
            raise BillError("تاریخ پرداخت نمی‌تواند بعد از امروز باشد.")
        p.amount = -amount if p.kind == "refund" else amount
        p.paid_on = paid_on
        p.method_id = method_id
        p.account_id = account_id
        p.note = note or None
        p.save()
        assert_not_overdrawn([p.visit_id])
        return p
