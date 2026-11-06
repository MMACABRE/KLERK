"""Settings store and the audit log (SPEC §4.1 settings, audit_log; §2.7).

The audit log is append-only: no update or delete path in the code. Its patient_id has no foreign
key, so an
entry survives the patient's deletion (legacy rule).
"""

from django.conf import settings
from django.db import models


class Setting(models.Model):
    key = models.CharField(max_length=40, primary_key=True)
    value = models.TextField()

    class Meta:
        db_table = "settings"


class AuditLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    action = models.CharField(max_length=40)
    patient_id = models.BigIntegerField(null=True, blank=True)
    detail = models.TextField(null=True, blank=True)
    ts = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "audit_log"
