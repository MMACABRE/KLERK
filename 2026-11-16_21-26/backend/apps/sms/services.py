"""SMS queue claims (SPEC §4.3, SMS claim).

A worker claims due rows before it sends them. The rows are locked with SKIP LOCKED and flipped
to 'sending' in the same transaction, so two workers never send the same row."""

from __future__ import annotations

from django.db import transaction

from apps.sms.models import SmsMessage


def claim_due(now_ms: int, limit: int = 20) -> list[int]:
    """Claim up to `limit` pending rows that are due. Returns their ids."""
    with transaction.atomic():
        due = list(
            SmsMessage.objects.select_for_update(skip_locked=True)
            .filter(status="pending", due_at__lte=now_ms)
            .order_by("due_at", "pk")[:limit]
        )
        ids = [int(message.pk) for message in due]
        SmsMessage.objects.filter(pk__in=ids, status="pending").update(status="sending")
    return ids
