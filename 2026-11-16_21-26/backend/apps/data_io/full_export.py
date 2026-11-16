"""Full export (D-R7 a; legacy src/lib/full-export.js): one streamed zip with a klerk.sql dump, patients.csv and one
folder per patient. Only folder names taken from the database and files found through apps.core.files are added."""

from __future__ import annotations

import os
import uuid
import zipfile
from collections.abc import Iterator
from typing import IO, Any, cast

from apps.billing.models import Payment
from apps.billing.ops import bill_for
from apps.core.codes import is_code
from apps.core.files import list_patient_files, resolve_patient_file, tmp_dir
from apps.core.jalali import to_jalali_input
from apps.data_io.csv_io import BOM, patients_csv, to_csv
from apps.patients.custom_boxes import add_custom_cells, custom_columns
from apps.patients.layouts import read_layout
from apps.patients.models import Medication, Patient
from apps.storage.models import Lot, StockMove
from apps.storage.services import qty_text
from apps.visits.logic import STATUS_LABEL_FA, hhmm
from apps.visits.models import Visit

README = BOM + """این فایل یک نسخه‌ی کامل از اطلاعات سامانه‌ی پرونده‌ی بیماران است.
این فایل اطلاعات محرمانه‌ی بیماران را دارد. آن را در جای امن نگه دارید و پس از استفاده حذف کنید.

محتویات:
  klerk.sql        نسخه‌ی کامل پایگاه داده (MySQL). برای بازگردانی روی سرور تازه به کار می‌رود.
  patients.csv     فهرست همه‌ی بیماران. با Excel باز می‌شود.
  patients/        یک پوشه برای هر بیمار، به نام کد او (مثلاً P-000123):
                     info.csv   مشخصات بیمار و داروهای او
                     visits.csv ویزیت‌های ثبت‌شده‌ی بیمار (فقط اگر ویزیتی باشد)
                     bills.csv  ردیف‌ها و پرداخت‌های صورتحساب ویزیت‌ها (با دسترسی امور مالی)
  finance/         payments.csv همه‌ی پرداخت‌ها (با دسترسی امور مالی)
  storage/         lots.csv و moves.csv بسته‌ها و گردش انبار (با دسترسی انبار)
                     بقیه‌ی فایل‌ها: اسناد و پیوست‌های بیمار، همان‌طور که روی سرور هستند.

برای بازگردانی روی یک سرور تازه، راهنمای docs/SETUP.md را ببینید.
"""

PAY_KIND_FA = {"payment": "پرداخت", "refund": "بازپرداخت", "move_out": "انتقال (خروج)", "move_in": "انتقال (ورود)"}
MOVE_FA = {"in": "ورود", "use": "مصرف", "return": "برگشت", "count": "اصلاح شمارش", "waste": "ضایعات"}
CHUNK = 1024 * 1024


class _Sink:
    """A write-only, non-seekable target for ZipFile; the generator drains it between writes."""

    def __init__(self) -> None:
        self.parts: list[bytes] = []

    def write(self, b: bytes) -> int:
        self.parts.append(bytes(b))
        return len(b)

    def flush(self) -> None:
        pass

    def drain(self) -> bytes:
        out = b"".join(self.parts)
        self.parts.clear()
        return out


def _meds(pid: int) -> str:
    return " ؛ ".join(
        " / ".join(x for x in (m.name, m.dosage, m.frequency, m.since) if x)
        for m in Medication.objects.filter(patient_id=pid).order_by("id")
    )


def _visits_csv(pid: int) -> str | None:
    rows = Visit.objects.filter(patient_id=pid).order_by("-visit_date", "-visit_time")
    if not rows:
        return None
    return to_csv(["تاریخ", "ساعت", "مدت (دقیقه)", "وضعیت", "شرح", "یادداشت"], [
        [to_jalali_input(v.visit_date), hhmm(v.visit_time), v.duration_min, STATUS_LABEL_FA.get(v.status, v.status),
         v.reason or "", v.notes or ""] for v in rows
    ])


def _bills_csv(pid: int) -> str | None:
    out: list[list[Any]] = []
    for v in Visit.objects.filter(patient_id=pid).order_by("visit_date", "visit_time"):
        b = bill_for(v)
        day = to_jalali_input(v.visit_date)
        for x in b["lines"]:
            ln = x["line"]
            price = ln.override_price if ln.override_price is not None else ln.unit_price
            out.append([day, "ردیف", ln.name, qty_text(ln.qty), price, x["disc"], x["net"], "", ""])
        if b["billDisc"]:
            out.append([day, "تخفیف کل", "", "", "", b["billDisc"], -b["billDisc"], "", ""])
        for p in b["payments"]:
            names = (p.method.name if p.method else None, p.account.name if p.account else None)
            how = " / ".join(x for x in names if x)
            out.append([day, PAY_KIND_FA[p.kind], "", "", "", "", p.amount, to_jalali_input(p.paid_on), how])
    if not out:
        return None
    return to_csv(["تاریخ ویزیت", "نوع", "شرح", "تعداد", "قیمت واحد (ریال)", "تخفیف (ریال)", "مبلغ (ریال)",
                   "تاریخ پرداخت", "روش / حساب"], out)


