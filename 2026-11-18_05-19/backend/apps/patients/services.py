"""Patient writes the routes run (SPEC §4.3): creation, code change, edit and deletion.

The code is computed like legacy nextPatientCode (src/lib/patient-store.js): highest numeric P-
code + 1, skipping codes that have a folder on disk, wrapping to the lowest free code at
P-999999. The code is separate from the row id. Creation and code change run under the named lock
'patient_code' (outside any transaction), with UNIQUE(code) as the backstop.

These functions take plain values and a user id and return the patient; the views parse the request, pick the
Persian message and build the HTTP answer. Errors are ServiceError subclasses (apps.core.errors); a refused
custom value is BoxError (apps.patients.custom_boxes)."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from typing import Any

from django.db import transaction

from apps.billing.ops import patient_has_payments, release_stock
from apps.billing.services import HasPaymentsError, lock_visits
from apps.core.audit import audit
from apps.core.codes import require_code
from apps.core.errors import Conflict
from apps.core.files import ensure_patient_dir, patient_dir, patient_dir_exists, trash_patient_folder
from apps.core.locks import get_for_update, named_lock
from apps.patients.custom_boxes import write_custom_values
from apps.patients.models import Patient
from apps.patients.validation import FORM_FIELDS
from apps.visits.models import Visit

FolderCheck = Callable[[str], bool]

MAX_CODE = 999_999
_LEADING_DIGITS = re.compile(r"\d*")
SAVED_FIELDS = {*FORM_FIELDS, "sms_optout"}


class CodeTakenError(Conflict):
    """The code is held by another patient or has a folder left on disk. `message` is the Persian text."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class FolderMoveError(Conflict):
    """A code change could not move the patient's folder; nothing was changed."""


def patient_code(number: int) -> str:
    return f"P-{number:06d}"


def _legacy_number(code: str) -> int:
    """CAST(substr(code, 3) AS INTEGER) as the legacy SQL did it: the leading digits, or 0."""
    digits = _LEADING_DIGITS.match(code[2:])
    return int(digits.group(0)) if digits and digits.group(0) else 0


def next_patient_code(*, folder_exists: FolderCheck) -> str:
    """The next free code (legacy nextPatientCode). Raises Conflict when every code is taken or has
    a folder."""
    numbers = [
        _legacy_number(c)
        for c in Patient.objects.filter(code__startswith="P-").values_list("code", flat=True)
    ]
    number = max(numbers, default=-1) + 1
    while number <= MAX_CODE and folder_exists(patient_code(number)):
        number += 1
    if number <= MAX_CODE:
        return patient_code(number)
    # Nothing is left above the highest code (a row or a hand change may hold P-999999): take the
    # lowest code that no patient holds and no folder uses.
    held = set(Patient.objects.values_list("code", flat=True))
    for candidate in range(MAX_CODE + 1):
        code = patient_code(candidate)
        if code not in held and not folder_exists(code):
            return code
    raise Conflict("patient codes are exhausted")


def code_taken_message(code: str) -> str | None:
    """Why `code` cannot be given out (another patient holds it, or its folder is still on disk), or None."""
    if Patient.objects.filter(code=code).exists():
        return f"کد {code} مال بیمار دیگری است."
    if patient_dir_exists(code):
        return f"پوشه‌ی {code} روی سرور هنوز وجود دارد (پرونده‌ی حذف‌شده یا کپی دستی)؛ این کد داده نمی‌شود."
    return None


# ---- create -----------------------------------------------------------------------------------------

def create_with_code(values: dict[str, Any], user_id: int, code: str, audit_detail: str | None = None) -> Patient:
    """The row, the folder and the audit row for a code already checked free. The caller holds the
    `patient_code` lock and runs this inside a transaction (the CSV import job does it per row)."""
    clean = {k: v for k, v in values.items() if k in SAVED_FIELDS}
    patient = Patient.objects.create(code=code, updated_by_id=user_id, **clean)
    ensure_patient_dir(code)
    audit(user_id, "patient_create", patient.pk, audit_detail or code)
    return patient


