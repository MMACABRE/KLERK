"""Signed-in user per request (SPEC §3.4; legacy loadSession).

Django DB sessions hold `uid`, `login_at` and `last_seen` (epoch ms). Absolute 8 h, idle 30 min; `last_seen`
is written at most once a minute. The user row and its permissions are read on every request, so a change
applies on the next click. user_sessions maps users to session keys for "sign out everywhere".
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from django.contrib.sessions.models import Session
from django.http import HttpRequest, HttpResponse
from django.middleware.csrf import rotate_token

from apps.accounts.models import User, UserSession
from apps.core.perms import owner_perms, parse_perms

SESSION_MAX_MS = 8 * 3600 * 1000
SESSION_IDLE_MS = 30 * 60 * 1000


@dataclass
class Me:
    id: int
    username: str
    display_name: str
    owner: bool
    perms: dict[str, Any] = field(default_factory=dict)


def now_ms() -> int:
    return int(time.time() * 1000)


def me_of(user: User) -> Me:
    perms = owner_perms() if user.is_owner else parse_perms(user.perms)
    return Me(id=user.pk, username=user.username, display_name=user.display_name, owner=user.is_owner, perms=perms)


def start_session(request: HttpRequest, user: User) -> None:
    """A fresh session key and CSRF token on every sign-in; the old key and token stop working."""
    old = request.session.session_key
    request.session.flush()
    rotate_token(request)
    if old:
        UserSession.objects.filter(session_key=old).delete()
    now = now_ms()
    request.session["uid"] = user.pk
    request.session["login_at"] = now
    request.session["last_seen"] = now
    request.session.save()
    key = request.session.session_key
    if key:
        UserSession.objects.update_or_create(session_key=key, defaults={"user": user})
    request.klerk_user = me_of(user)  # type: ignore[attr-defined]


def end_session(request: HttpRequest) -> None:
    key = request.session.session_key
    request.session.flush()
    if key:
        UserSession.objects.filter(session_key=key).delete()


def destroy_user_sessions(user_id: int) -> None:
    keys = list(UserSession.objects.filter(user_id=user_id).values_list("session_key", flat=True))
    Session.objects.filter(session_key__in=keys).delete()
    UserSession.objects.filter(user_id=user_id).delete()


class SessionUserMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.klerk_user = self._load(request)  # type: ignore[attr-defined]
        return self.get_response(request)

    def _load(self, request: HttpRequest) -> Me | None:
        s = request.session
        uid = s.get("uid")
        if not isinstance(uid, int):
            return None
        now = now_ms()
        login_at = s.get("login_at", 0)
        last_seen = s.get("last_seen", 0)
        if now - int(login_at) > SESSION_MAX_MS or now - int(last_seen) > SESSION_IDLE_MS:
            end_session(request)
            return None
        user = User.objects.filter(pk=uid, active=True, deleted_at__isnull=True).first()
        if user is None or not UserSession.objects.filter(session_key=s.session_key, user_id=uid).exists():
            end_session(request)
            return None
        if now - int(last_seen) > 60_000:
            s["last_seen"] = now
        return me_of(user)
