"""Visits: the timeline of a patient, past and planned (SPEC §4.1). A visit is also its bill (see
billing)."""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.patients.models import Patient

STATUS_CHOICES = [("scheduled", "scheduled"), ("done", "done"), ("cancelled", "cancelled")]
REMINDER_LEADS = ["none", "now", "h2", "d1", "d2"]


class Visit(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="visits")
    visit_date = models.DateField()
    visit_time = models.TimeField()
    duration_min = models.IntegerField(default=15)
    reason = models.CharField(max_length=200, null=True, blank=True)
    notes = models.CharField(max_length=1000, null=True, blank=True)
    status = models.CharField(max_length=10, default="scheduled", choices=STATUS_CHOICES)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    doctor_note = models.TextField(null=True, blank=True)
    disc_kind = models.CharField(max_length=7, null=True, blank=True)
    disc_value = models.BigIntegerField(default=0)
    reminder_lead = models.CharField(max_length=4, null=True, blank=True)

    class Meta:
        db_table = "visits"
        indexes = [
            models.Index(fields=["visit_date", "visit_time"], name="visits_when"),
            models.Index(fields=["patient", "visit_date"], name="visits_patient_date"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(duration_min__gte=5, duration_min__lte=90), name="visits_duration_check"
            ),
            models.CheckConstraint(
                condition=Q(status__in=["scheduled", "done", "cancelled"]),
                name="visits_status_check",
            ),
            models.CheckConstraint(
                condition=Q(disc_kind__in=["amount", "percent"]) | Q(disc_kind__isnull=True),
                name="visits_disc_kind_check",
            ),
            models.CheckConstraint(condition=Q(disc_value__gte=0), name="visits_disc_value_check"),
            models.CheckConstraint(
                condition=Q(reminder_lead__in=REMINDER_LEADS) | Q(reminder_lead__isnull=True),
                name="visits_reminder_lead_check",
            ),
        ]
