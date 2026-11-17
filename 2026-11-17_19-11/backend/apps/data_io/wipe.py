"""«حذف داده‌ها» (legacy src/lib/wipe.js): wipes whole kinds of data at once. Rows go in one transaction; the
patient folders move to data/trash after it commits."""

from __future__ import annotations

import os
from typing import Any

from django.db import transaction

from apps.billing.models import BillLine, Payment
from apps.core.audit import audit
from apps.core.files import data_dir, stamp_now, trash_dir
from apps.documents.models import Document
from apps.finance.models import Catalog
from apps.patients.models import Patient, PatientValue
from apps.storage.models import Lot, StockMove
from apps.visits.models import Visit

WIPE_KINDS = ["patients", "documents", "finance", "storage"]


def wipe_counts() -> dict[str, dict[str, int]]:
    return {
        "patients": {"patients": Patient.objects.count(), "visits": Visit.objects.count()},
        "documents": {
            "documents": Document.objects.count(),
            "photos": Patient.objects.filter(photo__isnull=False).count(),
        },
        "finance": {"payments": Payment.objects.count(), "lines": BillLine.objects.count()},
        "storage": {"lots": Lot.objects.count(), "moves": StockMove.objects.count(),
                    "items": Catalog.objects.filter(kind="item", deleted_at__isnull=True).count()},
    }


def effective_kinds(kinds: list[str]) -> list[str]:
    k = {x for x in kinds if x in WIPE_KINDS}
    if "patients" in k:
        k |= {"documents", "finance"}
    return [x for x in WIPE_KINDS if x in k]


def _trash_patient_folders() -> str | None:
    src = data_dir() / "patients"
    if not src.exists() or not any(src.iterdir()):
        return None
    name = f"wipe-{stamp_now()}"
    trash_dir().mkdir(parents=True, exist_ok=True)
    os.replace(src, trash_dir() / name)
    src.mkdir(parents=True, exist_ok=True)
    return name


def wipe_data(kinds: list[str], user_id: int | None) -> dict[str, Any]:
    k = effective_kinds(kinds)
    before = wipe_counts()
    with transaction.atomic():
        if "finance" in k:
            Payment.objects.all().delete()
            BillLine.objects.all().delete()
            Visit.objects.update(disc_kind=None, disc_value=0)
        if "patients" in k:
            for pid, code in Patient.objects.values_list("id", "code"):
                audit(user_id, "patient_delete", pid, code)
            PatientValue.objects.all().delete()
            Patient.objects.all().delete()
        elif "documents" in k:
            Document.objects.all().delete()
            Patient.objects.update(photo=None)
        if "storage" in k:
            StockMove.objects.all().delete()
            Lot.objects.all().delete()
            used = BillLine.objects.values_list("catalog_id", flat=True)
            Catalog.objects.filter(kind="item").exclude(pk__in=used).delete()
    trashed = file_error = None
    if "documents" in k:
        try:
            trashed = _trash_patient_folders()
        except OSError as err:
            file_error = str(err.errno)
    return {"kinds": k, "removed": {x: before[x] for x in k}, "trashed": trashed, "fileError": file_error}
