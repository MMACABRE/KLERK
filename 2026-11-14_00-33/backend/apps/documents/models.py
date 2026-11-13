"""Document metadata (SPEC §4.1). The patient folder on disk is the source of truth for which files
exist."""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.patients.models import Patient

CATEGORY_CHOICES = [
    ("consent", "consent"),
    ("lab", "lab"),
    ("imaging", "imaging"),
    ("surgery", "surgery"),
    ("other", "other"),
]


class Document(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="documents")
    filename = models.CharField(max_length=255)
    category = models.CharField(max_length=10, default="other", choices=CATEGORY_CHOICES)
    title = models.CharField(max_length=200, null=True, blank=True)
    doc_date = models.DateField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "documents"
        constraints = [
            models.UniqueConstraint(
                fields=["patient", "filename"], name="documents_patient_filename"
            ),
            models.CheckConstraint(
                condition=Q(category__in=["consent", "lab", "imaging", "surgery", "other"]),
                name="documents_category_check",
            ),
        ]
