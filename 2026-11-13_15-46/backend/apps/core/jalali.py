"""Jalali calendar and Tehran time, ported from src/lib/jalali.js and jalaali-js.

Pure Python: no Django import, no clock read. Functions take a `datetime.date` or an aware
`datetime`; the only place an ISO string enters is parse_iso_date. Truncating division (trunc_div,
trunc_mod) reproduces the JavaScript `~~` used by jalaali-js and jalali-math.js, including for
negative Jalali years. Storage timestamps are read by apps.core.legacy_time, not here. Time zone:
zoneinfo Asia/Tehran.

ICU (Intl) differs from jalaali-js on 366 days, Jalali 1503 (quirk row 16); this port follows
jalaali-js.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import NamedTuple
from zoneinfo import ZoneInfo

from .text import FA_DIGITS, js_trim, to_ascii_digits

TEHRAN = ZoneInfo("Asia/Tehran")

JALALI_MONTHS: tuple[str, ...] = (
    "فروردین",
    "اردیبهشت",
    "خرداد",
    "تیر",
    "مرداد",
    "شهریور",
    "مهر",
    "آبان",
    "آذر",
    "دی",
    "بهمن",
    "اسفند",
)
# Indexed by the JavaScript getUTCDay() value: 0 is Sunday.
WEEKDAYS_BY_JS_DAY: tuple[str, ...] = (
    "یکشنبه",
    "دوشنبه",
    "سه‌شنبه",
    "چهارشنبه",
    "پنجشنبه",
    "جمعه",
    "شنبه",
)

_BREAKS: tuple[int, ...] = (
    -61,
    9,
    38,
    199,
    426,
    686,
    756,
    818,
    1111,
    1181,
    1210,
    1635,
    2060,
    2097,
    2192,
    2262,
    2324,
    2394,
    2456,
    3178,
)
_JALALI_MIN = -61
_JALALI_MAX = 3177
_PARSE = re.compile(r"(\d{4})[/.\-](\d{1,2})[/.\-](\d{1,2})", re.ASCII)
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}", re.ASCII)
_FA_DOT = re.compile(r"(\d)\.(?=\d)", re.ASCII)
_FA_MAP = {ord(str(i)): FA_DIGITS[i] for i in range(10)}


class JalaliDate(NamedTuple):
    jy: int
    jm: int
    jd: int


class DayParts(NamedTuple):
    weekday: str
    day: str
    month: str
    year: str


class JalaliMonth(NamedTuple):
    start: date
    end: date
    jy: int
    jm: int


def trunc_div(a: int, b: int) -> int:
    """Integer division truncated toward zero (JavaScript ~~(a / b))."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


def trunc_mod(a: int, b: int) -> int:
    """Remainder with the sign of the dividend (JavaScript a - ~~(a / b) * b)."""
    return a - trunc_div(a, b) * b


def _fa(text: str) -> str:
    return text.translate(_FA_MAP)


def _pad2(n: int) -> str:
    return str(n).zfill(2)


def _jal_cal(jy: int) -> tuple[int, int, int]:
    """(leap, gy, march) for a Jalali year, as jalaali-js computes them."""
    gy = jy + 621
    leap_j = -14
    jp = _BREAKS[0]
    jm = 0
    jump = 0
    for i in range(1, len(_BREAKS)):
        jm = _BREAKS[i]
        jump = jm - jp
        if jy < jm:
            break
        leap_j = leap_j + trunc_div(jump, 33) * 8 + trunc_div(trunc_mod(jump, 33), 4)
        jp = jm
    n = jy - jp
    leap_j = leap_j + trunc_div(n, 33) * 8 + trunc_div(trunc_mod(n, 33) + 3, 4)
    if trunc_mod(jump, 33) == 4 and jump - n == 4:
        leap_j += 1
    leap_g = trunc_div(gy, 4) - trunc_div((trunc_div(gy, 100) + 1) * 3, 4) - 150
    march = 20 + leap_j - leap_g
    if jump - n < 6:
        n = n - jump + trunc_div(jump + 4, 33) * 33
    leap = trunc_mod(trunc_mod(n + 1, 33) - 1, 4)
    if leap == -1:
        leap = 4
    return leap, gy, march


