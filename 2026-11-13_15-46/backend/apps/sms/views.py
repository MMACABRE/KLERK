"""SMS API (SPEC §5.11; legacy src/routes/sms.js). Reminders are planned and sent by the worker (apps.sms.engine)."""

from __future__ import annotations

import re
from typing import Any

from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from apps.core import present
from apps.core.audit import audit
from apps.core.http import body, conflict, id_of, invalid, not_found, ok, page_args, paginate, route, text, user_of
from apps.core.jalali import fa_digits
from apps.core.perms import has
from apps.core.settings_store import DEFAULT_TEMPLATE, get_settings, set_settings
from apps.core.text import normalize_text, to_ascii_digits
from apps.patients.models import Patient
from apps.patients.views import SMS_KIND_LABEL, SMS_STATUS_LABEL, find_patient
from apps.search import query as sq
from apps.search.models import SavedSearch
from apps.search.views import stored_query
from apps.sms import engine, provider
from apps.sms.models import SmsMessage
from apps.sms.rules import (
    LEAD_KEYS,
    LEADS,
    MESSAGE_MAX,
    clean_text,
    normalize_mobile,
    render_template,
    sms_parts,
    validate_template,
    visit_date_text,
    visit_time_text,
)

PAGE_SIZE = 50
BULK_MAX = 500
WHY_LABEL = {"optout": "بیمار پیامک نمی‌خواهد", "archived": "پرونده بایگانی‌شده است", "phone": "شماره‌ی موبایل معتبر نیست"}
TEST_NOTICE = {
    "sent": "پیامک آزمایشی ارسال شد.",
    "failed": "پیامک آزمایشی ارسال نشد؛ دلیل در گزارش ارسال هست.",
    "no-key": "کلید پیامک ثبت نشده است.",
    "requeued": "اتصال به سامانه‌ی پیامک برقرار نشد؛ پیامک آزمایشی در صف ماند و چند دقیقه بعد دوباره فرستاده می‌شود.",
}
SENDER_LINE = re.compile(r"[A-Za-z0-9]{3,20}", re.ASCII)


def readiness() -> dict[str, Any]:
    s = get_settings()
    info = engine.key_info()
    return {"s": s, "info": info, "on": s["sms_enabled"] == "1", "hasKey": bool(info and info["usable"])}


def not_ready_text(r: dict[str, Any]) -> str | None:
    if not r["on"]:
        return "پیامک غیرفعال است. آن را از «تنظیمات» روشن کنید."
    if not r["hasKey"]:
        return "کلید پیامک ثبت نشده است."
    return None


def _ready_json(r: dict[str, Any]) -> dict[str, Any]:
    from datetime import UTC, datetime

    at = r["s"]["sms_balance_at"]
    try:
        at_text = present.dt(datetime.strptime(at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC))["text"] if at else ""  # type: ignore[index]
    except ValueError:
        at_text = ""
    return {"on": r["on"], "hasKey": r["hasKey"], "notReady": not_ready_text(r), "balance": r["s"]["sms_balance"],
            "balanceAt": at_text}


def log_view(request: HttpRequest) -> HttpResponse:
    q = request.GET
    status = q.get("status", "")
    status = status if status in SMS_STATUS_LABEL else ""
    kind = q.get("kind", "")
    kind = kind if kind in SMS_KIND_LABEL else ""
    rows = SmsMessage.objects.select_related("patient")
    if status:
        rows = rows.filter(status=status)
    if kind:
        rows = rows.filter(kind=kind)
    total = rows.count()
    page, size = page_args(request, PAGE_SIZE)
    pg = paginate(total, page, size)
    s = (pg["page"] - 1) * size
    from datetime import UTC, datetime

    return ok({
        "data": [
            {"id": m.pk, "kind": m.kind, "kindLabel": SMS_KIND_LABEL[m.kind], "status": m.status,
             "statusLabel": SMS_STATUS_LABEL[m.status][0], "statusChip": SMS_STATUS_LABEL[m.status][1],
             "reason": m.reason, "phone": m.phone, "body": m.body, "attempts": m.attempts,
             "due": present.dt(datetime.fromtimestamp(m.due_at / 1000, UTC)), "sentAt": present.dt(m.sent_at),
             "createdAt": present.dt(m.created_at),
             "patient": {"code": m.patient.code, "firstName": m.patient.first_name, "lastName": m.patient.last_name}
             if m.patient else None}
            for m in rows.order_by("-id")[s : s + size]
        ],
        "pagination": pg, "status": status, "kind": kind,
        "kinds": SMS_KIND_LABEL, "statuses": {k: v[0] for k, v in SMS_STATUS_LABEL.items()},
        "ready": _ready_json(readiness()),
    })


