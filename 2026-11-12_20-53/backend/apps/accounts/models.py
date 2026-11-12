"""Users, sign-in attempts and sessions (SPEC §4.1, §3.4, §3.5).

`username` is stored as typed (exact, NO PAD binary collation); `username_key` is its ASCII-folded
key
(apps.core.text.nocase_key), unique, and is what sign-in and the NOCASE order use (ADR-0012).
A unique functional index on `CASE WHEN is_owner THEN 1 END` allows at most one owner. It is an index, not a
generated column, so backups written by the MariaDB mysqldump in the image load back into MySQL.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.db.models import Case, IntegerField, Q, Value, When

from apps.core.text import nocase_key


class User(models.Model):
    ROLE_ADMIN = "admin"
    ROLE_STAFF = "staff"
    ROLES = [(ROLE_ADMIN, "admin"), (ROLE_STAFF, "staff")]

    username = models.CharField(max_length=80, unique=True)
    username_key = models.CharField(max_length=80, unique=True, editable=False)
    display_name = models.CharField(max_length=80)
    # History only: the permissions below decide access.
    role = models.CharField(max_length=10, choices=ROLES)
    password = models.CharField(max_length=255)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    perms = models.JSONField(default=dict)
    is_owner = models.BooleanField(default=False)

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["display_name"]

    class Meta:
        db_table = "users"
        constraints = [
            models.UniqueConstraint(
                Case(When(is_owner=True, then=Value(1)), default=None, output_field=IntegerField()),
                name="users_one_owner",
            ),
            models.CheckConstraint(
                condition=Q(role__in=["admin", "staff"]), name="users_role_check"
            ),
            models.CheckConstraint(
                condition=Q(active__in=[True, False]), name="users_active_check"
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.username_key = nocase_key(self.username)
        super().save(*args, **kwargs)

    def set_password(self, raw: str) -> None:
        self.password = make_password(raw)

    def check_password(self, raw: str) -> bool:
        """Django's check. A legacy hash that matches is re-hashed with the preferred hasher."""

        def rehash(new_raw: str) -> None:
            self.set_password(new_raw)
            self.save(update_fields=["password"])

        return check_password(raw, self.password, rehash)

    def __str__(self) -> str:
        return self.username


class LoginAttempt(models.Model):
    key = models.CharField(max_length=200)
    ip = models.CharField(max_length=200)
    ts = models.BigIntegerField()  # epoch milliseconds, a straight port of the legacy row

    class Meta:
        db_table = "login_attempts"
        indexes = [
            models.Index(fields=["key", "ts"], name="login_attempts_key_ts"),
            models.Index(fields=["ip", "ts"], name="login_attempts_ip_ts"),
        ]


class UserSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sessions")
    session_key = models.CharField(max_length=40, unique=True)

    class Meta:
        db_table = "user_sessions"
