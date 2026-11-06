"""SMS engine (legacy src/lib/sms-engine.js): plans reminder rows, sends due rows, reads the balance, cleans old rows.

Runs in the worker only (one tick a minute). A row is claimed by `UPDATE ... WHERE status='pending'` with rowcount 1,
so two workers never send one row. Nothing here raises to the caller or logs a number, name, text or key.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from django.conf import settings as dj
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.core.settings_store import DEFAULT_TEMPLATE, get_settings, set_settings
from apps.core.text import normalize_text
from apps.patients.models import Patient
from apps.sms import provider
from apps.sms.credentials import ensure_key, open_secret, read_key, seal
from apps.sms.models import SmsCredential, SmsMessage
from apps.sms.rules import (
    LEAD_KEYS,
    in_window,
    ms,
    normalize_mobile,
    reminder_due,
    render_template,
    send_hour_of,
    validate_template,
    visit_date_text,
    visit_start,
    visit_time_text,
)
from apps.visits.logic import hhmm
from apps.visits.models import Visit

log = logging.getLogger("klerk.sms")

MAX_REMINDERS = 2
MAX_ATTEMPTS = 3
RETRY_MS = 5 * 60 * 1000
BALANCE_EVERY_MS = 30 * 60 * 1000
RETENTION_DAYS = 180
BATCH = 20
API_KEY_PATTERN = r"[A-Za-z0-9_.-]{20,200}"

REASON = {
    "optout": "بیمار پیامک نمی‌خواهد.",
    "archived": "پرونده‌ی بیمار بایگانی‌شده است.",
    "phone": "شماره‌ی موبایل معتبر نیست.",
    "cap": f"حداکثر {MAX_REMINDERS} یادآوری برای هر ویزیت ارسال می‌شود.",
    "late": "زمان ارسال گذشته است.",
    "unknown": "نتیجه نامشخص است.",
    "gone": "ویزیت دیگر برنامه‌ریزی‌شده نیست.",
    "noLead": "یادآوری برای این ویزیت برداشته شد.",
}
RECOVERABLE = {REASON["optout"], REASON["archived"], REASON["phone"]}

_last_retention_day: str = ""


def key_path() -> Path:
    return Path(dj.DATA_DIR) / "sms.key"


def load_key() -> str | None:
    row = SmsCredential.objects.filter(pk=1).first()
    if row is None:
        return None
    key = read_key(key_path())
    return open_secret(row.secret, key) if key else None


def key_info() -> dict[str, Any] | None:
    row = SmsCredential.objects.filter(pk=1).first()
    if row is None:
        return None
    return {"hint": row.hint, "updatedAt": row.updated_at, "usable": load_key() is not None}


def save_key(api_key: str, user_id: int | None) -> str | None:
    """None on success, else a Persian error. The key itself is never echoed."""
    import re

    value = (api_key or "").strip()
    if not re.fullmatch(API_KEY_PATTERN, value, re.ASCII):
        return "کلید واردشده درست نیست."
    key = ensure_key(key_path())
    if key is None:
        return "پرونده‌ی رمزنگاری کلید خراب است."
    SmsCredential.objects.update_or_create(
        pk=1, defaults={"secret": seal(value, key), "hint": value[-4:], "updated_by_id": user_id}
    )
    return None


def remove_key() -> None:
    SmsCredential.objects.filter(pk=1).delete()


def _now() -> datetime:
    return timezone.now()


def _template(s: dict[str, Any]) -> str:
    text, error = validate_template(s["sms_template"])
    return DEFAULT_TEMPLATE if error else text


def _lead_of(lead: str | None, s: dict[str, Any]) -> str:
    if lead in LEAD_KEYS:
        return str(lead)
    return s["sms_lead"] if s["sms_lead"] in LEAD_KEYS else "d1"


def block_reason(optout: bool, status: str, phone: str | None) -> str | None:
    if optout:
        return REASON["optout"]
    if status == "archived":
        return REASON["archived"]
    if not normalize_mobile(phone):
        return REASON["phone"]
    return None


def plan_reminders() -> dict[str, int]:
    s = get_settings()
    t = _now()
    send_hour = send_hour_of(s["sms_hour"])
    stats = {"created": 0, "moved": 0, "revived": 0, "cancelled": 0, "skipped": 0}
    stats["cancelled"] += SmsMessage.objects.filter(kind="reminder", status="pending").exclude(
        visit__status="scheduled"
    ).filter(visit__isnull=False).update(status="cancelled", reason=REASON["gone"])
    today = timezone.localdate()
    visits = Visit.objects.select_related("patient").filter(status="scheduled", visit_date__gte=today)
    for v in visits:
        rows = list(SmsMessage.objects.filter(kind="reminder", visit=v).order_by("id"))
        lead = _lead_of(v.reminder_lead, s)
        vt = hhmm(v.visit_time)
        stamp = f"{v.visit_date.isoformat()} {vt}"
        pending = [r for r in rows if r.status == "pending"]
        if lead == "none":
            for r in pending:
                SmsMessage.objects.filter(pk=r.pk).update(status="cancelled", reason=REASON["noLead"], due_at=ms(t))
                stats["cancelled"] += 1
            continue
        if visit_start(v.visit_date, vt) <= t:
            continue
        due_dt = reminder_due(lead, v.visit_date, vt, send_hour, t)
        assert due_dt is not None
        due = ms(due_dt)
        p = v.patient
        block = block_reason(p.sms_optout, p.status, p.phone)
        same = next((r for r in rows if r.stamp == stamp), None)
        if same:
            if same.status == "pending":
                if block:
                    SmsMessage.objects.filter(pk=same.pk).update(status="skipped", reason=block, due_at=due)
                    stats["skipped"] += 1
                elif lead != "now":
                    SmsMessage.objects.filter(pk=same.pk, attempts=0).update(due_at=due)
            elif (same.status == "skipped" and same.reason in RECOVERABLE) or same.status == "cancelled":
                if not block:
                    SmsMessage.objects.filter(pk=same.pk).update(status="pending", reason=None, due_at=due)
                    stats["revived"] += 1
            continue
        waiting = pending[0] if pending else None
        if waiting:
            if block:
                SmsMessage.objects.filter(pk=waiting.pk).update(status="skipped", reason=block, stamp=stamp, due_at=due)
            else:
                SmsMessage.objects.filter(pk=waiting.pk).update(
                    status="pending", reason=None, stamp=stamp, due_at=waiting.due_at if lead == "now" else due
                )
            stats["moved"] += 1
            continue
        counted = sum(1 for r in rows if r.status in ("pending", "sending", "sent", "failed"))
        try:
            with transaction.atomic():
                if counted >= MAX_REMINDERS:
                    SmsMessage.objects.create(kind="reminder", patient=p, visit=v, stamp=stamp, status="skipped",
                                              reason=REASON["cap"], due_at=due)
                    stats["skipped"] += 1
                elif block:
                    SmsMessage.objects.create(kind="reminder", patient=p, visit=v, stamp=stamp, status="skipped",
                                              reason=block, due_at=due)
                    stats["skipped"] += 1
                else:
                    SmsMessage.objects.create(
                        kind="reminder", patient=p, visit=v, stamp=stamp, status="pending", due_at=due
                    )
                    stats["created"] += 1
        except IntegrityError:
            pass  # another worker planned the same (visit, stamp): the unique reminder_key keeps one row
    return stats


def _finish(mid: int, status: str, reason: str | None = None, provider_id: str | None = None,
            body: str | None = None, phone: str | None = None) -> None:
    upd: dict[str, Any] = {"status": status, "reason": reason, "provider_id": provider_id,
                           "sent_at": _now() if status == "sent" else None}
    if body is not None:
        upd["body"] = body
    if phone is not None:
        upd["phone"] = phone
    SmsMessage.objects.filter(pk=mid).update(**upd)


def _prepare(row: SmsMessage, s: dict[str, Any]) -> dict[str, Any]:
    if row.kind != "reminder":
        p = Patient.objects.filter(pk=row.patient_id).values("sms_optout", "status").first() if row.patient_id else None
        if p and p["sms_optout"]:
            return {"skip": REASON["optout"]}
        if p and p["status"] == "archived":
            return {"skip": REASON["archived"]}
        return {"phone": row.phone, "body": row.body}
    v = Visit.objects.select_related("patient").filter(pk=cast(int, row.visit_id)).first()
    if v is None or v.status != "scheduled":
        return {"skip": REASON["gone"], "status": "cancelled"}
    vt = hhmm(v.visit_time)
    if visit_start(v.visit_date, vt) <= _now():
        return {"skip": REASON["late"]}
    patient = v.patient
    block = block_reason(patient.sms_optout, patient.status, patient.phone)
    if block:
        return {"skip": block}
    body = render_template(_template(s), {
        "name": normalize_text(f"{patient.first_name} {patient.last_name}"),
        "date": visit_date_text(v.visit_date),
        "time": visit_time_text(vt),
    })
    return {"phone": normalize_mobile(patient.phone), "body": body}


def process(row: SmsMessage, api_key: str, s: dict[str, Any]) -> str:
    claimed = SmsMessage.objects.filter(pk=row.pk, status="pending").update(
        status="sending", attempts=F("attempts") + 1
    )
    if claimed != 1:
        return "busy"
    attempts = row.attempts + 1
    job = _prepare(row, s)
    if job.get("skip"):
        _finish(row.pk, job.get("status", "skipped"), job["skip"])
        return "skipped"
    if not job.get("phone") or not job.get("body"):
        _finish(row.pk, "failed", REASON["phone"])
        return "failed"
    r = provider.send(api_key, s["sms_line"], job["phone"], job["body"])
    if r["ok"]:
        _finish(row.pk, "sent", None, r.get("id"), job["body"], job["phone"])
        return "sent"
    if r.get("retry") and attempts < MAX_ATTEMPTS:
        SmsMessage.objects.filter(pk=row.pk).update(status="pending", due_at=ms(_now()) + RETRY_MS, body=job["body"],
                                                    phone=job["phone"])
        return "requeued"
    _finish(row.pk, "failed", r.get("text"), None, job["body"], job["phone"])
    return "failed"


def send_due(api_key: str, s: dict[str, Any]) -> dict[str, int]:
    t = _now()
    out = {"sent": 0, "failed": 0, "skipped": 0, "requeued": 0}
    rows = SmsMessage.objects.filter(status="pending", due_at__lte=ms(t))
    if not in_window(t):
        rows = rows.exclude(kind="reminder")
    taken = 0
    for row in list(rows.order_by("due_at", "id")[: BATCH * 5]):
        if taken >= BATCH:
            break
        outcome = process(row, api_key, s)
        if outcome == "busy":
            continue
        taken += 1
        out[outcome] += 1
    return out


def send_one(mid: int) -> str:
    api_key = load_key()
    if not api_key:
        return "no-key"
    row = SmsMessage.objects.filter(pk=mid).first()
    if row is None:
        return "gone"
    try:
        return process(row, api_key, get_settings())
    except Exception as err:  # noqa: BLE001
        log.error("sms send failed: %s", type(err).__name__)
        return "failed"


def recover_stuck() -> int:
    return SmsMessage.objects.filter(status="sending").update(status="failed", reason=REASON["unknown"])


def retry(mid: int) -> bool:
    return SmsMessage.objects.filter(pk=mid, status="failed").update(
        status="pending", reason=None, attempts=0, due_at=ms(_now())
    ) == 1


def _iso_now() -> str:
    return _now().astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def refresh_balance(api_key: str, s: dict[str, Any] | None = None) -> dict[str, Any]:
    s = s or get_settings()
    r = provider.balance(api_key)
    if not r["ok"]:
        return r
    try:
        threshold = min(1000, max(1, int(str(s["sms_low_threshold"]).strip() or "10")))
    except ValueError:
        threshold = 10
    count = r["count"]
    count_text = str(int(count)) if float(count).is_integer() else str(count)
    update = {"sms_balance": count_text, "sms_balance_at": _iso_now()}
    if count <= threshold and s["sms_low_alerted"] != "1":
        phone = normalize_mobile(s["sms_alert_phone"])
        if phone:
            SmsMessage.objects.create(kind="alert", phone=phone, status="pending", due_at=ms(_now()),
                                      body=f"اعتبار پیامک کلینیک رو به پایان است؛ {count_text} پیام باقی مانده.")
            update["sms_low_alerted"] = "1"
    elif count > threshold and s["sms_low_alerted"] == "1":
        update["sms_low_alerted"] = "0"
    set_settings(update)
    return r


def purge_old() -> int:
    global _last_retention_day
    day = timezone.localdate().isoformat()
    if day == _last_retention_day:
        return 0
    _last_retention_day = day
    cutoff = _now() - timedelta(days=RETENTION_DAYS)
    keep = Q(kind="reminder", visit__status="scheduled")
    n, _ = SmsMessage.objects.filter(created_at__lt=cutoff).exclude(keep).delete()
    return n


def tick() -> dict[str, Any]:
    try:
        purge_old()
        s = get_settings()
        if s["sms_enabled"] != "1":
            return {"skipped": "off"}
        api_key = load_key()
        if not api_key:
            return {"skipped": "no-key"}
        plan = plan_reminders()
        sent = send_due(api_key, s)
        last = s["sms_balance_at"]
        try:
            last_ms = ms(datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)) if last else None
        except ValueError:
            last_ms = None
        balance = None
        if sent["sent"] > 0 or last_ms is None or not (ms(_now()) - last_ms < BALANCE_EVERY_MS):
            balance = refresh_balance(api_key, get_settings())
        return {"plan": plan, "sent": sent, "balanceOk": balance["ok"] if balance else None}
    except Exception as err:  # noqa: BLE001
        log.error("sms tick failed: %s", type(err).__name__)
        return {"skipped": "error"}


def planned_reminder_count(default_lead: str) -> int:
    today = timezone.localdate()
    n = 0
    for v in Visit.objects.select_related("patient").filter(status="scheduled", visit_date__gte=today):
        p = v.patient
        if (
            (v.reminder_lead or default_lead) != "none" and not p.sms_optout and p.status != "archived"
            and normalize_mobile(p.phone)
        ):
            n += 1
    return n
