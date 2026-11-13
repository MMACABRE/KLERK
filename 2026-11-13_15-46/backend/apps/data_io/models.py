"""Patient CSV imports run as a job (02-KNOWN-BUGS BUG-2).

The confirm step used to insert every row inside one web request, so a file bigger than about 3,500 rows ran
past gunicorn's 120 s timeout and the worker was killed part-way: the rows inserted so far stayed, the rest were
lost, and nobody was told. Now the confirm only records a job; the worker inserts its rows in short batches.

One ImportRow per file row. A row starts `pending` (valid in the preview) or already `skipped` / `failed` (the
preview's duplicates and invalid rows, kept so the final report lists every line). The worker turns a pending row
into `inserted`, `skipped` or `failed` in the same transaction that inserts the patient, so a crash at any moment
leaves each row either fully done or still pending, and a resumed job never inserts a row twice. The row's
patient values are cleared once it is done; only the line number and the reason stay.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.db.models import Q

JOB_STATUSES = ["queued", "running", "done", "failed"]
ROW_STATES = ["pending", "inserted", "skipped", "failed"]


class ImportJob(models.Model):
    token = models.CharField(max_length=36, unique=True)  # the preview token: confirming twice finds this job
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    file_name = models.CharField(max_length=255)
    status = models.CharField(max_length=10, default="queued")
    total = models.IntegerField()
    labels = models.JSONField(default=dict)  # custom box labels at preview time, for "box was deleted" notes
    error = models.CharField(max_length=200, blank=True, default="")  # exception class name only, never data
    attempts = models.IntegerField(default=0)  # batches that failed in a row
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "import_jobs"
        indexes = [models.Index(fields=["status", "id"], name="import_jobs_status")]
        constraints = [
            models.CheckConstraint(condition=Q(status__in=JOB_STATUSES), name="import_jobs_status_known"),
        ]


class ImportRow(models.Model):
    job = models.ForeignKey(ImportJob, on_delete=models.CASCADE, related_name="rows")
    position = models.IntegerField()  # processing order: rows with a chosen code first, then the others
    line = models.IntegerField()  # the line in the uploaded file
    state = models.CharField(max_length=10, default="pending")
    note = models.CharField(max_length=300, blank=True, default="")
    payload = models.JSONField(null=True)  # values, code and custom cells while pending; NULL once done

    class Meta:
        db_table = "import_rows"
        constraints = [
            models.UniqueConstraint(fields=["job", "position"], name="import_rows_job_position"),
            models.CheckConstraint(condition=Q(state__in=ROW_STATES), name="import_rows_state_known"),
        ]
        indexes = [models.Index(fields=["job", "state", "position"], name="import_rows_job_state")]
