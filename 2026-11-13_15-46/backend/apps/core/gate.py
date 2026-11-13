"""The permission gate (SPEC §3.7; legacy src/lib/route-perms.js).

One rule table for every signed-in URL under /api/v1 and /print. First match wins. A signed-in path that
matches no rule is refused (404), so a new endpoint cannot go live without a decision here. Paths are
normalized the way legacy normalizePath does (per-segment decoding, lower case, collapsed and trailing slashes).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any
from urllib.parse import unquote

from django.http import HttpRequest, HttpResponse

from apps.core.http import MSG_401, MSG_403, MSG_404, ApiError, error_response
from apps.core.perms import EDIT, VIEW, can, has

Check = Callable[[Any], bool]


def P(area: str, level: int = VIEW) -> Check:  # noqa: N802
    return lambda u: can(u, area, level)


def F(flag: str) -> Check:  # noqa: N802
    return lambda u: has(u, flag)


def both(*checks: Check) -> Check:
    return lambda u: all(c(u) for c in checks)


def OPEN(_u: Any) -> bool:  # noqa: N802
    return True


def OWNER(u: Any) -> bool:  # noqa: N802
    return bool(getattr(u, "owner", False))


SEG = "[^/]+"


def _re(pattern: str) -> re.Pattern[str]:
    return re.compile(f"^{pattern}$")


# (method or '*', pattern on the normalized path without the /api/v1 prefix, check)
RULES: list[tuple[str, re.Pattern[str], Check]] = [
    ("GET", _re("/me"), OPEN),
    ("POST", _re("/me/password"), OPEN),
    ("POST", _re("/auth/logout"), OPEN),
    ("GET", _re("/dashboard"), OPEN),
    # Layouts before every /patients/<seg> rule, so "layout" is never read as a patient code.
    ("*", _re(f"/patients/layout(?:/undo|/reset|/boxes(?:/{SEG}(?:/choices)?)?)?"), F("layout")),
    ("*", _re("/dashboard/layout(?:/undo|/reset)?"), F("layout")),
    # Patients (every /patients/* path also needs patients view: NEEDS_PATIENTS below).
    ("GET", _re(f"/patients/{SEG}/delete-check"), F("patient_delete")),
    ("DELETE", _re(f"/patients/{SEG}"), F("patient_delete")),
    ("POST", _re(f"/patients/{SEG}/change-code"), F("patient_code")),
    ("GET", _re("/patients/form"), P("patients", EDIT)),
    ("GET", _re(f"/patients/{SEG}/history"), P("finance")),
    ("PUT", _re(f"/patients/{SEG}/discount"), P("finance", EDIT)),
    ("GET", _re(f"/patients/{SEG}/(?:documents|photo|files/{SEG})"), P("documents")),
    ("DELETE", _re(f"/patients/{SEG}/files/{SEG}"), F("document_delete")),
    ("*", _re(f"/patients/{SEG}/(?:documents|documents/classify|photo|photo/remove)"), P("documents", EDIT)),
    ("POST", _re(f"/patients/{SEG}/visits"), P("visits", EDIT)),
    ("*", _re(f"/patients/{SEG}/sms"), P("sms", EDIT)),
    ("GET", _re(f"/patients(?:/{SEG})?"), OPEN),
    ("*", _re(f"/patients(?:/{SEG}(?:/archive|/unarchive|/medications|/medications/{SEG})?)?"), P("patients", EDIT)),
    # Visits, bills and payments.
    ("PUT", _re(f"/visits/{SEG}/lines/{SEG}/price"), F("price_override")),
    (
        "*",
        _re(f"/visits/{SEG}/(?:lines(?:/{SEG}(?:/discount)?)?|discount|payments(?:/{SEG})?|refund|move-credit)"),
        P("finance", EDIT),
    ),
    ("GET", _re("/visits/patient-search"), P("visits", EDIT)),
    ("GET", _re(f"/visits(?:/{SEG})?"), P("visits")),
    ("*", _re(f"/visits/{SEG}(?:/status|/note)?"), P("visits", EDIT)),
    # Search lists patients. Its exports hold whole patient records, so they also need the data area, as the
    # data page exports do (agent default 2026-11-05, docs/security-scan-2026-11-05.md decision 1).
    ("GET", _re("/search/export\\.(?:csv|xlsx)"), both(P("data"), P("patients"))),
    ("GET", _re(f"/search(?:/fields|/saved(?:/{SEG})?)?"), P("patients")),
    ("*", _re(f"/search/saved(?:/{SEG})?"), P("patients")),
    # Data: import creates patients, exports hold every record (the zip also every document).
    ("*", _re(r"/data/imports/jobs/[0-9]+(?:/resume)?"), both(F("csv_import"), P("patients", EDIT))),
    ("*", _re(f"/data/imports(?:/{SEG}(?:/confirm)?)?"), both(F("csv_import"), P("patients", EDIT))),
    # The zip's database dump holds every table (payments, stock, users): the owner only (owner, 2026-11-13).
    ("POST", _re("/data/exports/full\\.zip"), OWNER),
    ("POST", _re("/data/exports/patients\\.(?:csv|xlsx)"), both(P("data"), P("patients"))),
    ("GET", _re("/data(?:/template\\.csv)?"), P("data")),
    # Users, audit, wipe.
    ("GET", _re("/audit"), F("audit_log")),
    ("GET", _re("/users"), P("users")),
    ("*", _re("/admin/wipe"), F("manage_users")),
    ("*", _re(f"/users(?:/{SEG}(?:/password|/activate|/deactivate|/permissions)?)?"), F("manage_users")),
    # Storage.
    ("POST", _re(f"/storage/lots/{SEG}/(?:count|waste)"), F("stock_adjust")),
    ("DELETE", _re(f"/storage/moves/{SEG}"), F("stock_adjust")),
    ("DELETE", _re(f"/storage/items/{SEG}"), both(F("stock_adjust"), F("finance_settings"))),
    ("POST", _re("/storage/items"), F("finance_settings")),
    ("GET", _re(f"/storage/items(?:/{SEG})?"), P("storage")),
    ("POST", _re(f"/storage/items/{SEG}/stock-in"), P("storage", EDIT)),
    # Finance.
    ("*", _re(f"/finance/(?:settings|catalog|methods|accounts)(?:/{SEG})?"), F("finance_settings")),
    ("GET", _re("/finance/pay"), both(P("finance", EDIT), P("patients"))),
    ("GET", _re("/finance/payments"), both(P("finance"), P("patients"))),
    ("GET", _re("/finance/overview"), P("finance")),
    # SMS (every /sms path lists patient names: NEEDS_PATIENTS).
    ("*", _re("/sms/(?:key|test)"), F("sms_key")),
    ("*", _re("/sms/bulk(?:/preview|/confirm)?"), F("sms_bulk")),
    ("PUT", _re("/sms/settings"), P("sms", EDIT)),
    ("POST", _re(f"/sms/{SEG}/retry"), P("sms", EDIT)),
    ("GET", _re("/sms(?:/settings)?"), P("sms")),
]

PRINT_RULES: list[tuple[str, re.Pattern[str], Check]] = [
    ("GET", _re(f"/print(?:/{SEG}){{0,3}}"), P("pdf")),
]

NEEDS_PATIENTS = re.compile(r"^/(?:patients|visits|sms)(?:/|$)")
NEEDS_PATIENTS_PRINT = re.compile(r"^/print/(?:patients|visits)(?:/|$)")

# Reachable without signing in.
PUBLIC = {
    ("GET", "/api/v1/auth/csrf"),
    ("POST", "/api/v1/auth/login"),
    ("PUT", "/api/v1/me/theme"),
    ("GET", "/api/v1/public/app-config"),
    ("GET", "/api/v1/public/contact"),
    ("GET", "/health"),
}


def normalize_path(p: str) -> str:
    parts = []
    for seg in p.split("/"):
        try:
            parts.append(unquote(seg, errors="strict").replace("/", "%2f"))
        except UnicodeDecodeError:
            parts.append(seg)
    s = "/".join(parts).lower()
    s = re.sub(r"/{2,}", "/", s)
    s = re.sub(r"(.)/+$", r"\1", s)
    return s or "/"


def find_rule(
    method: str, path: str, rules: list[tuple[str, re.Pattern[str], Check]] = RULES
) -> tuple[str, re.Pattern[str], Check] | None:
    for rule in rules:
        if (rule[0] == "*" or rule[0] == method) and rule[1].match(path):
            return rule
    return None


def allowed(user: Any, method: str, full_path: str) -> bool | None:
    """True/False for a gated path; None when no rule matches."""
    path = normalize_path(full_path)
    method = "GET" if method == "HEAD" else method
    if path.startswith("/print"):
        rule = find_rule(method, path, PRINT_RULES)
        extra = (not NEEDS_PATIENTS_PRINT.match(path)) or can(user, "patients")
    else:
        sub = path[len("/api/v1"):] or "/"
        rule = find_rule(method, sub)
        extra = (not NEEDS_PATIENTS.match(sub)) or can(user, "patients")
    if rule is None:
        return None
    return bool(rule[2](user)) and extra


class GateMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        raw = request.path_info
        norm = normalize_path(raw)
        gated = norm.startswith("/api/v1/") or norm == "/print" or norm.startswith("/print/")
        if not gated or (request.method, norm) in PUBLIC or (
            request.method == "HEAD" and ("GET", norm) in PUBLIC
        ):
            return self.get_response(request)
        user = getattr(request, "klerk_user", None)
        if user is None:
            return error_response(ApiError(401, MSG_401))
        verdict = allowed(user, request.method or "GET", raw)
        if verdict is None:
            return error_response(ApiError(404, MSG_404))
        if not verdict:
            return error_response(ApiError(403, MSG_403))
        return self.get_response(request)
