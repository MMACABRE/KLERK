"""Sums of Rial amounts from the database (SPEC §4.1, BIGINT money).

The ORM hands back an int. A raw cursor on MySQL hands back a Decimal (SUM of BIGINT is DECIMAL).
Both go through apps.core.money.rial, so a total is always an int, and a total outside BIGINT is
refused.
"""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet, Sum

from apps.core.money import rial


def sum_rial(queryset: QuerySet[Any], field: str) -> int:
    """The total of a money field over a queryset; 0 for no rows."""
    total = queryset.aggregate(total=Sum(field))["total"]
    return 0 if total is None else rial(total)
