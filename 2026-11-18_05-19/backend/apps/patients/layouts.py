"""Patient form layout and dashboard layout (D52-D54; legacy src/lib/layouts.js).

read_layout is forgiving (a bad row never breaks a page); check_layout is strict and guards every save. A save
keeps the old layout as `previous` (one-step undo). The row is locked before it is read (SPEC §4.3).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from typing import Any

from django.db import transaction

from apps.core.audit import audit
from apps.core.jalali import parse_iso_date, to_jalali_input
from apps.core.text import normalize_text
from apps.patients.catalogue import (
    BAD_SHAPE,
    BOX_BY_ID,
    BOXES,
    CARD_IDS,
    CARDS,
    CUSTOM_TYPE_IDS,
    LIMITS,
    NAME_BOXES,
    Reject,
    has_visible,
    is_obj,
)
from apps.patients.custom_boxes import BoxError, check_name, create_custom_box, live_custom_boxes, split_choices
from apps.patients.models import CustomBox, Layout

logger = logging.getLogger("klerk")


# A box's cell in its card's grid (owner decision 2026-11-17: the patient form gets the dashboard's home-screen
# editor). Optional: a card whose boxes have no cells flows in order, as before.
FORM_COLS = 4
FORM_ROWS = 80
FORM_MAX_H = 3
BAD_CELL = "جای کادر در کارت نامعتبر است."
CELL_OVERLAP = "کادرها روی هم افتاده‌اند."
_CELL_KEYS = ("x", "y", "w", "h")


def _cell(box: Any) -> dict[str, int] | None | bool:
    """The box's cell, None when it has none, False when it has a bad one."""
    if not is_obj(box) or not any(k in box for k in _CELL_KEYS):
        return None
    vals = [box.get(k) for k in _CELL_KEYS]
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in vals):
        return False
    x, y, w, h = vals
    if x < 0 or y < 0 or not 1 <= w <= FORM_COLS or not 1 <= h <= FORM_MAX_H or x + w > FORM_COLS or y + h > FORM_ROWS:
        return False
    return {"x": x, "y": y, "w": w, "h": h}


def _place_cells(raw: list[Any], boxes: list[dict[str, Any]], reject: Callable[[str], None]) -> None:
    """Copy each raw box's cell onto its checked box when every box of the card has a good cell and none overlap;
    otherwise the card keeps no cells (strict: Reject)."""
    cells = [_cell(b) for b in raw]
    if not boxes or all(c is None for c in cells):
        return
    if any(c is None or c is False for c in cells) or len(cells) != len(boxes):
        reject(BAD_CELL)
        return
    taken: set[tuple[int, int]] = set()
    for c in cells:
        assert isinstance(c, dict)
        mine = {(cx, cy) for cx in range(c["x"], c["x"] + c["w"]) for cy in range(c["y"], c["y"] + c["h"])}
        if mine & taken:
            reject(CELL_OVERLAP)
            return
        taken |= mine
    for b, c in zip(boxes, cells, strict=True):
        b.update(c)  # type: ignore[arg-type]


def default_form_layout() -> dict[str, Any]:
    return {
        "v": 1,
        "cards": [
            {
                "id": card["id"],
                "boxes": [
                    {"id": b["id"], "req": True} if b["id"] in NAME_BOXES else {"id": b["id"]}
                    for b in BOXES if b["card"] == card["id"]
                ],
            }
            for card in CARDS
        ],
    }


def _custom_index() -> dict[int, Any]:
    return {pk: deleted for pk, deleted in CustomBox.objects.values_list("id", "deleted_at")}


def _box_ref(box_id: Any, customs: dict[int, Any]) -> str:
    if not isinstance(box_id, str):
        raise Reject("کادر ناشناخته.")
    if box_id in BOX_BY_ID:
        return box_id
    m = re.fullmatch(r"c:(\d+)", box_id, re.ASCII)
    if not m:
        raise Reject("کادر ناشناخته.")
    n = int(m.group(1))
    if n not in customs:
        raise Reject("کادر سفارشی ناشناخته.")
    if customs[n] is not None:
        raise Reject("این کادر سفارشی حذف شده است.")
    return f"c:{n}"


