"""Patient codes (SPEC §2.2; legacy src/lib/files.js:12-27).

A code is `P-` followed by exactly six ASCII digits. Services refuse anything else
(BadCodeError), and the database checks the same shape. A code typed into a CSV cell is read more
loosely, as legacy parseCodeCell does."""

from __future__ import annotations

import re

from apps.core.errors import Invalid
from apps.core.text import js_trim, to_ascii_digits

CODE_RE = re.compile(r"P-[0-9]{6}")
_CELL_RE = re.compile(r"(?:P-?)?([0-9]{1,6})", re.IGNORECASE)


class BadCodeError(Invalid):
    """The text is not a patient code (P- and six ASCII digits)."""


class RefusedCell(BadCodeError):
    """A CSV code cell is malformed (never an empty cell, which means "give one automatically")."""


def is_code(value: object) -> bool:
    return isinstance(value, str) and CODE_RE.fullmatch(value) is not None


def require_code(value: object) -> str:
    if not is_code(value):
        raise BadCodeError(f"not a patient code: {value!r}")
    return str(value)


def patient_code(number: int) -> str:
    return f"P-{number:06d}"


def parse_code_cell(raw: object) -> str | None:
    """A CSV cell: `P-000301`, `p-301`, `301`, `P301` and Persian digits all mean P-000301. An empty
    cell is None (the code is then given automatically). Anything else raises RefusedCell."""
    text = js_trim(to_ascii_digits("" if raw is None else str(raw)))
    if not text:
        return None
    match = _CELL_RE.fullmatch(text)
    if match is None:
        raise RefusedCell(f"malformed code cell: {text!r}")
    return f"P-{match.group(1).rjust(6, '0')}"
