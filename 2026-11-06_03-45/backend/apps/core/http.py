"""HTTP helpers shared by every API view (SPEC §2.6).

One error shape: {"error": {"code", "message", "fields"}}. Views raise ApiError (or a ServiceError, which
apps.core.middleware.ErrorMiddleware maps) and return ok(...). `route()` builds one view from per-method
handlers, so a URL answers 405 for any other method.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from django.http import HttpRequest, HttpResponse, JsonResponse, QueryDict
from django.http.response import HttpResponseBase

MSG_401 = "نشست شما به پایان رسیده است. لطفاً دوباره وارد شوید."
MSG_403 = "شما اجازه‌ی دسترسی به این بخش را ندارید."
MSG_404 = "صفحه‌ی مورد نظر پیدا نشد."
MSG_413 = "حجم اطلاعات ارسالی بیش از حد مجاز است."
MSG_400 = "درخواست نامعتبر است."
MSG_500 = "خطایی در سرور رخ داد. لطفاً دوباره تلاش کنید."

_ID_RE = re.compile(r"[1-9][0-9]{0,14}", re.ASCII)

Handler = Callable[..., HttpResponseBase]


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        message: str,
        code: str | None = None,
        fields: dict[str, str] | None = None,
        extra: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code or _default_code(status)
        self.fields = fields or {}
        self.extra = extra or {}
        self.headers = headers or {}


def _default_code(status: int) -> str:
    return {
        400: "BAD_REQUEST",
        401: "UNAUTHENTICATED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        413: "TOO_LARGE",
        422: "VALIDATION_ERROR",
        429: "LOCKED",
        503: "BUSY",
    }.get(status, "SERVER_ERROR")


def error_response(err: ApiError) -> JsonResponse:
    payload: dict[str, Any] = {"code": err.code, "message": err.message}
    if err.fields:
        payload["fields"] = err.fields
    payload.update(err.extra)
    response = JsonResponse({"error": payload}, status=err.status)
    for name, value in err.headers.items():
        response[name] = value
    return response


def ok(data: Any = None, status: int = 200) -> JsonResponse:
    return JsonResponse({"ok": True} if data is None else data, status=status, safe=False,
                        json_dumps_params={"ensure_ascii": False})


def not_found(message: str = MSG_404) -> ApiError:
    return ApiError(404, message)


def invalid(message: str, fields: dict[str, str] | None = None, **extra: Any) -> ApiError:
    return ApiError(422, message, fields=fields, extra=extra)


def conflict(message: str, code: str = "CONFLICT", **extra: Any) -> ApiError:
    return ApiError(409, message, code=code, extra=extra)


def forbidden(message: str = MSG_403) -> ApiError:
    return ApiError(403, message)


def id_of(value: object) -> int:
    """A row id from a URL or form value, or 0 for anything else (legacy idOf)."""
    text = str(value) if isinstance(value, (str, int)) and not isinstance(value, bool) else ""
    return int(text) if _ID_RE.fullmatch(text) else 0


def body(request: HttpRequest) -> dict[str, Any]:
    """The request body as a dict: JSON object, or form fields (a repeated field becomes a list)."""
    cached: dict[str, Any] | None = getattr(request, "_klerk_body", None)
    if cached is not None:
        return cached
    data: dict[str, Any]
    ctype = request.META.get("CONTENT_TYPE", "")
    if ctype.startswith("application/json"):
        try:
            raw = json.loads(request.body or b"{}")
        except (ValueError, UnicodeDecodeError):
            raise ApiError(400, MSG_400) from None
        data = raw if isinstance(raw, dict) else {}
    else:
        form: QueryDict = request.POST if request.method == "POST" else _parse_form(request)
        data = {k: (v[0] if len(v) == 1 else v) for k, v in form.lists()}
    request._klerk_body = data  # type: ignore[attr-defined]
    return data


def _parse_form(request: HttpRequest) -> QueryDict:
    # Uploads are always POST (Django parses multipart only for POST); other methods send JSON or a form body.
    try:
        return QueryDict(request.body, encoding="utf-8")
    except Exception:  # noqa: BLE001
        return QueryDict()


def text(data: dict[str, Any], key: str, limit: int | None = None) -> str:
    """A field as one string ('' when missing). A repeated field (list) is refused as ''."""
    value = data.get(key)
    if value is None or isinstance(value, (list, dict)):
        return ""
    out = value if isinstance(value, str) else ("1" if value is True else "0" if value is False else str(value))
    return out[:limit] if limit is not None else out


def flag(data: dict[str, Any], key: str) -> bool:
    value = data.get(key)
    return value is True or value in ("1", "on", "true", 1)


def raw_field(data: dict[str, Any], key: str) -> Any:
    """A field as sent (a list stays a list, so money/qty parsers can refuse repeated fields)."""
    value = data.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return value


def route(**handlers: Handler) -> Callable[..., HttpResponseBase]:
    """One view for one URL; handlers keyed by HTTP method (GET, POST, PUT, PATCH, DELETE)."""
    allowed = {m.upper(): h for m, h in handlers.items()}
    if "GET" in allowed:
        allowed.setdefault("HEAD", allowed["GET"])

    def view(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
        handler = allowed.get(request.method or "")
        if handler is None:
            raise ApiError(405, MSG_404)
        return handler(request, *args, **kwargs)

    view.csrf_exempt = False  # type: ignore[attr-defined]
    # Read by the gate completeness test: every method of every URL must have a gate rule.
    view.methods = frozenset(allowed)  # type: ignore[attr-defined]
    return view


def page_args(request: HttpRequest, default_size: int) -> tuple[int, int]:
    try:
        page = max(1, int(request.GET.get("page", "1")))
    except ValueError:
        page = 1
    try:
        size = int(request.GET.get("pageSize", str(default_size)))
    except ValueError:
        size = default_size
    return page, min(max(1, size), 200)


def paginate(items_count: int, page: int, size: int) -> dict[str, int]:
    pages = max(1, -(-items_count // size))
    return {"page": min(page, pages), "pageSize": size, "total": items_count, "pages": pages}


def csrf_failure(request: HttpRequest, reason: str = "") -> HttpResponse:
    return error_response(ApiError(403, "Forbidden: cross-origin request", code="CSRF"))


def user_of(request: HttpRequest) -> Any:
    return getattr(request, "klerk_user", None)


def handler404(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    return error_response(ApiError(404, MSG_404))


def handler500(request: HttpRequest) -> HttpResponse:
    return error_response(ApiError(500, MSG_500))
