"""Reader for stored legacy timestamps: epoch milliseconds, 'Z' strings, and naive legacy text.

Returns an aware UTC datetime. Accepts only the three shapes the legacy app writes, matched anchored
with re.ASCII, and raises ValueError for anything else (empty text, other separators, offsets, week
dates, hour 24). No fromisoformat on raw input: its accepted set differs between Python versions.
None means no value at all. Pure Python, no clock read.

Deliberate divergence (quirk row 15): naive text, the legacy datetime('now') shape, is UTC. The
legacy app read it as local time. The T1.6 migration reads visits.created_at and updated_at through
this module. Epoch milliseconds use exact integer arithmetic (no float division).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

_ZULU = re.compile(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{3}))?Z", re.ASCII)
_NAIVE = re.compile(r"(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})(?:\.(\d{3}))?", re.ASCII)


def _from_text(match: re.Match[str]) -> datetime:
    year, month, day, hour, minute, second, millis = match.groups()
    micro = int(millis) * 1000 if millis else 0
    # datetime() rejects impossible fields (month 13, day 30 in February, hour 24).
    return datetime(
        int(year), int(month), int(day), int(hour), int(minute), int(second), micro, tzinfo=UTC
    )


def read_stored(value: int | str | None) -> datetime | None:
    """A stored timestamp as aware UTC. None for no value; ValueError for an unknown shape."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise TypeError("a stored timestamp is an int (epoch ms) or a str, not bool")
    if isinstance(value, int):
        try:
            return EPOCH + timedelta(milliseconds=value)
        except OverflowError as exc:
            raise ValueError(f"epoch milliseconds out of range: {value}") from exc
    if isinstance(value, str):
        match = _ZULU.fullmatch(value) or _NAIVE.fullmatch(value)
        if match is None:
            raise ValueError(f"not a stored timestamp shape: {value!r}")
        return _from_text(match)
    raise TypeError(f"a stored timestamp is an int or a str, not {type(value).__name__}")
