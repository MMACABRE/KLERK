"""Permissions as stored (legacy src/lib/perms.js). parse_perms turns any stored value into a clean
permission object, as parsePerms does: junk becomes "none", unknown flags are dropped, a flag
counts only when its area reaches the level the flag needs. Booleans are never levels; 1.0 is a
level, as JSON.parse makes it in Node."""

from __future__ import annotations

import json
from typing import Any

NONE = 0
VIEW = 1
EDIT = 2

AREAS = ["patients", "documents", "visits", "storage", "finance", "sms", "pdf", "data", "users"]
AREA_MAX = {
    "patients": EDIT,
    "documents": EDIT,
    "visits": EDIT,
    "storage": EDIT,
    "finance": EDIT,
    "sms": EDIT,
    "pdf": VIEW,
    "data": VIEW,
    "users": VIEW,
}
# flag -> (area, level that area needs for the flag to count)
FLAGS: dict[str, tuple[str, int]] = {
    "patient_delete": ("patients", EDIT),
    "patient_code": ("patients", EDIT),
    "document_delete": ("documents", EDIT),
    "full_zip": ("data", VIEW),
    "csv_import": ("data", VIEW),
    "manage_users": ("users", VIEW),
    "audit_log": ("users", VIEW),
    "stock_adjust": ("storage", EDIT),
    "finance_settings": ("finance", EDIT),
    "price_override": ("finance", EDIT),
    "sms_bulk": ("sms", EDIT),
    "sms_key": ("sms", EDIT),
    "layout": ("patients", EDIT),
}


def _level(value: Any, highest: int) -> int:
    """A JS integer in range: an int or a float with no fraction (bools are not levels)."""
    if isinstance(value, bool):
        return NONE
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, int) and NONE <= value <= highest:
        return value
    return NONE


def parse_perms(stored: object) -> dict[str, Any]:
    raw: Any = stored
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = None
    if not isinstance(raw, dict):
        raw = {}
    out: dict[str, Any] = {area: _level(raw.get(area), AREA_MAX[area]) for area in AREAS}
    flags = raw.get("flags")
    flag_list = flags if isinstance(flags, list) else []
    out["flags"] = [
        name for name, (area, needed) in FLAGS.items() if name in flag_list and out[area] >= needed
    ]
    return out


AREA_LABELS = {
    "patients": "بیماران",
    "documents": "مدارک",
    "visits": "ویزیت‌ها",
    "storage": "انبار",
    "finance": "امور مالی",
    "sms": "پیامک",
    "pdf": "فرم‌های چاپی",
    "data": "داده‌ها",
    "users": "کاربران",
}
LEVEL_LABELS = ["بدون دسترسی", "مشاهده", "ویرایش"]
FLAG_LABELS = {
    "patient_delete": "حذف بیمار",
    "patient_code": "تغییر کد بیمار",
    "document_delete": "حذف مدرک",
    "full_zip": "دریافت فایل کامل (zip)",
    "csv_import": "ورود بیماران از CSV",
    "manage_users": "مدیریت کاربران و دسترسی‌ها",
    "audit_log": "گزارش رویدادها",
    "stock_adjust": "اصلاح موجودی و ضایعات",
    "finance_settings": "تنظیمات مالی و قیمت‌ها",
    "price_override": "تغییر قیمت در صورتحساب",
    "sms_bulk": "ارسال پیامک گروهی",
    "sms_key": "کلید پیامک و هشدار اعتبار",
    "layout": "تنظیم فرم بیمار",
}


def _all() -> dict[str, Any]:
    out: dict[str, Any] = {a: AREA_MAX[a] for a in AREAS}
    out["flags"] = list(FLAGS)
    return out


PRESETS: dict[str, dict[str, Any]] = {
    "admin": {"label": "مدیر", "perms": _all()},
    "staff": {
        "label": "کارمند",
        "perms": {
            "patients": EDIT, "documents": EDIT, "visits": EDIT, "storage": VIEW, "finance": NONE,
            "sms": EDIT, "pdf": VIEW, "data": NONE, "users": NONE, "flags": ["document_delete"],
        },
    },
}


def owner_perms() -> dict[str, Any]:
    return parse_perms(_all())


def perms_from_body(data: dict[str, Any]) -> dict[str, Any]:
    """The permission editor's JSON: {areas: {area: level}, flags: [..]} or a flat perms object."""
    areas = data.get("areas") if isinstance(data.get("areas"), dict) else data
    raw: dict[str, Any] = {a: areas.get(a) for a in AREAS} if isinstance(areas, dict) else {}
    raw["flags"] = data.get("flags") if isinstance(data.get("flags"), list) else []
    return parse_perms(raw)


def can(user: Any, area: str, level: int = VIEW) -> bool:
    perms = getattr(user, "perms", None)
    return perms is not None and bool(perms) and int(perms.get(area, 0)) >= level


def has(user: Any, flag: str) -> bool:
    perms = getattr(user, "perms", None)
    return perms is not None and bool(perms) and flag in perms.get("flags", [])


def describe_perms(p: dict[str, Any]) -> str:
    return " ".join([*(f"{a}={p[a]}" for a in AREAS), *(f"+{f}" for f in p["flags"])])


def preset_of(p: dict[str, Any]) -> str | None:
    key = describe_perms(p)
    for name, preset in PRESETS.items():
        if describe_perms(parse_perms(preset["perms"])) == key:
            return name
    return None


def role_label(owner: bool, p: dict[str, Any]) -> str:
    if owner:
        return "مالک"
    name = preset_of(p)
    return PRESETS[name]["label"] if name else "سفارشی"
