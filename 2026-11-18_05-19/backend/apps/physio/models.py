"""Physiotherapy (SPEC §15.2): a course of prescribed sessions and the sessions ticked so far.

A course's state is never stored: it is unfinished while its ticked sessions are fewer than its count. Ticked
numbers are always 1 to done with no gaps (apps.physio.logic keeps that)."""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.patients.models import Patient

MAX_SESSIONS = 50


class PhysioCourse(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="physio_courses")
    sessions = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        db_table = "physio_courses"
        indexes = [models.Index(fields=["patient", "created_at"], name="physio_courses_patient")]
        constraints = [
            models.CheckConstraint(
                condition=Q(sessions__gte=1, sessions__lte=MAX_SESSIONS), name="physio_courses_sessions_check"
            ),
        ]


class PhysioSession(models.Model):
    course = models.ForeignKey(PhysioCourse, on_delete=models.CASCADE, related_name="ticks")
    number = models.PositiveSmallIntegerField()
    date = models.DateField()
    ticked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    ticked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "physio_sessions"
        constraints = [
            models.UniqueConstraint(fields=["course", "number"], name="physio_sessions_course_number"),
            models.CheckConstraint(
                condition=Q(number__gte=1, number__lte=MAX_SESSIONS), name="physio_sessions_number_check"
            ),
        ]
