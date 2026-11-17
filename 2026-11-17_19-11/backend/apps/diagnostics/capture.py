"""Error reports and log records (ADR-0013 "Error reports"), built from an allow-list only.

A report never holds str(exc), a request body, query values, headers, cookies, local variables or formatted log
text: MySQL messages and our own f-strings can carry patient values. It holds the exception class, the MySQL error
number, the code path (repo-relative file + function) and the last 20 log templates of the same request.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
import threading
import time
import traceback
import uuid
from collections import deque
from collections.abc import Callable
from contextvars import ContextVar
from pathlib import Path
from types import TracebackType
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse

from apps.diagnostics import store

REPO_ROOT = Path(__file__).resolve().parents[2]  # backend/
RECENT = 20

_ctx: ContextVar[dict[str, Any] | None] = ContextVar("klerk_diag_ctx", default=None)


def version() -> dict[str, str]:
    return {"version": os.environ.get("KLERK_VERSION", ""), "image": os.environ.get("KLERK_IMAGE", "")}


def _own(logger_name: str) -> bool:
    return logger_name in ("apps", "klerk") or logger_name.startswith(("apps.", "klerk."))


def log_item(record: logging.LogRecord) -> dict[str, Any]:
    """A log record as the allow-list keeps it: the template our code wrote, never the formatted text; for other
    loggers (django, gunicorn, mysqlclient) no text at all."""
    item: dict[str, Any] = {"level": record.levelname, "logger": record.name}
    if _own(record.name) and isinstance(record.msg, str):
        item["msg"] = record.msg[:300]
    return item


def frames(tb: TracebackType | None) -> list[dict[str, str]]:
    """Repo-relative file and function of each frame inside backend/; library frames are counted, not named."""
    out: list[dict[str, str]] = []
    outside = 0
    for fs in traceback.extract_tb(tb):
        try:
            rel = Path(fs.filename).resolve().relative_to(REPO_ROOT).as_posix()
        except ValueError:
            outside += 1
            continue
        if rel.startswith(("tests/", ".venv")):
            continue
        if outside:
            out.append({"file": "<library>", "function": f"{outside} frames"})
            outside = 0
        out.append({"file": rel, "function": fs.name})
    if outside:
        out.append({"file": "<library>", "function": f"{outside} frames"})
    return out[-30:]


def fingerprint(exc_type: str, fr: list[dict[str, str]]) -> str:
    own = [f"{f['file']}:{f['function']}" for f in fr if f["file"] != "<library>"][-5:]
    return hashlib.sha256("|".join([exc_type, *own]).encode()).hexdigest()[:16]


def _mysql_code(exc: BaseException) -> int | None:
    from django.db import Error as DbError

    if not isinstance(exc, DbError):
        return None
    for cand in (exc.__cause__, exc):
        args = getattr(cand, "args", ())
        if args and isinstance(args[0], int):
            return int(args[0])
    return None


def report(exc: BaseException, process: str, status: int | None = None) -> None:
    """Write one error report. Never raises."""
    try:
        ctx = _ctx.get() or {}
        fr = frames(exc.__traceback__)
        exc_type = type(exc).__name__
        rec: dict[str, Any] = {
            "process": process, "request_id": ctx.get("request_id"), "route": ctx.get("route"),
            "method": ctx.get("method"), "status": status, "user_id": ctx.get("user_id"),
            "duration_ms": round((time.perf_counter() - ctx["start"]) * 1000) if "start" in ctx else None,
            **version(), "exc_type": exc_type, "mysql_code": _mysql_code(exc), "frames": fr,
            "fingerprint": fingerprint(exc_type, fr), "recent": list(ctx.get("recent", ())),
        }
        store.append("errors", rec)
    except Exception:  # noqa: BLE001 - the reporter must never turn one error into two
        pass


def _route_of(request: HttpRequest) -> str | None:
    match = getattr(request, "resolver_match", None)
    if match is None:
        return None
    return str(match.route or match.view_name or "")[:200] or None


class DiagnosticsContextMiddleware:
    """Outermost: a request id, the start time, the route and user once known, and the request's recent logs."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        ctx: dict[str, Any] = {"request_id": uuid.uuid4().hex, "method": request.method, "start": time.perf_counter(),
                               "route": None, "user_id": None, "recent": deque(maxlen=RECENT), "request": request}
        token = _ctx.set(ctx)
        try:
            return self.get_response(request)
        finally:
            _ctx.reset(token)


def _fill_from_request(ctx: dict[str, Any]) -> None:
    request = ctx.get("request")
    if request is None:
        return
    ctx["route"] = _route_of(request)
    user = getattr(request, "klerk_user", None)
    ctx["user_id"] = getattr(user, "id", None)


def report_request(exc: BaseException) -> None:
    """A web request failed with a 500: ErrorMiddleware calls this for view errors, the signal below for errors
    raised in other middleware layers."""
    ctx = _ctx.get()
    if ctx is not None:
        _fill_from_request(ctx)
    report(exc, "web", 500)


def on_request_exception(sender: Any, request: HttpRequest | None = None, **kwargs: Any) -> None:
    """got_request_exception: sent only when no process_exception answered (ErrorMiddleware answers view errors)."""
    exc = sys.exc_info()[1]
    from apps.core.errors import ServiceError
    from apps.core.http import ApiError

    if exc is None or isinstance(exc, (ApiError, ServiceError)):
        return  # an answer on purpose (4xx), not a fault
    report_request(exc)


class DiagLogHandler(logging.Handler):
    """Keeps each request's last 20 records for its error report, and writes INFO and above to the log file."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if record.name.startswith("apps.diagnostics"):
                return
            item = log_item(record)
            ctx = _ctx.get()
            if ctx is not None:
                ctx["recent"].append({"ts": store.now_iso(), **item})
                if ctx.get("route") is None:
                    _fill_from_request(ctx)
                item["route"] = ctx.get("route")
            if record.levelno >= logging.INFO:
                proc = "worker" if store.process_name() == "worker" else "web"
                store.append("logs", {"process": proc, **item})
        except Exception:  # noqa: BLE001
            pass


def install_hooks(process: str) -> None:
    """Unhandled exceptions outside a request (worker, management commands, threads)."""
    previous = sys.excepthook

    def hook(t: type[BaseException], e: BaseException, tb: TracebackType | None) -> None:
        if e.__traceback__ is None:
            e = e.with_traceback(tb)
        report(e, process)
        previous(t, e, tb)

    def thread_hook(args: threading.ExceptHookArgs) -> None:
        if args.exc_value is not None:
            report(args.exc_value, process)

    sys.excepthook = hook
    threading.excepthook = thread_hook


def handler_installed() -> bool:
    return any(isinstance(h, DiagLogHandler) for h in logging.getLogger().handlers)


def install_log_handler() -> None:
    if not getattr(settings, "DIAGNOSTICS_RECORD", True) or handler_installed():
        return
    logging.getLogger().addHandler(DiagLogHandler(level=logging.DEBUG))