def _check_new_box(box: dict[str, Any], pending: dict[str, set[Any]]) -> dict[str, Any]:
    m = re.fullmatch(r"new:(\d{1,2})", str(box.get("id")), re.ASCII)
    k = int(m.group(1)) if m else 0
    if not m or k < 1 or k > 99 or k in pending["keys"]:
        raise Reject("کادر تازه‌ی چیدمان نامعتبر است.")
    pending["keys"].add(k)
    if box.get("type") not in CUSTOM_TYPE_IDS:
        raise Reject("نوع کادر تازه را انتخاب کنید.")
    try:
        name, key = check_name(box.get("label"), pending["names"])
        choices = None
        if box["type"] == "choice":
            raw = box.get("choices")
            choices = split_choices(",".join(raw) if isinstance(raw, list) else raw)
    except BoxError as err:
        raise Reject(err.message) from None
    pending["names"].add(key)
    return {"id": f"new:{k}", "type": box["type"], "label": name, "choices": choices}


def clean_form(input_: Any, strict: bool) -> dict[str, Any] | None:
    customs = _custom_index()

    def reject(msg: str) -> None:
        if strict:
            raise Reject(msg)

    pending: dict[str, set[Any]] = {"keys": set(), "names": set()}
    if not is_obj(input_) or input_.get("v") != 1 or not isinstance(input_.get("cards"), list):
        reject(BAD_SHAPE)
        return None
    cards: list[dict[str, Any]] = []
    card_ids: set[str] = set()
    placed: set[str] = set()
    box_count = 0
    for card in input_["cards"]:
        out: dict[str, Any] | None = None
        if is_obj(card) and isinstance(card.get("id"), str):
            if card["id"] in CARD_IDS:
                out = {"id": card["id"]}
            else:
                m = re.fullmatch(r"card:(\d{1,3})", card["id"], re.ASCII)
                n = int(m.group(1)) if m else 0
                label = normalize_text(card["label"]) if isinstance(card.get("label"), str) else ""
                if m and 1 <= n <= 999 and has_visible(label) and len(label) <= LIMITS["cardLabel"]:
                    out = {"id": f"card:{n}", "label": label}
        if out is None:
            reject("کارت ناشناخته یا نام کارت نامعتبر است.")
            continue
        if out["id"] in card_ids:
            reject("کارت تکراری است.")
            continue
        if len(cards) >= LIMITS["cards"]:
            reject("بیش از ۱۲ کارت نمی‌شود.")
            continue
        card_ids.add(out["id"])
        if not isinstance(card.get("boxes"), list):
            reject("کادرهای کارت نامعتبر است.")
        boxes: list[dict[str, Any]] = []
        kept: list[Any] = []
        for box in card.get("boxes") if isinstance(card.get("boxes"), list) else []:
            if strict and is_obj(box) and isinstance(box.get("id"), str) and box["id"].startswith("new:"):
                if box_count >= LIMITS["boxes"]:
                    raise Reject("بیش از ۸۰ کادر نمی‌شود.")
                item = _check_new_box(box, pending)
                box_count += 1
                if box.get("req") is True:
                    item["req"] = True
                boxes.append(item)
                kept.append(box)
                continue
            try:
                ref = _box_ref(box.get("id") if is_obj(box) else None, customs)
            except Reject as err:
                reject(str(err))
                continue
            if ref in placed:
                reject("کادر تکراری است.")
                continue
            if box_count >= LIMITS["boxes"]:
                reject("بیش از ۸۰ کادر نمی‌شود.")
                continue
            placed.add(ref)
            box_count += 1
            item = {"id": ref}
            if ref in NAME_BOXES or box.get("req") is True:
                item["req"] = True
            boxes.append(item)
            kept.append(box)
        _place_cells(kept, boxes, reject)
        entry: dict[str, Any] = {"id": out["id"]}
        if "label" in out:
            entry["label"] = out["label"]
        entry["boxes"] = boxes
        cards.append(entry)
    missing = [i for i in NAME_BOXES if i not in placed]
    if missing:
        reject("نام و نام خانوادگی باید در فرم باشند.")
        if not cards:
            cards.append({"id": "identity", "boxes": []})
        cards[0]["boxes"][0:0] = [{"id": i, "req": True} for i in missing]
    return {"v": 1, "cards": cards}


def _kind(
    name: str,
) -> tuple[Callable[[], dict[str, Any]], Callable[[Any, bool], dict[str, Any] | None]]:
    from apps.dashboard.grid import clean_any, default_layout

    if name == "patient_form":
        return default_form_layout, clean_form
    if name == "dashboard":  # layout v2 (ADR-0014); a stored v1 row converts on read
        return default_layout, clean_any
    raise ValueError(f"unknown layout {name}")


