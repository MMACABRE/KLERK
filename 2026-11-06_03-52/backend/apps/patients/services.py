"""Patient rows and what hangs off them: creation, code change, deletion, custom values and layouts
(SPEC §4.3).

The code is computed like legacy nextPatientCode (src/lib/patient-store.js): highest numeric P-
code + 1, skipping codes that have a folder on disk, wrapping to the lowest free code at
P-999999. The code is separate from the row id. Creation and code change run under the named lock
'patient_code' (outside any transaction), with UNIQUE(code) as the backstop and one retry.

Errors are ServiceError subclasses only (apps.core.errors)."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.billing.models import Payment
from apps.billing.services import HasPaymentsError, lock_visits
from apps.core.codes import require_code
from apps.core.errors import Conflict, Invalid, NotFound
from apps.core.locks import get_for_update, named_lock
from apps.patients.models import CustomBox, Layout, Patient, PatientValue
from apps.visits.models import Visit

FolderCheck = Callable[[str], bool]

MAX_CODE = 999_999
_LEADING_DIGITS = re.compile(r"\d*")


class CodeTakenError(Conflict):
    """The code is held by another patient or has a folder left on disk."""


class BoxGoneError(NotFound):
    """The custom box was deleted, so nothing may be written to it."""


class BoxInUseError(Conflict):
    """Patients hold a value in the box or the choice, so it cannot be removed."""


class NoSuchChoiceError(NotFound):
    """The choice id is not in the box."""


class ChoiceNotCurrentError(Invalid):
    """A value is not a current choice of its box."""


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


def create_patient(fields: dict[str, Any], *, folder_exists: FolderCheck) -> Patient:
    """Insert a patient with the next code. Retries once if UNIQUE(code) refuses the code a race
    chose."""
    with named_lock("patient_code"):
        for attempt in range(2):
            code = next_patient_code(folder_exists=folder_exists)
            try:
                with transaction.atomic():
                    return Patient.objects.create(code=code, **fields)
            except IntegrityError as exc:
                if Patient.objects.filter(code=code).exists():
                    if attempt == 0:
                        continue
                    raise CodeTakenError(code) from None
                raise Invalid(f"patient could not be saved: {exc}") from None
    raise Conflict(
        "patient code could not be assigned"
    )  # pragma: no cover - the loop returns or raises


def change_patient_code(patient_id: int, new_code: str, *, folder_exists: FolderCheck) -> Patient:
    """Give a patient another code. Refused when another row or a folder on disk already has it."""
    code = require_code(new_code)
    with named_lock("patient_code"), transaction.atomic():
        patient = get_for_update(Patient.objects.all(), patient_id, "patient")
        taken_by_other = Patient.objects.filter(code=new_code).exclude(pk=patient_id).exists()
        if taken_by_other or folder_exists(new_code):
            raise CodeTakenError(new_code)
        patient.code = code
        patient.save()
        return patient


def delete_patient(patient_id: int) -> None:
    """Delete a patient and its visits, unless any visit has a payment. Locks the patient row, then
    its visits."""
    with transaction.atomic():
        patient = get_for_update(Patient.objects.all(), patient_id, "patient")
        visit_ids = list(Visit.objects.filter(patient=patient).values_list("pk", flat=True))
        lock_visits(visit_ids)
        if Payment.objects.filter(visit_id__in=visit_ids).exists():
            raise HasPaymentsError(f"patient {patient_id} has payments")
        patient.delete()


def delete_custom_box(box_id: int) -> None:
    """Delete a custom box for good. Refused while any patient holds a value in it."""
    with transaction.atomic():
        box = get_for_update(CustomBox.objects.all(), box_id, "custom box")
        if box.deleted_at is not None:
            raise BoxGoneError(f"box {box_id} is already deleted")
        if PatientValue.objects.filter(box=box).exists():
            raise BoxInUseError(f"box {box_id} holds values")
        box.deleted_at = timezone.now()
        box.save(update_fields=["deleted_at"])


def remove_choice(box_id: int, choice_id: int) -> None:
    """Remove a choice from a choice box. Refused while any patient holds it. choice_seq keeps the
    id."""
    with transaction.atomic():
        box = get_for_update(CustomBox.objects.all(), box_id, "custom box")
        if box.deleted_at is not None:
            raise BoxGoneError(f"box {box_id} is deleted")
        choices: list[dict[str, Any]] = list(box.choices or [])
        if not any(c["id"] == choice_id for c in choices):
            raise NoSuchChoiceError(f"choice {choice_id} is not in box {box_id}")
        if PatientValue.objects.filter(box=box, value=str(choice_id)).exists():
            raise BoxInUseError(f"choice {choice_id} is held")
        box.choices = [c for c in choices if c["id"] != choice_id]
        box.choice_seq = max([box.choice_seq, choice_id, *(c["id"] for c in choices)])
        box.save(update_fields=["choices", "choice_seq"])


def _is_current_choice(box: CustomBox, value: str, held: str | None) -> bool:
    """A value of a choice box must name a current (not hidden) choice; a hidden one stays only if
    held already."""
    if value == "":
        return True
    if not value.isascii() or not value.isdigit():
        return False
    choice_id = int(value)
    live = {int(c["id"]) for c in (box.choices or []) if not c.get("hidden")}
    if choice_id in live:
        return True
    every = {int(c["id"]) for c in (box.choices or [])}
    return held == value and choice_id in every


def save_patient_values(patient_id: int, values: Mapping[int, str]) -> None:
    """Write a patient's custom values. Locks the patient row, then the boxes in ascending id. A
    deleted box, or a choice value that is not a current choice of its box, refuses the whole
    save."""
    with transaction.atomic():
        patient = get_for_update(Patient.objects.all(), patient_id, "patient")
        boxes = list(
            CustomBox.objects.select_for_update().filter(pk__in=sorted(values)).order_by("pk")
        )
        if len(boxes) != len(values) or any(b.deleted_at is not None for b in boxes):
            raise BoxGoneError(f"patient {patient.pk}: a box is gone")
        for box in boxes:
            row = PatientValue.objects.filter(patient=patient, box=box).first()
            held = row.value if row is not None else None
            if box.type == "choice" and not _is_current_choice(box, values[box.pk], held):
                raise ChoiceNotCurrentError(f"box {box.pk}: value is not a current choice")
            if row is None:
                row = PatientValue(patient=patient, box=box, value="")
            row.value = values[box.pk]
            row.save()


def save_layout(name: str, current: Any) -> Layout:
    """Save a layout; the layout it replaces becomes `previous`. The row is locked, so two saves
    never lose both."""
    Layout.objects.get_or_create(name=name, defaults={"current": {}})
    with transaction.atomic():
        layout = get_for_update(Layout.objects.all(), name, "layout")
        layout.previous = layout.current
        layout.current = current
        layout.save()
        return layout
