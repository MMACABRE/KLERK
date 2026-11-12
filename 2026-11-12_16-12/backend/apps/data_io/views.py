"""Data API (SPEC §5.9, §5.10 wipe; legacy src/routes/data.js, admin.js wipe)."""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from typing import Any

from django.db import transaction
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from django.http.response import HttpResponseBase
from django.utils import timezone

from apps.core import present
from apps.core.audit import audit
from apps.core.codes import RefusedCell, parse_code_cell
from apps.core.files import _ext, patient_dir_exists, tmp_dir
from apps.core.http import ApiError, body, invalid, ok, route, text, user_of
from apps.core.perms import can
from apps.core.text import fa_key, normalize_text
from apps.data_io.csv_io import (
    COLUMNS,
    MAX_CSV_BYTES,
    MAX_CSV_ROWS,
    TEMPLATE_FIELDS,
    CsvError,
    parse_patient_csv,
    patient_table,
    patients_csv,
    template_csv,
)
from apps.data_io.xlsx import XLSX_TYPE, to_xlsx
from apps.patients.custom_boxes import (
    BoxError,
    add_custom_cells,
    check_custom_value,
    custom_columns,
    live_custom_boxes,
    shown_custom_boxes,
    write_custom_values,
)
from apps.patients.layouts import read_layout
from apps.patients.models import Patient
from apps.patients.validation import STATUSES, validate_patient
from apps.patients.views import _insert

PREVIEW_ROWS = 200
TOKEN_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
STAGE_TTL_S = 3600
WIPE_WORD = "حذف"


def _stage_path(token: str) -> Any:
    return tmp_dir() / f"import-{token}.json"


def _sweep() -> None:
    for n in os.listdir(tmp_dir()):
        if re.fullmatch(r"import-[0-9a-f-]{36}\.json", n):
            p = tmp_dir() / n
            try:
                if time.time() - p.stat().st_mtime > STAGE_TTL_S:
                    p.unlink()
            except OSError:
                pass


def _raw_cells(b: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in b.items() if re.fullmatch(r"c\d+", k)}


def _check_cells(
    boxes: list[Any], cells: dict[str, Any], confirm: bool = False, labels: dict[str, str] | None = None
) -> tuple[dict[int, str | None], str | None]:
    custom: dict[int, str | None] = {}
    error = None
    for box in boxes:
        raw = cells.get(f"c{box.pk}")
        if raw is None:
            continue
        try:
            v = check_custom_value(box, raw, by_label=True)
        except BoxError as err:
            msg = "این کادر یا گزینه دیگر وجود ندارد." if confirm and box.type == "choice" else err.message
            error = error or f"«{box.label}»: {msg}"
            continue
        if v is not None:
            custom[box.pk] = v
    live = {f"c{b.pk}" for b in boxes}
    for key in cells:
        if key not in live:
            error = error or f"«{(labels or {}).get(key, 'کادر سفارشی')}»: این کادر یا گزینه دیگر وجود ندارد."
            break
    return custom, error


def page(request: HttpRequest) -> HttpResponse:
    shown = shown_custom_boxes(read_layout("patient_form"))
    header = dict(COLUMNS)
    return ok({
        "templateColumns": [header[f] for f in TEMPLATE_FIELDS] + [b.label for b in shown],
        "maxRows": MAX_CSV_ROWS, "statuses": STATUSES,
    })


def template(request: HttpRequest) -> HttpResponse:
    shown = shown_custom_boxes(read_layout("patient_form"))
    r = HttpResponse(template_csv([b.label for b in shown]), content_type="text/csv; charset=utf-8")
    r["Content-Disposition"] = 'attachment; filename="patients-template.csv"'
    return r


