"""Finance figures (legacy src/lib/finance.js). Income counts on the day money moved: payments and refunds by
paid_on; moves between visits are not income."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Count, Q, Sum

from apps.billing.models import BillLine, Payment
from apps.billing.ops import bill_for
from apps.core.aggregates import sum_rial
from apps.core.jalali import TEHRAN, add_days
from apps.storage.models import StockMove
from apps.visits.models import Visit

INCOME = Q(kind__in=["payment", "refund"])


def income_between(start: date, end: date) -> dict[str, int]:
    rows = Payment.objects.filter(INCOME, paid_on__range=(start, end))
    agg = rows.aggregate(n=Count("id"))
    return {"total": sum_rial(rows, "amount"), "count": int(agg["n"] or 0)}


def income_by_day(start: date, end: date) -> list[dict[str, Any]]:
    rows = {
        r["paid_on"]: int(r["t"] or 0)
        for r in Payment.objects.filter(INCOME, paid_on__range=(start, end)).values("paid_on").annotate(t=Sum("amount"))
    }
    out, d = [], start
    while d <= end:
        out.append({"day": d, "total": rows.get(d, 0)})
        d = add_days(d, 1)
    return out


def outstanding() -> dict[str, int]:
    ids = set(BillLine.objects.values_list("visit_id", flat=True)) | set(
        Payment.objects.values_list("visit_id", flat=True)
    )
    remaining = credit = 0
    for v in Visit.objects.filter(pk__in=ids):
        b = bill_for(v)
        remaining += b["remaining"]
        credit += b["credit"]
    return {"remaining": remaining, "credit": credit}


def revenue_by_source(start: date, end: date) -> dict[str, Any]:
    by_kind = {"service": 0, "item": 0}
    by_name: dict[str, int] = {}
    bill_disc = 0
    for v in Visit.objects.exclude(status="cancelled").filter(visit_date__range=(start, end)):
        b = bill_for(v)
        bill_disc += b["billDisc"]
        for x in b["lines"]:
            by_kind[x["line"].kind] += x["net"]
            by_name[x["line"].name] = by_name.get(x["line"].name, 0) + x["net"]
    rows: list[dict[str, Any]] = [{"label": k, "value": v} for k, v in by_name.items()]
    top = sorted(rows, key=lambda r: -r["value"])
    return {"byKind": by_kind, "billDisc": bill_disc, "top": top}


def usage_by_day(start: date, end: date) -> list[dict[str, Any]]:
    lo = datetime.combine(start, time(0), tzinfo=TEHRAN)
    hi = datetime.combine(add_days(end, 1), time(0), tzinfo=TEHRAN)
    per: dict[date, Decimal] = {}
    for ts, q in StockMove.objects.filter(reason__in=["use", "return"], ts__gte=lo, ts__lt=hi).values_list("ts", "qty"):
        day = ts.astimezone(TEHRAN).date()
        per[day] = per.get(day, Decimal("0")) + q
    out, d = [], start
    while d <= end:
        out.append({"day": d, "total": max(float(-per.get(d, Decimal("0"))), 0.0)})
        d = add_days(d, 1)
    return out


_ = timedelta
