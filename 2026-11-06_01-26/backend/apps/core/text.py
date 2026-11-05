"""Text rules of the legacy app, reproduced exactly: JavaScript whitespace and case, Persian and
Arabic digits, and the key functions of src/lib/normalize.js (normalizeText, faKey) plus the legacy
COLLATE NOCASE key.

Standard library only. The one import from this package is the generated data module js_case_data,
which itself imports nothing. Every table is written as code points, so no invisible character sits
in the source.

Four comparison rules live here, one per legacy site (round 13, quirk rows 19-21):
- js_trim and JS_WHITESPACE: JavaScript's trim and \\s (25 code points), not Python's str.strip.
- js_lower: JavaScript toLowerCase, with final sigma. Not str.lower and not casefold.
- nocase_key: ASCII A-Z folded to a-z only, as the legacy COLLATE NOCASE does. Kelvin sign and
  Persian stay.
- normalize_text and fa_key: the legacy step order.
"""

from __future__ import annotations

import re
import string
import unicodedata
from bisect import bisect_right

from .js_case_data import CASE_IGNORABLE, CASED, LOWER

# JavaScript WhiteSpace and LineTerminator: the set of \s and String.prototype.trim (25 code
# points).
JS_WHITESPACE_CODES: tuple[int, ...] = (
    0x0009,
    0x000A,
    0x000B,
    0x000C,
    0x000D,
    0x0020,
    0x00A0,
    0x1680,
    0x2000,
    0x2001,
    0x2002,
    0x2003,
    0x2004,
    0x2005,
    0x2006,
    0x2007,
    0x2008,
    0x2009,
    0x200A,
    0x2028,
    0x2029,
    0x202F,
    0x205F,
    0x3000,
    0xFEFF,
)
JS_WHITESPACE: str = "".join(chr(cp) for cp in JS_WHITESPACE_CODES)
# One whitespace code point, for removing every one of them.
WS_RE = re.compile("[" + re.escape(JS_WHITESPACE) + "]")

ZWNJ = chr(0x200C)
TATWEEL = chr(0x0640)

FA_DIGITS: str = "".join(chr(0x06F0 + i) for i in range(10))
AR_DIGITS: str = "".join(chr(0x0660 + i) for i in range(10))
_DIGIT_MAP: dict[int, str] = {ord(ch): str(i) for i, ch in enumerate(FA_DIGITS)} | {
    ord(ch): str(i) for i, ch in enumerate(AR_DIGITS)
}

# normalize.js: yeh (U+064A, U+0649) to Persian yeh, kaf (U+0643) to Persian kaf, tatweel removed.
_YEH_KAF_TATWEEL: dict[int, int | None] = {
    0x064A: 0x06CC,
    0x0649: 0x06CC,
    0x0643: 0x06A9,
    0x0640: None,
}
_BLANKS_RE = re.compile("[ \t]+")
# faKey: ZWNJ and every JS whitespace code point are dropped.
_FA_KEY_DROP_RE = re.compile("[" + re.escape(ZWNJ + JS_WHITESPACE) + "]+")
# faKey: teh marbuta to heh, alef with hamza above or below and alef wasla to alef, waw with hamza
# to waw.
_FA_KEY_FOLD: dict[int, int] = {
    0x0629: 0x0647,
    0x0623: 0x0627,
    0x0625: 0x0627,
    0x0671: 0x0627,
    0x0624: 0x0648,
}
_NOCASE: dict[int, int] = {
    ord(upper): ord(lower)
    for upper, lower in zip(string.ascii_uppercase, string.ascii_lowercase, strict=True)
}
_SIGMA = chr(0x03A3)
_FINAL_SIGMA = chr(0x03C2)
_SMALL_SIGMA = chr(0x03C3)

_CASED_STARTS: tuple[int, ...] = tuple(first for first, _ in CASED)
_IGNORABLE_STARTS: tuple[int, ...] = tuple(first for first, _ in CASE_IGNORABLE)


def _require_str(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError(f"expected str, not {type(value).__name__}")
    return value


def js_trim(text: str) -> str:
    """String.prototype.trim: strips the JavaScript whitespace set, not only ASCII spaces."""
    return _require_str(text).strip(JS_WHITESPACE)


def to_ascii_digits(text: str) -> str:
    """Persian (U+06F0..U+06F9) and Arabic (U+0660..U+0669) digits to ASCII, as toAsciiDigits."""
    return _require_str(text).translate(_DIGIT_MAP)


def normalize_text(text: str) -> str:
    """normalizeText of src/lib/normalize.js, in its step order: NFC, digits, yeh, kaf, tatweel,
    collapse of [ \\t]+ to one space, then trim. For storage."""
    text = unicodedata.normalize("NFC", _require_str(text))
    text = to_ascii_digits(text)
    text = text.translate(_YEH_KAF_TATWEEL)
    text = _BLANKS_RE.sub(" ", text)
    return js_trim(text)


def fa_key(text: str) -> str:
    """faKey of src/lib/normalize.js: normalizeText, then ZWNJ and whitespace dropped, Arabic letter
    forms folded, then JavaScript toLowerCase. For comparison and search only."""
    text = _FA_KEY_DROP_RE.sub("", normalize_text(text))
    text = text.translate(_FA_KEY_FOLD)
    return js_lower(text)


def nocase_key(text: str) -> str:
    """The legacy COLLATE NOCASE key: ASCII A-Z folded to a-z, nothing else changes. Sorting by
    this key gives the order of ORDER BY ... COLLATE NOCASE."""
    return _require_str(text).translate(_NOCASE)


def _in_ranges(cp: int, ranges: tuple[tuple[int, int], ...], starts: tuple[int, ...]) -> bool:
    index = bisect_right(starts, cp) - 1
    return index >= 0 and cp <= ranges[index][1]


def _is_cased(ch: str) -> bool:
    return _in_ranges(ord(ch), CASED, _CASED_STARTS)


def _is_case_ignorable(ch: str) -> bool:
    return _in_ranges(ord(ch), CASE_IGNORABLE, _IGNORABLE_STARTS)


def _final_sigma(text: str, index: int) -> bool:
    """Final_Sigma: a cased letter before (through case-ignorable marks), none after."""
    before = index - 1
    while before >= 0 and _is_case_ignorable(text[before]):
        before -= 1
    if before < 0 or not _is_cased(text[before]):
        return False
    after = index + 1
    while after < len(text) and _is_case_ignorable(text[after]):
        after += 1
    return not (after < len(text) and _is_cased(text[after]))


def js_lower(text: str) -> str:
    """String.prototype.toLowerCase: Node's per-code-point table, and final sigma by context."""
    text = _require_str(text)
    out: list[str] = []
    for index, ch in enumerate(text):
        if ch == _SIGMA:
            out.append(_FINAL_SIGMA if _final_sigma(text, index) else _SMALL_SIGMA)
        else:
            out.append(LOWER.get(ord(ch), ch))
    return "".join(out)
