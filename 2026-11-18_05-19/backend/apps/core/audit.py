"""audit(user_id, action, patient_id, detail) (SPEC §2.7). Never patient field values or passwords in detail."""

from __future__ import annotations

from apps.core.labels import AUDIT_ACTIONS as LEGACY_ACTIONS
from apps.core.models import AuditLog

# Actions the new app adds (SPEC §14): labels for the audit page and its filter. labels.py is generated from the
# legacy code and is not edited by hand.
NEW_ACTIONS: dict[str, str] = {
    "setting_change": "تغییر تنظیمات",
    "folder_create": "ساخت پوشه‌ی اسناد",
    "folder_rename": "تغییر نام پوشه‌ی اسناد",
    "folder_delete": "حذف پوشه‌ی اسناد",
    # Diagnostics feed (ADR-0013)
    "diag_on": "روشن کردن عیب‌یابی",
    "diag_renew": "تمدید کلید عیب‌یابی",
    "diag_off": "خاموش کردن عیب‌یابی",
    "diag_expired": "پایان مهلت عیب‌یابی",
    "diag_read": "خواندن عیب‌یابی",
    # Physiotherapy (SPEC §15.7): detail is the patient code, course id and session number only.
    "physio_create": "ساخت دوره‌ی فیزیوتراپی",
    "physio_count": "تغییر تعداد جلسه‌های فیزیوتراپی",
    "physio_delete": "حذف دوره‌ی فیزیوتراپی",
    "physio_tick": "ثبت جلسه‌ی فیزیوتراپی",
    "physio_date": "تغییر تاریخ جلسه‌ی فیزیوتراپی",
    "physio_untick": "برداشتن جلسه‌ی فیزیوتراپی",
}
AUDIT_ACTIONS: dict[str, str] = {**LEGACY_ACTIONS, **NEW_ACTIONS}


def audit(user_id: int | None, action: str, patient_id: int | None = None, detail: str | None = None) -> None:
    AuditLog.objects.create(user_id=user_id, action=action, patient_id=patient_id, detail=detail)
