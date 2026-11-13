"""The patient CSV import job: staged by the confirm request, run by the worker (see models.py).

`run_batch()` takes the oldest unfinished job and inserts its pending rows under the `patient_code` lock for
about BATCH_S seconds, one transaction per row, then lets go so the patient form and the SMS tick are never
held up for long. Taken codes and national ids are read once per batch, not per row, and automatic codes are
counted up in memory (the lock keeps every other creator out while the batch runs).

A batch that raises (database gone, disk full) leaves its rows pending; after MAX_ATTEMPTS failed batches in a
row the job stops as `failed` and the page offers to resume it. Every finish or stop writes the
`patient_import` audit row with the counts only.
"""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.db import DatabaseError, OperationalError, transaction
from django.db.models import Count
from django.utils import timezone

from apps.core import present
from apps.core.audit import audit
from apps.core.errors import LockBusy
from apps.core.files import patient_dir, patient_dir_exists
from apps.core.locks import named_lock
from apps.data_io.models import ImportJob, ImportRow
from apps.ops.health import worker_alive
from apps.patients.custom_boxes import BoxError, check_custom_value, live_custom_boxes, write_custom_values
from apps.patients.models import Patient

log = logging.getLogger("klerk.import")

BATCH_S = 2.0  # how long one batch holds the patient_code lock
BATCH_ROWS = 500  # rows read per batch (a batch usually ends on time first)
MAX_ATTEMPTS = 3
DB_REFUSED_NOTE = "پایگاه داده این ردیف را نپذیرفت و ثبت نشد."  # C8, new string for the owner to read
KEEP_DAYS = 30  # finished jobs (line numbers and reasons only) are removed after this

NOTE_CODE_TAKEN = "کد بیمار در سامانه ثبت شده است؛ رد می‌شود"
NOTE_CODE_FOLDER = "پوشهٔ این کد بیمار روی سرور هست ولی بیماری با این کد ثبت نشده است؛ رد می‌شود"
NOTE_NID_TAKEN = "کد ملی در سامانه ثبت شده است؛ رد می‌شود"
NOTE_BOX_GONE = "این کادر یا گزینه دیگر وجود ندارد."


# ---- values between the preview, the staged file and the job ---------------------------------------