def read_layout(name: str) -> dict[str, Any]:
    make, clean = _kind(name)
    row = Layout.objects.filter(pk=name).first()
    if row is None:
        return make()
    try:
        layout = clean(row.current, False)
    except Reject:
        layout = None
    if not layout:
        logger.error("layout %s: stored layout is unreadable, the default is used", name)
        return make()
    return layout


def check_layout(name: str, value: Any) -> dict[str, Any]:
    """Strict check for a save. `value` is the JSON text or an already parsed object. Raises Reject."""
    _, clean = _kind(name)
    if isinstance(value, str):
        if len(value.encode("utf-8")) > LIMITS["json"]:
            raise Reject("چیدمان خیلی بزرگ است.")
        try:
            value = json.loads(value)
        except ValueError:
            raise Reject("چیدمان خوانده نشد. دوباره تلاش کنید.") from None
    elif len(json.dumps(value, ensure_ascii=False).encode("utf-8")) > LIMITS["json"]:
        raise Reject("چیدمان خیلی بزرگ است.")
    out = clean(value, True)
    if out is None:
        raise Reject(BAD_SHAPE)
    return out


def _materialize(name: str, layout: dict[str, Any], user_id: int | None) -> dict[str, Any]:
    if name != "patient_form":
        return layout
    cards = []
    for card in layout["cards"]:
        boxes = []
        for b in card["boxes"]:
            if not b["id"].startswith("new:"):
                boxes.append(b)
                continue
            choices = ",".join(b["choices"]) if b.get("choices") else None
            made = create_custom_box(b["type"], b["label"], choices, user_id)
            item = {"id": f"c:{made.pk}", "req": True} if b.get("req") else {"id": f"c:{made.pk}"}
            boxes.append({**item, **{k: b[k] for k in _CELL_KEYS if k in b}})
        cards.append({**card, "boxes": boxes})
    return {"v": 1, "cards": cards}


def _locked_row(name: str) -> tuple[Layout, bool]:
    make, _ = _kind(name)
    _, created = Layout.objects.get_or_create(name=name, defaults={"current": make(), "previous": None})
    return Layout.objects.select_for_update().get(pk=name), created


def save_layout(name: str, layout: dict[str, Any], user_id: int | None) -> None:
    with transaction.atomic():
        row, _ = _locked_row(name)
        stored = _materialize(name, layout, user_id)
        row.previous = row.current
        row.current = stored
        row.updated_by_id = user_id
        row.save()
        audit(user_id, "layout.save", None, name)


def undo_layout(name: str, user_id: int | None) -> bool:
    with transaction.atomic():
        row = Layout.objects.select_for_update().filter(pk=name).first()
        if row is None or row.previous is None:
            return False
        row.current, row.previous = row.previous, row.current
        row.updated_by_id = user_id
        row.save()
        audit(user_id, "layout.undo", None, name)
        return True


def reset_layout(name: str, user_id: int | None) -> None:
    make, _ = _kind(name)
    with transaction.atomic():
        row, _ = _locked_row(name)
        row.previous = row.current
        row.current = make()
        row.updated_by_id = user_id
        row.save()
        audit(user_id, "layout.reset", None, name)


def has_previous(name: str) -> bool:
    return Layout.objects.filter(pk=name, previous__isnull=False).exists()


def shown_box_ids(boxes_field: Any) -> set[str]:
    live = {f"c:{b.pk}" for b in live_custom_boxes()}
    if not isinstance(boxes_field, str):
        saved = [b["id"] for c in read_layout("patient_form")["cards"] for b in c["boxes"]]
        return {*NAME_BOXES, *saved}
    posted = [s.strip() for s in boxes_field.split(",")]
    return {*NAME_BOXES, *(i for i in posted if i in BOX_BY_ID or i in live)}


def required_box_ids(layout: dict[str, Any]) -> set[str]:
    return {b["id"] for c in layout["cards"] for b in c["boxes"] if b.get("req")}


def custom_form_values(patient_id: int) -> dict[str, str]:
    from apps.patients.models import PatientValue

    types = dict(CustomBox.objects.values_list("id", "type"))
    out = {}
    for bid, value in PatientValue.objects.filter(patient_id=patient_id).values_list("box_id", "value"):
        if types.get(bid) == "date":
            try:
                value = to_jalali_input(parse_iso_date(value))
            except ValueError:
                pass
        out[f"c_{bid}"] = value
    return out
