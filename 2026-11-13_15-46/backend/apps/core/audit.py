"""audit(user_id, action, patient_id, detail) (SPEC §2.7). Never patient field values or passwords in detail."""

from __future__ import annotations

from apps.core.models import AuditLog


def audit(user_id: int | None, action: str, patient_id: int | None = None, detail: str | None = None) -> None:
    AuditLog.objects.create(user_id=user_id, action=action, patient_id=patient_id, detail=detail)