def retry(request: HttpRequest, mid: str) -> HttpResponse:
    me = user_of(request)
    row = SmsMessage.objects.filter(pk=id_of(mid)).values("id", "patient_id").first()
    if row is None:
        raise not_found("پیام مورد نظر پیدا نشد.")
    if engine.retry(row["id"]):
        audit(me.id, "sms_retry", row["patient_id"])
    return ok()


def _sample(template: str) -> str:
    _, err = validate_template(template)
    t = DEFAULT_TEMPLATE if err else template
    return render_template(t, {
        "name": "علی رضایی", "date": visit_date_text(timezone.localdate()),
        "time": visit_time_text("09:30"),
    })


def get_settings_view(request: HttpRequest) -> HttpResponse:
    me = user_of(request)
    r = readiness()
    s = r["s"]
    can_key = has(me, "sms_key")
    out: dict[str, Any] = {
        "settings": {"smsEnabled": s["sms_enabled"] == "1", "smsLine": s["sms_line"], "smsLead": s["sms_lead"],
                     "smsHour": s["sms_hour"], "smsTemplate": s["sms_template"], "smsBalance": s["sms_balance"],
                     "smsBalanceAt": s["sms_balance_at"]},
        "planned": engine.planned_reminder_count(s["sms_lead"] if s["sms_lead"] in LEAD_KEYS else "d1"),
        "leads": LEADS, "canKey": can_key, "sample": _sample(s["sms_template"]),
        "tokensSample": {
            "name": "علی رضایی", "date": visit_date_text(timezone.localdate()),
            "time": visit_time_text("09:30"),
        },
        "ready": _ready_json(r), "defaultTemplate": DEFAULT_TEMPLATE,
        "testNotices": TEST_NOTICE,
    }
    if can_key:
        info = r["info"]
        out["key"] = {
            "hint": info["hint"], "usable": info["usable"], "updatedAt": present.dt(info["updatedAt"]),
        } if info else None
        out["settings"].update({"smsAlertPhone": s["sms_alert_phone"], "smsLowThreshold": s["sms_low_threshold"]})
    return ok(out)


def put_settings(request: HttpRequest) -> HttpResponse:
    me = user_of(request)
    data = body(request)
    before = get_settings()
    can_key = has(me, "sms_key")
    errors: dict[str, str] = {}
    values: dict[str, str] = {}
    line = text(data, "smsLine").strip()
    if not SENDER_LINE.fullmatch(line):
        errors["smsLine"] = "شماره‌ی خط فرستنده باید ۳ تا ۲۰ حرف یا رقم لاتین باشد."
    values["sms_line"] = line
    lead = text(data, "smsLead")
    if lead not in LEAD_KEYS:
        errors["smsLead"] = "زمان پیش‌فرض یادآوری معتبر نیست."
    values["sms_lead"] = lead
    hour_text = to_ascii_digits(text(data, "smsHour")).strip()
    hour = int(hour_text) if re.fullmatch(r"\d{1,2}", hour_text, re.ASCII) else -1
    if not 8 <= hour <= 21:
        errors["smsHour"] = "ساعت ارسال باید بین ۸ و ۲۱ باشد."
    values["sms_hour"] = str(hour)
    tpl, tpl_err = validate_template(data.get("smsTemplate"))
    if tpl_err:
        errors["smsTemplate"] = tpl_err
    values["sms_template"] = tpl
    if can_key:
        alert = text(data, "smsAlertPhone").strip()
        phone = normalize_mobile(alert) if alert else ""
        if alert and not phone:
            errors["smsAlertPhone"] = "شماره‌ی موبایل هشدار معتبر نیست."
        values["sms_alert_phone"] = phone or ""
        th_text = to_ascii_digits(text(data, "smsLowThreshold")).strip()
        th = int(th_text) if re.fullmatch(r"\d{1,4}", th_text, re.ASCII) else -1
        if not 1 <= th <= 1000:
            errors["smsLowThreshold"] = "حد اعتبار باید عددی بین ۱ تا ۱۰۰۰ پیام باشد."
        values["sms_low_threshold"] = str(th)
    want_on = data.get("smsEnabled") in (True, "1", 1)
    planned = None
    if want_on and before["sms_enabled"] != "1" and "smsLead" not in errors:
        planned = engine.planned_reminder_count(values["sms_lead"])
        if to_ascii_digits(text(data, "confirmCount")).strip() != str(planned):
            errors["smsEnabled"] = (
                f"روشن کردن پیامک برای {planned} ویزیتِ برنامه‌ریزی‌شده یادآوری می‌فرستد؛ "
                "تیک تأیید را بزنید."
            )
    if errors:
        raise invalid("لطفاً خطاهای مشخص‌شده را برطرف کنید.", errors, planned=planned)
    with transaction.atomic():
        set_settings({**values, "sms_enabled": "1" if want_on else "0"})
        audit(me.id, "sms_settings")
    return ok({"notice": "تنظیمات ذخیره شد."})


