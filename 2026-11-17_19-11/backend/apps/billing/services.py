"""Visit locks and payment groups shared by the payment routes (apps.billing.ops; SPEC §4.3).

Every money change locks the visit rows it touches, in ascending id, before it reads the credit, so two refunds
of the full credit cannot both pass."""

from __future__ import annotations

from collections.abc import Iterable

from django.db.models import QuerySet

from apps.billing.models import Payment
from apps.core.errors import Conflict, NotFound
from apps.visits.models import Visit


class HasPaymentsError(Conflict):
    """The visit or patient has payments, so it cannot be deleted."""


def lock_visits(visit_ids: Iterable[int]) -> list[Visit]:
    """Lock the visit rows in ascending id. A missing row is NotFound."""
    wanted = sorted(set(visit_ids))
    rows = list(Visit.objects.select_for_update().filter(pk__in=wanted).order_by("pk"))
    if len(rows) != len(wanted):
        raise NotFound(f"visits {wanted}: not all found")
    return rows


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
