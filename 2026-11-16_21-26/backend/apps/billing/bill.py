"""The bill of a visit, as the legacy billFor computes it (src/lib/bill.js:23-47).

Each line: effective price (override when set, else unit), quantity, then its discount. The
subtotal is the sum of the net lines; the visit discount comes off the subtotal; a cancelled
visit owes nothing; paid is the sum of its payments."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from apps.core.money import discount_of, line_gross


@dataclass(frozen=True)
class Totals:
    owed: int
    paid: int


def bill_totals(
    lines: Iterable[dict[str, Any]],
    payments: Iterable[int],
    *,
    cancelled: bool,
    disc_kind: str | None,
    disc_value: int | None,
) -> Totals:
    subtotal = 0
    for line in lines:
        price = line["override_price"] if line["override_price"] is not None else line["unit_price"]
        gross = line_gross(int(price), float(line["qty"]))
        subtotal += gross - discount_of(gross, line["disc_kind"], line["disc_value"])
    owed = 0 if cancelled else subtotal - discount_of(subtotal, disc_kind, disc_value)
    return Totals(owed=owed, paid=sum(int(p) for p in payments))
