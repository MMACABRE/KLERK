"""Form and custom-box catalogue (legacy src/lib/layout-catalogue.js): cards, boxes, custom types, limits."""

from __future__ import annotations

import re
from typing import Any

from apps.core.errors import Invalid

CARDS = [
    {"id": "identity", "label": "هویت"},
    {"id": "visit", "label": "مراجعه"},
    {"id": "contact", "label": "تماس و نشانی"},
    {"id": "emergency", "label": "تماس اضطراری"},
    {"id": "insurance", "label": "بیمه"},
    {"id": "medical", "label": "اطلاعات پزشکی"},
]

BOXES = [
    {"id": "first_name", "label": "نام", "card": "identity", "full": False},
    {"id": "last_name", "label": "نام خانوادگی", "card": "identity", "full": False},
    {"id": "father_name", "label": "نام پدر", "card": "identity", "full": False},
    {"id": "national_id", "label": "کد ملی", "card": "identity", "full": False},
    {"id": "birth_date", "label": "تاریخ تولد", "card": "identity", "full": False},
    {"id": "sex", "label": "جنسیت", "card": "identity", "full": False},
    {"id": "status", "label": "وضعیت", "card": "identity", "full": False},
    {"id": "visit_reason", "label": "علت مراجعه", "card": "visit", "full": True},
    {"id": "referral", "label": "معرف", "card": "visit", "full": False},
    {"id": "phone", "label": "تلفن همراه", "card": "contact", "full": False},
    {"id": "email", "label": "ایمیل", "card": "contact", "full": False},
    {"id": "city", "label": "شهر", "card": "contact", "full": False},
    {"id": "sms_optout", "label": "دریافت نکردن پیامک", "card": "contact", "full": False},
    {"id": "address", "label": "نشانی", "card": "contact", "full": True},
    {"id": "emergency_name", "label": "نام", "card": "emergency", "full": False},
    {"id": "emergency_phone", "label": "تلفن", "card": "emergency", "full": False},
    {"id": "emergency_relation", "label": "نسبت", "card": "emergency", "full": False},
    {"id": "insurance_name", "label": "نوع بیمه", "card": "insurance", "full": False},
    {"id": "insurance_number", "label": "شماره بیمه", "card": "insurance", "full": False},
    {"id": "blood_type", "label": "گروه خونی", "card": "medical", "full": False},
    {"id": "blood_pressure", "label": "فشار خون", "card": "medical", "full": False},
    {"id": "height_cm", "label": "قد (سانتی\u200cمتر)", "card": "medical", "full": False},
    {"id": "weight_kg", "label": "وزن (کیلوگرم)", "card": "medical", "full": False},
    {"id": "allergies", "label": "حساسیت\u200cها", "card": "medical", "full": True},
    {"id": "conditions", "label": "بیماری\u200cهای زمینه\u200cای", "card": "medical", "full": True},
    {"id": "medical_notes", "label": "یادداشت\u200cهای بالینی", "card": "medical", "full": True},
]

CUSTOM_TYPES = [
    {"id": "short_text", "label": "متن کوتاه", "full": False},
    {"id": "long_text", "label": "متن بلند", "full": True},
    {"id": "number", "label": "عدد", "full": False},
    {"id": "date", "label": "تاریخ", "full": False},
    {"id": "choice", "label": "انتخاب از فهرست", "full": False},
    {"id": "yes_no", "label": "بله / خیر", "full": False},
]

LIMITS = {
    "cards": 12, "boxes": 80, "json": 64 * 1024, "cardLabel": 40, "boxName": 60, "shortText": 200,
    "longText": 5000, "choicesMin": 2, "choicesMax": 30,
}

CUSTOM_TYPE_IDS = {t["id"] for t in CUSTOM_TYPES}
CARD_IDS = {c["id"] for c in CARDS}
BOX_BY_ID = {b["id"]: b for b in BOXES}
NAME_BOXES = ["first_name", "last_name"]
BAD_SHAPE = "شکل چیدمان درست نیست."

_INVISIBLE_ONLY = re.compile("^[\\s\u200b-\u200f\u2060\ufeff]*$")


class Reject(Invalid):
    """Raised by a strict layout read; the message is the Persian text the editor shows."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message_fa = message


def length(s: str) -> int:
    return len(s)


def is_obj(v: Any) -> bool:
    return isinstance(v, dict)


def has_visible(s: Any) -> bool:
    return not _INVISIBLE_ONLY.match(str(s))
