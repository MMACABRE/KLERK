"""Money in whole Rial, ported from src/lib/money.js and src/lib/bill.js.

Legacy quirks are kept unless docs/legacy-quirks.md lists a change. Display and arithmetic take
typed input: an int Rial (anything else raises TypeError). Only the text parsers read user text.
Toman display uses integer rounding half away from zero, which equals Math.round on the magnitude.
Line totals keep the legacy float rounding, so historical bills recompute to the same Rial.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from decimal import Decimal

from .jsnum import is_integer, is_safe_integer, js_round
from .text import WS_RE, js_trim, to_ascii_digits

# 1e14, the legacy MAX_RIAL: far beyond any bill; every sum stays a safe integer.
MAX_RIAL = 100_000_000_000_000
_PERCENT_SIGN = "٪"
_PERCENT_ERROR = "درصد تخفیف باید عددی صحیح از ۰ تا ۱۰۰ باشد."
_AMOUNT_ERROR = "مبلغ تخفیف درست نیست."
_LIST_ERROR = "مقدار تخفیف درست نیست."

_GROUPED = re.compile(r"\d{1,3}(?:[,،٬]\d{3})+(?:t|r|تومان|ریال)?", re.IGNORECASE | re.ASCII)
_SEPARATORS = re.compile(r"[,،٬]")
_PLAIN = re.compile(r"(\d+)(t|r|تومان|ریال)?", re.IGNORECASE | re.ASCII)
_TOMAN_SUFFIX = re.compile(r"t|تومان", re.IGNORECASE | re.ASCII)
# A percent as legacy Number() reads a plain decimal: sign, digits, optional '.'. Exponent and
# radix forms (1e2, 0x10, 0o, 0b) and words (Infinity, NaN) do not match, so they are refused.
_PERCENT_NUMBER = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)", re.ASCII)
_DISCOUNT_NOISE = re.compile("[%٪]")


def _int_arg(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int Rial, not {type(value).__name__}")
    return value


def _opt_int(name: str, value: object) -> int | None:
    if value is None:
        return None
    return _int_arg(name, value)


def _float_arg(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number, not {type(value).__name__}")
    return float(value)


def format_money(rial: int, cur: str = "T") -> str:
    """Rial -> display text such as '1,250,000 T'.

    Toman rounds half away from zero; -1..-4 read '-0 T'.
    """
    n = _int_arg("rial", rial)
    if cur == "R":
        return f"{n:,} R"
    sign = "-" if n < 0 else ""
    return f"{sign}{(abs(n) + 5) // 10:,} T"


def money_input(rial: int, cur: str = "T") -> str:
    """Rial -> the number a form field shows.

    Whole Toman as a number; otherwise Rial with an R suffix.
    """
    n = _int_arg("rial", rial)
    if cur == "R":
        return str(n)
    if n % 10 != 0:
        return f"{n}R"
    return str(n // 10)


def parse_money(text: str | Sequence[str] | None, cur: str = "T") -> int | None:
    """User text -> Rial integer, or None when empty or not a whole non-negative amount."""
    if isinstance(text, (list, tuple)):
        return None
    s = to_ascii_digits("" if text is None else str(text))
    s = WS_RE.sub("", s)
    if _SEPARATORS.search(s) and not _GROUPED.fullmatch(s):
        return None
    s = _SEPARATORS.sub("", s)
    if not s:
        return None
    m = _PLAIN.fullmatch(s)
    if not m:
        return None
    digits, suffix = m.group(1), m.group(2)
    unit = cur
    if suffix:
        unit = "T" if _TOMAN_SUFFIX.fullmatch(suffix) else "R"
    n = float(digits) * (1 if unit == "R" else 10)
    if is_safe_integer(n) and n <= MAX_RIAL:
        return int(n)
    return None


def parse_discount(
    kind: str, text: str | Sequence[str] | None, cur: str = "T"
) -> dict[str, object] | None:
    """A typed discount: {'kind', 'value'}, None for no discount, or {'error': message}.

    A percent reads as legacy Number() does, except exponent and radix forms, which are refused
    (deliberate divergence, quirk row 5).
    """
    if isinstance(text, (list, tuple)):
        return {"error": _LIST_ERROR}
    raw = js_trim("" if text is None else str(text))
    if not raw or raw == "0":
        return None
    if kind == "percent":
        digits = WS_RE.sub("", _DISCOUNT_NOISE.sub("", to_ascii_digits(raw)))
        if _PERCENT_NUMBER.fullmatch(digits):
            p = float(digits)
            if is_integer(p) and 0 <= p <= 100:
                return {"kind": "percent", "value": int(p)} if p else None
        return {"error": _PERCENT_ERROR}
    rial = parse_money(raw, cur)
    if rial is None:
        return {"error": _AMOUNT_ERROR}
    return {"kind": "amount", "value": rial} if rial else None


def discount_of(gross: int, kind: str | None, value: int | None) -> int:
    """How much a discount takes off gross (Rial).

    Percent is one float path (the legacy operations) rounded half up with js_round.
    Never more than gross.
    """
    g = _int_arg("gross", gross)
    v = _opt_int("value", value)
    if not kind or not v or g <= 0:
        return 0
    if kind == "percent":
        d = int(js_round(float(g) * float(v) / 100.0))
    else:
        d = v
    return min(max(d, 0), g)


def describe_discount(kind: str | None, value: int | None, cur: str = "T") -> str:
    """Short text for a discount, e.g. '10٪' or '50,000 T'."""
    v = _opt_int("value", value)
    if not kind or not v:
        return ""
    if kind == "percent":
        return f"{v}{_PERCENT_SIGN}"
    return format_money(v, cur)


def line_gross(price: int, qty: float) -> int:
    """A bill line before discount: price times quantity, float-rounded (src/lib/bill.js:16).

    The caller passes the effective price (override_price when set, else unit_price).
    """
    p = _int_arg("price", price)
    q = _float_arg("qty", qty)
    return int(js_round(float(p) * q))


def line_too_large(price: int, qty: float) -> bool:
    """A line above the money limit is refused (src/lib/bill.js:20)."""
    return line_gross(price, qty) > MAX_RIAL


def rial(value: object) -> int:
    """An aggregate or database value as a Rial int. Never rounds.

    int passes; an integral Decimal becomes int; a fractional or non-finite Decimal
    raises ValueError; bool and any other type raise TypeError.
    """
    if isinstance(value, bool):
        raise TypeError("rial() takes int or Decimal, not bool")
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError(f"not a whole Rial amount: {value}")
        # Zero is whole whatever its exponent (Decimal("0E+20") has adjusted() 20).
        if value.is_zero():
            return 0
        # Refused before any conversion: no integer of 19 digits or more is built.
        if value.adjusted() >= 19:
            raise ValueError(f"Rial amount outside BIGINT: {value}")
        if value != value.to_integral_value():
            raise ValueError(f"not a whole Rial amount: {value}")
        number = int(value)
    elif isinstance(value, int):
        number = value
    else:
        raise TypeError(f"rial() takes int or Decimal, not {type(value).__name__}")
    if not -(2**63) <= number <= 2**63 - 1:
        raise ValueError(f"Rial amount outside BIGINT: {number}")
    return number
