"""Custom boxes (D53; legacy src/lib/custom-boxes.js): names, choices, values and their display text.

Writes lock the box row (SPEC §4.3). Choice ids are never reused (choice_seq)."""

from __future__ import annotations

import re
from typing import Any, cast

from django.db import transaction
from django.utils import timezone

from apps.core.audit import audit
from apps.core.jalali import fa_digits, parse_iso_date, parse_jalali, to_jalali_input
from apps.core.locks import get_for_update
from apps.core.text import fa_key, normalize_text
from apps.patients.catalogue import BOXES, CUSTOM_TYPE_IDS, CUSTOM_TYPES, LIMITS, has_visible
from apps.patients.models import CustomBox, PatientValue

MSG_BOX_IN_USE = "این کادر مقدار دارد و حذف نمی‌شود. آن را از فرم پنهان کنید."
MSG_CHOICE_HELD = "بیماری این گزینه را دارد و حذف نمی‌شود. آن را از فرم پنهان کنید."


class BoxError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def box_json(b: CustomBox) -> dict[str, Any]:
    full = next(t["full"] for t in CUSTOM_TYPES if t["id"] == b.type)
    return {"id": b.pk, "type": b.type, "label": b.label, "choices": b.choices or None, "full": full}


def live_custom_boxes() -> list[CustomBox]:
    return list(CustomBox.objects.filter(deleted_at__isnull=True).order_by("id"))


def split_choices(
    raw: Any, minimum: int = LIMITS["choicesMin"], existing: list[dict[str, Any]] | None = None
) -> list[str]:
    existing = existing or []
    items = [normalize_text(s) for s in re.split("[,،]", "" if raw is None else str(raw))]
    items = [s for s in items if has_visible(s)]
    if len(items) < minimum:
        raise BoxError("گزینه‌ی تازه را بنویسید." if minimum == 1 else "برای انتخاب از فهرست ۲ تا ۳۰ گزینه لازم است.")
    if len(items) > LIMITS["choicesMax"] - len(existing):
        raise BoxError("هر فهرست بیشتر از ۳۰ گزینه ندارد.")
    if any(len(s) > LIMITS["boxName"] for s in items):
        raise BoxError("هر گزینه باید بین ۱ تا ۶۰ نویسه باشد.")
    keys = {fa_key(c["label"]) for c in existing}
    if any(fa_key(s) in keys for s in items) or len({fa_key(s) for s in items}) != len(items):
        raise BoxError("گزینه‌ها نباید تکراری باشند.")
    return items


def taken_name_keys() -> set[str]:
    from apps.data_io.csv_io import reserved_header_keys

    return {
        *(fa_key(cast(str, b["label"])) for b in BOXES),
        *reserved_header_keys(),
        *(fa_key(b.label) for b in live_custom_boxes()),
    }


def check_name(label: Any, pending: set[str] | None = None) -> tuple[str, str]:
    name = normalize_text("" if label is None else str(label))
    if not has_visible(name) or len(name) > LIMITS["boxName"]:
        raise BoxError("نام کادر باید بین ۱ تا ۶۰ نویسه باشد.")
    key = fa_key(name)
    if key in taken_name_keys() or key in (pending or set()):
        raise BoxError("این نام قبلاً برای کادر دیگری استفاده شده است.")
    return name, key


def create_custom_box(type_: Any, label: Any, choices: Any, user_id: int | None) -> CustomBox:
    if type_ not in CUSTOM_TYPE_IDS:
        raise BoxError("نوع کادر را انتخاب کنید.")
    name, _ = check_name(label)
    stored = None
    seq = 0
    if type_ == "choice":
        labels = split_choices(choices)
        stored = [{"id": i + 1, "label": t, "hidden": False} for i, t in enumerate(labels)]
        seq = len(stored)
    box = CustomBox.objects.create(type=type_, label=name, choices=stored, choice_seq=seq)
    audit(user_id, "custom_box.create", None, f"{box.pk} {type_} {name}")
    return box


def _live_choice_box(box_id: int) -> CustomBox:
    box = get_for_update(CustomBox.objects.filter(deleted_at__isnull=True), box_id, "custom box")
    if box.type != "choice":
        raise BoxError("کادر پیدا نشد.")
    return box


