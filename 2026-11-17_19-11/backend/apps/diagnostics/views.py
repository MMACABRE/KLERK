"""Diagnostics routes (ADR-0013 "API"). The four read routes are reached only through the token check in the gate;
the token routes are the protected owner's; client-errors takes any signed-in user's browser error."""

from __future__ import annotations

import re
import threading
import time
from collections import defaultdict, deque
from typing import Any

from django.http import HttpRequest, HttpResponse

from apps.core.http import ApiError, body, ok, route, user_of
from apps.diagnostics import stats as st
from apps.diagnostics import store
from apps.diagnostics import token as tk

CLIENT_MAX_BYTES = 8 * 1024
CLIENT_PER_MIN = 10
_client_calls: dict[int, deque[float]] = defaultdict(deque)
_client_lock = threading.Lock()
_SAFE = re.compile(r"[^\w .:/<>()\[\]{}@$#+\-]")


def _limit(request: HttpRequest) -> int:
    raw = request.GET.get("limit", "200")
    return max(1, min(1000, int(raw))) if raw.isdigit() else 200


def specs(request: HttpRequest) -> HttpResponse:
    return ok(st.specs())


def stats(request: HttpRequest) -> HttpResponse:
    return ok(st.stats())


def errors(request: HttpRequest) -> HttpResponse:
    return ok(store.error_groups(request.GET.get("since") or None, _limit(request)))


def logs(request: HttpRequest) -> HttpResponse:
    process = request.GET.get("process") or None
    if process not in (None, "web", "worker", "client"):
        raise ApiError(400, "process باید web، worker یا client باشد.")
    return ok(store.read(("logs", "client"), request.GET.get("since") or None, _limit(request), process))


def _clean(value: Any, size: int) -> str:
    """Only identifier-like text survives: a browser error name, a route pattern, a file or function name."""
    return _SAFE.sub("", str(value))[:size] if isinstance(value, str) else ""


def client_error(request: HttpRequest) -> HttpResponse:
    if len(request.body) > CLIENT_MAX_BYTES:
        raise ApiError(413, "گزارش خطا بزرگ‌تر از حد مجاز است.")
    me = user_of(request)
    now = time.monotonic()
    with _client_lock:
        calls = _client_calls[me.id]
        while calls and now - calls[0] > 60:
            calls.popleft()
        if len(calls) >= CLIENT_PER_MIN:
            return HttpResponse(status=429)
        calls.append(now)
    data = body(request)
    stack = data.get("stack")
    raw_frames: list[Any] = stack if isinstance(stack, list) else []
    frames = [{"file": _clean(str(f.get("file") or "").split("?")[0].split("#")[0], 120),
               "function": _clean(f.get("function"), 80)}
              for f in raw_frames[:20] if isinstance(f, dict)]
    store.append("client", {
        "process": "client", "level": "ERROR", "logger": "browser",
        "msg": _clean(data.get("message_template") or data.get("name"), 80),
        "route": _clean(data.get("route"), 120), "frames": frames, "client_version": _clean(data.get("version"), 40),
        "user_id": me.id,
    })
    return HttpResponse(status=204)


def token_state(request: HttpRequest) -> HttpResponse:
    return ok(tk.state())


def token_create(request: HttpRequest) -> HttpResponse:
    return ok({"token": tk.create(user_of(request).id), **tk.state()}, 201)


def token_renew(request: HttpRequest) -> HttpResponse:
    if not tk.renew(user_of(request).id):
        raise ApiError(404, "عیب‌یابی روشن نیست.")
    return ok(tk.state())


def token_revoke(request: HttpRequest) -> HttpResponse:
    tk.revoke(user_of(request).id)
    return HttpResponse(status=204)


specs_view = route(GET=specs)
stats_view = route(GET=stats)
errors_view = route(GET=errors)
logs_view = route(GET=logs)
client_errors_view = route(POST=client_error)
token_view = route(GET=token_state, POST=token_create, PUT=token_renew, DELETE=token_revoke)
