"""Bill lines and payments (SPEC §4.1). The visit is the bill: lines freeze name and price; payments
are
signed Rial rows, and a visit with payments cannot be deleted (PROTECT)."""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.finance.models import Account, Catalog, PayMethod
from apps.visits.models import Visit


class BillLine(models.Model):
    visit = models.ForeignKey(Visit, on_delete=models.CASCADE, related_name="bill_lines")
    catalog = models.ForeignKey(Catalog, on_delete=models.PROTECT, related_name="bill_lines")
    kind = models.CharField(max_length=7)
    name = models.CharField(max_length=200)
    qty = models.DecimalField(max_digits=12, decimal_places=2)
    unit_price = models.BigIntegerField()
    override_price = models.BigIntegerField(null=True, blank=True)
    disc_kind = models.CharField(max_length=7, null=True, blank=True)
    disc_value = models.BigIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "bill_lines"
        constraints = [
            models.CheckConstraint(
                condition=Q(kind__in=["service", "item"]), name="bill_lines_kind_check"
            ),
            models.CheckConstraint(condition=Q(qty__gt=0), name="bill_lines_qty_check"),
            models.CheckConstraint(
                condition=Q(unit_price__gte=0), name="bill_lines_unit_price_check"
            ),
            models.CheckConstraint(
                condition=Q(override_price__isnull=True) | Q(override_price__gte=0),
                name="bill_lines_override_check",
            ),
            models.CheckConstraint(
                condition=Q(disc_kind__in=["amount", "percent"]) | Q(disc_kind__isnull=True),
                name="bill_lines_disc_kind_check",
            ),
            models.CheckConstraint(
                condition=Q(disc_value__gte=0), name="bill_lines_disc_value_check"
            ),
        ]


class Payment(models.Model):
    visit = models.ForeignKey(Visit, on_delete=models.PROTECT, related_name="payments")
    amount = models.BigIntegerField()
    kind = models.CharField(max_length=8)
    paid_on = models.DateField(db_index=True)
    method = models.ForeignKey(
        PayMethod, on_delete=models.PROTECT, null=True, blank=True, related_name="payments"
    )
    account = models.ForeignKey(
        Account, on_delete=models.PROTECT, null=True, blank=True, related_name="payments"
    )
    move_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    note = models.TextField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payments"
        constraints = [
            models.CheckConstraint(condition=~Q(amount=0), name="payments_amount_check"),
            models.CheckConstraint(
                condition=Q(kind__in=["payment", "refund", "move_out", "move_in"]),
                name="payments_kind_check",
            ),
        ]
