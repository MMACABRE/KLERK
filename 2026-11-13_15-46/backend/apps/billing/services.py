"""Payments, refunds, credit moves and payment deletion (SPEC §4.3).

Every change locks the visit rows it touches, in ascending id, before it reads the credit. The
credit is the sum of a visit's payment rows, so two refunds of the full credit cannot both pass.
Money given back or moved out must never leave a visit with a negative credit (legacy
assertNotOverdrawn)."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any

from django.db import transaction
from django.db.models import QuerySet

from apps.billing.models import Payment
from apps.core.aggregates import sum_rial
from apps.core.errors import Conflict, Invalid, NotFound
from apps.visits.models import Visit


class OverdrawError(Conflict):
    """The change would leave a visit with more money given back than it received."""


class HasPaymentsError(Conflict):
    """The visit or patient has payments, so it cannot be deleted."""


class CancelledVisitError(Conflict):
    """A payment cannot be taken on a cancelled visit (refunds and moves can)."""


def lock_visits(visit_ids: Iterable[int]) -> list[Visit]:
    """Lock the visit rows in ascending id. A missing row is NotFound."""
    wanted = sorted(set(visit_ids))
    rows = list(Visit.objects.select_for_update().filter(pk__in=wanted).order_by("pk"))
    if len(rows) != len(wanted):
        raise NotFound(f"visits {wanted}: not all found")
    return rows


def credit_of(visit: Visit) -> int:
    return sum_rial(Payment.objects.filter(visit=visit), "amount")


def add_payment(visit_id: int, amount: int, paid_on: date, user: Any = None) -> Payment:
    """Take `amount` Rial (positive) on a visit that is not cancelled."""
    if amount <= 0:
        raise Invalid("amount must be positive")
    with transaction.atomic():
        (visit,) = lock_visits([visit_id])
        if visit.status == "cancelled":
            raise CancelledVisitError(visit_id)
        return Payment.objects.create(
            visit=visit, amount=amount, kind="payment", paid_on=paid_on, created_by=user
        )


def add_refund(visit_id: int, amount: int, paid_on: date, user: Any = None) -> Payment:
    """Refund `amount` Rial (a positive number) from a visit's net credit."""
    if amount <= 0:
        raise Invalid("amount must be positive")
    with transaction.atomic():
        (visit,) = lock_visits([visit_id])
        if amount > credit_of(visit):
            raise OverdrawError(f"visit {visit_id}: refund {amount} is more than the credit")
        return Payment.objects.create(
            visit=visit, amount=-amount, kind="refund", paid_on=paid_on, created_by=user
        )


def move_credit(from_id: int, to_id: int, amount: int, paid_on: date, user: Any = None) -> int:
    """Move `amount` Rial of credit from one visit to another. Returns the move id (the move_out
    row)."""
    if amount <= 0 or from_id == to_id:
        raise Invalid("a move needs a positive amount and two different visits")
    with transaction.atomic():
        rows = {v.pk: v for v in lock_visits([from_id, to_id])}
        if amount > credit_of(rows[from_id]):
            raise OverdrawError(f"visit {from_id}: move {amount} is more than the credit")
        out = Payment.objects.create(
            visit=rows[from_id], amount=-amount, kind="move_out", paid_on=paid_on, created_by=user
        )
        Payment.objects.filter(pk=out.pk).update(move_id=out.pk)
        Payment.objects.create(
            visit=rows[to_id],
            amount=amount,
            kind="move_in",
            paid_on=paid_on,
            move_id=out.pk,
            created_by=user,
        )
        return int(out.pk)


def _payment(payment_id: int) -> Payment:
    row = Payment.objects.filter(pk=payment_id).first()
    if row is None:
        raise NotFound(f"payment {payment_id} not found")
    return row


def _group(payment: Payment) -> QuerySet[Payment]:
    """A move's two halves go together; any other payment stands alone."""
    if payment.move_id is None:
        return Payment.objects.filter(pk=payment.pk)
    return Payment.objects.filter(move_id=payment.move_id)


def delete_payment(payment_id: int) -> None:
    """Delete a payment (both halves of a move). Refused when a visit would be left overdrawn."""
    with transaction.atomic():
        first = _payment(payment_id)
        visit_ids = set(_group(first).values_list("visit_id", flat=True))
        locked = lock_visits(visit_ids)
        current = _payment(payment_id)
        if set(_group(current).values_list("visit_id", flat=True)) - visit_ids:
            raise Conflict("the payment's move changed while it was being deleted")
        _group(current).delete()
        for visit in locked:
            if credit_of(visit) < 0:
                raise OverdrawError(f"visit {visit.pk}: deleting the payment overdraws it")


def set_payment_amount(payment_id: int, amount: int) -> None:
    """Change a plain payment or refund. The sign stays with its kind; a move's halves are not
    edited here."""
    if amount == 0:
        raise Invalid("amount must not be zero")
    with transaction.atomic():
        first = _payment(payment_id)
        if first.move_id is not None:
            raise Invalid("a move's halves are changed by deleting and moving again")
        (visit,) = lock_visits([first.visit_id])
        current = _payment(payment_id)
        magnitude = abs(amount)
        current.amount = magnitude if current.amount > 0 else -magnitude
        current.save(update_fields=["amount"])
        if credit_of(visit) < 0:
            raise OverdrawError(f"visit {visit.pk}: the new amount overdraws it")
