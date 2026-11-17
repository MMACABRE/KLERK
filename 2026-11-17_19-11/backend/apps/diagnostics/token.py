"""The diagnostics token (ADR-0013 "Token"). The feed is on exactly while a valid token exists.

Form `kd_` + 43 url-safe characters, shown once. Stored as its sha256 hex with created and expiry times in
settings rows; compared with hmac.compare_digest. Sent only as `Authorization: Bearer kd_...`; session cookies are
ignored on the read routes. Wrong tokens count in the sign-in attempts table under `diag|<ip>`: 20 in 15 minutes
lock that address (429). Good calls: 60 a minute per process.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Any

from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from apps.accounts.lockout import LOCK_WINDOW_MS, MAX_FAILS_PER_IP, client_ip
from apps.accounts.models import LoginAttempt
from apps.accounts.session import now_ms
from apps.core.audit import audit
from apps.core.http import MSG_404, ApiError, error_response
from apps.core.jalali import format_jalali_datetime
from apps.core.models import Setting
from apps.core.settings_store import get_settings, set_setting

LIFETIME = timedelta(days=30)
PREFIX = "kd_"
RATE_PER_MIN = 60
MSG_401 = "کلید عیب‌یابی نادرست است."
MSG_429 = "درخواست‌های زیاد؛ کمی بعد دوباره تلاش کنید."

_calls: deque[float] = deque()
_calls_lock = threading.Lock()


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _jalali(iso: str) -> str:
    try:
        return format_jalali_datetime(datetime.fromisoformat(iso))
    except ValueError:
        return ""


def state() -> dict[str, Any]:
    s = get_settings()
    expires = s.get("diag_token_expires") or ""
    last = (s.get("diag_last_read") or "").split("|")
    read = {"at": last[0], "atText": _jalali(last[0]), "ip": last[1]} if len(last) == 2 and last[0] else None
    return {"on": bool(s.get("diag_token_hash")) and not _expired(expires), "expires": expires or None,
            "expiresText": _jalali(expires) if expires else "", "created": s.get("diag_token_created") or None,
            "lastRead": read}


def _expired(expires: str) -> bool:
    try:
        return datetime.fromisoformat(expires) <= timezone.now()
    except ValueError:
        return True


def create(user_id: int) -> str:
    """Create or replace the token; the answer is the only time it is shown."""
    token = PREFIX + secrets.token_urlsafe(32)
    now = timezone.now()
    set_setting("diag_token_hash", _hash(token))
    set_setting("diag_token_created", now.isoformat())
    set_setting("diag_token_expires", (now + LIFETIME).isoformat())
    audit(user_id, "diag_on", None)
    return token


def renew(user_id: int) -> bool:
    if not state()["on"]:
        return False
    set_setting("diag_token_expires", (timezone.now() + LIFETIME).isoformat())
    audit(user_id, "diag_renew", None)
    return True


def revoke(user_id: int | None, action: str = "diag_off") -> None:
    for key in ("diag_token_hash", "diag_token_created", "diag_token_expires"):
        Setting.objects.filter(pk=key).delete()
    audit(user_id, action, None)


def _rate_ok() -> bool:
    now = time.monotonic()
    with _calls_lock:
        while _calls and now - _calls[0] > 60:
            _calls.popleft()
        if len(_calls) >= RATE_PER_MIN:
            return False
        _calls.append(now)
        return True


def _note_read(ip: str) -> None:
    s = get_settings()
    last = (s.get("diag_last_read") or "").split("|")
    today = timezone.localdate().isoformat()
    if not (len(last) == 2 and last[0][:10] == today and last[1] == ip):
        audit(None, "diag_read", None, ip[:64])
    set_setting("diag_last_read", f"{timezone.localtime().isoformat(timespec='seconds')}|{ip[:64]}")


def check_request(request: HttpRequest) -> HttpResponse | None:
    """None lets a token read through; otherwise the refusal. Feed off: 404, as if the routes did not exist."""
    s = get_settings()
    stored = s.get("diag_token_hash") or ""
    if not stored:
        return error_response(ApiError(404, MSG_404))
    if _expired(s.get("diag_token_expires") or ""):
        revoke(None, "diag_expired")
        return error_response(ApiError(404, MSG_404))
    ip = client_ip(request)
    key = f"diag|{ip}"
    since = now_ms() - LOCK_WINDOW_MS
    if LoginAttempt.objects.filter(key=key, ts__gte=since).count() >= MAX_FAILS_PER_IP:
        return error_response(ApiError(429, MSG_429))
    auth = request.META.get("HTTP_AUTHORIZATION", "")
    given = auth[7:].strip() if auth[:7].lower() == "bearer " else ""
    if not given.startswith(PREFIX) or not hmac.compare_digest(_hash(given), stored):
        # ip holds the key too, so these failures never count toward the sign-in limit of that address
        LoginAttempt.objects.create(key=key, ip=key, ts=now_ms())
        return error_response(ApiError(401, MSG_401))
    if not _rate_ok():
        return error_response(ApiError(429, MSG_429))
    _note_read(ip)
    return None
