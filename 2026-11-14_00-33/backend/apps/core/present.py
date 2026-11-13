"""Small JSON shapes shared by the views (SPEC §2.3-§2.6): dates as ISO plus Jalali text, money as Rial plus
display text, quantities as strings plus Persian display."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from apps.core.jalali import day_parts, fa_digits, format_jalali, format_jalali_datetime, to_jalali_input
from apps.core.money import format_money, money_input


def d(value: date | None) -> dict[str, Any] | None:
    if value is None:
        return None
    p = day_parts(value)
    return {"iso": value.isoformat(), "input": to_jalali_input(value), "long": format_jalali(value),
            "short": format_jalali(value, "short"),
            "parts": {"weekday": p.weekday, "day": p.day, "month": p.month, "year": p.year}}


def dt(value: datetime | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {"iso": value.isoformat(), "text": format_jalali_datetime(value)}


def t(value: time | str | None) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) else f"{value.hour:02d}:{value.minute:02d}"


def money(rial: int | None, cur: str) -> dict[str, Any] | None:
    if rial is None:
        return None
    r = int(rial)
    return {"rial": r, "display": format_money(r, cur), "input": money_input(r, cur)}


def qty(value: Decimal | float | int | None) -> dict[str, Any] | None:
    if value is None:
        return None
    dec = Decimal(str(value)).quantize(Decimal("0.01"))
    plain = format(dec.normalize(), "f")
    if plain in ("-0", ""):
        plain = "0"
    return {"value": str(dec), "text": plain, "display": fa_digits(plain)}


def decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    s = format(value.normalize(), "f")
    return "0" if s == "-0" else s
