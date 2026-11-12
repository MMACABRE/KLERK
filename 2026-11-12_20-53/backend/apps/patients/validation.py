"""The patient form's rules (legacy src/lib/patient-form.js). Returns (values, errors)."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from django.utils import timezone

from apps.core.jalali import parse_jalali
from apps.core.text import normalize_text

STATUSES = ["active", "pending", "critical", "archived"]
SEXES = ["female", "male"]
BLOOD_TYPES = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
TEXT_FIELDS = {
    "father_name": 80, "city": 100, "emergency_name": 100, "emergency_relation": 60, "insurance_name": 100,
    "insurance_number": 60, "blood_pressure": 20, "referral": 120,
}
LONG_TEXT_FIELDS = {"address": 2000, "medical_notes": 5000, "visit_reason": 1000}
FORM_FIELDS = [
    "first_name", "last_name", "father_name", "national_id", "birth_date", "sex", "phone", "email", "address", "city",
    "emergency_name", "emergency_phone", "emergency_relation", "insurance_name", "insurance_number", "status",
    "visit_reason", "referral", "blood_type", "allergies", "conditions", "medical_notes", "height_cm", "weight_kg",
    "blood_pressure",
]


def _get(body: dict[str, Any], key: str) -> str:
    v = body.get(key)
    if v is None or isinstance(v, (list, dict)):
        return ""
    if isinstance(v, bool):
        v = "1" if v else ""
    return normalize_text(str(v))


def validate_patient(body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    errors: dict[str, str] = {}
    values: dict[str, Any] = {}
    for field, label in (("first_name", "نام"), ("last_name", "نام خانوادگی")):
        v = _get(body, field)
        if not v:
            errors[field] = f"{label} را وارد کنید."
        elif len(v) > 80:
            errors[field] = f"{label} بیش از حد طولانی است."
        values[field] = v

    nid = _get(body, "national_id")
    if nid and not re.fullmatch(r"\d{10}", nid, re.ASCII):
        errors["national_id"] = "کد ملی باید ۱۰ رقم باشد."
    values["national_id"] = nid or None

    for field in ("phone", "emergency_phone"):
        v = re.sub(r"[\s-]", "", _get(body, field))
        if v and not re.fullmatch(r"\+?\d{7,15}", v, re.ASCII):
            errors[field] = "شماره تلفن معتبر نیست."
        values[field] = v or None

    email = _get(body, "email")
    if email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        errors["email"] = "نشانی ایمیل معتبر نیست."
    values["email"] = email or None

    raw_date = _get(body, "birth_date")
    if raw_date:
        iso = parse_jalali(raw_date)
        if iso is None:
            errors["birth_date"] = "تاریخ را به شکل ۱۴۰۳/۰۵/۱۲ وارد کنید."
        elif iso > timezone.localdate():
            errors["birth_date"] = "تاریخ تولد نمی‌تواند در آینده باشد."
        values["birth_date"] = iso
    else:
        values["birth_date"] = None

    sex = _get(body, "sex")
    if sex and sex not in SEXES:
        errors["sex"] = "جنسیت نامعتبر است."
    values["sex"] = sex or None

    status = _get(body, "status") or "active"
    if status not in STATUSES:
        errors["status"] = "وضعیت نامعتبر است."
    values["status"] = status

    if _get(body, "sms_optout_form") == "1":
        values["sms_optout"] = _get(body, "sms_optout") in ("1", "true", "on")

    blood = _get(body, "blood_type")
    if blood and blood not in BLOOD_TYPES:
        errors["blood_type"] = "گروه خونی نامعتبر است."
    values["blood_type"] = blood or None

    for field, label, lo, hi in (("height_cm", "قد", 30, 250), ("weight_kg", "وزن", 1, 500)):
        raw = re.sub("[٫,]", ".", _get(body, field))
        n = Decimal(raw) if re.fullmatch(r"\d{1,3}(\.\d{1,2})?", raw, re.ASCII) else None
        if raw and not (n is not None and lo <= n <= hi):
            errors[field] = f"{label} باید عددی بین {lo} و {hi} باشد."
        values[field] = n if raw and field not in errors else None

    for field, limit in {**TEXT_FIELDS, **LONG_TEXT_FIELDS}.items():
        v = _get(body, field)
        if len(v) > limit:
            errors[field] = "متن بیش از حد طولانی است."
        values[field] = v or None

    for field in ("allergies", "conditions"):
        items = [s.strip() for s in re.split("[,،]", _get(body, field))]
        joined = ", ".join(s for s in items if s)
        if len(joined) > 1000:
            errors[field] = "فهرست بیش از حد طولانی است."
        values[field] = joined or None
    return values, errors
