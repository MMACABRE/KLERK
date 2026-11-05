"""Site-wide settings (legacy src/lib/settings.js). Key/value rows; DEFAULTS is the allowed-key list.

Upsert (SPEC §4.3): the row is created if missing, then locked before it is written, so two writers of one
key never interleave. An unknown key is refused."""

from __future__ import annotations

from typing import Any

from django.db import transaction

from apps.core.models import Setting
from apps.core.qty import round_qty

DEFAULT_TEMPLATE = "{نام} عزیز، نوبت شما {تاریخ} ساعت {ساعت} ثبت شده است."

DEFAULTS: dict[str, str] = {
    "currency": "T",
    "low_warn": "10",
    "low_crit": "5",
    "clinic_name": "KLERK | کلرک",
    "clinic_address": "",
    "clinic_phone": "",
    "sms_enabled": "0",
    "sms_line": "90008361",
    "sms_lead": "d1",
    "sms_hour": "17",
    "sms_template": DEFAULT_TEMPLATE,
    "sms_alert_phone": "",
    "sms_low_threshold": "10",
    "sms_low_alerted": "0",
    "sms_balance": "",
    "sms_balance_at": "",
}


def _num(text: str) -> float:
    try:
        return float(text)
    except ValueError:
        return 0.0


def get_settings() -> dict[str, Any]:
    s: dict[str, Any] = dict(DEFAULTS)
    s.update({row.key: row.value for row in Setting.objects.all()})
    s["currency"] = "R" if s["currency"] == "R" else "T"
    s["low_warn"] = max(0.0, round_qty(_num(str(s["low_warn"]))))
    s["low_crit"] = max(0.0, round_qty(_num(str(s["low_crit"]))))
    return s


def clinic_name() -> str:
    value = Setting.objects.filter(pk="clinic_name").values_list("value", flat=True).first()
    return value or DEFAULTS["clinic_name"]


def set_setting(key: str, value: str) -> None:
    if key not in DEFAULTS:
        raise KeyError(f"unknown setting {key}")
    Setting.objects.get_or_create(key=key, defaults={"value": ""})
    with transaction.atomic():
        row = Setting.objects.select_for_update().get(pk=key)
        row.value = str(value)
        row.save()


def set_settings(values: dict[str, Any]) -> None:
    for key, value in values.items():
        set_setting(key, str(value))
