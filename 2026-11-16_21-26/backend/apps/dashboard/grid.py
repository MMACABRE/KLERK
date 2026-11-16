"""Dashboard layout v2 (ADR-0014): items at fixed cells on an 8-column grid, tiles for pages and print forms.

Layout shape: {"v": 2, "items": [{"id", "x", "y", "w", "h"}]}. `x` counts columns from the inline start. Items
never overlap and stay inside 8 columns and 40 rows. A v1 layout converts on read (`from_v1`).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from apps.core.perms import can
from apps.dashboard.widgets import QUICK_BUTTONS, WIDGET_BY_ID, clean_dashboard, default_dashboard_layout
from apps.patients.catalogue import BAD_SHAPE, Reject, is_obj

COLS = 8
ROWS = 40
OVERLAP = "ویجت‌ها روی هم افتاده‌اند."
OUT_OF_GRID = "ویجت از جدول داشبورد بیرون زده است."
UNKNOWN = "ویجت ناشناخته است."
DUPLICATE = "ویجت تکراری است."
BAD_SIZE = "اندازه‌ی ویجت مجاز نیست."

Box = tuple[int, int, int, int]  # min w, min h, max w, max h

# One v1 column is two v2 columns, so a widget keeps the width it had on the v1 4-column grid; rows are unchanged.
WIDGET_LIMITS: dict[str, Box] = {
    "active": (2, 1, 4, 1), "pending": (2, 1, 4, 1), "critical": (2, 1, 4, 1), "income_today": (2, 1, 4, 1),
    "sms": (4, 1, 4, 2), "alerts": (4, 1, 4, 2), "today_visits": (4, 2, 8, 3), "recent": (4, 2, 8, 2),
    "print_forms": (4, 1, 4, 3),
}
TILE_LIMITS: Box = (1, 1, 2, 2)


def _pdf_and(*areas: str) -> Callable[[Any], bool]:
    return lambda u: can(u, "pdf") and all(can(u, a) for a in areas)


def _tile(id_: str, href: str, icon: str, title: str, needs: Callable[[Any], bool]) -> dict[str, Any]:
    return {"id": f"tile:{id_}", "href": href, "icon": icon, "title": title, "needs": needs}


# Quick buttons keep their ids and wording; the rest reuse the sidebar and print-index titles. Each `needs`
# matches the sidebar link or the print view's own check (`apps/printing/views.py`, plus `pdf` from the gate).
TILES: list[dict[str, Any]] = [
    *({**b, "id": f"tile:{b['id']}"} for b in QUICK_BUTTONS),
    _tile("visits", "/visits", "calendar", "ویزیت‌ها", lambda u: can(u, "patients") and can(u, "visits")),
    _tile("sms", "/sms", "mail", "پیامک", lambda u: can(u, "sms") and can(u, "patients")),
    _tile("print", "/print", "print", "فرم‌های چاپی", lambda u: can(u, "pdf")),
    _tile("contact", "/contact", "help", "تماس با ما", lambda u: True),
    _tile("print_finance_day", "/print/finance/day", "print", "گزارش مالی روزانه", _pdf_and("finance", "patients")),
    _tile("print_visits_day", "/print/visits/day", "print", "فهرست ویزیت‌های روز",
          _pdf_and("visits", "patients", "finance")),
    _tile("print_visits_report", "/print/visits/report", "print", "گزارش کامل روزانه",
          _pdf_and("visits", "patients", "finance")),
    _tile("print_daily_full", "/print/day/full", "print", "خلاصه‌ی روزانه", _pdf_and("patients")),
    _tile("print_stock_usage", "/print/stock/usage", "print", "کالاهای مصرف‌شده", _pdf_and("storage")),
    _tile("print_stock_day", "/print/stock/day", "print", "گزارش روزانه‌ی مصرف کالا",
          _pdf_and("storage", "patients", "visits")),
    _tile("print_stock_inventory", "/print/stock/inventory", "print", "موجودی انبار", _pdf_and("storage")),
]
TILE_BY_ID = {t["id"]: t for t in TILES}


def limits(id_: str) -> Box | None:
    if id_ in TILE_BY_ID:
        return TILE_LIMITS
    return WIDGET_LIMITS.get(id_)


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _cells(x: int, y: int, w: int, h: int) -> set[tuple[int, int]]:
    return {(cx, cy) for cx in range(x, x + w) for cy in range(y, y + h)}


def clean_v2(input_: Any, strict: bool) -> dict[str, Any] | None:
    """Check a v2 layout. Strict raises Reject on the first fault; lenient drops faulty items."""

    def reject(msg: str) -> None:
        if strict:
            raise Reject(msg)

    if not is_obj(input_) or input_.get("v") != 2 or not isinstance(input_.get("items"), list):
        reject(BAD_SHAPE)
        return None
    items: list[dict[str, Any]] = []
    taken: set[tuple[int, int]] = set()
    seen: set[str] = set()
    for it in input_["items"]:
        if not is_obj(it) or not all(_is_int(it.get(k)) for k in ("x", "y", "w", "h")):
            reject(BAD_SHAPE)
            continue
        box = limits(it.get("id")) if isinstance(it.get("id"), str) else None
        if box is None:
            reject(UNKNOWN)
            continue
        if it["id"] in seen:
            reject(DUPLICATE)
            continue
        x, y, w, h = it["x"], it["y"], it["w"], it["h"]
        if x < 0 or y < 0 or w < 1 or h < 1 or x + w > COLS or y + h > ROWS:
            reject(OUT_OF_GRID)
            continue
        if not (box[0] <= w <= box[2] and box[1] <= h <= box[3]):
            reject(BAD_SIZE)
            continue
        cells = _cells(x, y, w, h)
        if cells & taken:
            reject(OVERLAP)
            continue
        taken |= cells
        seen.add(it["id"])
        items.append({"id": it["id"], "x": x, "y": y, "w": w, "h": h})
    return {"v": 2, "items": items}


def _next_fit(taken: set[tuple[int, int]], w: int, h: int, start: tuple[int, int]) -> tuple[int, int] | None:
    """The first free spot at or after `start` (row, column) in reading order; never before it."""
    for y in range(start[0], ROWS - h + 1):
        for x in range(start[1] if y == start[0] else 0, COLS - w + 1):
            if not _cells(x, y, w, h) & taken:
                return x, y
    return None


def from_v1(v1: dict[str, Any]) -> dict[str, Any]:
    """Pack a clean v1 layout into v2 in v1 order: each item at the first free spot at or after the one before it
    (CSS grid's default flow), so a later item never lands above an earlier one. A widget's v1 width doubles (one
    v1 column is two v2 columns). `quick` becomes its buttons as tiles, the first one 2x2 (as v1 draws it), the
    rest 1x1."""
    wanted: list[tuple[str, int, int]] = []
    for wid in v1["widgets"]:
        if wid["id"] == "quick":
            wanted += [(f"tile:{b}", 2 if i == 0 else 1, 2 if i == 0 else 1) for i, b in enumerate(v1["quick"])]
        else:
            w, h = (int(n) for n in wid["size"].split("x"))
            wanted.append((wid["id"], w * 2, h))
    taken: set[tuple[int, int]] = set()
    items: list[dict[str, Any]] = []
    cursor = (0, 0)
    for id_, w, h in wanted:
        spot = _next_fit(taken, w, h, cursor)
        if spot is None:  # 320 cells hold every item; kept for safety
            continue
        taken |= _cells(*spot, w, h)
        cursor = (spot[1], spot[0])
        items.append({"id": id_, "x": spot[0], "y": spot[1], "w": w, "h": h})
    return {"v": 2, "items": items}


def clean_any(input_: Any, strict: bool) -> dict[str, Any] | None:
    """Read either version; v1 is checked by the v1 rules, then converted."""
    if is_obj(input_) and input_.get("v") == 1:
        v1 = clean_dashboard(input_, strict)
        return from_v1(v1) if v1 is not None else None
    return clean_v2(input_, strict)


def default_layout() -> dict[str, Any]:
    return from_v1(default_dashboard_layout())


def build_grid(
    user: Any, layout: dict[str, Any], editing: bool, load: Callable[[dict[str, Any]], Any], ctx: dict[str, Any]
) -> dict[str, Any]:
    """The answer's `grid`: each layout item at its cell, in reading order (row, then column), which is also the
    DOM and Tab order and the flow of narrow windows (ADR-0014 "Screens"). Outside edit mode an item the user may
    not open, or a widget with nothing to show, is left out. In edit mode every item is listed, `locked` when the
    user may not open it (its data then stays empty)."""
    items: list[dict[str, Any]] = []
    for it in sorted(layout["items"], key=lambda i: (i["y"], i["x"])):
        cell = {"id": it["id"], "x": it["x"], "y": it["y"], "w": it["w"], "h": it["h"]}
        tile = TILE_BY_ID.get(it["id"])
        if tile is not None:
            allowed = tile["needs"](user)
            if allowed or editing:
                text = tile["text"](ctx) if allowed and "text" in tile else ""
                items.append({**cell, "kind": "tile", "href": tile["href"], "icon": tile["icon"],
                              "title": tile["title"], "text": text, "locked": not allowed})
            continue
        d = WIDGET_BY_ID[it["id"]]
        allowed = d["needs"](user)
        data = load(d) if allowed else None
        if editing or (allowed and data is not None):
            items.append({**cell, "kind": "widget", "label": d["label"], "data": data, "locked": not allowed})
    return {"cols": COLS, "items": items}


def catalogue() -> list[dict[str, Any]]:
    """Every item a layout may hold, with its size limits, for the editor's add list and resize handle."""
    out: list[dict[str, Any]] = []
    for wid, box in WIDGET_LIMITS.items():
        out.append({"id": wid, "kind": "widget", "label": WIDGET_BY_ID[wid]["label"], "min": box[:2], "max": box[2:]})
    for t in TILES:
        out.append({"id": t["id"], "kind": "tile", "label": t["title"], "icon": t["icon"],
                    "min": TILE_LIMITS[:2], "max": TILE_LIMITS[2:]})
    return out
