"""Storage API (SPEC §5.7; legacy src/routes/storage.js)."""

from __future__ import annotations

from typing import Any, cast

from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from apps.core import present
from apps.core.audit import audit
from apps.core.http import body, conflict, id_of, invalid, not_found, ok, raw_field, route, text, user_of
from apps.core.jalali import fa_digits, parse_jalali
from apps.core.money import parse_money
from apps.core.perms import can
from apps.core.qty import parse_qty
from apps.core.settings_store import get_settings
from apps.core.text import normalize_text
from apps.finance.models import Catalog
from apps.storage import services as st
from apps.storage.models import Lot, StockMove

REASON_LABEL = {
    "in": "ورود", "use": "مصرف در ویزیت", "return": "برگشت از ویزیت", "count": "اصلاح شمارش", "waste": "ضایعات",
}
UNDO_MESSAGES = {
    "bill": "این ردیف مال صورتحساب یک ویزیت است؛ برای برگرداندنش، ردیف کالا را از همان صورتحساب حذف کنید.",
    "later": "بعد از این ورود، ردیف‌های دیگری برای همین بسته ثبت شده است؛ اول آن‌ها را حذف کنید.",
}


def _cur() -> str:
    return str(get_settings()["currency"])


def _user(me: Any) -> Any:
    from apps.accounts.models import User

    return User.objects.filter(pk=me.id).first()


def _num_or_nan(v: Any, allow_zero: bool = True) -> Any:
    return parse_qty(v, allow_zero=allow_zero)


def read_item_form(data: dict[str, Any], cur: str) -> tuple[dict[str, str], dict[str, Any]]:
    errors: dict[str, str] = {}
    name = normalize_text(text(data, "name"))[:120]
    row: dict[str, Any] = {"name": name}
    if not name:
        errors["name"] = "نام کالا را وارد کنید."
    row["sale_price"] = parse_money(raw_field(data, "salePrice"), cur)
    if row["sale_price"] is None:
        errors["salePrice"] = "قیمت فروش را به عدد وارد کنید."
    pc = text(data, "purchaseCost", 30)
    row["purchase_cost"] = parse_money(pc, cur) if pc.strip() else None
    if pc.strip() and row["purchase_cost"] is None:
        errors["purchaseCost"] = "قیمت خرید درست نیست."
    for k, key in (("low_warn", "lowWarn"), ("low_crit", "lowCrit")):
        v = _num_or_nan(text(data, key, 10))
        if v is not None and v != v:
            errors[key] = "یک عدد وارد کنید (تا دو رقم اعشار) یا خالی بگذارید."
            row[k] = None
        else:
            row[k] = st.to_qty(v) if v is not None else None
    if (
        "lowWarn" not in errors and "lowCrit" not in errors
        and row["low_warn"] is not None and row["low_crit"] is not None
    ):
        if row["low_crit"] > row["low_warn"]:
            errors["lowCrit"] = "حد بحرانی نباید از حد هشدار بیشتر باشد."
    return errors, row


def _qty_text(value: Any) -> Any:
    return cast(dict[str, Any], present.qty(value))["text"]


def _find_item(iid: str) -> Catalog:
    c = Catalog.objects.filter(pk=id_of(iid), kind="item", deleted_at__isnull=True).first()
    if c is None:
        raise not_found("کالای مورد نظر پیدا نشد.")
    return c


def list_items(request: HttpRequest) -> HttpResponse:
    me = user_of(request)
    s = get_settings()
    cur = str(s["currency"])
    rows = st.items_with_stock(s)
    alert = [r for r in rows if r["low"] or r["expiry"]]
    chosen = alert if request.GET.get("f") == "alert" else rows
    return ok({
        "filter": "alert" if request.GET.get("f") == "alert" else "all",
        "alertCount": len(alert),
        "settings": {"lowWarn": present.qty(s["low_warn"]), "lowCrit": present.qty(s["low_crit"])},
        "data": [
            {"id": r["item"].pk, "name": r["item"].name, "usable": present.qty(r["usable"]),
             "nextExpiry": present.d(r["next_expiry"]), "low": r["low"], "expiry": r["expiry"],
             "salePrice": present.money(r["item"].sale_price, cur) if can(me, "finance") else None}
            for r in chosen
        ],
    })


