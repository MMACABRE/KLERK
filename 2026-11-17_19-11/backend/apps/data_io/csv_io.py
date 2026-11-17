"""CSV for patient exports and imports (legacy src/lib/csv.js). Exports are UTF-8 with a BOM."""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from typing import Any

from apps.core.jalali import local_day, to_jalali_input
from apps.core.labels import SEX, STATUS
from apps.core.text import fa_key, normalize_text, to_ascii_digits

BOM = "﻿"

COLUMNS: list[tuple[str, str]] = [
    ("code", "کد بیمار"),
    ("national_id", "کد ملی"),
    ("first_name", "نام"),
    ("last_name", "نام خانوادگی"),
    ("father_name", "نام پدر"),
    ("birth_date", "تاریخ تولد"),
    ("sex", "جنسیت"),
    ("phone", "تلفن"),
    ("email", "ایمیل"),
    ("address", "نشانی"),
    ("city", "شهر"),
    ("emergency_name", "نام تماس اضطراری"),
    ("emergency_phone", "تلفن تماس اضطراری"),
    ("emergency_relation", "نسبت تماس اضطراری"),
    ("insurance_name", "بیمه"),
    ("insurance_number", "شماره بیمه"),
    ("status", "وضعیت"),
    ("visit_reason", "علت مراجعه"),
    ("referral", "معرف"),
    ("blood_type", "گروه خونی"),
    ("allergies", "حساسیت‌ها"),
    ("conditions", "بیماری‌ها"),
    ("medical_notes", "یادداشت پزشکی"),
    ("height_cm", "قد (سانتی‌متر)"),
    ("weight_kg", "وزن (کیلوگرم)"),
    ("blood_pressure", "فشار خون"),
    ("updated_at", "آخرین تغییر"),
]
TEMPLATE_FIELDS = ["code", "national_id", "first_name", "last_name", "father_name", "birth_date", "sex", "phone",
                   "city", "allergies", "conditions"]
HEADER_OF = dict(COLUMNS)

MAX_CSV_BYTES = 5 * 1024 * 1024
MAX_CSV_ROWS = 5000

_FORMULA = re.compile(r"^[=+\-@\t\r]")
_NUMBERISH = re.compile(r"^[+-]?\d[\d\s.\-]*$")


def safe_cell(value: Any) -> str:
    if value is None:
        return ""
    s = str(value)
    if _FORMULA.match(s) and not _NUMBERISH.match(s):
        return f"'{s}"
    return s


def _quote(s: str) -> str:
    return '"' + s.replace('"', '""') + '"' if re.search(r'[",\r\n]', s) else s


def to_csv(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [",".join(_quote(safe_cell(h)) for h in headers)]
    lines.extend(",".join(_quote(safe_cell(c)) for c in row) for row in rows)
    return BOM + "\r\n".join(lines) + "\r\n"


def _cell(field: str, row: dict[str, Any]) -> Any:
    v = row.get(field)
    if v is None:
        return ""
    if field == "birth_date" and isinstance(v, date):
        return to_jalali_input(v)
    if field == "updated_at" and isinstance(v, datetime):
        return to_jalali_input(local_day(v))
    if field == "sex":
        return SEX.get(v, v)
    if field == "status":
        return STATUS.get(v, {}).get("label", v)
    if hasattr(v, "normalize") and not isinstance(v, str):  # Decimal height/weight: 172.00 -> 172
        return format(v.normalize(), "f")
    return v


def patient_table(
    rows: list[dict[str, Any]], extra: list[tuple[str, str]] | None = None
) -> tuple[list[str], list[list[Any]]]:
    extra = extra or []
    fields = [f for f, _ in COLUMNS]
    headers = [h for _, h in COLUMNS] + [h for _, h in extra]
    body = [[_cell(f, r) for f in fields] + [r.get(k, "") for k, _ in extra] for r in rows]
    return headers, body


def patients_csv(rows: list[dict[str, Any]], extra: list[tuple[str, str]] | None = None) -> str:
    return to_csv(*patient_table(rows, extra))


def template_csv(custom_headers: list[str]) -> str:
    return to_csv(
        [HEADER_OF[f] for f in TEMPLATE_FIELDS] + custom_headers,
        [["", "0012345678", "سارا", "احمدی", "محمد", "1368/04/12", "زن", "09121234567", "تهران", "پنی‌سیلین", "دیابت",
          *["" for _ in custom_headers]]],
    )


FIELD_OF_HEADER: dict[str, str] = {**{fa_key(h): f for f, h in COLUMNS}, **{fa_key(f): f for f, _ in COLUMNS}}


def reserved_header_keys() -> set[str]:
    return set(FIELD_OF_HEADER)


def _reverse(labels: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in labels.items():
        out[fa_key(k)] = k
        out[fa_key(v if isinstance(v, str) else v["label"])] = k
    return out


SEX_IN = _reverse(SEX)
STATUS_IN = _reverse(STATUS)


class CsvError(Exception):
    pass


def _restore_zeros(body: dict[str, Any]) -> None:
    def digits(v: Any) -> str:
        return to_ascii_digits(str(v or "")).strip()

    nid = digits(body.get("national_id"))
    if re.fullmatch(r"\d{8,9}", nid):
        body["national_id"] = nid.rjust(10, "0")
    for field in ("phone", "emergency_phone"):
        phone = digits(body.get(field))
        if re.fullmatch(r"[1-9]\d{9}", phone):
            body[field] = f"0{phone}"


def _delimiter(text: str) -> str:
    head = re.split(r"\r?\n", text[:4096])[0]
    return max([",", ";", "\t"], key=lambda d: (len(head.split(d)), -[",", ";", "\t"].index(d)))


def parse_patient_csv(raw: bytes, custom: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """[{line, body}] with patient form field names. custom: fa_key(box name) -> 'c<id>'."""
    custom = custom or {}
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise CsvError("فایل CSV خوانده نشد. فایل را با الگوی سامانه بسازید و با کدگذاری UTF-8 ذخیره کنید.") from None
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=_delimiter(text))
    try:
        header = next(reader, None)
        if header is None:
            return []
        fields = [FIELD_OF_HEADER.get(fa_key(h.strip())) or custom.get(fa_key(h.strip())) for h in header]
        for i, f in enumerate(fields):
            if f and fields.index(f) != i:
                raise CsvError(f"ستون «{header[i].strip()[:40]}» دو بار آمده است. هر ستون فقط یک بار مجاز است.")
        out: list[dict[str, Any]] = []
        for record in reader:
            if not any(c.strip() for c in record):
                continue
            if len(out) >= MAX_CSV_ROWS:
                raise CsvError(f"حداکثر {MAX_CSV_ROWS} ردیف در هر بار ورود مجاز است.")
            body: dict[str, Any] = {}
            for i, value in enumerate(record):
                f = fields[i] if i < len(fields) else None
                if not f or f == "updated_at":
                    continue
                v = value.strip()
                body[f] = v[1:] if re.match(r"^'[=+\-@]", v) else v
            _restore_zeros(body)
            if body.get("sex"):
                body["sex"] = SEX_IN.get(fa_key(normalize_text(body["sex"])), body["sex"])
            if body.get("status"):
                body["status"] = STATUS_IN.get(fa_key(normalize_text(body["status"])), body["status"])
            out.append({"line": reader.line_num, "body": body})
        return out
    except csv.Error:
        raise CsvError("فایل CSV خوانده نشد. فایل را با الگوی سامانه بسازید و با کدگذاری UTF-8 ذخیره کنید.") from None
