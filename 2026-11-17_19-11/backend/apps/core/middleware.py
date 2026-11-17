"""Cross-cutting middleware (SPEC §3.2, §3.3, §2.6): security headers, same-origin check, error shape."""

from __future__ import annotations

import logging
from collections.abc import Callable
from urllib.parse import urlsplit

from django.core.exceptions import RequestDataTooBig, TooManyFieldsSent
from django.http import HttpRequest, HttpResponse
from django.http.multipartparser import MultiPartParserError

from apps.core import errors
from apps.core.http import MSG_400, MSG_413, MSG_500, ApiError, error_response

logger = logging.getLogger("klerk")

CSP = (
    "default-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; "
    "form-action 'self'; frame-ancestors 'none'"
)
HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
}

Next = Callable[[HttpRequest], HttpResponse]


class HeadersMiddleware:
    def __init__(self, get_response: Next) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        for name, value in HEADERS.items():
            if name not in response:
                response[name] = value
        if getattr(request, "klerk_user", None) is not None and "Cache-Control" not in response:
            response["Cache-Control"] = "private, no-store"
        return response


class SameOriginMiddleware:
    """Every state-changing request needs an Origin whose host equals the request host (legacy sameOriginOnly)."""

    def __init__(self, get_response: Next) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.META.get("HTTP_ORIGIN", "")
            try:
                host = urlsplit(origin).netloc if origin else ""
            except ValueError:
                host = ""
            if not host or host != request.get_host():
                return HttpResponse("Forbidden: cross-origin request", status=403, content_type="text/plain")
        return self.get_response(request)


def _status_for(exc: errors.ServiceError) -> int:
    status = getattr(exc, "status", None)
    if isinstance(status, int):
        return status
    if isinstance(exc, errors.NotFound):
        return 404
    if isinstance(exc, errors.Conflict):
        return 409
    if isinstance(exc, errors.Invalid):
        return 422
    if isinstance(exc, errors.LockBusy):
        return 503
    return 500


class ErrorMiddleware:
    """Turns ApiError, ServiceError and body-size errors into the one JSON error shape; never a stack trace."""

    def __init__(self, get_response: Next) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        try:
            return self.get_response(request)
        except ApiError as err:
            return error_response(err)

    def process_exception(self, request: HttpRequest, exc: Exception) -> HttpResponse | None:
        if isinstance(exc, ApiError):
            return error_response(exc)
        if isinstance(exc, RequestDataTooBig):
            return error_response(ApiError(413, MSG_413))
        if isinstance(exc, (TooManyFieldsSent, MultiPartParserError)):
            return error_response(ApiError(400, MSG_400))
        if isinstance(exc, errors.ServiceError):
            status = _status_for(exc)
            message = getattr(exc, "message_fa", None) or (MSG_500 if status >= 500 else MSG_400)
            return error_response(ApiError(status, message, code=exc.code or type(exc).__name__))
        from apps.diagnostics.capture import report_request

        report_request(exc)
        logger.exception("unhandled error on %s %s", request.method, request.path.split("?")[0])
        return error_response(ApiError(500, MSG_500))
