"""Sign-in, sign-out, the shell's `me`, theme, own password, users admin and the audit log (SPEC §5.1, §5.10)."""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.middleware.csrf import get_token
from django.utils import timezone

from apps.accounts.lockout import MESSAGES, attempt_login, check_current_password, client_ip, password_problem
from apps.accounts.models import User
from apps.accounts.session import destroy_user_sessions, end_session, start_session
from apps.core.audit import audit
from apps.core.codes import is_code
from apps.core.http import ApiError, body, forbidden, id_of, invalid, not_found, ok, page_args, paginate, route, text
from apps.core.jalali import format_jalali_datetime
from apps.core.labels import AUDIT_ACTIONS
from apps.core.models import AuditLog
from apps.core.perms import (
    AREA_LABELS,
    AREA_MAX,
    AREAS,
    FLAG_LABELS,
    FLAGS,
    LEVEL_LABELS,
    PRESETS,
    describe_perms,
    has,
    parse_perms,
    perms_from_body,
    preset_of,
    role_label,
)
from apps.core.settings_store import clinic_name, get_settings
from apps.core.text import nocase_key, normalize_text
from apps.ops.health import problems
from apps.patients.models import Patient

USERNAME_RE = re.compile(r"[a-zA-Z0-9._-]{3,32}", re.ASCII)
AUDIT_PAGE_SIZE = 50

CONTACT = {
    "name": "حسین هویسی",
    "phone": "+989165069060",
    "phoneShown": "+98 916 506 9060",
    "email": "hosseinhoveysi@gmail.com",
}


def _theme(request: HttpRequest) -> str:
    t = request.COOKIES.get("theme", "")
    return t if t in ("light", "dark") else ""


def _diag_on() -> bool:
    from apps.diagnostics.token import state

    return bool(state()["on"])


def me_payload(request: HttpRequest) -> dict[str, Any]:
    me = request.klerk_user  # type: ignore[attr-defined]
    s = get_settings()
    return {
        "id": me.id,
        "username": me.username,
        "displayName": me.display_name,
        "owner": me.owner,
        "roleLabel": role_label(me.owner, me.perms),
        "perms": {"areas": {a: me.perms[a] for a in AREAS}, "flags": me.perms["flags"]},
        "siteName": s["clinic_name"] or clinic_name(),
        "currency": s["currency"],
        "smsOn": s["sms_enabled"] == "1",
        "smsDefaultLead": s["sms_lead"],
        "patientCount": Patient.objects.exclude(status="archived").count(),
        "theme": _theme(request),
        # S4: worker or nightly backup stopped; only the people who can act on it see it.
        "systemProblems": problems() if me.owner or has(me, "manage_users") else [],
        "diagOn": me.owner and _diag_on(),  # the owner's header chip «عیب‌یابی روشن» (ADR-0013)
    }


# ---- session ------------------------------------------------------------------------------------

def csrf(request: HttpRequest) -> HttpResponse:
    get_token(request)
    return ok({"siteName": clinic_name(), "signedIn": getattr(request, "klerk_user", None) is not None,
               "theme": _theme(request)})


def login(request: HttpRequest) -> HttpResponse:
    data = body(request)
    username = text(data, "username").strip()[:64]
    password = text(data, "password")[:256]
    result = attempt_login(username, password, client_ip(request))
    error = result.get("error")
    if error == "busy":
        raise ApiError(503, MESSAGES["busy"], code="BUSY", headers={"Retry-After": "5"})
    if error:
        known = User.objects.filter(username_key=nocase_key(username)).values_list("username", flat=True).first()
        action = "login_locked" if error == "locked" else "login_failed"
        detail = known or "(unknown user)"
        repeat = action == "login_locked" and AuditLog.objects.filter(
            action="login_locked", detail=detail, ts__gte=timezone.now() - timedelta(minutes=15)
        ).exists()
        if not repeat:
            audit(None, action, None, detail)
        raise ApiError(429 if error == "locked" else 401, MESSAGES[error], code=error.upper())
    user = result["user"]
    start_session(request, user)
    audit(user.pk, "login")
    get_token(request)
    return ok(me_payload(request))