def _next_choice_id(box: CustomBox) -> int:
    return max([box.choice_seq or 0, *(int(c["id"]) for c in (box.choices or []))]) + 1


def set_choice_hidden(box_id: int, choice_id: Any, hidden: bool, user_id: int | None) -> None:
    with transaction.atomic():
        box = _live_choice_box(box_id)
        choices = list(box.choices or [])
        cid = int(choice_id) if str(choice_id).isdigit() else -1
        hit = next((c for c in choices if int(c["id"]) == cid), None)
        if hit is None:
            raise BoxError("گزینه پیدا نشد.")
        hit["hidden"] = bool(hidden)
        box.choices = choices
        box.save(update_fields=["choices"])
        audit(user_id, "custom_box.edit", None, f"{box.pk} {'hide' if hidden else 'show'} {cid}")


def remove_choice(box_id: int, choice_id: Any, user_id: int | None) -> None:
    with transaction.atomic():
        box = _live_choice_box(box_id)
        cid = int(choice_id) if str(choice_id).isdigit() else -1
        choices = list(box.choices or [])
        if not any(int(c["id"]) == cid for c in choices):
            raise BoxError("گزینه پیدا نشد.")
        if PatientValue.objects.filter(box=box, value=str(cid)).exists():
            raise BoxError(MSG_CHOICE_HELD)
        seq = _next_choice_id(box) - 1
        box.choices = [c for c in choices if int(c["id"]) != cid]
        box.choice_seq = seq
        box.save(update_fields=["choices", "choice_seq"])
        audit(user_id, "custom_box.edit", None, f"{box.pk} remove {cid}")


def add_choices(box_id: int, text_: Any, user_id: int | None) -> None:
    with transaction.atomic():
        box = _live_choice_box(box_id)
        existing = list(box.choices or [])
        labels = split_choices(text_, 1, existing)
        nxt = _next_choice_id(box)
        added = []
        for label in labels:
            added.append({"id": nxt, "label": label, "hidden": False})
            nxt += 1
        box.choices = existing + added
        box.choice_seq = nxt - 1
        box.save(update_fields=["choices", "choice_seq"])
        for c in added:
            audit(user_id, "custom_box.edit", None, f"{box.pk} add {c['id']}")


def delete_custom_box(box_id: int, user_id: int | None) -> None:
    with transaction.atomic():
        box = CustomBox.objects.select_for_update().filter(pk=box_id, deleted_at__isnull=True).first()
        if box is None:
            raise BoxError("کادر پیدا نشد.")
        if PatientValue.objects.filter(box=box).exists():
            raise BoxError(MSG_BOX_IN_USE)
        box.deleted_at = timezone.now()
        box.save(update_fields=["deleted_at"])
        audit(user_id, "custom_box.delete", None, f"{box.pk} {box.type}")


_NUMBER = re.compile(r"-?\d{1,9}(\.\d{1,2})?", re.ASCII)


def _js_number_text(s: str) -> str:
    """String(Number(s)) for the plain decimals the number box accepts."""
    n = float(s)
    if n == 0:
        return "0"
    return str(int(n)) if n.is_integer() else repr(n)


def check_custom_value(box: CustomBox, raw: Any, by_label: bool = False, keep: str | None = None) -> str | None:
    """The value to store (None clears it). Raises BoxError with the Persian message."""
    text_ = normalize_text("" if raw is None or isinstance(raw, (list, dict)) else str(raw))
    if text_ == "":
        return None
    t = box.type
    if t in ("short_text", "long_text"):
        if t == "long_text":
            limit, msg = LIMITS["longText"], "بیش از ۵۰۰۰ نویسه است."
        else:
            limit, msg = LIMITS["shortText"], "بیش از ۲۰۰ نویسه است."
        if len(text_) > limit:
            raise BoxError(msg)
        return text_
    if t == "number":
        if "," in text_:
            raise BoxError("عدد را بدون جداکننده‌ی هزارگان و با ممیز بنویسید.")
        s = text_.replace("٫", ".", 1)
        if not _NUMBER.fullmatch(s):
            raise BoxError("عدد را درست وارد کنید، مثلاً ۶۸٫۵ یا -۳٫۵.")
        return _js_number_text(s)
    if t == "date":
        iso = parse_jalali(text_)
        if iso is None:
            raise BoxError("تاریخ را به شکل ۱۴۰۳/۰۵/۱۲ وارد کنید.")
        return iso.isoformat()
    if t == "choice":
        choices = box.choices or []
        if by_label:
            hit = next((c for c in choices if not c.get("hidden") and normalize_text(c["label"]) == text_), None)
        else:
            hit = next(
                (c for c in choices if text_.isdigit() and text_.isascii() and int(c["id"]) == int(text_)
                 and (not c.get("hidden") or text_ == str(keep))),
                None,
            )
        if hit:
            return str(hit["id"])
        raise BoxError("گزینه را از فهرست انتخاب کنید.")
    if t == "yes_no":
        if text_ in ("1", "0"):
            return text_
        if by_label:
            key = fa_key(text_)
            if key in ("بله", "yes"):
                return "1"
            if key in ("خیر", "no"):
                return "0"
        raise BoxError("بله یا خیر را انتخاب کنید.")
    raise BoxError("نوع کادر نامعتبر است.")


