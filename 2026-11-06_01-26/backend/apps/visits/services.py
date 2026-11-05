"""Visit booking, rescheduling, un-cancelling and deletion (SPEC §4.3).

One doctor means one calendar: the overlap check and the write run under the named lock
'visit_slots' (outside any transaction), then the patient row, then the visit row. A cancelled
visit takes no slot. Overlap follows legacy findOverlap: a visit may run past midnight into the
next day, so the check looks one day either side."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from django.db import transaction

from apps.billing.models import Payment
from apps.billing.services import HasPaymentsError
from apps.core.errors import Conflict, NotFound
from apps.core.locks import get_for_update, named_lock
from apps.patients.models import Patient
from apps.visits.models import Visit


class OverlapError(Conflict):
    """The visit overlaps another visit that takes a slot."""


def _span(visit_date: date, visit_time: time, duration_min: int) -> tuple[datetime, datetime]:
    start = datetime.combine(visit_date, visit_time)
    return start, start + timedelta(minutes=duration_min)


def _assert_free(visit_date: date, visit_time: time, duration_min: int, exclude_id: int) -> None:
    start, end = _span(visit_date, visit_time, duration_min)
    window = (visit_date - timedelta(days=1), visit_date + timedelta(days=1))
    others = (
        Visit.objects.filter(visit_date__range=window)
        .exclude(status="cancelled")
        .exclude(pk=exclude_id)
        .order_by("visit_date", "visit_time", "pk")
    )
    for other in others:
        other_start, other_end = _span(other.visit_date, other.visit_time, other.duration_min)
        if start < other_end and other_start < end:
            raise OverlapError(f"visit {other.pk} overlaps")


def book_visit(
    patient: Patient, visit_date: date, visit_time: time, duration_min: int, **fields: Any
) -> Visit:
    """Create a visit unless it overlaps a visit that is not cancelled. A deleted patient is
    NotFound."""
    with named_lock("visit_slots"), transaction.atomic():
        get_for_update(Patient.objects.all(), patient.pk, "patient")
        _assert_free(visit_date, visit_time, duration_min, exclude_id=0)
        return Visit.objects.create(
            patient=patient,
            visit_date=visit_date,
            visit_time=visit_time,
            duration_min=duration_min,
            **fields,
        )


def _lock_patient_and_visit(visit_id: int) -> Visit:
    """Lock the patient row, then the visit row (the order in apps.core.locks)."""
    patient_id = Visit.objects.filter(pk=visit_id).values_list("patient_id", flat=True).first()
    if patient_id is None:
        raise NotFound(f"visit {visit_id} not found")
    get_for_update(Patient.objects.all(), patient_id, "patient")
    return get_for_update(Visit.objects.all(), visit_id, "visit")


def reschedule_visit(visit_id: int, visit_date: date, visit_time: time, duration_min: int) -> Visit:
    """Move a visit to another slot unless the new slot overlaps another visit."""
    with named_lock("visit_slots"), transaction.atomic():
        visit = _lock_patient_and_visit(visit_id)
        _assert_free(visit_date, visit_time, duration_min, exclude_id=visit.pk)
        visit.visit_date = visit_date
        visit.visit_time = visit_time
        visit.duration_min = duration_min
        visit.save()
        return visit


def uncancel_visit(visit_id: int) -> Visit:
    """Schedule a cancelled visit again, unless its slot is taken by another visit now."""
    with named_lock("visit_slots"), transaction.atomic():
        visit = _lock_patient_and_visit(visit_id)
        if visit.status != "cancelled":
            return visit
        _assert_free(visit.visit_date, visit.visit_time, visit.duration_min, exclude_id=visit.pk)
        visit.status = "scheduled"
        visit.save()
        return visit


def delete_visit(visit_id: int) -> None:
    """Delete a visit that has no payments. A payment taken at the same time waits for this row
    lock."""
    with transaction.atomic():
        visit = get_for_update(Visit.objects.all(), visit_id, "visit")
        if Payment.objects.filter(visit=visit).exists():
            raise HasPaymentsError(f"visit {visit_id} has payments")
        visit.delete()