def logout(request: HttpRequest) -> HttpResponse:
    me = request.klerk_user  # type: ignore[attr-defined]
    end_session(request)
    if me:
        audit(me.id, "logout")
    response = ok()
    response.delete_cookie("sid", samesite="Strict")
    return response


def me(request: HttpRequest) -> HttpResponse:
    return ok(me_payload(request))


def theme(request: HttpRequest) -> HttpResponse:
    value = text(body(request), "theme")
    response = ok({"theme": value if value in ("light", "dark") else ""})
    if value in ("light", "dark"):
        response.set_cookie("theme", value, max_age=365 * 24 * 3600, httponly=True, secure=True, samesite="Lax")
    else:
        response.delete_cookie("theme", samesite="Lax")
    return response


def app_config(request: HttpRequest) -> HttpResponse:
    return ok({"siteName": clinic_name(), "theme": _theme(request)})


def contact(request: HttpRequest) -> HttpResponse:
    return ok({"contact": CONTACT, "siteName": clinic_name()})


def change_password(request: HttpRequest) -> HttpResponse:
    me = request.klerk_user  # type: ignore[attr-defined]
    data = body(request)
    current = text(data, "current", 256)
    new = text(data, "password", 256)
    repeat = text(data, "confirm", 256) or text(data, "repeat", 256)
    verdict = check_current_password(me.id, current)
    if verdict == "locked":
        raise ApiError(429, "به دلیل تلاش‌های ناموفق زیاد، تغییر رمز به مدت ۱۵ دقیقه مسدود شد.")
    if verdict == "wrong":
        raise invalid("رمز فعلی نادرست است.", {"current": "رمز فعلی نادرست است."})
    problem = password_problem(new)
    if problem:
        raise invalid(problem, {"password": problem})
    if new != repeat:
        raise invalid("تکرار رمز جدید با آن یکسان نیست.", {"confirm": "تکرار رمز جدید با آن یکسان نیست."})
    if new == current:
        same = "رمز جدید باید با رمز فعلی فرق داشته باشد."
        raise invalid(same, {"password": same})
    with transaction.atomic():
        User.objects.filter(pk=me.id).update(password=make_password(new))
        audit(me.id, "password_change")
    destroy_user_sessions(me.id)
    start_session(request, User.objects.get(pk=me.id))
    return ok({"done": True})


# ---- users admin --------------------------------------------------------------------------------

def _user_json(u: User) -> dict[str, Any]:
    perms = parse_perms(u.perms)
    return {
        "id": u.pk,
        "username": u.username,
        "displayName": u.display_name,
        "owner": u.is_owner,
        "active": u.active,
        "createdAt": u.created_at.isoformat(),
        "createdAtJalali": format_jalali_datetime(u.created_at),
        "label": role_label(u.is_owner, perms),
    }


def list_users(request: HttpRequest) -> HttpResponse:
    rows = User.objects.filter(deleted_at__isnull=True).order_by("-is_owner", "-active", "id")
    return ok({
        "data": [_user_json(u) for u in rows],
        "presets": {k: v["label"] for k, v in PRESETS.items()},
    })


def create_user(request: HttpRequest) -> HttpResponse:
    me = request.klerk_user  # type: ignore[attr-defined]
    data = body(request)
    username = text(data, "username").strip()
    display = normalize_text(text(data, "displayName") or text(data, "display_name"))[:80]
    preset = text(data, "preset")
    preset = preset if preset in PRESETS else "staff"
    password = text(data, "password", 256)
    if not USERNAME_RE.fullmatch(username):
        m = "نام کاربری باید ۳ تا ۳۲ نویسه‌ی لاتین، عدد یا نقطه، خط تیره و زیرخط باشد."
        raise invalid(m, {"username": m})
    if not display:
        raise invalid("نام نمایشی را وارد کنید.", {"displayName": "نام نمایشی را وارد کنید."})
    problem = password_problem(password)
    if problem:
        raise invalid(problem, {"password": problem})
    from apps.core.text import nocase_key

    if User.objects.filter(Q(username=username) | Q(username_key=nocase_key(username))).exists():
        raise invalid("این نام کاربری قبلاً ثبت شده است.", {"username": "این نام کاربری قبلاً ثبت شده است."})
    with transaction.atomic():
        u = User(username=username, display_name=display, role=preset, perms=parse_perms(PRESETS[preset]["perms"]))
        u.set_password(password)
        u.save()
        audit(me.id, "user_create", None, f"{username} ({preset})")
    return ok({"user": _user_json(u), "notice": f"کاربر «{username}» ساخته شد."}, 201)