def custom_display(box: CustomBox | dict[str, Any], value: Any, ascii_digits: bool = False) -> str:
    if value is None or value == "":
        return ""
    t = box.type if isinstance(box, CustomBox) else box["type"]
    choices = (box.choices if isinstance(box, CustomBox) else box.get("choices")) or []

    def digits(s: str) -> str:
        return s if ascii_digits else fa_digits(s)

    if t == "date":
        try:
            return digits(to_jalali_input(parse_iso_date(str(value))))
        except ValueError:
            return ""
    if t == "number":
        return digits(str(value))
    if t == "choice":
        hit = next((c for c in choices if str(c["id"]) == str(value)), None)
        return hit["label"] if hit else "(گزینه‌ی حذف‌شده)"
    if t == "yes_no":
        return "بله" if value == "1" else "خیر"
    return str(value)


def custom_values(patient_id: int) -> dict[int, str]:
    return dict(PatientValue.objects.filter(patient_id=patient_id).values_list("box_id", "value"))


def write_custom_values(patient_id: int, values: dict[int, str | None]) -> None:
    """Upsert or delete (None) the given values. Call inside the patient save's transaction.
    Locks the boxes in ascending id first (SPEC §4.3), so a parallel box delete cannot slip between."""
    if not values:
        return
    live = {
        b.pk
        for b in CustomBox.objects.select_for_update()
        .filter(pk__in=sorted(values), deleted_at__isnull=True)
        .order_by("pk")
    }
    for box_id, value in values.items():
        if box_id not in live:
            continue
        if value is None:
            PatientValue.objects.filter(patient_id=patient_id, box_id=box_id).delete()
        else:
            row = PatientValue.objects.filter(patient_id=patient_id, box_id=box_id).first()
            if row is None:
                PatientValue(patient_id=patient_id, box_id=box_id, value=value).save()
            else:
                row.value = value
                row.save()


def shown_custom_boxes(layout: dict[str, Any]) -> list[CustomBox]:
    live = {b.pk: b for b in live_custom_boxes()}
    ids = [b["id"] for c in layout["cards"] for b in c["boxes"] if b["id"].startswith("c:")]
    return [live[int(i[2:])] for i in ids if int(i[2:]) in live]


def custom_columns(layout: dict[str, Any]) -> list[tuple[str, str]]:
    live = {b.pk: b for b in live_custom_boxes()}
    shown = [b.pk for b in shown_custom_boxes(layout)]
    hidden = [i for i in live if i not in shown]
    return [(f"c{i}", live[i].label) for i in [*shown, *hidden]]


def add_custom_cells(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    boxes = {b.pk: b for b in live_custom_boxes()}
    if not boxes or not rows:
        return rows
    ids = [r["id"] for r in rows]
    cells: dict[int, dict[str, str]] = {}
    for pid, bid, value in PatientValue.objects.filter(box_id__in=list(boxes), patient_id__in=ids).values_list(
        "patient_id", "box_id", "value"
    ):
        box = boxes[bid]
        if box.type == "choice" and not any(str(c["id"]) == value for c in box.choices or []):
            continue
        t = custom_display(box, value, ascii_digits=True)
        if t:
            cells.setdefault(pid, {})[f"c{bid}"] = t
    return [{**r, **cells.get(r["id"], {})} for r in rows]
