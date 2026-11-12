"""Quantities (pieces, up to two decimal places), ported from src/lib/qty.js. Pure Python.

Rounding goes through js_round (Math.round), so 1.005 rounds to 1 exactly as the legacy app does.
Deliberate divergence (quirk row 8): a comma group with a leading zero ('0,500') is refused.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from decimal import Decimal

from .jsnum import js_round
from .text import WS_RE, to_ascii_digits

MAX_QTY = 1_000_000

_THOUSANDS = re.compile(r"\d{1,3}(?:,\d{3})+", re.ASCII)
_DECIMAL_SEP = re.compile(r"(\d*)[.٫/,،](\d+)", re.ASCII)
_QTY = re.compile(r"(?:\d{1,7}(?:\.\d{1,2})?|\.\d{1,2})", re.ASCII)
_THOUSANDS_SEP = re.compile("٬")  # Persian thousands separator, dropped before parsing


def round_qty(n: float = 0.0) -> float:
    """Round to two decimal places, as Math.round((Number(n) || 0) * 100) / 100."""
    if isinstance(n, bool) or not isinstance(n, (int, float)):
        raise TypeError(f"n must be a number, not {type(n).__name__}")
    v = float(n)
    if math.isnan(v) or v == 0.0:
        v = 0.0
    return js_round(v * 100.0) / 100.0


def parse_qty(text: str | Sequence[str] | None, allow_zero: bool = False) -> float | None:
    """A quantity typed in a form.

    None for empty; NaN for junk, out of range or a leading-zero group; else the rounded value.
    """
    if isinstance(text, (list, tuple)):
        return math.nan
    s = to_ascii_digits("" if text is None else str(text))
    s = WS_RE.sub("", _THOUSANDS_SEP.sub("", s))
    if not s:
        return None
    if _THOUSANDS.fullmatch(s):
        if s[0] == "0":
            return math.nan
        s = s.replace(",", "")
    else:
        m = _DECIMAL_SEP.fullmatch(s)
        if m:
            s = f"{m.group(1)}.{m.group(2)}"
    if not _QTY.fullmatch(s):
        return math.nan
    n = round_qty(float(s))
    ok = (n >= 0 if allow_zero else n > 0) and n <= MAX_QTY
    return n if ok else math.nan


def qty_from_db(value: object) -> float:
    """The one point where a stored quantity (DECIMAL(12,2), read as Decimal) becomes a float in
    Python.

    Values are exact to two decimals in the database, so the float is the nearest double to that
    decimal.
    """
    if isinstance(value, bool) or not isinstance(value, (Decimal, int)):
        raise TypeError(f"a stored quantity is a Decimal or int, not {type(value).__name__}")
    if isinstance(value, Decimal) and value != value.quantize(Decimal("0.01")):
        raise ValueError(f"a stored quantity has more than two decimals: {value}")
    return float(value)