def _g2d(gy: int, gm: int, gd: int) -> int:
    d = trunc_div((gy + trunc_div(gm - 8, 6) + 100100) * 1461, 4)
    d += trunc_div(153 * trunc_mod(gm + 9, 12) + 2, 5) + gd - 34840408
    return d - trunc_div(trunc_div(gy + 100100 + trunc_div(gm - 8, 6), 100) * 3, 4) + 752


def _d2g(jdn: int) -> tuple[int, int, int]:
    j = 4 * jdn + 139361631
    j = j + trunc_div(trunc_div(4 * jdn + 183187720, 146097) * 3, 4) * 4 - 3908
    i = trunc_div(trunc_mod(j, 1461), 4) * 5 + 308
    gd = trunc_div(trunc_mod(i, 153), 5) + 1
    gm = trunc_mod(trunc_div(i, 153), 12) + 1
    gy = trunc_div(j, 1461) - 100100 + trunc_div(8 - gm, 6)
    return gy, gm, gd


def _j2d(jy: int, jm: int, jd: int) -> int:
    _, gy, march = _jal_cal(jy)
    return _g2d(gy, 3, march) + (jm - 1) * 31 - trunc_div(jm, 7) * (jm - 7) + jd - 1


def _d2j(jdn: int) -> tuple[int, int, int]:
    jy = _d2g(jdn)[0] - 621
    leap, gy, march = _jal_cal(jy)
    k = jdn - _g2d(gy, 3, march)
    if k >= 0:
        if k <= 185:
            return jy, 1 + trunc_div(k, 31), trunc_mod(k, 31) + 1
        k -= 186
    else:
        jy -= 1
        k += 179
        if leap == 1:
            k += 1
    return jy, 7 + trunc_div(k, 30), trunc_mod(k, 30) + 1


def jalali_month_length(jy: int, jm: int) -> int:
    """Days in a Jalali month; Esfand has 30 days in a leap year."""
    if jm <= 6:
        return 31
    if jm <= 11:
        return 30
    return 30 if _jal_cal(jy)[0] == 0 else 29


def is_leap_jalali_year(jy: int) -> bool:
    return jalali_month_length(jy, 12) == 30


def parse_iso_date(text: str) -> date:
    """The only entry for an ISO date string: 'YYYY-MM-DD', ASCII, a real calendar date.

    Raises ValueError for anything else (quirk row 18: the legacy code accepted lenient ISO text).
    """
    if not isinstance(text, str) or not _ISO_DATE.fullmatch(text):
        raise ValueError(f"not a valid YYYY-MM-DD date: {text}")
    try:
        return date(int(text[0:4]), int(text[5:7]), int(text[8:10]))
    except ValueError:
        raise ValueError(f"not a valid YYYY-MM-DD date: {text}") from None


def to_jalaali(day: date) -> JalaliDate:
    """Gregorian date to Jalali. Raises ValueError outside jalaali-js's supported range."""
    jdn = _g2d(day.year, day.month, day.day)
    jy, jm, jd = _d2j(jdn)
    if jy < _JALALI_MIN or jy > _JALALI_MAX:
        raise ValueError(
            f"Invalid Julian Day number {jdn}: outside the supported Jalaali range "
            f"[{_JALALI_MIN}, {_JALALI_MAX}]"
        )
    return JalaliDate(jy, jm, jd)


def to_gregorian(jy: int, jm: int, jd: int) -> date:
    gy, gm, gd = _d2g(_j2d(jy, jm, jd))
    return date(gy, gm, gd)


def parse_jalali(text: str | None) -> date | None:
    """'1403/05/12', '۱۴۰۳-۵-۱۲' or '1403.05.12' -> the Gregorian date.

    None when empty or not a real date in 1200..1600.
    """
    s = js_trim(to_ascii_digits("" if text is None else str(text)))
    m = _PARSE.fullmatch(s)
    if not m:
        return None
    jy, jm, jd = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not 1200 <= jy <= 1600:
        return None
    if not (1 <= jm <= 12 and 1 <= jd <= jalali_month_length(jy, jm)):
        return None
    return to_gregorian(jy, jm, jd)


