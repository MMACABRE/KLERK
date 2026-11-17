"""Dashboard catalogue (D54; legacy src/lib/dashboard.js): widgets, quick buttons, default layout, reader."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from django.db.models import Count
from django.utils import timezone

from apps.core import present
from apps.core.jalali import fa_digits
from apps.core.perms import EDIT, can, has
from apps.core.settings_store import get_settings
from apps.patients.catalogue import BAD_SHAPE, Reject, is_obj

log = logging.getLogger("klerk")


def _fa(n: int) -> str:
    return fa_digits(f"{n:,}".replace(",", "٬"))


def sees_patients(u: Any) -> bool:
    return can(u, "patients")


def _stat(status: str) -> Callable[[dict[str, Any]], Any]:
    return lambda ctx: {"n": ctx["counts"].get(status, 0), "total": ctx["total"]}


def _income_today(ctx: dict[str, Any]) -> Any:
    from apps.finance.services import income_between

    today = timezone.localdate()
    r = income_between(today, today)
    return {"total": present.money(r["total"], ctx["cur"]), "count": r["count"]}


def _sms(ctx: dict[str, Any]) -> Any:
    from apps.sms.engine import key_info
    from apps.sms.models import SmsMessage

    s = get_settings()
    if s["sms_enabled"] != "1":
        return None
    info = key_info()
    out: dict[str, Any] = {"noKey": not (info and info["usable"]), "low": None, "failed": 0}
    if s["sms_balance"] != "":
        try:
            left = int(float(s["sms_balance"]) // 1)
        except ValueError:
            left = None
        try:
            th = int(s["sms_low_threshold"]) or 10
        except ValueError:
            th = 10
        if left is not None and left <= th:
            out["low"] = left
    out["failed"] = SmsMessage.objects.filter(
        status="failed", created_at__gte=timezone.now() - timedelta(days=1)
    ).count()
    return out if out["noKey"] or out["low"] is not None or out["failed"] else None


def _alerts(ctx: dict[str, Any]) -> Any:
    from apps.storage.services import alerts

    a = alerts(get_settings())
    return [{"itemId": x["item"].pk, "name": x["item"].name, "level": x["level"], "text": x["text"]} for x in a] or None


def _today_visits(ctx: dict[str, Any]) -> Any:
    from apps.patients.views import visit_item
    from apps.visits.logic import todays_visits

    return [visit_item(v, ctx["user"], False, with_patient=True) for v in todays_visits()]


def _recent(ctx: dict[str, Any]) -> Any:
    from apps.patients.models import Patient
    from apps.patients.views import patient_row

    return [patient_row(p) for p in Patient.objects.order_by("-updated_at", "-id")[:8]]


WIDGETS: list[dict[str, Any]] = [
    {"id": "quick", "label": "دسترسی سریع", "sizes": ["4x2", "4x1", "2x2"], "needs": lambda u: True,
     "load": lambda ctx: None},  # v1 only: a stored v1 layout converts its buttons to tiles (grid.from_v1)
    {"id": "active", "label": "بیماران فعال", "sizes": ["1x1", "2x1"], "defaultSize": "2x1", "needs": sees_patients,
     "load": _stat("active")},
    {"id": "pending", "label": "در انتظار", "sizes": ["1x1", "2x1"], "needs": sees_patients, "load": _stat("pending")},
    {"id": "critical", "label": "بحرانی", "sizes": ["1x1", "2x1"], "needs": sees_patients, "load": _stat("critical")},
    {"id": "income_today", "label": "درآمد امروز", "sizes": ["2x1", "1x1"], "needs": lambda u: can(u, "finance"),
     "load": _income_today},
    {"id": "sms", "label": "پیامک", "sizes": ["2x1", "2x2"], "needs": lambda u: can(u, "sms") and can(u, "patients"),
     "load": _sms},
    {"id": "alerts", "label": "هشدارها", "sizes": ["2x2", "2x1"], "needs": lambda u: can(u, "storage"),
     "load": _alerts},
    {"id": "today_visits", "label": "ویزیت‌های امروز", "sizes": ["2x2", "4x2", "2x3"],
     "needs": lambda u: can(u, "patients") and can(u, "visits"), "load": _today_visits},
    {"id": "recent", "label": "آخرین پرونده‌های به‌روزشده", "sizes": ["4x2", "2x2"], "needs": sees_patients,
     "load": _recent},
    # ADR-0014 step 4; v1 sizes only so the default (a v1 list converted to v2) can place it.
    {"id": "print_forms", "label": "فرم‌های چاپی", "sizes": ["2x2", "2x1", "2x3"], "needs": lambda u: can(u, "pdf"),
     "load": lambda ctx: _print_forms(ctx)},
]


def _print_forms(ctx: dict[str, Any]) -> Any:
    """The print forms the user may open, each with the date it takes: `day` (?d=), `range` (?from=&to=) or none."""
    from apps.dashboard.grid import TILES

    takes = {"print_stock_usage": "range", "print_stock_inventory": ""}
    forms = [{"id": t["id"].removeprefix("tile:"), "href": t["href"], "title": t["title"],
              "takes": takes.get(t["id"].removeprefix("tile:"), "day")}
             for t in TILES if t["id"].startswith("tile:print_") and t["needs"](ctx["user"])]
    return forms or None

QUICK_BUTTONS: list[dict[str, Any]] = [
    {"id": "new_patient", "href": "/patients/new", "icon": "plus", "title": "ثبت بیمار جدید",
     "text": lambda ctx: "پرونده‌ی تازه با کد خودکار بسازید", "needs": lambda u: can(u, "patients", EDIT)},
    {"id": "pay", "href": "/finance/pay", "icon": "wallet", "title": "ثبت پرداخت",
     "text": lambda ctx: "بیمار و ویزیت را انتخاب کنید",
     "needs": lambda u: can(u, "finance", EDIT) and can(u, "patients")},
    {"id": "patients", "href": "/patients", "icon": "users", "title": "فهرست بیماران",
     "text": lambda ctx: _fa(ctx["total"] - ctx["counts"].get("archived", 0)) + " پرونده", "needs": sees_patients},
    {"id": "search", "href": "/search", "icon": "search", "title": "جستجوی پیشرفته",
     "text": lambda ctx: "جستجو با چند شرط و خروجی اکسل", "needs": sees_patients},
    {"id": "upload", "href": "/patients", "icon": "upload", "title": "بارگذاری مدرک",
     "text": lambda ctx: "بیمار را انتخاب کنید و فایل را رها کنید",
     "needs": lambda u: can(u, "documents", EDIT) and can(u, "patients")},
    {"id": "storage", "href": "/storage", "icon": "box", "title": "انبار",
     "text": lambda ctx: "موجودی، ورود کالا و تاریخ انقضا",
     "needs": lambda u: can(u, "storage")},
    {"id": "finance", "href": "/finance", "icon": "wallet", "title": "امور مالی",
     "text": lambda ctx: "درآمد، پرداخت‌ها و نمودارها",
     "needs": lambda u: can(u, "finance")},
    {"id": "data", "href": "/data", "icon": "swap", "title": "ورود و خروج داده",
     "text": lambda ctx: "ورود از CSV و دریافت فایل کامل",
     "needs": lambda u: can(u, "data")},
    {"id": "users", "href": "/admin/users", "icon": "users", "title": "مدیریت کاربران",
     "text": lambda ctx: "حساب‌ها و دسترسی‌های کارکنان", "needs": lambda u: can(u, "users")},
    {"id": "audit", "href": "/admin/audit", "icon": "shield", "title": "گزارش فعالیت",
     "text": lambda ctx: "چه کسی، چه زمانی، چه کاری کرد", "needs": lambda u: has(u, "audit_log")},
    {"id": "account", "href": "/account", "icon": "shield", "title": "حساب کاربری",
     "text": lambda ctx: "تغییر رمز عبور",
     "needs": lambda u: True},
]

QUICK = [b["id"] for b in QUICK_BUTTONS]
WIDGET_BY_ID = {w["id"]: w for w in WIDGETS}


def default_dashboard_layout() -> dict[str, Any]:
    return {"v": 1, "widgets": [{"id": w["id"], "size": w.get("defaultSize", w["sizes"][0])} for w in WIDGETS],
            "quick": list(QUICK)}


def clean_dashboard(input_: Any, strict: bool) -> dict[str, Any] | None:
    def reject(msg: str) -> None:
        if strict:
            raise Reject(msg)

    if not is_obj(input_) or input_.get("v") != 1 or not isinstance(input_.get("widgets"), list) or not isinstance(
        input_.get("quick"), list
    ):
        reject(BAD_SHAPE)
        return None
    widgets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for w in input_["widgets"]:
        d = WIDGET_BY_ID.get(w.get("id")) if is_obj(w) and isinstance(w.get("id"), str) else None
        if d is None:
            reject("ویجت ناشناخته است.")
            continue
        if d["id"] in seen:
            reject("ویجت تکراری است.")
            continue
        size = w.get("size")
        if size not in d["sizes"]:
            reject("اندازه‌ی ویجت مجاز نیست.")
            size = d["sizes"][0]
        seen.add(d["id"])
        widgets.append({"id": d["id"], "size": size})
    quick: list[str] = []
    for i in input_["quick"]:
        if not isinstance(i, str) or i not in QUICK:
            reject("دکمه‌ی دسترسی سریع ناشناخته است.")
            continue
        if i in quick:
            reject("دکمه‌ی دسترسی سریع تکراری است.")
            continue
        quick.append(i)
    return {"v": 1, "widgets": widgets, "quick": quick}


def _load(d: dict[str, Any], ctx: dict[str, Any]) -> Any:
    try:
        return d["load"](ctx)
    except Exception as err:  # noqa: BLE001
        log.error("dashboard widget %s failed: %s", d["id"], type(err).__name__)
        return None


def dashboard(user: Any, editing: bool) -> dict[str, Any]:
    """GET /dashboard (ADR-0014 layout v2): the layout, the items drawn at their cells, and in edit mode the
    catalogue of every item with its size limits and the ones not in the layout."""
    from apps.dashboard.grid import build_grid, catalogue
    from apps.patients.layouts import has_previous, read_layout
    from apps.patients.models import Patient

    layout = read_layout("dashboard")
    editing = editing and has(user, "layout")
    counts: dict[str, int] = {}
    if can(user, "patients"):
        counts = {r["status"]: r["n"] for r in Patient.objects.values("status").annotate(n=Count("id"))}
    total = sum(counts.values())
    ctx = {"user": user, "counts": counts, "total": total, "cur": get_settings()["currency"]}
    out: dict[str, Any] = {
        "editing": editing, "layout": layout, "grid": build_grid(user, layout, editing, lambda d: _load(d, ctx), ctx),
        "hasPrevious": has_previous("dashboard"), "total": total, "counts": counts,
    }
    if editing:
        cat = catalogue()
        in_layout = {i["id"] for i in layout["items"]}
        out["catalogue"] = cat
        out["removed"] = [c["id"] for c in cat if c["id"] not in in_layout]
    return out
