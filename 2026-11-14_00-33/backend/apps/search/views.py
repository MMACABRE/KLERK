"""Search API (SPEC §5.8; legacy src/routes/search.js). Same query names as legacy (join, s, f1..f6...)."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from apps.core import present
from apps.core.audit import audit
from apps.core.http import body, id_of, invalid, not_found, ok, page_args, paginate, route, text, user_of
from apps.core.perms import has
from apps.core.text import normalize_text
from apps.data_io.csv_io import patient_table, patients_csv
from apps.data_io.xlsx import XLSX_TYPE, to_xlsx
from apps.patients.custom_boxes import add_custom_cells, custom_columns
from apps.patients.layouts import read_layout
from apps.patients.models import Patient
from apps.patients.views import patient_row
from apps.search import query as sq
from apps.search.models import SavedSearch

PAGE_SIZE = 25
MAX_SAVED_PER_USER = 50


def _fields_json(fields: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"key": k, "type": f["type"], "label": f["label"], "ops": f["ops"], "hidden": f.get("hidden", False),
         "choices": f.get("choices"), "custom": f.get("custom")}
        for k, f in fields.items()
    ]


def fields(request: HttpRequest) -> HttpResponse:
    return ok({
        "fields": _fields_json(sq.search_fields()), "operators": sq.OPERATORS, "maxRules": sq.MAX_RULES,
        "statusKeys": sq.STATUS_KEYS,
    })


def _saved_for(me: Any) -> list[dict[str, Any]]:
    rows = SavedSearch.objects.select_related("user").order_by("-id")
    if not has(me, "manage_users"):
        rows = rows.filter(user_id=me.id)
    return [{"id": s.pk, "name": s.name, "owner": s.user.display_name if s.user else None, "mine": s.user_id == me.id,
             "created": present.d(timezone.localtime(s.created_at).date())}
            for s in rows]


def search(request: HttpRequest) -> HttpResponse:
    all_fields = sq.search_fields()
    query = sq.query_from_form(request.GET)
    out: dict[str, Any] = {
        "query": query, "summary": sq.describe(query, all_fields), "params": sq.query_to_params(query),
        "results": None,
    }
    if "join" not in request.GET:
        return ok(out)
    try:
        q = sq.build_q(query, all_fields)
    except sq.SearchError as err:
        raise invalid(err.message, query=query, summary=out["summary"]) from None
    rows = Patient.objects.filter(q).order_by("-updated_at", "-id")
    total = rows.count()
    page, size = page_args(request, PAGE_SIZE)
    pg = paginate(total, page, size)
    start = (pg["page"] - 1) * size
    out["results"] = {"data": [patient_row(p) for p in rows[start : start + size]], "pagination": pg}
    return ok(out)


def _export_rows(request: HttpRequest) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    try:
        q = sq.build_q(sq.query_from_form(request.GET), sq.search_fields())
    except sq.SearchError as err:
        raise invalid(err.message) from None
    rows = [dict(r) for r in Patient.objects.filter(q).order_by("id").values()]
    return add_custom_cells(rows), custom_columns(read_layout("patient_form"))


def export_csv(request: HttpRequest) -> HttpResponse:
    rows, extra = _export_rows(request)
    audit(user_of(request).id, "export_search", None, f"{len(rows)} rows, csv")
    r = HttpResponse(patients_csv(rows, extra), content_type="text/csv; charset=utf-8")
    r["Content-Disposition"] = 'attachment; filename="patients-search.csv"'
    return r


def export_xlsx(request: HttpRequest) -> HttpResponse:
    rows, extra = _export_rows(request)
    audit(user_of(request).id, "export_search", None, f"{len(rows)} rows, xlsx")
    headers, table = patient_table(rows, extra)
    r = HttpResponse(to_xlsx(headers, table, "نتیجه‌ی جستجو"), content_type=XLSX_TYPE)
    r["Content-Disposition"] = 'attachment; filename="patients-search.xlsx"'
    return r


def saved_list(request: HttpRequest) -> HttpResponse:
    return ok({"data": _saved_for(user_of(request))})


def saved_create(request: HttpRequest) -> HttpResponse:
    me = user_of(request)
    data = body(request)
    query = sq.query_from_form(data)
    name = normalize_text(text(data, "name"))[:80]
    if not name:
        raise invalid("برای جستجو یک نام وارد کنید.", {"name": "برای جستجو یک نام وارد کنید."})
    try:
        sq.build_q(query, sq.search_fields())
    except sq.SearchError as err:
        raise invalid(err.message, {"name": err.message}) from None
    active = {
        "join": query["join"], "status": query["status"],
        "rules": [{k: r.get(k) for k in ("field", "op", "value", "value2")} for r in query["rules"] if sq.has_rule(r)],
    }
    if not active["rules"] and not active["status"]:
        raise invalid("حداقل یک شرط با مقدار لازم است.", {"name": "حداقل یک شرط با مقدار لازم است."})
    if SavedSearch.objects.filter(user_id=me.id).count() >= MAX_SAVED_PER_USER:
        m = "تعداد جستجوهای ذخیره‌شده به سقف رسیده است. چند مورد را حذف کنید."
        raise invalid(m, {"name": m})
    s = SavedSearch.objects.create(user_id=me.id, name=name, query_json=active)
    return ok({"id": s.pk, "params": sq.query_to_params(query)}, 201)


def _find_saved(request: HttpRequest, sid: str) -> SavedSearch:
    me = user_of(request)
    row = SavedSearch.objects.filter(pk=id_of(sid)).first()
    if row is None or not (has(me, "manage_users") or row.user_id == me.id):
        raise not_found("جستجوی ذخیره‌شده پیدا نشد.")
    return row


def stored_query(row: SavedSearch) -> dict[str, Any]:
    stored = row.query_json if isinstance(row.query_json, dict) else {}
    return {
        "join": "or" if stored.get("join") == "or" else "and",
        "status": sq.status_filter(stored.get("status")),
        "rules": stored.get("rules") if isinstance(stored.get("rules"), list) else [],
    }


def saved_get(request: HttpRequest, sid: str) -> HttpResponse:
    row = _find_saved(request, sid)
    return ok({"id": row.pk, "name": row.name, "params": sq.query_to_params(stored_query(row))})


def saved_delete(request: HttpRequest, sid: str) -> HttpResponse:
    _find_saved(request, sid).delete()
    return ok()


saved_view = route(GET=saved_list, POST=saved_create)
saved_item_view = route(GET=saved_get, DELETE=saved_delete)
