"""Pure SMS rules (legacy src/lib/sms-rules.js): mobile numbers, wording, parts, when a reminder is due."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

from apps.core.jalali import TEHRAN, day_parts, fa_digits, parse_iso_date
from apps.core.settings_store import DEFAULT_TEMPLATE
from apps.core.text import to_ascii_digits

TOKENS = {"نام": "name", "تاریخ": "date", "ساعت": "time"}
TEMPLATE_MAX = 300
MESSAGE_MAX = 500
LEADS = {"none": "بدون یادآوری", "now": "همین الان", "h2": "۲ ساعت قبل", "d1": "۱ روز قبل", "d2": "۲ روز قبل"}
LEAD_KEYS = list(LEADS)
WINDOW_START = 8 * 60
WINDOW_END = 21 * 60
_CONTROL = re.compile("[\u0000-\u0009\u000b-\u001f\u007f\u200e\u200f\u202a-\u202e\u2066-\u2069]")
_NO_JOIN = re.compile("[رزژدذوا]$")


def normalize_mobile(value: Any) -> str | None:
    s = re.sub(r"[\s\-()]", "", to_ascii_digits("" if value is None else str(value)))
    if s.startswith("+98"):
        s = "0" + s[3:]
    elif s.startswith("0098"):
        s = "0" + s[4:]
    elif re.fullmatch(r"98\d{10}", s, re.ASCII):
        s = "0" + s[2:]
    elif re.fullmatch(r"9\d{9}", s, re.ASCII):
        s = "0" + s
    return s if re.fullmatch(r"09\d{9}", s, re.ASCII) else None


def clean_text(value: Any) -> str:
    s = ("" if value is None else str(value)).replace("ي", "ی").replace("ك", "ک")
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    return _CONTROL.sub("", s).strip()


def validate_template(value: Any) -> tuple[str, str | None]:
    text = clean_text(value)
    if not text:
        return text, "متن پیامک را وارد کنید."
    if len(text) > TEMPLATE_MAX:
        return text, f"متن پیامک نباید بیش از {fa_digits(str(TEMPLATE_MAX))} نویسه باشد."
    for m in re.finditer(r"\{([^{}]*)\}", text):
        if m.group(1) not in TOKENS:
            return text, f"«{{{m.group(1)}}}» شناخته\u200cشده نیست. فقط {{نام}}، {{تاریخ}} و {{ساعت}} مجاز است."
    if re.search(r"[{}]", re.sub(r"\{[^{}]*\}", "", text)):
        return text, "آکولاد باز یا بسته\u200cی بی\u200cجفت در متن هست."
    if "{تاریخ}" not in text or "{ساعت}" not in text:
        return text, "متن یادآوری باید {تاریخ} و {ساعت} را داشته باشد."
    return text, None


def visit_date_text(d: date) -> str:
    p = day_parts(d)
    return f"{p.weekday} {p.day}ام {p.month}{'' if _NO_JOIN.search(p.month) else chr(0x200C)}ماه"


def visit_time_text(t: str) -> str:
    h, m = t.split(":")[:2]
    return fa_digits(f"{int(h)}:{m}")


def render_template(template: str, vars_: dict[str, str]) -> str:
    out = re.sub(r"\{([^{}]*)\}", lambda m: vars_.get(TOKENS[m.group(1)], "") if m.group(1) in TOKENS else m.group(0),
                 str(template))
    return clean_text(out)[:MESSAGE_MAX]


def sms_parts(text: str) -> int:
    n = len(str(text))
    return 0 if n == 0 else 1 if n <= 70 else -(-n // 67)


def minutes_of_day(d: datetime) -> int:
    local = d.astimezone(TEHRAN)
    return local.hour * 60 + local.minute


def in_window(d: datetime) -> bool:
    m = minutes_of_day(d)
    return WINDOW_START <= m <= WINDOW_END


def visit_start(d: date, t: str) -> datetime:
    return datetime(d.year, d.month, d.day, int(t[:2]), int(t[3:5]), tzinfo=TEHRAN)


def pull_into_window(d: datetime) -> datetime:
    m = minutes_of_day(d)
    if WINDOW_START <= m <= WINDOW_END:
        return d
    local = d.astimezone(TEHRAN)
    if m < WINDOW_START:
        local = local - timedelta(days=1)
    return local.replace(hour=21, minute=0, second=0, microsecond=0)


def send_hour_of(v: Any) -> int:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return 17
    return int(n) if n.is_integer() and 8 <= n <= 21 else 17


def reminder_due(lead: str, visit_date: date, visit_time: str, send_hour: int, now: datetime) -> datetime | None:
    if lead == "none" or lead not in LEAD_KEYS:
        return None
    if lead == "now":
        return now
    start = visit_start(visit_date, visit_time)
    if lead == "h2":
        return pull_into_window(start - timedelta(hours=2))
    days = 2 if lead == "d2" else 1
    day = visit_date - timedelta(days=days)
    return datetime(day.year, day.month, day.day, send_hour_of(send_hour), 0, tzinfo=TEHRAN)


def ms(d: datetime) -> int:
    return int(d.timestamp() * 1000)


_ = (DEFAULT_TEMPLATE, parse_iso_date)
