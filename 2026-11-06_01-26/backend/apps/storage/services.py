"""Stock: taking, returning, counting, wasting, undoing and deleting (SPEC §4.3).

Every change locks the catalog item row first, then its lots in ascending id. The rows are read
after the lock, so a second change sees what the first one committed. A lot is usable when it has
pieces left and has not expired (legacy USABLE); earliest expiry first, a lot without expiry goes
last. Remaining never goes below zero."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.billing.models import BillLine
from apps.core.errors import Conflict, Invalid, NotFound
from apps.core.locks import get_for_update
from apps.finance.models import Catalog
from apps.storage.models import Lot, StockMove


class ShortError(Conflict):
    """The item or lot does not hold the quantity asked for."""


class UndoError(Conflict):
    """A stock entry cannot be removed. `code` says why: 'bill', 'later' or 'short' (legacy
    StockUndoError)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _lock_item(item_id: int) -> Catalog:
    items = Catalog.objects.filter(kind="item", deleted_at__isnull=True)
    return get_for_update(items, item_id, "item")


def _lock_catalog(catalog_id: int) -> Catalog:
    return get_for_update(Catalog.objects.all(), catalog_id, "catalog item")


def _item_of_lot(lot_id: int) -> int:
    item_id = Lot.objects.filter(pk=lot_id).values_list("item_id", flat=True).first()
    if item_id is None:
        raise NotFound(f"lot {lot_id} not found")
    return int(item_id)


def _usable_lots(item_id: int, today: date) -> list[Lot]:
    return list(
        Lot.objects.select_for_update()
        .filter(item_id=item_id, remaining__gt=0)
        .filter(Q(expires_on__isnull=True) | Q(expires_on__gte=today))
        .order_by(F("expires_on").asc(nulls_last=True), "id")
    )


def take_stock(
    item_id: int,
    qty: Decimal,
    user: Any = None,
    line_id: int | None = None,
    today: date | None = None,
) -> list[StockMove]:
    """Take `qty` pieces of an item from its usable lots.

    Earliest expiry first, in one transaction."""
    if qty <= 0:
        raise Invalid("qty must be positive")
    with transaction.atomic():
        _lock_item(item_id)
        lots = _usable_lots(item_id, today or timezone.localdate())
        if sum((lot.remaining for lot in lots), Decimal("0")) < qty:
            raise ShortError(f"item {item_id}: not enough stock for {qty}")
        moves: list[StockMove] = []
        left = qty
        for lot in lots:
            if left <= 0:
                break
            take = min(lot.remaining, left)
            lot.remaining = lot.remaining - take
            lot.save(update_fields=["remaining"])
            moves.append(
                StockMove.objects.create(
                    lot=lot, qty=-take, reason="use", line_id=line_id, user=user
                )
            )
            left = left - take
        return moves


def return_stock(line_id: int, user: Any = None) -> Decimal:
    """Put back what a bill line still holds, to the same lots. Returns the pieces returned."""
    with transaction.atomic():
        catalog_id = (
            BillLine.objects.filter(pk=line_id).values_list("catalog_id", flat=True).first()
        )
        if catalog_id is None:
            return Decimal("0")
        _lock_catalog(int(catalog_id))
        totals: dict[int, Decimal] = {}
        rows = StockMove.objects.filter(line_id=line_id, reason__in=["use", "return"])
        for lot_id, qty in rows.values_list("lot_id", "qty"):
            totals[lot_id] = totals.get(lot_id, Decimal("0")) + qty
        held = {lot_id: -total for lot_id, total in totals.items() if total < 0}
        returned = Decimal("0")
        for lot in Lot.objects.select_for_update().filter(pk__in=sorted(held)).order_by("pk"):
            back = held[lot.pk]
            lot.remaining = lot.remaining + back
            lot.save(update_fields=["remaining"])
            StockMove.objects.create(lot=lot, qty=back, reason="return", line_id=line_id, user=user)
            returned += back
        return returned


def count_lot(lot_id: int, counted: Decimal, note: str | None = None, user: Any = None) -> Decimal:
    """Set a lot's remaining count to what was really counted. Returns the change."""
    if counted < 0:
        raise Invalid("counted must not be negative")
    item_id = _item_of_lot(lot_id)
    with transaction.atomic():
        _lock_item(item_id)
        lot = get_for_update(Lot.objects.all(), lot_id, "lot")
        delta = counted - lot.remaining
        if delta != 0:
            lot.remaining = counted
            lot.save(update_fields=["remaining"])
            StockMove.objects.create(lot=lot, qty=delta, reason="count", note=note, user=user)
        return delta


def waste_lot(lot_id: int, qty: Decimal, note: str | None = None, user: Any = None) -> Decimal:
    """Write `qty` pieces of one lot off (expired, broken). Refused when the lot holds fewer."""
    if qty <= 0:
        raise Invalid("qty must be positive")
    item_id = _item_of_lot(lot_id)
    with transaction.atomic():
        _lock_item(item_id)
        lot = get_for_update(Lot.objects.all(), lot_id, "lot")
        if qty > lot.remaining:
            raise ShortError(f"lot {lot_id} holds {lot.remaining}")
        lot.remaining = lot.remaining - qty
        lot.save(update_fields=["remaining"])
        StockMove.objects.create(lot=lot, qty=-qty, reason="waste", note=note, user=user)
        return qty