def _find(uid: str) -> User:
    user = User.objects.filter(pk=id_of(uid), deleted_at__isnull=True).first()
    if user is None:
        raise not_found("کاربر پیدا نشد.")
    return user


def reset_password(request: HttpRequest, uid: str) -> HttpResponse:
    me = request.klerk_user  # type: ignore[attr-defined]
    user = _find(uid)
    if user.is_owner and not me.owner:
        raise forbidden("حساب مالک سامانه را فقط خود او می‌تواند تغییر دهد.")
    password = text(body(request), "password", 256)
    problem = password_problem(password)
    if problem:
        raise invalid(problem, {"password": problem})
    with transaction.atomic():
        User.objects.filter(pk=user.pk).update(password=make_password(password))
        audit(me.id, "user_password_reset", None, user.username)
    destroy_user_sessions(user.pk)
    if user.pk == me.id:
        start_session(request, User.objects.get(pk=user.pk))
        return ok({"notice": "رمز شما عوض شد و از دستگاه‌های دیگر خارج شدید."})
    return ok({"notice": f"رمز «{user.username}» عوض شد و او از همه‌ی دستگاه‌ها خارج شد."})


def _set_active(request: HttpRequest, uid: str, active: bool) -> HttpResponse:
    me = request.klerk_user  # type: ignore[attr-defined]
    user = _find(uid)
    if user.is_owner:
        raise invalid("حساب مالک سامانه غیرفعال نمی‌شود.")
    if not active and user.pk == me.id:
        raise invalid("نمی‌توانید حساب خودتان را غیرفعال کنید.")
    with transaction.atomic():
        User.objects.filter(pk=user.pk).update(active=active)
        audit(me.id, "user_activate" if active else "user_deactivate", None, user.username)
    if not active:
        destroy_user_sessions(user.pk)
    return ok({"user": _user_json(User.objects.get(pk=user.pk))})


def activate(request: HttpRequest, uid: str) -> HttpResponse:
    return _set_active(request, uid, True)


def deactivate(request: HttpRequest, uid: str) -> HttpResponse:
    return _set_active(request, uid, False)


def delete_user(request: HttpRequest, uid: str) -> HttpResponse:
    me = request.klerk_user  # type: ignore[attr-defined]
    user = _find(uid)
    if user.is_owner:
        raise invalid("حساب مالک سامانه حذف نمی‌شود.")
    if user.pk == me.id:
        raise invalid("نمی‌توانید حساب خودتان را حذف کنید.")
    with transaction.atomic():
        user.active = False
        user.deleted_at = timezone.now()
        user.username = f"{user.username}~{user.pk}"
        user.save()
        audit(me.id, "user_delete", None, user.username.rsplit("~", 1)[0])
    destroy_user_sessions(user.pk)
    return ok({"notice": f"کاربر «{user.username.rsplit('~', 1)[0]}» حذف شد."})


def _perms_target(request: HttpRequest, uid: str) -> User:
    me = request.klerk_user  # type: ignore[attr-defined]
    user = _find(uid)
    if user.is_owner:
        raise forbidden("مالک سامانه همه‌ی دسترسی‌ها را دارد و دسترسی‌اش تغییر نمی‌کند.")
    if user.pk == me.id:
        raise forbidden("دسترسی‌های خودتان را نمی‌توانید تغییر دهید.")
    return user


def _perms_json(user: User, perms: dict[str, Any]) -> dict[str, Any]:
    return {
        "user": _user_json(user),
        "perms": {"areas": {a: perms[a] for a in AREAS}, "flags": perms["flags"]},
        "preset": preset_of(perms),
        "presets": {k: {"label": v["label"], "perms": parse_perms(v["perms"])} for k, v in PRESETS.items()},
        "areas": [{"key": a, "label": AREA_LABELS[a], "max": AREA_MAX[a]} for a in AREAS],
        "levels": LEVEL_LABELS,
        "flags": [{"key": f, "label": FLAG_LABELS[f], "area": FLAGS[f][0], "needs": FLAGS[f][1]} for f in FLAGS],
    }