def put_key(request: HttpRequest) -> HttpResponse:
    me = user_of(request)
    api_key = text(body(request), "apiKey").strip()
    if not re.fullmatch(engine.API_KEY_PATTERN, api_key, re.ASCII):
        raise invalid("کلید واردشده درست نیست.", {"apiKey": "کلید واردشده درست نیست."})
    check = provider.balance(api_key)
    if not check["ok"]:
        raise invalid(check["text"], {"apiKey": check["text"]})
    err = engine.save_key(api_key, me.id)
    if err:
        raise invalid(err, {"apiKey": err})
    count = check["count"]
    set_settings({"sms_balance": str(int(count)) if float(count).is_integer() else str(count),
                  "sms_balance_at": timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ"), "sms_low_alerted": "0"})
    audit(me.id, "sms_key_set")
    return ok({"notice": "کلید ذخیره شد."})


def delete_key(request: HttpRequest) -> HttpResponse:
    me = user_of(request)
    engine.remove_key()
    set_settings({"sms_balance": "", "sms_balance_at": "", "sms_low_alerted": "0"})
    audit(me.id, "sms_key_remove")
    return ok({"notice": "کلید پاک شد."})


def test(request: HttpRequest) -> HttpResponse:
    me = user_of(request)
    s = get_settings()
    phone = normalize_mobile(s["sms_alert_phone"])
    if not phone:
        m = "نخست شماره‌ی موبایل هشدار را ذخیره کنید."
        raise invalid(m, {"smsAlertPhone": m})
    msg = SmsMessage.objects.create(
        kind="test", phone=phone, body=f"پیامک آزمایشی {s['clinic_name']}", status="pending",
        due_at=int(timezone.now().timestamp() * 1000), created_by_id=me.id,
    )
    outcome = engine.send_one(msg.pk)
    audit(me.id, "sms_test")
    key = outcome if outcome in TEST_NOTICE else "failed"
    return ok({"outcome": key, "notice": TEST_NOTICE[key]})


# ---- bulk ---------------------------------------------------------------------------------------

def validate_body(value: Any, allow_name: bool) -> tuple[str, str | None]:
    t = clean_text(value)
    if not t:
        return t, "متن پیامک را وارد کنید."
    if len(t) > MESSAGE_MAX:
        return t, "متن پیامک نباید بیش از ۵۰۰ نویسه باشد."
    stripped = t.replace("{نام}", "") if allow_name else t
    if re.search(r"[{}]", stripped):
        return t, "فقط {نام} به‌عنوان جای‌گزین مجاز است." if allow_name else "نویسه‌های { و } مجاز نیستند."
    return t, None


def fill_name(t: str, first: str, last: str) -> str:
    return t.replace("{نام}", normalize_text(f"{first} {last}"))[:MESSAGE_MAX]


def why_not(optout: bool, status: str, phone: str | None) -> str | None:
    if optout:
        return "optout"
    if status == "archived":
        return "archived"
    if not normalize_mobile(phone):
        return "phone"
    return None


def _saved_for(me: Any) -> list[SavedSearch]:
    rows = SavedSearch.objects.order_by("-id")
    return list(rows if has(me, "manage_users") else rows.filter(user_id=me.id))


def recipients_for(row: SavedSearch) -> dict[str, Any] | None:
    query = stored_query(row)
    query["rules"] = query["rules"][: sq.MAX_RULES]
    try:
        q = sq.build_q(query, sq.search_fields())
    except sq.SearchError:
        return None
    skipped = {"optout": 0, "archived": 0, "phone": 0, "duplicate": 0}
    seen: set[str] = set()
    eligible = []
    rows = list(
        Patient.objects.filter(q).order_by("id")
        .values("id", "first_name", "last_name", "phone", "sms_optout", "status")
    )
    for p in rows:
        why = why_not(p["sms_optout"], p["status"], p["phone"])
        if why:
            skipped[why] += 1
            continue
        phone = normalize_mobile(p["phone"])
        assert phone
        if phone in seen:
            skipped["duplicate"] += 1
            continue
        seen.add(phone)
        eligible.append({**p, "phone": phone})
    return {"eligible": eligible, "skipped": skipped, "total": len(rows)}


def bulk_page(request: HttpRequest) -> HttpResponse:
    return ok({
        "saved": [{"id": s.pk, "name": s.name} for s in _saved_for(user_of(request))],
        "ready": _ready_json(readiness()), "bulkMax": BULK_MAX,
    })


def _bulk_state(request: HttpRequest) -> dict[str, Any]:
    me = user_of(request)
    data = body(request)
    r = readiness()
    nr = not_ready_text(r)
    if nr:
        raise invalid(nr)
    row = next((s for s in _saved_for(me) if s.pk == id_of(text(data, "saved"))), None)
    if row is None:
        raise invalid("جستجوی ذخیره‌شده را انتخاب کنید.")
    t, err = validate_body(data.get("text"), True)
    if err:
        raise invalid(err)
    found = recipients_for(row)
    if found is None:
        raise invalid("این جستجو اجرا نمی‌شود. آن را در صفحه‌ی جستجو درست کنید.")
    if not found["eligible"]:
        raise invalid("این جستجو گیرنده‌ی مجازی ندارد.")
    if len(found["eligible"]) > BULK_MAX:
        raise invalid(f"حداکثر {fa_digits(str(BULK_MAX))} گیرنده در هر ارسال. جستجو را محدودتر کنید.")
    return {"found": found, "text": t, "balance": r["s"]["sms_balance"], "data": data}


def _preview(st: dict[str, Any]) -> dict[str, Any]:
    e = st["found"]["eligible"]
    sample = fill_name(st["text"], e[0]["first_name"], e[0]["last_name"])
    return {
        "count": len(e), "skipped": st["found"]["skipped"], "sample": sample, "partsEach": sms_parts(sample),
        "partsTotal": sum(sms_parts(fill_name(st["text"], p["first_name"], p["last_name"])) for p in e),
        "balance": st["balance"], "text": st["text"],
    }


def bulk_preview(request: HttpRequest) -> HttpResponse:
    return ok({"preview": _preview(_bulk_state(request))})


def bulk_confirm(request: HttpRequest) -> HttpResponse:
    me = user_of(request)
    st = _bulk_state(request)
    e = st["found"]["eligible"]
    if to_ascii_digits(text(st["data"], "confirmCount")).strip() != str(len(e)):
        raise invalid("تعداد واردشده با تعداد گیرندگان یکی نیست. پیش‌نمایش دوباره نشان داده شد.", preview=_preview(st))
    now_ms = int(timezone.now().timestamp() * 1000)
    with transaction.atomic():
        SmsMessage.objects.bulk_create([
            SmsMessage(
                kind="bulk", patient_id=p["id"], phone=p["phone"],
                body=fill_name(st["text"], p["first_name"], p["last_name"]),
                status="pending", due_at=now_ms, created_by_id=me.id,
            )
            for p in e
        ])
        audit(me.id, "sms_bulk", None, f"{len(e)} recipients")
    return ok({"queued": len(e)})


# ---- one patient --------------------------------------------------------------------------------

def _patient_state(p: Patient) -> str | None:
    why = why_not(p.sms_optout, p.status, p.phone)
    return WHY_LABEL[why] if why else not_ready_text(readiness())


def patient_page(request: HttpRequest, code: str) -> HttpResponse:
    p = find_patient(code)
    return ok({
        "patient": {"code": p.code, "firstName": p.first_name, "lastName": p.last_name},
        "phone": normalize_mobile(p.phone), "blocked": _patient_state(p),
    })


def patient_send(request: HttpRequest, code: str) -> HttpResponse:
    me = user_of(request)
    p = find_patient(code)
    t, err = validate_body(body(request).get("text"), False)
    blocked = _patient_state(p)
    if blocked:
        raise conflict(blocked, "SMS_BLOCKED")
    if err:
        raise invalid(err, {"text": err})
    with transaction.atomic():
        SmsMessage.objects.create(kind="custom", patient=p, phone=normalize_mobile(p.phone), body=t, status="pending",
                                  due_at=int(timezone.now().timestamp() * 1000), created_by_id=me.id)
        audit(me.id, "sms_send", p.pk, "1 recipient")
    return ok({"queued": 1}, 201)


settings_view = route(GET=get_settings_view, PUT=put_settings)
key_view = route(PUT=put_key, POST=put_key, DELETE=delete_key)
patient_view = route(GET=patient_page, POST=patient_send)
