"""IranPayamak client (legacy src/lib/sms-provider.js). Fixed base URL, API key in a header, no redirects, 15 s
timeout. Never raises; never logs or returns the key. Tests replace the transport with set_transport()."""

from __future__ import annotations

import errno
import json
import socket
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

BASE_URL = "https://api.iranpayamak.com/ws/v1/"
TIMEOUT_S = 15
ACCEPTED = {"pending-approval", "in-queue", "sent", "init"}

# transport(method, url, headers, body_bytes) -> (status, parsed json or None). Raises OSError-like on failure.
Transport = Callable[[str, str, dict[str, str], bytes | None], tuple[int, Any]]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:  # noqa: D102
        raise urllib.error.URLError("redirect refused")


_opener = urllib.request.build_opener(_NoRedirect)


def _urllib_transport(method: str, url: str, headers: dict[str, str], data: bytes | None) -> tuple[int, Any]:
    req = urllib.request.Request(url, data=data, method=method, headers=headers)  # noqa: S310 - fixed https URL
    try:
        with _opener.open(req, timeout=TIMEOUT_S) as res:  # nosec B310
            raw = res.read()
            status = res.status
    except urllib.error.HTTPError as err:
        raw = err.read()
        status = err.code
    try:
        return status, json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return status, None


_transport: Transport = _urllib_transport


def set_transport(t: Transport | None) -> None:
    global _transport
    _transport = t or _urllib_transport


def _failure(code: str, text: str, retry: bool = False) -> dict[str, Any]:
    return {"ok": False, "code": code, "text": text, "retry": retry}


def _never_sent(err: object) -> bool:
    """The request never left this server (legacy NEVER_SENT: ENOTFOUND, EAI_AGAIN, ECONNREFUSED, ENETUNREACH), so
    sending again cannot double a text."""
    if isinstance(err, (socket.gaierror, ConnectionRefusedError)):
        return True
    return isinstance(err, OSError) and err.errno == errno.ENETUNREACH


def _call(
    api_key: str, method: str, route: str, body: dict[str, Any] | None = None
) -> tuple[int, Any] | dict[str, Any]:
    headers = {"Api-Key": api_key, "accept": "application/json"}
    data = None
    if body is not None:
        headers["content-type"] = "application/json; charset=utf-8"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    try:
        return _transport(method, BASE_URL + route, headers, data)
    except urllib.error.URLError as err:
        reason = getattr(err, "reason", None)
        if _never_sent(reason):
            return _failure("never-sent", "اتصال به سرویس پیامک برقرار نشد.", True)
        if isinstance(reason, (TimeoutError, socket.timeout)):
            return _failure("timeout", "پاسخی از سرویس پیامک نرسید؛ نتیجه نامشخص است.")
        return _failure("network", "ارتباط با سرویس پیامک قطع شد؛ نتیجه نامشخص است.")
    except TimeoutError:
        return _failure("timeout", "پاسخی از سرویس پیامک نرسید؛ نتیجه نامشخص است.")
    except Exception as err:  # noqa: BLE001
        if _never_sent(err):
            return _failure("never-sent", "اتصال به سرویس پیامک برقرار نشد.", True)
        return _failure("network", "ارتباط با سرویس پیامک قطع شد؛ نتیجه نامشخص است.")


def _pick(d: Any, a: str, b: str) -> Any:
    if not isinstance(d, dict):
        return None
    return d.get(a) if d.get(a) is not None else d.get(b)


def _short(m: Any) -> str:
    if isinstance(m, dict):
        parts: list[str] = []
        for v in m.values():
            parts.extend(str(x) for x in (v if isinstance(v, list) else [v]))
        m = " ".join(parts)
    return " ".join(str(m or "").split())[:120]


def balance(api_key: str) -> dict[str, Any]:
    r = _call(api_key, "GET", "account/balance")
    if isinstance(r, dict):
        return r
    status, js = r
    if status in (401, 403):
        return _failure("auth", "کلید پیامک پذیرفته نشد.")
    d = js.get("data") if isinstance(js, dict) else None
    try:
        count = float(_pick(d, "balance_count", "balanceCount"))
    except (TypeError, ValueError):
        count = float("nan")
    if not (200 <= status < 300) or count != count:
        return _failure(f"http-{status}", "موجودی از سرویس پیامک خوانده نشد.")
    try:
        amount = float(_pick(d, "balance_amount", "balanceAmount") or 0)
    except (TypeError, ValueError):
        amount = 0.0
    return {"ok": True, "count": count, "amount": amount}


def send(api_key: str, line: str, phone: str, text: str) -> dict[str, Any]:
    r = _call(api_key, "POST", "sms/simple",
              {"text": text, "line_number": str(line), "recipients": [phone], "number_format": "persian"})
    if isinstance(r, dict):
        return r
    status, js = r
    if status in (401, 403):
        return _failure("auth", "کلید پیامک پذیرفته نشد.")
    if status >= 500:
        return _failure(f"http-{status}", "سرویس پیامک خطا داد؛ نتیجه نامشخص است.")
    d = js.get("data") if isinstance(js, dict) else None
    st = str((d or {}).get("status", "")) if isinstance(d, dict) else ""
    if st == "insufficient-balance":
        return _failure("no-credit", "اعتبار کافی نیست.")
    ok_status = 200 <= status < 300
    pid = d.get("id") if isinstance(d, dict) else None
    if (
        ok_status and (not isinstance(js, dict) or js.get("status") != "error")
        and (st in ACCEPTED or pid is not None)
    ):
        return {"ok": True, "id": None if pid is None else str(pid), "status": st}
    message = _short(js.get("message") if isinstance(js, dict) else None) or "ارسال پذیرفته نشد."
    return _failure(f"http-{status}", message)
