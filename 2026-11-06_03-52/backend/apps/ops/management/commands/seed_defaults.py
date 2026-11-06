"""Fresh install only: the default accounts, payment methods and the «ویزیت» service (SPEC §4.1 seeds).
Does nothing when any of those tables already has a row (a migrated clinic brings its own). Never run it before
the cutover's one-time migration tool (backend/tools/): that tool refuses a target that is not empty."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.finance.models import Account, Catalog, PayMethod


class Command(BaseCommand):
    help = "Seed the default accounts, payment methods and visit service on an empty database."

    def handle(self, *args: Any, **o: Any) -> None:
        if Account.objects.exists() or PayMethod.objects.exists() or Catalog.objects.exists():
            self.stdout.write("already seeded")
            return
        with transaction.atomic():
            cash = Account.objects.create(name="صندوق")
            bank = Account.objects.create(name="حساب بانکی")
            PayMethod.objects.create(name="نقدی", default_account=cash)
            PayMethod.objects.create(name="کارت‌خوان", default_account=bank)
            PayMethod.objects.create(name="کارت به کارت", default_account=bank)
            Catalog.objects.create(kind="service", name="ویزیت", sale_price=0, fixed=True)
        self.stdout.write("seeded")
