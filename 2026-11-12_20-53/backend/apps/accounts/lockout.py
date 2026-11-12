"""Sign-in with lockout (SPEC §3.5; legacy src/auth.js startAttempt/finishAttempt).

Order: purge old rows -> count -> insert the attempt row -> check the password -> delete the key's rows
only on success. Count and insert run under one named lock, so a parallel burst cannot skip the count.
At most 16 password checks run at once per process (busy beyond). The same table holds the `pw|<id>`
guesses of the account page and the wipe confirmation.
"""

from __future__ import annotations

import ipaddress
import threading
from typing import Any

from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.http import HttpRequest

from apps.accounts.backends import _unknown_hash
from apps.accounts.models import LoginAttempt, User
from apps.accounts.session import now_ms
from apps.core.locks import named_lock
from apps.core.text import js_lower, nocase_key

LOCK_WINDOW_MS = 15 * 60 * 1000
MAX_FAILS_PER_USER_IP = 5
MAX_FAILS_PER_IP = 20
MAX_CHECKS_IN_FLIGHT = 16

_in_flight = threading.BoundedSemaphore(MAX_CHECKS_IN_FLIGHT)

MESSAGES = {
    "invalid": "نام کاربری یا رمز عبور نادرست است.",
    "locked": "به دلیل تلاش‌های ناموفق زیاد، ورود به مدت ۱۵ دقیقه مسدود شد.",
    "busy": "سامانه در حال حاضر شلوغ است. چند ثانیه بعد دوباره تلاش کنید.",
}


def _trusted(addr: str) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    for net in settings.TRUSTED_PROXY_NETS:
        try:
            if ip in ipaddress.ip_network(net, strict=False):
                return True
        except ValueError:
            continue
    return False


def client_ip(request: HttpRequest) -> str:
    """REMOTE_ADDR, or the right-most untrusted X-Forwarded-For entry when the peer is a trusted proxy."""
    peer: str = request.META.get("REMOTE_ADDR", "") or ""
    if not _trusted(peer):
        return peer
    chain: list[str] = [p.strip() for p in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if p.strip()]
    for addr in reversed(chain):
        if not _trusted(addr):
            return addr
    return chain[0] if chain else peer


def _start(username: str, ip: str, now: int) -> tuple[str, User | None] | None:
    key = f"{js_lower(username)}|{ip}"
    since = now - LOCK_WINDOW_MS
    with named_lock("login_attempts", 5):
        LoginAttempt.objects.filter(ts__lt=since).delete()
        user_fails = LoginAttempt.objects.filter(key=key, ts__gte=since).count()
        ip_fails = LoginAttempt.objects.filter(ip=ip, ts__gte=since).count()
        if user_fails >= MAX_FAILS_PER_USER_IP or ip_fails >= MAX_FAILS_PER_IP:
            return None
        LoginAttempt.objects.create(key=key, ip=ip, ts=now)
    user = User.objects.filter(
        username_key=nocase_key(username), active=True, deleted_at__isnull=True
    ).first()
    return key, user


def attempt_login(username: str, password: str, ip: str) -> dict[str, Any]:
    """{'user': User} or {'error': 'invalid' | 'locked' | 'busy'}."""
    if not _in_flight.acquire(blocking=False):
        return {"error": "busy"}
    try:
        started = _start(username, ip, now_ms())
        if started is None:
            return {"error": "locked"}
        key, user = started
        if user is None:
            check_password(password, _unknown_hash())
            ok = False
        else:
            ok = user.check_password(password)
        if not ok:
            return {"error": "invalid"}
        LoginAttempt.objects.filter(key=key).delete()
        return {"user": user}
    finally:
        _in_flight.release()


def _guess_key(user_id: int) -> str:
    return f"pw|{user_id}"


def password_guess_locked(user_id: int) -> bool:
    k = _guess_key(user_id)
    return LoginAttempt.objects.filter(key=k, ts__gte=now_ms() - LOCK_WINDOW_MS).count() >= MAX_FAILS_PER_USER_IP


def record_password_guess(user_id: int) -> None:
    k = _guess_key(user_id)
    LoginAttempt.objects.create(key=k, ip=k, ts=now_ms())


def clear_password_guesses(user_id: int) -> None:
    LoginAttempt.objects.filter(key=_guess_key(user_id)).delete()


def _start_guess(user_id: int) -> bool:
    """Count and record one guess as a single step, under the same lock as sign-in. Without the lock, parallel
    requests all read the count before any of them wrote, and more than five guesses reached the slow check."""
    with named_lock("login_attempts", 5):
        if password_guess_locked(user_id):
            return False
        record_password_guess(user_id)
    return True


def check_current_password(user_id: int, password: str) -> str:
    """'locked', 'wrong' or 'ok'. The guess is counted before the slow check and cleared only when right."""
    if not _start_guess(user_id):
        return "locked"
    user = User.objects.get(pk=user_id)
    if not _in_flight.acquire(timeout=10):
        return "wrong"
    try:
        good = user.check_password(password)
    finally:
        _in_flight.release()
    if not good:
        return "wrong"
    clear_password_guesses(user_id)
    return "ok"


def password_problem(password: object) -> str | None:
    if not isinstance(password, str) or len(password) < 10:
        return "رمز عبور باید دست‌کم ۱۰ نویسه باشد."
    return None
