"""Patients, their medications, the id sequence, layouts, custom boxes and their values (SPEC §4.1,
§2.2).

Field sizes are the legacy patient form's limits (src/lib/patient-form.js). Every text that is
compared by key
has a key column, set by apply_keys() on every save (see apps/patients/keys.py).
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.patients.keys import apply_keys, key_of

SEX_CHOICES = [("female", "female"), ("male", "male")]
STATUS_CHOICES = [
    ("active", "active"),
    ("pending", "pending"),
    ("critical", "critical"),
    ("archived", "archived"),
]
DISC_CHOICES = [("amount", "amount"), ("percent", "percent")]
BOX_TYPES = [
    ("short_text", "short_text"),
    ("long_text", "long_text"),
    ("number", "number"),
    ("date", "date"),
    ("choice", "choice"),
    ("yes_no", "yes_no"),
]
LAYOUT_NAMES = [("patient_form", "patient_form"), ("dashboard", "dashboard")]


class Patient(models.Model):
    code = models.CharField(max_length=8, unique=True)  # P-000123; the folder name, not the row id
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    father_name = models.CharField(max_length=80, null=True, blank=True)
    national_id = models.CharField(max_length=20, null=True, blank=True, db_index=True)
    birth_date = models.DateField(null=True, blank=True)
    sex = models.CharField(max_length=6, choices=SEX_CHOICES, null=True, blank=True)
    phone = models.CharField(max_length=30, null=True, blank=True)
    email = models.CharField(max_length=254, null=True, blank=True)
    address = models.CharField(max_length=2000, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    emergency_name = models.CharField(max_length=100, null=True, blank=True)
    emergency_phone = models.CharField(max_length=30, null=True, blank=True)
    emergency_relation = models.CharField(max_length=60, null=True, blank=True)
    insurance_name = models.CharField(max_length=100, null=True, blank=True)
    insurance_number = models.CharField(max_length=60, null=True, blank=True)
    status = models.CharField(
        max_length=10, default="active", choices=STATUS_CHOICES, db_index=True
    )
    blood_type = models.CharField(max_length=3, null=True, blank=True)
    allergies = models.CharField(max_length=1000, null=True, blank=True)
    conditions = models.CharField(max_length=1000, null=True, blank=True)
    medical_notes = models.TextField(max_length=5000, null=True, blank=True)
    height_cm = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    weight_kg = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    blood_pressure = models.CharField(max_length=20, null=True, blank=True)
    visit_reason = models.CharField(max_length=1000, null=True, blank=True)
    referral = models.CharField(max_length=120, null=True, blank=True)
    photo = models.CharField(max_length=255, null=True, blank=True)
    disc_kind = models.CharField(max_length=7, null=True, blank=True, choices=DISC_CHOICES)
    disc_value = models.BigIntegerField(default=0)
    sms_optout = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # Search keys (SPEC §2.2), written by apply_keys(); never edited by hand.
    name_key = models.CharField(max_length=200, editable=False, db_index=True)
    father_name_key = models.CharField(max_length=200, editable=False)
    city_key = models.CharField(max_length=200, editable=False, db_index=True)
    allergies_key = models.CharField(max_length=1000, editable=False)
    conditions_key = models.CharField(max_length=1000, editable=False)
    visit_reason_key = models.CharField(max_length=1000, editable=False)
    referral_key = models.CharField(max_length=500, editable=False)
    # NOCASE sort keys (legacy `last_name COLLATE NOCASE, first_name COLLATE NOCASE`), ASCII fold
    # only (ADR-0012).
    last_name_sort = models.CharField(max_length=80, editable=False, default="")
    first_name_sort = models.CharField(max_length=80, editable=False, default="")

    class Meta:
        db_table = "patients"
        indexes = [
            models.Index(
                fields=["last_name_sort", "first_name_sort", "id"], name="patients_name_order"
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(sex__in=["female", "male"]) | Q(sex__isnull=True),
                name="patients_sex_check",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["active", "pending", "critical", "archived"]),
                name="patients_status_check",
            ),
            models.CheckConstraint(
                condition=Q(disc_kind__in=["amount", "percent"]) | Q(disc_kind__isnull=True),
                name="patients_disc_kind_check",
            ),
            models.CheckConstraint(
                condition=Q(disc_value__gte=0), name="patients_disc_value_check"
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        apply_keys(self)
        super().save(*args, **kwargs)


class Medication(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="medications")
    name = models.CharField(max_length=200)
    dosage = models.CharField(max_length=200, null=True, blank=True)
    frequency = models.CharField(max_length=200, null=True, blank=True)
    since = models.CharField(max_length=200, null=True, blank=True)

    class Meta:
        db_table = "medications"


class Layout(models.Model):
    """The saved patient form or dashboard layout. No row means the default layout (legacy layouts
    table)."""

    name = models.CharField(max_length=12, primary_key=True)
    current = models.JSONField()
    previous = models.JSONField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        db_table = "layouts"
        constraints = [
            models.CheckConstraint(
                condition=Q(name__in=["patient_form", "dashboard"]), name="layouts_name_check"
            ),
        ]


class CustomBox(models.Model):
    """A custom field. The id is never reused (AUTO_INCREMENT is persistent); choice_seq keeps
    choice ids unique."""

    type = models.CharField(max_length=10, choices=BOX_TYPES)
    label = models.CharField(max_length=60)
    choices = models.JSONField(null=True, blank=True)
    choice_seq = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "custom_boxes"
        constraints = [
            models.CheckConstraint(
                condition=Q(
                    type__in=["short_text", "long_text", "number", "date", "choice", "yes_no"]
                ),
                name="custom_boxes_type_check",
            ),
        ]


class PatientValue(models.Model):
    pk = models.CompositePrimaryKey("patient", "box")
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="values")
    box = models.ForeignKey(CustomBox, on_delete=models.PROTECT, related_name="values")
    value = models.TextField()
    value_key = models.TextField(editable=False)

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.value_key = key_of(self.value)
        super().save(*args, **kwargs)

    class Meta:
        db_table = "patient_values"
        # The index on (box_id, value_key(191)) is a prefix index: added by RunSQL in the migration.