def create_item(request: HttpRequest) -> HttpResponse:
    me = user_of(request)
    errors, row = read_item_form(body(request), _cur())
    if errors:
        raise invalid("لطفاً خطاهای مشخص‌شده را برطرف کنید.", errors)
    c = Catalog.objects.create(kind="item", **row)
    audit(me.id, "catalog_add", None, f"item={c.pk} price={row['sale_price']}")
    return ok({"id": c.pk}, 201)


def show_item(request: HttpRequest, iid: str) -> HttpResponse:
    me = user_of(request)
    item = _find_item(iid)
    s = get_settings()
    cur = str(s["currency"])
    today = timezone.localdate()
    lots = sorted(
        Lot.objects.filter(item=item),
        key=lambda lot: (lot.remaining == 0, lot.expires_on is None, lot.expires_on or today, lot.pk),
    )
    moves = StockMove.objects.filter(lot__item=item).select_related("lot", "user").order_by("-id")[:50]
    return ok({
        "item": {
            "id": item.pk, "name": item.name, "active": item.active,
            "salePrice": present.money(item.sale_price, cur) if can(me, "finance") else None,
            "purchaseCost": present.money(item.purchase_cost, cur) if can(me, "finance") else None,
            "lowWarn": present.qty(item.low_warn), "lowCrit": present.qty(item.low_crit),
        },
        "usable": present.qty(st.available(item.pk, today)),
        "lots": [
            {"id": lot.pk, "receivedOn": present.d(lot.received_on), "qtyIn": present.qty(lot.qty_in),
             "remaining": present.qty(lot.remaining), "expiresOn": present.d(lot.expires_on),
             "unitCost": (
                 present.money(lot.unit_cost, cur) if can(me, "finance") and lot.unit_cost is not None else None
             ),
             "level": st.expiry_level(lot, today)}
            for lot in lots
        ],
        "moves": [
            {"id": m.pk, "qty": present.qty(m.qty), "reason": m.reason, "reasonLabel": REASON_LABEL[m.reason],
             "lineId": m.line_id, "note": m.note, "who": m.user.display_name if m.user else None,
             "ts": present.dt(m.ts), "expiresOn": present.d(m.lot.expires_on), "lotId": m.lot_id}
            for m in moves
        ],
        "settings": {"lowWarn": present.qty(s["low_warn"]), "lowCrit": present.qty(s["low_crit"])},
    })


def stock_in(request: HttpRequest, iid: str) -> HttpResponse:
    me = user_of(request)
    item = _find_item(iid)
    data = body(request)
    errors: dict[str, str] = {}
    qty = parse_qty(raw_field(data, "qty"))
    if not qty or qty != qty:
        errors["qty"] = "تعداد را به عدد وارد کنید (تا دو رقم اعشار، مثل ۰٫۵)."
    exp_raw = text(data, "expiresOn", 20)
    expires = None
    if exp_raw.strip():
        expires = parse_jalali(exp_raw)
        if expires is None:
            errors["expiresOn"] = "تاریخ انقضا را به شکل ۱۴۰۵/۰۸/۱۵ وارد کنید."
    cost_raw = text(data, "unitCost", 30)
    cost = parse_money(cost_raw, _cur()) if cost_raw.strip() else None
    if cost_raw.strip() and cost is None:
        errors["unitCost"] = "قیمت خرید درست نیست."
    if errors:
        raise invalid("لطفاً خطاهای مشخص‌شده را برطرف کنید.", errors)
    q = st.to_qty(qty)  # type: ignore[arg-type]
    lot = st.stock_in(item.pk, q, timezone.localdate(), expires, cost, _user(me))
    audit(me.id, "stock_in", None, f"item={item.pk} lot={lot.pk} qty={_qty_text(q)}")
    return ok({"lot": lot.pk}, 201)