def _payments_csv() -> str:
    rows = Payment.objects.select_related("visit__patient", "method", "account").order_by("paid_on", "id")
    return to_csv(["تاریخ پرداخت", "کد بیمار", "تاریخ ویزیت", "نوع", "مبلغ (ریال)", "روش", "حساب", "یادداشت"], [
        [to_jalali_input(p.paid_on), p.visit.patient.code, to_jalali_input(p.visit.visit_date), PAY_KIND_FA[p.kind],
         p.amount, p.method.name if p.method else "", p.account.name if p.account else "", p.note or ""] for p in rows
    ])


def _lots_csv() -> str:
    rows = Lot.objects.select_related("item").order_by("item__name", "id")
    return to_csv(["کالا", "تاریخ ورود", "انقضا", "ورودی", "مانده", "قیمت خرید هر عدد (ریال)"], [
        [lot.item.name, to_jalali_input(lot.received_on), to_jalali_input(lot.expires_on) if lot.expires_on else "",
         qty_text(lot.qty_in), qty_text(lot.remaining), lot.unit_cost if lot.unit_cost is not None else ""]
        for lot in rows
    ])


def _moves_csv() -> str:
    rows = StockMove.objects.select_related("lot__item").order_by("id")
    return to_csv(["زمان", "کالا", "نوع", "تعداد", "یادداشت"], [
        [m.ts.isoformat(), m.lot.item.name, MOVE_FA[m.reason], qty_text(m.qty), m.note or ""] for m in rows
    ])


def stream_full_export(finance: bool, storage: bool) -> Iterator[bytes]:
    """Yields the zip in pieces. The SQL dump is taken first into data/tmp (mode 600) and removed afterwards."""
    from apps.ops.backup import dump_to

    snapshot = tmp_dir() / f"export-{uuid.uuid4().hex}.sql"
    fd = os.open(snapshot, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            dump_to(f)
    except Exception:
        snapshot.unlink(missing_ok=True)
        raise

    def gen() -> Iterator[bytes]:
        sink = _Sink()
        try:
            with zipfile.ZipFile(cast(IO[bytes], sink), "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
                z.writestr("README.txt", README)
                yield sink.drain()
                with open(snapshot, "rb") as src, z.open("klerk.sql", "w", force_zip64=True) as dst:
                    while chunk := src.read(CHUNK):
                        dst.write(chunk)
                        yield sink.drain()
                custom = custom_columns(read_layout("patient_form"))
                patients = add_custom_cells([dict(r) for r in Patient.objects.order_by("id").values()])
                z.writestr("patients.csv", patients_csv(patients, custom))
                if finance:
                    z.writestr("finance/payments.csv", _payments_csv())
                if storage:
                    z.writestr("storage/lots.csv", _lots_csv())
                    z.writestr("storage/moves.csv", _moves_csv())
                yield sink.drain()
                for p in patients:
                    if not is_code(p["code"]):
                        continue
                    base = f"patients/{p['code']}"
                    z.writestr(f"{base}/info.csv", patients_csv([{**p, "medications": _meds(p["id"])}],
                                                                [("medications", "داروها"), *custom]))
                    visits = _visits_csv(p["id"])
                    if visits:
                        z.writestr(f"{base}/visits.csv", visits)
                    bills = _bills_csv(p["id"]) if finance else None
                    if bills:
                        z.writestr(f"{base}/bills.csv", bills)
                    used = {"info.csv", *(["visits.csv"] if visits else []), *(["bills.csv"] if bills else [])}
                    yield sink.drain()
                    for f in list_patient_files(p["code"]):
                        full = resolve_patient_file(p["code"], f["filename"])
                        if not full:
                            continue
                        name = f["filename"]
                        while name.lower() in used:
                            name = f"_{name}"
                        used.add(name.lower())
                        with open(full, "rb") as src, z.open(f"{base}/{name}", "w", force_zip64=True) as dst:
                            while chunk := src.read(CHUNK):
                                dst.write(chunk)
                                yield sink.drain()
            yield sink.drain()
        finally:
            snapshot.unlink(missing_ok=True)

    return gen()
