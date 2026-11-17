"""Typed query helpers. They are the canary that mypy (1.19.1) with django-stubs (5.2.9) checks in
strict mode."""

from __future__ import annotations

from django.db.models import QuerySet

from apps.patients.models import Patient


def patients_in_name_order(queryset: QuerySet[Patient]) -> list[int]:
    """Patient ids in the legacy name order: last name, then first name, both NOCASE (ASCII fold),
    then id."""
    return list(
        queryset.order_by("last_name_sort", "first_name_sort", "id").values_list("id", flat=True)
    )