def parse_gregorian(text: str | None) -> date | None:
    """'2026/11/15', '۲۰۲۶-۱۱-۱۵' or '2026.11.15' (Gregorian) -> the date.

    None when empty or not a real date in 1821..2221 (the Gregorian span of Jalali 1200..1600).
    """
    s = js_trim(to_ascii_digits("" if text is None else str(text)))
    m = _PARSE.fullmatch(s)
    if not m:
        return None
    gy, gm, gd = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not 1821 <= gy <= 2221:
        return None
    try:
        return date(gy, gm, gd)
    except ValueError:
        return None


def to_jalali_input(day: date) -> str:
    """A date as the form shows it: '1403/05/12' (ASCII digits)."""
    jy, jm, jd = to_jalaali(day)
    return f"{jy}/{_pad2(jm)}/{_pad2(jd)}"


def format_jalali(day: date, style: str = "long") -> str:
    """A date as text: '۱۲ مرداد ۱۴۰۳' (long) or '۱۴۰۳/۰۵/۱۲' (short)."""
    jy, jm, jd = to_jalaali(day)
    if style == "short":
        return _fa(f"{jy}/{_pad2(jm)}/{_pad2(jd)}")
    return _fa(f"{jd} {JALALI_MONTHS[jm - 1]} {jy}")


def _js_day(day: date) -> int:
    """JavaScript getUTCDay() of a Gregorian date: 0 Sunday .. 6 Saturday."""
    return (day.weekday() + 1) % 7


def day_parts(day: date) -> DayParts:
    """Persian text parts of a date, for date headers."""
    jy, jm, jd = to_jalaali(day)
    return DayParts(
        weekday=WEEKDAYS_BY_JS_DAY[_js_day(day)],
        day=_fa(str(jd)),
        month=JALALI_MONTHS[jm - 1],
        year=_fa(str(jy)),
    )


def add_days(day: date, n: int) -> date:
    """Add n days to a date."""
    return day + timedelta(days=n)


def week_start(day: date) -> date:
    """The Saturday that starts the Iranian week holding day."""
    return add_days(day, -((_js_day(day) + 1) % 7))


def jalali_month(day: date, shift: int = 0) -> JalaliMonth:
    """First and last day of the Jalali month holding day; shift moves that many months."""
    jalali = to_jalaali(day)
    jy, jm = jalali.jy, jalali.jm + shift
    while jm < 1:
        jm += 12
        jy -= 1
    while jm > 12:
        jm -= 12
        jy += 1
    return JalaliMonth(
        start=to_gregorian(jy, jm, 1),
        end=to_gregorian(jy, jm, jalali_month_length(jy, jm)),
        jy=jy,
        jm=jm,
    )


def age_from(birth: date, today: date) -> int:
    """Full years between a birth date and `today` (passed in, never the clock)."""
    age = today.year - birth.year
    if (today.month, today.day) < (birth.month, birth.day):
        age -= 1
    return age


def fa_digits(text: str | None) -> str:
    """Persian digits for display; a dot between digits becomes the Persian decimal sign."""
    s = _FA_DOT.sub("\\1٫", "" if text is None else str(text))
    return s.translate(_FA_MAP)


def local_day(moment: datetime) -> date:
    """The Tehran calendar day of an aware moment."""
    if moment.tzinfo is None:
        raise ValueError("local_day needs an aware datetime")
    return moment.astimezone(TEHRAN).date()


def format_jalali_datetime(moment: datetime | date | None) -> str:
    """A moment in Tehran time as '۱۴۰۵/۰۷/۲۴ ۱۱:۴۵'. None gives ''.

    A date (no time) is its midnight in Tehran. Any other type raises TypeError.
    """
    if moment is None:
        return ""
    if isinstance(moment, datetime):
        if moment.tzinfo is None:
            raise ValueError("format_jalali_datetime needs an aware datetime")
        local = moment.astimezone(TEHRAN)
    elif isinstance(moment, date):
        local = datetime(moment.year, moment.month, moment.day, tzinfo=TEHRAN)
    else:
        raise TypeError(f"expected date, datetime or None, not {type(moment).__name__}")
    jalali = to_jalaali(local.date())
    text = (
        f"{jalali.jy}/{_pad2(jalali.jm)}/{_pad2(jalali.jd)} "
        f"{_pad2(local.hour)}:{_pad2(local.minute)}"
    )
    return _fa(text)
