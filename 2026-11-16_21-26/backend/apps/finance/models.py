"""Catalog of services and stock items, payment accounts and methods (SPEC §4.1). Money is whole
Rial."""

from typing import Any

from django.db import models
from django.db.models import Q

from apps.core.text import fa_key


class Account(models.Model):
    name = models.CharField(max_length=100)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "accounts"


class PayMethod(models.Model):
    name = models.CharField(max_length=100)
    default_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, null=True, blank=True, related_name="methods"
    )
    active = models.BooleanField(default=True)

    class Meta:
        db_table = "pay_methods"


class Catalog(models.Model):
    kind = models.CharField(max_length=7)
    name = models.CharField(max_length=200)
    name_key = models.CharField(max_length=200, editable=False, db_index=True)
    sale_price = models.BigIntegerField()
    purchase_cost = models.BigIntegerField(null=True, blank=True)
    fixed = models.BooleanField(default=False)
    low_warn = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    low_crit = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "catalog"
        constraints = [
            models.CheckConstraint(
                condition=Q(kind__in=["service", "item"]), name="catalog_kind_check"
            ),
            models.CheckConstraint(condition=Q(sale_price__gte=0), name="catalog_sale_price_check"),
            models.CheckConstraint(
                condition=Q(purchase_cost__isnull=True) | Q(purchase_cost__gte=0),
                name="catalog_purchase_cost_check",
            ),
            models.CheckConstraint(
                condition=Q(low_warn__isnull=True) | Q(low_warn__gte=0),
                name="catalog_low_warn_check",
            ),
            models.CheckConstraint(
                condition=Q(low_crit__isnull=True) | Q(low_crit__gte=0),
                name="catalog_low_crit_check",
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.name_key = fa_key(self.name)
        super().save(*args, **kwargs)
