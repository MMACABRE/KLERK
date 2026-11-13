"""Stock lots and the ledger of stock moves (SPEC §4.1). Quantities are pieces, up to 2 decimals
(apps.core.qty). Lots are used earliest expiry first; remaining never goes below zero."""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.finance.models import Catalog

REASONS = ["in", "use", "return", "count", "waste"]


class Lot(models.Model):
    item = models.ForeignKey(Catalog, on_delete=models.PROTECT, related_name="lots")
    received_on = models.DateField()
    qty_in = models.DecimalField(max_digits=12, decimal_places=2)
    remaining = models.DecimalField(max_digits=12, decimal_places=2)
    expires_on = models.DateField(null=True, blank=True)
    unit_cost = models.BigIntegerField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "lots"
        indexes = [models.Index(fields=["item", "expires_on"], name="lots_item_expiry")]
        constraints = [
            models.CheckConstraint(condition=Q(qty_in__gt=0), name="lots_qty_in_check"),
            models.CheckConstraint(condition=Q(remaining__gte=0), name="lots_remaining_check"),
            models.CheckConstraint(
                condition=Q(unit_cost__isnull=True) | Q(unit_cost__gte=0),
                name="lots_unit_cost_check",
            ),
        ]


class StockMove(models.Model):
    lot = models.ForeignKey(Lot, on_delete=models.PROTECT, related_name="moves")
    qty = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=6)
    line_id = models.BigIntegerField(
        null=True, blank=True, db_index=True
    )  # no foreign key, as in legacy
    note = models.TextField(null=True, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    ts = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "stock_moves"
        constraints = [
            models.CheckConstraint(condition=~Q(qty=0), name="stock_moves_qty_check"),
            models.CheckConstraint(
                condition=Q(reason__in=REASONS), name="stock_moves_reason_check"
            ),
        ]
