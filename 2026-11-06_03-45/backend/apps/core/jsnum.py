"""JavaScript number rules that the legacy code relies on, reproduced exactly.

The legacy functions run on JavaScript numbers (IEEE doubles). The helpers here give the same
results: Math.round (ties toward +infinity, -0 kept), Number.isInteger and Number.isSafeInteger.
Text rules (trim, whitespace, digits, case) live in apps.core.text.
"""

from __future__ import annotations

import math

MAX_SAFE_INTEGER = 9007199254740991


def js_round(x: float) -> float:
    """Math.round: ties toward +infinity; a zero result from a negative x is -0."""
    if not math.isfinite(x):
        return x
    floor = math.floor(x)
    result = float(floor + 1) if x - floor >= 0.5 else float(floor)
    if result == 0.0 and (x < 0.0 or math.copysign(1.0, x) < 0.0):
        return -0.0
    return result


def is_integer(x: float) -> bool:
    """Number.isInteger."""
    return math.isfinite(x) and x == math.floor(x)


def is_safe_integer(x: float) -> bool:
    """Number.isSafeInteger."""
    return math.isfinite(x) and x == math.floor(x) and abs(x) <= MAX_SAFE_INTEGER