def jsonable(values: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in values.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif v is not None and not isinstance(v, (str, int, float, bool)):
            out[k] = str(v)
        else:
            out[k] = v
    return out


def from_json(values: dict[str, Any]) -> dict[str, Any]:
    out = dict(values)
    if out.get("birth_date"):
        out["birth_date"] = date.fromisoformat(out["birth_date"])
    for k in ("height_cm", "weight_kg"):
        if out.get(k) is not None:
            out[k] = Decimal(out[k])
    return out


def check_cells(
    boxes: list[Any], cells: dict[str, Any], confirm: bool = False, labels: dict[str, str] | None = None
) -> tuple[dict[int, str | None], str | None]:
    custom: dict[int, str | None] = {}
    error = None
    for box in boxes:
        raw = cells.get(f"c{box.pk}")
        if raw is None:
            continue
        try:
            v = check_custom_value(box, raw, by_label=True)
        except BoxError as err:
            msg = NOTE_BOX_GONE if confirm and box.type == "choice" else err.message
            error = error or f"«{box.label}»: {msg}"
            continue
        if v is not None:
            custom[box.pk] = v
    live = {f"c{b.pk}" for b in boxes}
    for key in cells:
        if key not in live:
            error = error or f"«{(labels or {}).get(key, 'کادر سفارشی')}»: {NOTE_BOX_GONE}"
            break
    return custom, error


# ---- staging ----------------------------------------------------------------------------------------

def create_job(token: str, user_id: int, file_name: str, staged: dict[str, Any]) -> ImportJob:
    """One job per preview token. Valid rows with a chosen code run first (as the old confirm did), then the
    valid rows without one; the preview's duplicates and invalid rows are stored already decided."""
    valid = staged["rows"]
    ordered = [r for r in valid if r["code"]] + [r for r in valid if not r["code"]]
    others = staged.get("others", [])
    with transaction.atomic():
        job = ImportJob.objects.create(
            token=token, user_id=user_id, file_name=file_name[:255], total=len(valid) + len(others),
            labels=staged.get("labels", {}),
        )
        rows = [
            ImportRow(job=job, position=i, line=r["line"], payload={"values": r["values"], "code": r["code"],
                                                                     "cells": r.get("cells") or {}})
            for i, r in enumerate(ordered)
        ]
        rows += [
            ImportRow(job=job, position=len(ordered) + i, line=r["line"], state=r["state"], note=r["note"][:300])
            for i, r in enumerate(others)
        ]
        ImportRow.objects.bulk_create(rows, batch_size=500)
    return job


# ---- the worker side --------------------------------------------------------------------------------

class _Codes:
    """Automatic codes for one batch, like next_patient_code: highest P- number + 1, skipping codes that have a
    folder. Counted in memory from the taken set; past P-999999 it asks next_patient_code (lowest free)."""

    def __init__(self, taken: set[str]) -> None:
        from apps.patients.services import _legacy_number

        self.taken = taken
        self.number = max((_legacy_number(c) for c in taken if c.startswith("P-")), default=-1) + 1

    def next(self) -> str:
        from apps.patients.services import MAX_CODE, next_patient_code, patient_code

        while self.number <= MAX_CODE:
            code = patient_code(self.number)
            self.number += 1
            if code not in self.taken and not patient_dir_exists(code):
                return code
        return next_patient_code(folder_exists=patient_dir_exists)

    def add(self, code: str) -> None:
        """A code just inserted: a chosen code above the highest moves the next automatic code past it."""
        from apps.patients.services import _legacy_number

        self.taken.add(code)
        self.number = max(self.number, _legacy_number(code) + 1)


def _payload(row: ImportRow) -> dict[str, Any]:
    payload: dict[str, Any] = row.payload or {}
    return payload


def _decide(row: ImportRow, taken: set[str], nids: set[str]) -> tuple[str, str] | None:
    code = _payload(row)["code"]
    nid = _payload(row)["values"].get("national_id")
    if code and code in taken:
        return "skipped", NOTE_CODE_TAKEN
    if code and patient_dir_exists(code):
        return "skipped", NOTE_CODE_FOLDER
    if nid and nid in nids:
        return "skipped", NOTE_NID_TAKEN
    return None


def _drop_new_folder(code: str) -> None:
    """A row whose transaction failed after its folder was made: remove the (still empty) folder so the code
    stays free. rmdir refuses a folder that holds anything."""
    try:
        patient_dir(code).rmdir()
    except OSError:
        pass


def _run_row(job: ImportJob, row: ImportRow, boxes: list[Any], taken: set[str], nids: set[str],
             codes: _Codes) -> None:
    from apps.patients import services as patient_services

    payload = _payload(row)
    decided = _decide(row, taken, nids)
    code = None
    try:
        with transaction.atomic():
            if decided is None:
                custom, error = check_cells(boxes, payload["cells"], confirm=True, labels=job.labels)
                if error:
                    decided = ("failed", error)
            if decided is None:
                values = from_json(payload["values"])
                code = payload["code"] or codes.next()
                patient = patient_services.create_with_code(values, job.user_id, code, audit_detail="import")
                write_custom_values(patient.pk, custom)
                decided = ("inserted", "")
            ImportRow.objects.filter(pk=row.pk, state="pending").update(
                state=decided[0], note=decided[1][:300], payload=None
            )
    except BoxError as err:  # a choice removed after the preview checked the row
        if code:
            _drop_new_folder(code)
        ImportRow.objects.filter(pk=row.pk, state="pending").update(state="failed", note=err.message[:300],
                                                                    payload=None)
        return
    except DatabaseError as err:
        if code:
            _drop_new_folder(code)
        if isinstance(err, OperationalError):
            raise  # the database is gone: the whole batch is retried
        # C8: the database refused this one row (a constraint, a bad value). Mark it and go on with the next row.
        log.warning("import job %s row %s refused: %s", job.pk, row.line, type(err).__name__)
        ImportRow.objects.filter(pk=row.pk, state="pending").update(state="failed", note=DB_REFUSED_NOTE,
                                                                    payload=None)
        return
    except BaseException:
        if code:
            _drop_new_folder(code)
        raise
    if decided[0] == "inserted" and code:
        codes.add(code)
        nid = payload["values"].get("national_id")
        if nid:
            nids.add(nid)


def counts(job: ImportJob) -> dict[str, int]:
    by_state = dict(job.rows.values_list("state").annotate(n=Count("id")).values_list("state", "n"))
    return {s: by_state.get(s, 0) for s in ("pending", "inserted", "skipped", "failed")}


def _close(job: ImportJob, status: str) -> None:
    c = counts(job)
    job.status = status
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "finished_at", "error", "attempts"])
    word = "done" if status == "done" else f"stopped ({job.error})"
    audit(job.user_id, "patient_import", None,
          f"job {job.pk} {word}: inserted {c['inserted']}, skipped {c['skipped']}, failed {c['failed']}, "
          f"pending {c['pending']}")