def _lot(lid: str) -> Lot:
    lot = Lot.objects.select_related("item").filter(pk=id_of(lid), item__kind="item").first()
    if lot is None:
        raise not_found("کالای مورد نظر پیدا نشد.")
    return lot


def count(request: HttpRequest, lid: str) -> HttpResponse:
    me = user_of(request)
    lot = _lot(lid)
    data = body(request)
    counted = parse_qty(raw_field(data, "counted"), allow_zero=True)
    note = normalize_text(text(data, "note"))[:200]
    if counted is None or counted != counted:
        m = "تعداد شمارش‌شده را به عدد وارد کنید (تا دو رقم اعشار، مثل ۰٫۵)."
        raise invalid(m, {f"lot{lot.pk}": m})
    if not note:
        raise invalid("دلیل اصلاح را بنویسید.", {f"lot{lot.pk}": "دلیل اصلاح را بنویسید."})
    delta = st.count_lot(lot.pk, st.to_qty(counted), note, _user(me))
    audit(me.id, "stock_count", None, f"item={lot.item_id} lot={lot.pk} delta={_qty_text(delta)}")
    return ok({"itemId": lot.item_id})


def waste(request: HttpRequest, lid: str) -> HttpResponse:
    me = user_of(request)
    lot = _lot(lid)
    data = body(request)
    qty = parse_qty(raw_field(data, "qty"))
    note = normalize_text(text(data, "note"))[:200]
    if not qty or qty != qty:
        m = "تعداد ضایعات را به عدد وارد کنید (تا دو رقم اعشار، مثل ۰٫۵)."
        raise invalid(m, {f"lot{lot.pk}": m})
    if not note:
        raise invalid("دلیل ضایعات را بنویسید.", {f"lot{lot.pk}": "دلیل ضایعات را بنویسید."})
    q = st.to_qty(qty)
    try:
        st.waste_lot(lot.pk, q, note, _user(me))
    except st.ShortError:
        fresh = Lot.objects.get(pk=lot.pk)
        m = f"این بسته فقط {fa_digits(_qty_text(fresh.remaining))} عدد دارد."
        raise conflict(m, f"lot{lot.pk}") from None
    audit(me.id, "stock_waste", None, f"item={lot.item_id} lot={lot.pk} qty={_qty_text(q)}")
    return ok({"itemId": lot.item_id})


def delete_item(request: HttpRequest, iid: str) -> HttpResponse:
    me = user_of(request)
    item = _find_item(iid)
    lots = Lot.objects.filter(item=item).count()
    moves = StockMove.objects.filter(lot__item=item).count()
    kept = st.delete_item(item.pk)
    audit(me.id, "stock_item_delete", None, f"item={item.pk} lots={lots} moves={moves} kept={1 if kept else 0}")
    return ok({"notice": "کالا و همه‌ی گردش آن حذف شد."})


def delete_move(request: HttpRequest, mid: str) -> HttpResponse:
    me = user_of(request)
    move = StockMove.objects.select_related("lot").filter(pk=id_of(mid), lot__item__kind="item").first()
    if move is None:
        raise not_found("این ردیف پیدا نشد.")
    try:
        st.undo_move(move.pk)
    except st.UndoError as err:
        if err.code == "short":
            remaining = Lot.objects.filter(pk=move.lot_id).values_list("remaining", flat=True).first()
            m = (
                "با حذف این ردیف موجودی بسته منفی می‌شود؛ "
                f"این بسته الان {fa_digits(_qty_text(remaining))} عدد دارد."
            )
        else:
            m = UNDO_MESSAGES[err.code]
        raise conflict(m, f"move{move.pk}") from None
    audit(me.id, "stock_move_delete", None,
          f"item={move.lot.item_id} lot={move.lot_id} move={move.pk} reason={move.reason} "
          f"qty={_qty_text(move.qty)}")
    return ok({"itemId": move.lot.item_id})


items_view = route(GET=list_items, POST=create_item)
item_view = route(GET=show_item, DELETE=delete_item)
