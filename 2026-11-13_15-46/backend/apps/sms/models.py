"""SMS credentials and the message queue and log (SPEC §4.1, §3.9).

A unique functional index on (kind = reminder: visit|stamp) means one reminder per visit and schedule, even
across restarts or a second worker. It is an index, not a generated column, so backups written by the MariaDB
mysqldump in the image load back into MySQL.
"""

from django.conf import settings
from django.db import models
from django.db.models import Case, CharField, Q, Value, When
from django.db.models.functions import Cast, Concat

from apps.patients.models import Patient
from apps.visits.models import Visit

SMS_KINDS = ["reminder", "custom", "bulk", "alert", "test"]
# One value per (visit, stamp) for reminders, NULL for every other kind (NULLs never clash in a unique index).
REMINDER_KEY = Case(
    When(kind="reminder", then=Concat(Cast("visit_id", CharField()), Value("|"), "stamp", output_field=CharField())),
    default=None,
    output_field=CharField(),
)
SMS_STATUSES = ["pending", "sending", "sent", "failed", "skipped", "cancelled"]


class SmsCredential(models.Model):
    """One row (id 1): the clinic's own provider key, AES-GCM text. The key file lives outside the
    database."""

    id = models.IntegerField(primary_key=True)
    secret = models.TextField()
    hint = models.CharField(max_length=4)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        db_table = "sms_credentials"
        constraints = [models.CheckConstraint(condition=Q(id=1), name="sms_credentials_one_row")]


class SmsMessage(models.Model):
    kind = models.CharField(max_length=8)
    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, null=True, blank=True, related_name="sms_messages"
    )
    visit = models.ForeignKey(
        Visit, on_delete=models.CASCADE, null=True, blank=True, related_name="sms_messages"
    )
    stamp = models.CharField(max_length=16, null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    body = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=9, default="pending")
    reason = models.TextField(null=True, blank=True)
    due_at = models.BigIntegerField()  # epoch milliseconds, a straight port
    attempts = models.IntegerField(default=0)
    provider_id = models.CharField(max_length=64, null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "sms_messages"
        indexes = [
            models.Index(fields=["status", "due_at"], name="sms_status_due"),
            models.Index(fields=["patient", "id"], name="sms_patient_id"),
            models.Index(fields=["visit", "id"], name="sms_visit_id"),
        ]
        constraints = [
            models.UniqueConstraint(REMINDER_KEY, name="sms_reminder_once"),
            models.CheckConstraint(condition=Q(kind__in=SMS_KINDS), name="sms_kind_check"),
            models.CheckConstraint(condition=Q(status__in=SMS_STATUSES), name="sms_status_check"),
        ]