def run_batch(budget_s: float = BATCH_S) -> bool:
    """Work on the oldest unfinished job for about budget_s. Returns False when there was nothing to do."""
    job = ImportJob.objects.filter(status__in=["queued", "running"]).order_by("id").first()
    if job is None:
        return False
    if job.status == "queued":
        ImportJob.objects.filter(pk=job.pk).update(status="running")
        job.status = "running"
    rows = list(job.rows.filter(state="pending").order_by("position")[:BATCH_ROWS])
    if not rows:
        _close(job, "done")
        return True
    boxes = live_custom_boxes()
    try:
        with named_lock("patient_code"):
            taken = set(Patient.objects.values_list("code", flat=True))
            nids = {n for n in Patient.objects.values_list("national_id", flat=True) if n}
            codes = _Codes(taken)
            started = time.monotonic()
            for row in rows:
                _run_row(job, row, boxes, taken, nids, codes)
                if time.monotonic() - started >= budget_s:
                    break
    except LockBusy:
        return True  # someone is saving a patient; try again on the next turn
    except Exception as err:  # noqa: BLE001 - any failure is retried, then reported on the page
        job.attempts += 1
        job.error = type(err).__name__[:200]
        log.error("import job %s batch failed: %s", job.pk, job.error)
        if job.attempts >= MAX_ATTEMPTS:
            _close(job, "failed")
        else:
            job.save(update_fields=["attempts", "error"])
        return True
    if job.attempts:
        job.attempts, job.error = 0, ""
        job.save(update_fields=["attempts", "error"])
    if not job.rows.filter(state="pending").exists():
        _close(job, "done")
    return True


def run_all() -> None:
    """Run every unfinished job to its end (tests and `manage.py` use it; the worker calls run_batch)."""
    while run_batch():
        if not ImportJob.objects.filter(status__in=["queued", "running"]).exists():
            break


def resume(job: ImportJob) -> None:
    ImportJob.objects.filter(pk=job.pk, status="failed").update(status="queued", attempts=0, error="",
                                                               finished_at=None)


def sweep_jobs(now: Any = None) -> int:
    cutoff = (now or timezone.now()) - timedelta(days=KEEP_DAYS)
    deleted, _ = ImportJob.objects.filter(created_at__lt=cutoff).delete()
    return deleted


# ---- the page ---------------------------------------------------------------------------------------

def report(job: ImportJob) -> dict[str, Any]:
    c = counts(job)
    problems = list(job.rows.filter(state__in=["skipped", "failed"]).order_by("line").values("line", "state", "note"))
    return {
        "id": job.pk, "status": job.status, "fileName": job.file_name, "total": job.total,
        "done": job.total - c["pending"], "pending": c["pending"], "inserted": c["inserted"],
        "skipped": c["skipped"],
        "failed": [{"line": p["line"], "message": p["note"]} for p in problems if p["state"] == "failed"],
        "skippedRows": [{"line": p["line"], "message": p["note"]} for p in problems if p["state"] == "skipped"],
        "createdAt": present.dt(job.created_at), "finishedAt": present.dt(job.finished_at),
        "workerAlive": worker_alive(),
    }