def insert_patient(values: dict[str, Any], user_id: int, chosen: str | None = None, audit_detail: str | None = None,
                   *, writes: dict[int, str | None] | None = None, staged: list[Any] | None = None,
                   meta: dict[str, Any] | None = None) -> Patient:
    """insertPatient: the next free code (or the chosen one), the folder, the audit row, the custom values and the
    staged files; all or nothing (ADR-0007), under the code lock. On failure the files moved into the new folder
    and the folder itself are removed, so the code stays free. A chosen code that is taken is CodeTakenError."""
    from apps.documents.services import save_document

    with named_lock("patient_code"):
        code: str | None = None
        placed: list[str] = []
        try:
            with transaction.atomic():
                if chosen:
                    taken = code_taken_message(chosen)
                    if taken:
                        raise CodeTakenError(taken)
                    code = chosen
                else:
                    code = next_patient_code(folder_exists=patient_dir_exists)
                patient = create_with_code(values, user_id, code, audit_detail)
                if writes is not None:
                    write_custom_values(patient.pk, writes)
                for up in staged or []:
                    save_document(patient, up, meta or {}, user_id, placed)
                return patient
        except BaseException:
            _remove_new_folder(code, placed)
            raise


def _remove_new_folder(code: str | None, placed: list[str]) -> None:
    if code is None:
        return
    folder = patient_dir(code)
    for name in placed:
        (folder / name).unlink(missing_ok=True)
    try:
        folder.rmdir()
    except OSError:
        pass


# ---- edit, code change, delete ----------------------------------------------------------------------

def save_patient(patient_id: int, values: dict[str, Any], writes: dict[int, str | None], user_id: int,
                 changed: list[str]) -> Patient:
    """Write the form fields and custom values; locks the patient row, then the boxes (write_custom_values).
    Audits the edit, and an archive or unarchive when the status flipped."""
    with transaction.atomic():
        locked = get_for_update(Patient.objects.all(), patient_id, "patient")
        was_archived = locked.status == "archived"
        for k, v in values.items():
            if k in SAVED_FIELDS:
                setattr(locked, k, v)
        locked.updated_by_id = user_id
        locked.save()
        write_custom_values(locked.pk, writes)
        audit(user_id, "patient_edit", locked.pk, ",".join(changed))
        if "status" in values and (values["status"] == "archived") != was_archived:
            audit(user_id, "patient_archive" if values["status"] == "archived" else "patient_unarchive", locked.pk)
        return locked


def change_code(patient_id: int, new: str, user_id: int) -> Patient:
    """Give a patient another (already parsed) code and move its folder. A taken code is CodeTakenError; any other
    failure undoes the folder move and is FolderMoveError. A text that is not a code is BadCodeError."""
    require_code(new)
    moved: tuple[Any, Any] | None = None
    try:
        with named_lock("patient_code"), transaction.atomic():
            locked = get_for_update(Patient.objects.all(), patient_id, "patient")
            taken = code_taken_message(new)
            if taken:
                raise CodeTakenError(taken)
            old = locked.code
            locked.code = new
            locked.updated_by_id = user_id
            locked.save()
            audit(user_id, "patient_code", locked.pk, f"{old} → {new}")
            src, dst = patient_dir(old), patient_dir(new)
            if src.exists():
                os.replace(src, dst)
                moved = (src, dst)
            else:
                ensure_patient_dir(new)
            return locked
    except CodeTakenError:
        raise
    except Exception as err:
        if moved:
            try:
                os.replace(moved[1], moved[0])
            except OSError:
                pass
        raise FolderMoveError(f"patient {patient_id}: code change failed") from err


def delete_patient(patient_id: int, user_id: int) -> Patient:
    """Delete a patient and its visits, unless any visit has a payment (HasPaymentsError). Locks the patient row,
    then its visits; the folder goes to the trash after the commit."""
    with transaction.atomic():
        locked = get_for_update(Patient.objects.all(), patient_id, "patient")
        ids = list(Visit.objects.filter(patient=locked).values_list("id", flat=True))
        lock_visits(ids)
        if patient_has_payments(locked.pk):
            raise HasPaymentsError(f"patient {patient_id} has payments")
        code, pk = locked.code, locked.pk
        release_stock(ids, None)
        locked.delete()
        audit(user_id, "patient_delete", pk, code)
    trash_patient_folder(code)
    locked.pk = pk
    return locked