def _jsonable(values: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in values.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif v is not None and not isinstance(v, (str, int, float, bool)):
            out[k] = str(v)
        else:
            out[k] = v
    return out


def _from_json(values: dict[str, Any]) -> dict[str, Any]:
    from datetime import date
    from decimal import Decimal

    out = dict(values)
    if out.get("birth_date"):
        out["birth_date"] = date.fromisoformat(out["birth_date"])
    for k in ("height_cm", "weight_kg"):
        if out.get(k) is not None:
            out[k] = Decimal(out[k])
    return out


def import_preview(request: HttpRequest) -> HttpResponse:
    me = user_of(request)
    f = request.FILES.get("file") or request.FILES.get("csv_file")
    if f is None:
        raise invalid("فایلی انتخاب نشده است.")
    if (f.size or 0) > MAX_CSV_BYTES:
        raise invalid("حجم فایل بیش از ۵ مگابایت است.")
    name = f.name or ""
    if _ext(name).lower() != ".csv":
        raise invalid("فقط فایل CSV پذیرفته می‌شود.")
    boxes = live_custom_boxes()
    try:
        records = parse_patient_csv(f.read(), {fa_key(b.label): f"c{b.pk}" for b in boxes})
    except CsvError as err:
        raise invalid(str(err)) from None
    if not records:
        raise invalid("فایل ردیفی ندارد.")
    existing = set(Patient.objects.exclude(national_id__isnull=True).values_list("national_id", flat=True))
    taken_codes = set(Patient.objects.values_list("code", flat=True))
    seen: set[str] = set()
    seen_codes: set[str] = set()
    rows = []
    for rec in records:
        b = rec["body"]
        values, errors = validate_patient(b)
        _, custom_error = _check_cells(boxes, _raw_cells(b))
        try:
            code = parse_code_cell(b.get("code"))
            bad_code = False
        except RefusedCell:
            code, bad_code = None, True
        first = next(iter(errors.values()), None) or custom_error
        state, note = "valid", "بدون خطا"
        if first:
            state, note = "invalid", first
        elif bad_code:
            state, note = "invalid", "کد بیمار را به شکل P-000123 بنویسید یا خالی بگذارید تا خودکار داده شود."
        elif code and code in taken_codes:
            state, note = "duplicate", "کد بیمار در سامانه ثبت شده است؛ رد می‌شود"
        elif code and code in seen_codes:
            state, note = "duplicate", "کد بیمار در همین فایل تکرار شده است؛ رد می‌شود"
        elif code and patient_dir_exists(code):
            state, note = "invalid", "پوشهٔ این کد بیمار روی سرور هست ولی بیماری با این کد ثبت نشده است؛ رد می‌شود"
        elif values["national_id"] and values["national_id"] in existing:
            state, note = "duplicate", "کد ملی در سامانه ثبت شده است؛ رد می‌شود"
        elif values["national_id"] and values["national_id"] in seen:
            state, note = "duplicate", "کد ملی در همین فایل تکرار شده است؛ رد می‌شود"
        if state == "valid" and values["national_id"]:
            seen.add(values["national_id"])
        if state == "valid" and code:
            seen_codes.add(code)
        rows.append({"line": rec["line"], "state": state, "note": note, "values": values, "code": code,
                     "cells": _raw_cells(b)})
    counts = {"valid": 0, "invalid": 0, "duplicate": 0}
    for r in rows:
        counts[r["state"]] += 1
    _sweep()
    token = str(uuid.uuid4())
    labels = {f"c{b.pk}": b.label for b in boxes}
    staged = {"userId": me.id, "labels": labels, "rows": [
        {"line": r["line"], "values": _jsonable(r["values"]), "code": r["code"], "cells": r["cells"]}
        for r in rows if r["state"] == "valid"
    ]}
    fd = os.open(_stage_path(token), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        json.dump(staged, out, ensure_ascii=False)
    return ok({
        "token": token, "fileName": name, "size": f.size, "total": len(rows), "counts": counts,
        "rows": [
            {"line": r["line"], "state": r["state"], "note": r["note"], "code": r["code"],
             "firstName": r["values"]["first_name"], "lastName": r["values"]["last_name"],
             "nationalId": r["values"]["national_id"], "birthDate": present.d(r["values"]["birth_date"]),
             "phone": r["values"]["phone"]}
            for r in rows[:PREVIEW_ROWS]
        ],
    })


def _read_stage(request: HttpRequest, token: str) -> dict[str, Any]:
    me = user_of(request)
    if not TOKEN_RE.fullmatch(token):
        raise invalid("درخواست نامعتبر است.")
    path = _stage_path(token)
    try:
        if time.time() - path.stat().st_mtime > STAGE_TTL_S:
            raise ValueError("expired")
        staged: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        path.unlink(missing_ok=True)
        raise invalid("این پیش‌نمایش منقضی شده است. فایل را دوباره بارگذاری کنید.") from None
    if staged.get("userId") != me.id:
        raise ApiError(403, "این پیش‌نمایش متعلق به کاربر دیگری است.")
    path.unlink(missing_ok=True)
    return staged


def import_confirm(request: HttpRequest, token: str) -> HttpResponse:
    me = user_of(request)
    staged = _read_stage(request, token)
    inserted, failed, skipped = 0, [], 0
    boxes = live_custom_boxes()
    ordered = [r for r in staged["rows"] if r["code"]] + [r for r in staged["rows"] if not r["code"]]
    for r in ordered:
        values = _from_json(r["values"])
        code = r["code"]
        taken = code and (Patient.objects.filter(code=code).exists() or patient_dir_exists(code))
        if taken or (values.get("national_id") and Patient.objects.filter(national_id=values["national_id"]).exists()):
            skipped += 1
            continue
        custom, error = _check_cells(boxes, r.get("cells") or {}, confirm=True, labels=staged["labels"])
        if error:
            failed.append({"line": r["line"], "message": error})
            continue
        try:
            p = _insert(values, me.id, code, audit_detail="import")
        except ApiError:
            skipped += 1
            continue
        with transaction.atomic():
            write_custom_values(p.pk, custom)
        inserted += 1
    audit(me.id, "patient_import", None, f"inserted {inserted}, skipped {skipped}, failed {len(failed)}")
    return ok({"inserted": inserted, "skipped": skipped, "failed": failed})


def import_cancel(request: HttpRequest, token: str) -> HttpResponse:
    if TOKEN_RE.fullmatch(token):
        _stage_path(token).unlink(missing_ok=True)
    return ok()


def _export(request: HttpRequest, fmt: str) -> HttpResponse:
    me = user_of(request)
    typed = text(body(request), "status")
    status = typed if typed in STATUSES else None
    rows_qs = Patient.objects.filter(status=status) if status else Patient.objects.all()
    rows = [dict(r) for r in rows_qs.order_by("id").values()]
    audit(me.id, "export_patients", None, f"{len(rows)} rows, {fmt}{', ' + status if status else ''}")
    extra = custom_columns(read_layout("patient_form"))
    with_custom = add_custom_cells(rows)
    if fmt == "csv":
        r = HttpResponse(patients_csv(with_custom, extra), content_type="text/csv; charset=utf-8")
    else:
        headers, table = patient_table(with_custom, extra)
        r = HttpResponse(to_xlsx(headers, table, "بیماران"), content_type=XLSX_TYPE)
    r["Content-Disposition"] = f'attachment; filename="patients.{fmt}"'
    return r


def export_csv(request: HttpRequest) -> HttpResponse:
    return _export(request, "csv")


def export_xlsx(request: HttpRequest) -> HttpResponse:
    return _export(request, "xlsx")


def export_full(request: HttpRequest) -> HttpResponseBase:
    from apps.data_io.full_export import stream_full_export

    me = user_of(request)
    audit(me.id, "export_full")
    stamp = timezone.localdate().isoformat()
    r = StreamingHttpResponse(
        stream_full_export(can(me, "finance"), can(me, "storage")), content_type="application/zip"
    )
    r["Content-Disposition"] = f'attachment; filename="clinic-export-{stamp}.zip"'
    r["Cache-Control"] = "private, no-store"
    return r


# ---- wipe ---------------------------------------------------------------------------------------

def wipe_page(request: HttpRequest) -> HttpResponse:
    from apps.data_io.wipe import WIPE_KINDS, wipe_counts

    return ok({"counts": wipe_counts(), "kinds": WIPE_KINDS})


def wipe(request: HttpRequest) -> HttpResponse:
    import logging

    from apps.accounts.lockout import check_current_password
    from apps.data_io.wipe import WIPE_KINDS, wipe_data
    from apps.ops.backup import backup_before_wipe

    me = user_of(request)
    data = body(request)
    raw: Any = data.get("kinds")
    if not isinstance(raw, list):
        raw = [data["kind"]] if isinstance(data.get("kind"), str) else data.get("kind") or []
    chosen = [str(k) for k in raw if str(k) in WIPE_KINDS]
    if not chosen:
        raise invalid("دست‌کم یکی از دسته‌ها را انتخاب کنید.")
    if normalize_text(text(data, "confirm")).strip() != WIPE_WORD:
        raise invalid(f"برای تأیید، کلمه‌ی «{WIPE_WORD}» را بنویسید.")
    verdict = check_current_password(me.id, text(data, "password", 256))
    if verdict == "locked":
        raise ApiError(429, "به دلیل تلاش‌های ناموفق زیاد، این کار به مدت ۱۵ دقیقه مسدود شد.")
    if verdict == "wrong":
        raise invalid("رمز عبور نادرست است.")
    try:
        backup = backup_before_wipe().name
    except Exception as err:  # noqa: BLE001
        logging.getLogger("klerk").error("data wipe refused: the backup could not be written (%s)", type(err).__name__)
        raise ApiError(500, "نسخه‌ی پشتیبان ساخته نشد، پس چیزی حذف نشد. فضای دیسک سرور را بررسی کنید.") from None
    result = wipe_data(chosen, me.id)
    extra = (f" trash={result['trashed']}" if result["trashed"] else "") + (
        f" file_error={result['fileError']}" if result["fileError"] else "")
    audit(me.id, "data_wipe", None, f"kinds={','.join(result['kinds'])} backup={backup}{extra}")
    return ok({**result, "backup": backup})


wipe_view = route(GET=wipe_page, POST=wipe)