def get_perms(request: HttpRequest, uid: str) -> HttpResponse:
    user = _perms_target(request, uid)
    return ok(_perms_json(user, parse_perms(user.perms)))


def put_perms(request: HttpRequest, uid: str) -> HttpResponse:
    me = request.klerk_user  # type: ignore[attr-defined]
    user = _perms_target(request, uid)
    perms = perms_from_body(body(request))
    with transaction.atomic():
        User.objects.filter(pk=user.pk).update(perms=perms)
        audit(me.id, "user_perms", None, f"{user.username}: {describe_perms(perms)}")
    out = _perms_json(User.objects.get(pk=user.pk), perms)
    out["notice"] = "دسترسی‌ها ذخیره شد. از درخواست بعدی کاربر اعمال می‌شود."
    return ok(out)


# ---- audit log ----------------------------------------------------------------------------------

def audit_log(request: HttpRequest) -> HttpResponse:
    q = request.GET
    user_id = id_of(q.get("user", ""))
    action = q.get("action", "")
    action = action if action in AUDIT_ACTIONS else ""
    code = normalize_text(q.get("patient", "")[:20]).upper()
    rows = AuditLog.objects.all()
    note = None
    if user_id:
        rows = rows.filter(user_id=user_id)
    if action:
        rows = rows.filter(action=action)
    if code:
        ids: set[int] = set()
        if is_code(code):
            ids.update(Patient.objects.filter(code=code).values_list("id", flat=True))
            deleted = AuditLog.objects.filter(action="patient_delete", detail=code)
            ids.update(i for i in deleted.values_list("patient_id", flat=True) if i)
            # A code change's detail is "<old> -> <new>": match either end in SQL, not by reading every row.
            changed = AuditLog.objects.filter(Q(detail__startswith=code) | Q(detail__endswith=code),
                                              action="patient_code", patient_id__isnull=False)
            ids.update(i for i in changed.values_list("patient_id", flat=True) if i)
        else:
            note = "کد بیمار را به شکل P-000123 وارد کنید."
        rows = rows.filter(patient_id__in=ids)
    total = rows.count()
    page, size = page_args(request, AUDIT_PAGE_SIZE)
    pg = paginate(total, page, size)
    start = (pg["page"] - 1) * size
    chunk = list(rows.select_related("user").order_by("-id")[start : start + size])
    pids = {r.patient_id for r in chunk if r.patient_id}
    codes: dict[int, str] = {}
    deleted = AuditLog.objects.filter(action="patient_delete", patient_id__in=pids)
    for pid, detail in deleted.values_list("patient_id", "detail"):
        if pid and detail:
            codes[pid] = detail
    codes.update(dict(Patient.objects.filter(pk__in=pids).values_list("id", "code")))
    # Deleted users stay selectable: their history is what the audit log keeps (NULL deleted_at sorts first).
    users = User.objects.order_by("deleted_at", "id")
    return ok({
        "data": [
            {
                "id": r.pk,
                "ts": r.ts.isoformat(),
                "tsJalali": format_jalali_datetime(r.ts),
                "action": r.action,
                "actionLabel": AUDIT_ACTIONS.get(r.action, r.action),
                "patientId": r.patient_id,
                "code": codes.get(r.patient_id) if r.patient_id else None,
                "detail": r.detail,
                "username": r.user.username if r.user else None,
                "displayName": r.user.display_name if r.user else None,
            }
            for r in chunk
        ],
        "pagination": pg,
        "users": [{"id": u.pk, "username": u.username, "displayName": u.display_name} for u in users],
        "actions": AUDIT_ACTIONS,
        "filters": {"user": user_id or "", "action": action, "patient": code},
        "patientNote": note,
    })


users_view = route(GET=list_users, POST=create_user)
user_password_view = route(POST=reset_password)
user_activate_view = route(POST=activate)
user_deactivate_view = route(POST=deactivate)
user_view = route(DELETE=delete_user)
user_perms_view = route(GET=get_perms, PUT=put_perms)