def undo_move(move_id: int) -> None:
    """Remove one wrong stock entry and undo its effect. Bill entries are removed with their bill
    line."""
    catalog_id = StockMove.objects.filter(pk=move_id).values_list("lot__item_id", flat=True).first()
    if catalog_id is None:
        raise NotFound(f"stock move {move_id} not found")
    with transaction.atomic():
        _lock_catalog(int(catalog_id))
        move = get_for_update(StockMove.objects.all(), move_id, "stock move")
        lot = get_for_update(Lot.objects.all(), move.lot_id, "lot")
        if move.reason in ("use", "return"):
            raise UndoError("bill")
        if move.reason == "in":
            if StockMove.objects.filter(lot=lot).exclude(pk=move.pk).exists():
                raise UndoError("later")
            move.delete()
            lot.delete()
            return
        remaining = lot.remaining - move.qty
        if remaining < 0:
            raise UndoError("short")
        lot.remaining = remaining
        lot.save(update_fields=["remaining"])
        move.delete()


def delete_item(item_id: int) -> bool:
    """Delete a stock item with its lots and stock history. Returns True when a bill line still
    names it, in which case the catalog row is kept hidden (legacy deleteItem)."""
    with transaction.atomic():
        item = _lock_item(item_id)
        lots = list(Lot.objects.select_for_update().filter(item=item).order_by("pk"))
        StockMove.objects.filter(lot__in=lots).delete()
        Lot.objects.filter(pk__in=[lot.pk for lot in lots]).delete()
        kept = BillLine.objects.filter(catalog=item).exists()
        if kept:
            item.active = False
            item.deleted_at = timezone.now()
            item.save()
        else:
            item.delete()
        return kept


# ---- reads, stock-in and alerts (legacy src/lib/stock.js) -------------------------------------

def short_message(name: str, available_qty: Decimal | float) -> str:
    from apps.core.jalali import fa_digits

    return f"موجودی «{name}» کافی نیست؛ موجود قابل مصرف: {fa_digits(qty_text(available_qty))} عدد."


def qty_text(q: Decimal | float | int | None) -> str:
    """A quantity as JS String(number): 2.5 -> '2.5', 3.00 -> '3'."""
    if q is None:
        return ""
    d = Decimal(str(q)).quantize(Decimal("0.01"))
    s = format(d.normalize(), "f")
    return "0" if s in ("-0", "") else s


def to_qty(value: float) -> Decimal:
    """A parsed quantity (float with at most two decimals) as the stored Decimal."""
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _usable_q(today: date) -> Q:
    return Q(remaining__gt=0) & (Q(expires_on__isnull=True) | Q(expires_on__gte=today))


def available(item_id: int, today: date | None = None) -> Decimal:
    from django.db.models import Sum

    total = (
        Lot.objects.filter(_usable_q(today or timezone.localdate()), item_id=item_id)
        .aggregate(t=Sum("remaining"))["t"]
    )
    return total or Decimal("0")


def stock_in(
    item_id: int, qty: Decimal, received_on: date, expires_on: date | None, unit_cost: int | None, user: Any = None
) -> Lot:
    with transaction.atomic():
        _lock_item(item_id)
        lot = Lot.objects.create(
            item_id=item_id, received_on=received_on, qty_in=qty, remaining=qty, expires_on=expires_on,
            unit_cost=unit_cost, created_by=user,
        )
        StockMove.objects.create(lot=lot, qty=qty, reason="in", user=user)
        return lot


def days_until(iso: date, today: date) -> int:
    return (iso - today).days


def expiry_level(lot: Lot, today: date) -> str | None:
    if not lot.expires_on or lot.remaining <= 0:
        return None
    d = days_until(lot.expires_on, today)
    return "expired" if d < 0 else "crit" if d <= 10 else "warn" if d <= 30 else None


def low_level(item: Catalog, count: Decimal, settings: dict[str, Any]) -> str | None:
    crit = float(item.low_crit) if item.low_crit is not None else float(settings["low_crit"])
    warn = float(item.low_warn) if item.low_warn is not None else float(settings["low_warn"])
    c = float(count)
    return "crit" if c <= crit else "warn" if c <= warn else None


def items_with_stock(settings: dict[str, Any], today: date | None = None) -> list[dict[str, Any]]:
    today = today or timezone.localdate()
    items = list(Catalog.objects.filter(kind="item", active=True).order_by("name", "id"))
    lots = list(Lot.objects.filter(remaining__gt=0, item__in=items))
    out = []
    for it in items:
        mine = [lot for lot in lots if lot.item_id == it.pk]
        usable_lots = [lot for lot in mine if lot.expires_on is None or lot.expires_on >= today]
        usable = sum((lot.remaining for lot in usable_lots), Decimal("0"))
        expiries = [lot.expires_on for lot in usable_lots if lot.expires_on]
        levels = [lv for lv in (expiry_level(lot, today) for lot in mine) if lv]
        expiry = next((x for x in ("expired", "crit", "warn") if x in levels), None)
        out.append({
            "item": it, "usable": usable, "next_expiry": min(expiries) if expiries else None,
            "low": low_level(it, usable, settings), "expiry": expiry,
        })
    return out


def alerts(settings: dict[str, Any], today: date | None = None) -> list[dict[str, Any]]:
    from apps.core.jalali import fa_digits

    out = []
    for row in items_with_stock(settings, today):
        it = row["item"]
        if row["low"]:
            msg = f"موجودی کم: {fa_digits(qty_text(row['usable']))} عدد"
            out.append({"item": it, "level": row["low"], "text": msg})
        if row["expiry"] == "expired":
            out.append({"item": it, "level": "crit", "text": "منقضی شده؛ باید به ضایعات برود"})
        elif row["expiry"]:
            out.append({
                "item": it, "level": row["expiry"],
                "text": "انقضا در ۱۰ روز آینده" if row["expiry"] == "crit" else "انقضا در ۳۰ روز آینده",
            })
    out.sort(key=lambda a: (0 if a["level"] == "crit" else 1, a["item"].name))
    return out
