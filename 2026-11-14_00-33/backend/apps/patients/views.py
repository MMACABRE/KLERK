"""Patients API (SPEC §5.3; legacy src/routes/patients.js, layout routes and bill.js history/discount)."""

from __future__ import annotations

from typing import Any, cast

from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from apps.billing.ops import (
    PATIENT_PAYMENTS_BLOCK,
    bills_for,
    patient_balance,
    patient_has_payments,
    visit_numbers,
)
from apps.core import present
from apps.core.audit import audit
from apps.core.codes import RefusedCell, is_code, parse_code_cell
from apps.core.files import patient_dir_exists, resolve_patient_file
from apps.core.http import (
    ApiError,
    body,
    conflict,
    id_of,
    invalid,
    not_found,
    ok,
    page_args,
    paginate,
    raw_field,
    route,
    text,
    user_of,
)
from apps.core.jalali import age_from, to_jalali_input
from apps.core.labels import CATEGORY, SEX, STATUS
from apps.core.money import describe_discount, money_input, parse_discount
from apps.core.perms import EDIT, can, has
from apps.core.settings_store import get_settings
from apps.core.text import fa_key, normalize_text
from apps.documents.services import (
    CATEGORIES,
    NEW_FILES_MAX,
    PHOTO_ERRORS,
    documents_for,
    receive_many,
)
from apps.patients import layouts as L
from apps.patients.catalogue import BOXES, CARDS, CUSTOM_TYPES, LIMITS, Reject
from apps.patients.custom_boxes import (
    BoxError,
    add_choices,
    box_json,
    check_custom_value,
    create_custom_box,
    custom_display,
    custom_values,
    delete_custom_box,
    live_custom_boxes,
    remove_choice,
    set_choice_hidden,
    taken_name_keys,
)
from apps.patients.models import CustomBox, Medication, Patient, PatientValue
from apps.patients.services import (
    CodeTakenError,
    FolderMoveError,
    code_taken_message,
    delete_patient,
    insert_patient,
    save_patient,
)
from apps.patients.services import (
    change_code as change_patient_code,
)
from apps.patients.validation import FORM_FIELDS, SEXES, STATUSES, validate_patient
from apps.visits.logic import LEADS, end_time, flags, hhmm, visits_for

PAGE_SIZE = 25
NOT_FOUND = "پرونده‌ی مورد نظر پیدا نشد."
CODE_FORMAT_ERROR = "کد را به شکل P-000123 یا فقط عدد آن (تا ۶ رقم) وارد کنید."
SORTS = {
    "updated": ["-updated_at", "-id"],
    "name": ["last_name_sort", "first_name_sort", "id"],
    "code": ["code"],
}
SUGGEST_COLUMNS = ["visit_reason", "referral"]
SMS_KIND_LABEL = {
    "reminder": "یادآوری", "custom": "پیام تکی", "bulk": "پیام گروهی", "alert": "هشدار اعتبار", "test": "آزمایشی",
}
SMS_STATUS_LABEL = {
    "pending": ["در انتظار", "chip-info"], "sending": ["در حال ارسال", "chip-info"], "sent": ["ارسال شد", "chip-ok"],
    "failed": ["ناموفق", "chip-crit"], "skipped": ["ارسال نشد", "chip-mute"], "cancelled": ["لغو شد", "chip-mute"],
}


def find_patient(code: str) -> Patient:
    p = Patient.objects.filter(code=code).first() if is_code(code) else None
    if p is None:
        raise not_found(NOT_FOUND)
    return p


code_taken_error = code_taken_message


def _age(p: Patient) -> int | None:
    return age_from(p.birth_date, timezone.localdate()) if p.birth_date else None


def patient_row(p: Patient) -> dict[str, Any]:
    return {
        "id": p.pk, "code": p.code, "firstName": p.first_name, "lastName": p.last_name,
        "birthDate": present.d(p.birth_date), "age": _age(p), "sex": p.sex, "sexLabel": SEX.get(p.sex or "", ""),
        "status": p.status, "statusLabel": STATUS[p.status]["label"], "statusChip": STATUS[p.status]["chip"],
        "updatedAt": present.dt(p.updated_at),
        "updatedDay": present.d(timezone.localtime(p.updated_at).date()) if p.updated_at else None,
    }


def patient_full(p: Patient, cur: str, finance: bool) -> dict[str, Any]:
    """The whole record. The standing discount is money: only for users with the finance area."""
    out = patient_row(p)
    for f in FORM_FIELDS:
        if f in ("first_name", "last_name", "birth_date", "sex", "status"):
            continue
        v = getattr(p, f)
        key = "".join(w.capitalize() if i else w for i, w in enumerate(f.split("_")))
        out[key] = present.decimal_text(v) if f in ("height_cm", "weight_kg") else v
    out.update({
        "fatherName": p.father_name, "smsOptout": p.sms_optout, "photo": bool(p.photo),
        "createdAt": present.dt(p.created_at), "createdDay": present.d(timezone.localtime(p.created_at).date()),
    })
    if not finance:
        return out
    out.update({
        "discKind": p.disc_kind, "discValue": p.disc_value,
        "discText": describe_discount(p.disc_kind, p.disc_value, cur),
        "discInput": (
            money_input(p.disc_value, cur) if p.disc_kind == "amount" else (str(p.disc_value) if p.disc_value else "")
        ),
    })
    return out


def _cur() -> str:
    return str(get_settings()["currency"])


# ---- list -----------------------------------------------------------------------------------------

def list_patients(request: HttpRequest) -> HttpResponse:
    q = request.GET
    wanted = q.getlist("status")[-1] if q.getlist("status") else ""
    status = wanted if wanted in STATUSES else ""
    sex = q.get("sex", "")
    sex = sex if sex in SEXES else ""
    sort = q.get("sort", "updated")
    sort = sort if sort in ("updated", "name", "birth_desc", "birth_asc", "code") else "updated"
    term = normalize_text(q.get("q", "")[:100])
    rows = Patient.objects.all()
    if term:
        digits = term.replace(" ", "").replace("-", "")
        rows = rows.filter(
            Q(name_key__contains=fa_key(term)) | Q(code__contains=term) | Q(phone__contains=digits)
            | Q(national_id__contains=digits)
        )
    rows = rows.filter(status=status) if status else rows.exclude(status="archived")
    if sex:
        rows = rows.filter(sex=sex)
    if sort == "birth_desc":
        from django.db.models import F

        rows = rows.order_by(F("birth_date").desc(nulls_last=True), "id")
    elif sort == "birth_asc":
        from django.db.models import F

        rows = rows.order_by(F("birth_date").asc(nulls_last=True), "id")
    else:
        rows = rows.order_by(*SORTS[sort])
    total = rows.count()
    page, size = page_args(request, PAGE_SIZE)
    pg = paginate(total, page, size)
    start = (pg["page"] - 1) * size
    return ok({
        "data": [patient_row(p) for p in rows[start : start + size]],
        "pagination": pg,
        "filters": {"q": term, "status": status, "sex": sex, "sort": sort},
    })


def suggestions(request: HttpRequest | None = None) -> Any:
    out = {}
    for col in SUGGEST_COLUMNS:
        out[col] = list(
            Patient.objects.exclude(**{f"{col}__isnull": True}).values(col).annotate(n=Count("id"))
            .order_by("-n", col).values_list(col, flat=True)[:200]
        )
    return ok(out) if request is not None else out


# ---- form data ------------------------------------------------------------------------------------

def _edit_values(p: Patient) -> dict[str, Any]:
    vals: dict[str, Any] = {}
    for f in FORM_FIELDS:
        v = getattr(p, f)
        if f == "birth_date":
            vals[f] = to_jalali_input(v) if v else ""
        elif f in ("height_cm", "weight_kg"):
            vals[f] = present.decimal_text(v) or ""
        else:
            vals[f] = v or ""
    vals["sms_optout"] = "1" if p.sms_optout else ""
    vals.update(L.custom_form_values(p.pk))
    return vals


def form_data(request: HttpRequest) -> HttpResponse:
    me = user_of(request)
    code = request.GET.get("code", "")
    patient = find_patient(code) if code else None
    from apps.patients.services import next_patient_code

    return ok({
        "patient": patient_full(patient, _cur(), can(me, "finance")) if patient else None,
        "values": _edit_values(patient) if patient else {"status": "active", "doc_category": "other"},
        "layout": L.read_layout("patient_form"),
        "builtin": {"cards": CARDS, "boxes": BOXES},
        "customBoxes": {str(b.pk): box_json(b) for b in live_custom_boxes()},
        "suggestions": suggestions(),
        "nextCode": (
            next_patient_code(folder_exists=patient_dir_exists)
            if not patient and has(me, "patient_code") else None
        ),
        "newFilesMax": NEW_FILES_MAX,
        "categories": [{"id": c, "label": CATEGORY[c]} for c in CATEGORIES],
        "statuses": [{"id": s, **STATUS[s]} for s in STATUSES],
        "sexes": [{"id": s, "label": SEX[s]} for s in SEXES],
        "bloodTypes": ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"],
        "smsOn": get_settings()["sms_enabled"] == "1",
        "leads": LEADS,
    })


def _check_layout_boxes(
    data: dict[str, Any], values: dict[str, Any], errors: dict[str, str], stored: dict[int, str] | None, editing: bool
) -> dict[int, str | None]:
    layout = L.read_layout("patient_form")
    required = L.required_box_ids(layout)
    posted = L.shown_box_ids(data.get("boxes"))
    shown = posted if editing else posted | required
    for b in BOXES:
        bid = cast(str, b["id"])
        if bid in shown:
            continue
        errors.pop(bid, None)
        if editing:
            values.pop(bid, None)
    for b in BOXES:
        bid = cast(str, b["id"])
        if bid not in shown or bid not in required or bid == "sms_optout" or bid in errors:
            continue
        if values.get(bid) in (None, ""):
            errors[bid] = f"{b['label']} را وارد کنید."
    writes: dict[int, str | None] = {}
    for box in live_custom_boxes():
        if f"c:{box.pk}" not in shown:
            continue
        key = f"c_{box.pk}"
        try:
            v = check_custom_value(box, data.get(key), keep=(stored or {}).get(box.pk))
        except BoxError as err:
            errors[key] = err.message
            continue
        if v is None and f"c:{box.pk}" in required:
            errors[key] = f"{box.label} را وارد کنید."
        else:
            writes[box.pk] = v
    return writes


def create(request: HttpRequest) -> HttpResponse:
    me = user_of(request)
    data = body(request)
    values, errors = validate_patient(data)
    writes = _check_layout_boxes(data, values, errors, None, editing=False)
    files = request.FILES.getlist("files") if can(me, "documents", EDIT) else []
    category = text(data, "doc_category") or text(data, "docCategory")
    category = category if category in CATEGORIES else "other"
    chosen = None
    if has(me, "patient_code"):
        try:
            chosen = parse_code_cell(text(data, "code")[:20])
        except RefusedCell:
            errors["code"] = CODE_FORMAT_ERROR
        if chosen:
            taken = code_taken_error(chosen)
            if taken:
                errors["code"] = taken
    staged = []
    if files and not errors:
        try:
            staged = receive_many(files)
        except ValueError as err:
            errors["files"] = str(err)
    if errors:
        if files and "files" not in errors:
            errors["files"] = "پرونده ذخیره نشد؛ فایل‌ها را دوباره انتخاب کنید."
        raise invalid("لطفاً خطاهای مشخص‌شده را برطرف کنید.", errors)
    meta = {"category": category, "title": None, "doc_date": None, "notes": None}
    try:
        patient = insert_patient(values, me.id, chosen, writes=writes, staged=staged, meta=meta)
    except CodeTakenError as err:
        raise invalid(err.message, {"code": err.message}) from None
    except BoxError as err:
        raise invalid(err.message) from None
    finally:
        for up in staged:
            up.discard()
    return ok({"code": patient.code, "files": len(staged)}, 201)


# ---- profile --------------------------------------------------------------------------------------

def _reminder(visit_id: int) -> dict[str, Any] | None:
    from apps.sms.models import SmsMessage

    m = (
        SmsMessage.objects.filter(kind="reminder", visit_id=visit_id)
        .order_by("-id").values("status", "reason", "due_at").first()
    )
    if not m:
        return None
    from datetime import UTC, datetime

    due = datetime.fromtimestamp(m["due_at"] / 1000, UTC)
    return {"status": m["status"], "reason": m["reason"], "due": present.dt(due)}


def visit_item(v: Any, me: Any, sms_on: bool, with_patient: bool = False) -> dict[str, Any]:
    f = flags(v)
    out = {
        "id": v.pk, "date": present.d(v.visit_date), "time": hhmm(v.visit_time),
        "until": end_time(v.visit_time, v.duration_min), "durationMin": v.duration_min, "reason": v.reason,
        "notes": v.notes, "status": v.status, "overdue": f["overdue"], "ongoing": f["ongoing"],
        "reminderLead": v.reminder_lead,
    }
    if sms_on and v.status == "scheduled":
        r = _reminder(v.pk)
        out["reminder"] = r if r and r["status"] != "cancelled" else None
    if with_patient:
        p = v.patient
        out["patient"] = {"code": p.code, "firstName": p.first_name, "lastName": p.last_name, "status": p.status}
    return out


def doc_item(d: dict[str, Any]) -> dict[str, Any]:
    from datetime import datetime

    row = d["row"]
    ext = d["filename"].rsplit(".", 1)[-1].lower() if "." in d["filename"] else ""
    return {
        "filename": d["filename"], "size": d["size"],
        "modified": present.dt(datetime.fromisoformat(d["modified"].replace("Z", "+00:00"))),
        "ext": ext, "image": ext in ("jpg", "jpeg", "png"),
        "category": row.category if row else None, "categoryLabel": CATEGORY.get(row.category, "") if row else "",
        "title": row.title if row else None, "docDate": present.d(row.doc_date) if row else None,
        "notes": row.notes if row else None,
    }


def show(request: HttpRequest, code: str) -> HttpResponse:
    me = user_of(request)
    p = find_patient(code)
    s = get_settings()
    cur = str(s["currency"])
    sms_on = s["sms_enabled"] == "1"
    out: dict[str, Any] = {"patient": patient_full(p, cur, can(me, "finance"))}
    out["hasPhoto"] = bool(p.photo and resolve_patient_file(p.code, p.photo))
    out["photoError"] = PHOTO_ERRORS.get(request.GET.get("photo", ""))
    out["medications"] = [
        {"id": m.pk, "name": m.name, "dosage": m.dosage, "frequency": m.frequency}
        for m in Medication.objects.filter(patient=p).order_by("id")
    ]
    out["customInfo"] = [
        {"label": label, "text": custom_display({"type": t, "choices": ch}, value)}
        for label, t, ch, value in PatientValue.objects.filter(patient=p).select_related("box").order_by("box_id")
        .values_list("box__label", "box__type", "box__choices", "value")
    ]
    if can(me, "documents"):
        out["files"] = [doc_item(d) for d in documents_for(p)]
    if can(me, "visits"):
        vf = visits_for(p.pk)
        out["visits"] = {
            "next": visit_item(vf["next"], me, sms_on) if vf["next"] else None,
            "upcoming": [visit_item(v, me, sms_on) for v in vf["upcoming"]],
            "rest": [visit_item(v, me, sms_on) for v in vf["rest"]],
        }
    if can(me, "finance"):
        bal = patient_balance(p.pk)
        out["balance"] = {
            "remaining": present.money(bal["remaining"], cur),
            "credit": present.money(bal["credit"], cur),
        }
    if can(me, "sms"):
        from apps.sms.models import SmsMessage

        m = SmsMessage.objects.filter(patient=p).order_by("-id").values("kind", "status").first()
        out["lastSms"] = (
            {"kindText": SMS_KIND_LABEL[m["kind"]], "statusText": SMS_STATUS_LABEL[m["status"]][0],
             "chip": SMS_STATUS_LABEL[m["status"]][1]} if m else None
        )
    return ok(out)


def edit(request: HttpRequest, code: str) -> HttpResponse:
    me = user_of(request)
    p = find_patient(code)
    data = body(request)
    values, errors = validate_patient(data)
    stored = custom_values(p.pk)
    writes = _check_layout_boxes(data, values, errors, stored, editing=True)
    if errors:
        raise invalid("لطفاً خطاهای مشخص‌شده را برطرف کنید.", errors)
    changed = [k for k in FORM_FIELDS if k in values and (values[k] if values[k] != "" else None) != getattr(p, k)]
    for bid, v in writes.items():
        if stored.get(bid) != v:
            changed.append(f"c:{bid}")
    try:
        save_patient(p.pk, values, writes, me.id, changed)
    except BoxError as err:
        raise invalid(err.message) from None
    return ok({"code": p.code})


def change_code(request: HttpRequest, code: str) -> HttpResponse:
    me = user_of(request)
    p = find_patient(code)
    data = body(request)
    typed = text(data, "code", 20) or text(data, "new_code", 20)
    again = text(data, "confirm", 20) or text(data, "new_code2", 20)

    def cell(s: str) -> str | None | bool:
        try:
            return parse_code_cell(s)
        except RefusedCell:
            return False

    if cell(typed) != cell(again):
        raise invalid("دو کدی که وارد کردید یکی نیستند.", {"code": "دو کدی که وارد کردید یکی نیستند."})
    new = cell(typed)
    if not new:
        raise invalid(CODE_FORMAT_ERROR, {"code": CODE_FORMAT_ERROR})
    if new == p.code:
        raise invalid("این همان کد فعلی بیمار است.", {"code": "این همان کد فعلی بیمار است."})
    assert isinstance(new, str)
    try:
        change_patient_code(p.pk, new, me.id)
    except CodeTakenError as err:
        raise invalid(err.message, {"code": err.message}) from None
    except FolderMoveError:
        raise ApiError(
            422, "تغییر کد انجام نشد؛ پوشه‌ی بیمار روی سرور جابه‌جا نشد. دوباره تلاش کنید یا با پشتیبانی تماس بگیرید."
        ) from None
    return ok({"code": new})


def _set_status(request: HttpRequest, code: str, status: str, action: str) -> HttpResponse:
    me = user_of(request)
    p = find_patient(code)
    with transaction.atomic():
        Patient.objects.filter(pk=p.pk).update(status=status, updated_at=timezone.now(), updated_by_id=me.id)
        audit(me.id, action, p.pk)
    return ok({"code": p.code, "status": status})


def archive(request: HttpRequest, code: str) -> HttpResponse:
    return _set_status(request, code, "archived", "patient_archive")


def unarchive(request: HttpRequest, code: str) -> HttpResponse:
    return _set_status(request, code, "active", "patient_unarchive")


def delete_check(request: HttpRequest, code: str) -> HttpResponse:
    p = find_patient(code)
    from apps.core.files import list_patient_files

    return ok({
        "patient": patient_row(p),
        "blocked": patient_has_payments(p.pk),
        "message": PATIENT_PAYMENTS_BLOCK if patient_has_payments(p.pk) else None,
        "counts": {"visits": p.visits.count(), "files": len(list_patient_files(p.code))},
    })


def delete(request: HttpRequest, code: str) -> HttpResponse:
    from apps.billing.services import HasPaymentsError

    me = user_of(request)
    p = find_patient(code)
    try:
        delete_patient(p.pk, me.id)
    except HasPaymentsError:
        raise conflict(PATIENT_PAYMENTS_BLOCK, "PATIENT_PAYMENTS_BLOCK") from None
    return ok()


def add_medication(request: HttpRequest, code: str) -> HttpResponse:
    me = user_of(request)
    p = find_patient(code)
    data = body(request)
    name = normalize_text(text(data, "name"))[:100]
    if not name:
        raise invalid("نام دارو را وارد کنید.", {"name": "نام دارو را وارد کنید."})
    with transaction.atomic():
        m = Medication.objects.create(
            patient=p, name=name, dosage=normalize_text(text(data, "dosage"))[:60] or None,
            frequency=normalize_text(text(data, "frequency"))[:60] or None,
        )
        audit(me.id, "medication_add", p.pk)
    return ok({"id": m.pk}, 201)


def remove_medication(request: HttpRequest, code: str, mid: str) -> HttpResponse:
    me = user_of(request)
    p = find_patient(code)
    with transaction.atomic():
        n, _ = Medication.objects.filter(pk=id_of(mid), patient=p).delete()
        if n:
            audit(me.id, "medication_remove", p.pk)
    return ok()


# ---- history and standing discount ----------------------------------------------------------------

def history(request: HttpRequest, code: str) -> HttpResponse:
    from apps.billing.views import bill_json
    from apps.visits.models import Visit

    p = find_patient(code)
    cur = _cur()
    visits = []
    totals = {"owed": 0, "paid": 0, "remaining": 0, "credit": 0}
    rows = list(Visit.objects.filter(patient=p).order_by("-visit_date", "-visit_time", "-id"))
    bills, numbers = bills_for(rows), visit_numbers(rows)  # C1: a few queries for the whole history
    for v in rows:
        b = bills[v.pk]
        for k in totals:
            totals[k] += b[k]
        visits.append({
            "id": v.pk, "date": present.d(v.visit_date), "time": hhmm(v.visit_time), "status": v.status,
            "reason": v.reason, "doctorNote": v.doctor_note, "number": numbers[v.pk], "bill": bill_json(b, cur),
        })
    return ok({
        "patient": patient_full(p, cur, True), "visits": visits,  # the route needs finance
        "totals": {k: present.money(v, cur) for k, v in totals.items()},
    })


def set_discount(request: HttpRequest, code: str) -> HttpResponse:
    me = user_of(request)
    p = find_patient(code)
    data = body(request)
    d = parse_discount(
        text(data, "discKind") or text(data, "disc_kind"),
        raw_field(data, "discValue") or raw_field(data, "disc_value"),
        _cur(),
    )
    if d and "error" in d:
        raise invalid(str(d["error"]), {"discValue": str(d["error"])})
    with transaction.atomic():
        Patient.objects.filter(pk=p.pk).update(disc_kind=d["kind"] if d else None, disc_value=d["value"] if d else 0)
        audit(me.id, "patient_discount", p.pk, f"{d['kind']}={d['value']}" if d else "none")
    return ok()


# ---- layout editor --------------------------------------------------------------------------------

def layout_page(request: HttpRequest) -> HttpResponse:
    used_boxes = set(PatientValue.objects.values_list("box_id", flat=True).distinct())
    used_choices: dict[str, list[str]] = {}
    for bid, value in PatientValue.objects.values_list("box_id", "value").distinct():
        used_choices.setdefault(str(bid), []).append(value)
    return ok({
        "layout": L.read_layout("patient_form"),
        "catalogue": {"cards": CARDS, "boxes": BOXES, "types": CUSTOM_TYPES},
        "customBoxes": [box_json(b) for b in live_custom_boxes()],
        "usedBoxes": sorted(used_boxes),
        "usedChoices": used_choices,
        "hasPrevious": L.has_previous("patient_form"),
        "taken": sorted(taken_name_keys()),
        "limits": {"boxName": LIMITS["boxName"], "cardLabel": LIMITS["cardLabel"], "choicesMin": LIMITS["choicesMin"],
                   "choicesMax": LIMITS["choicesMax"], "choiceLabel": LIMITS["boxName"]},
    })


def layout_save_for(name: str) -> Any:
    def save(request: HttpRequest) -> HttpResponse:
        me = user_of(request)
        data = body(request)
        value = data.get("layout", data if data else None)
        if value is None or value == {}:
            raise invalid("چیدمان ذخیره نشد. فرم را دوباره بفرستید.")
        try:
            layout = L.check_layout(name, value)
            L.save_layout(name, layout, me.id)
        except Reject as err:
            raise invalid(str(err)) from None
        except BoxError as err:
            raise invalid(err.message) from None
        return ok({"saved": True, "layout": L.read_layout(name)})

    return save


def layout_undo_for(name: str) -> Any:
    def undo(request: HttpRequest) -> HttpResponse:
        return ok({"undone": L.undo_layout(name, user_of(request).id), "layout": L.read_layout(name)})

    return undo


def layout_reset_for(name: str) -> Any:
    def reset(request: HttpRequest) -> HttpResponse:
        L.reset_layout(name, user_of(request).id)
        return ok({"reset": True, "layout": L.read_layout(name)})

    return reset


def _live_box(box_id: str) -> CustomBox:
    b = CustomBox.objects.filter(pk=id_of(box_id), deleted_at__isnull=True).first()
    if b is None:
        raise not_found(NOT_FOUND)
    return b


def create_box(request: HttpRequest) -> HttpResponse:
    data = body(request)
    try:
        box = create_custom_box(text(data, "type"), text(data, "label"), text(data, "choices"), user_of(request).id)
    except BoxError as err:
        raise invalid(err.message, {"box": err.message}) from None
    return ok({"box": box_json(box)}, 201)


def box_detail(request: HttpRequest, box_id: str) -> HttpResponse:
    b = _live_box(box_id)
    return ok({"box": box_json(b), "used": PatientValue.objects.filter(box=b).exists()})


def box_delete(request: HttpRequest, box_id: str) -> HttpResponse:
    b = _live_box(box_id)
    try:
        delete_custom_box(b.pk, user_of(request).id)
    except BoxError as err:
        raise conflict(err.message) from None
    return ok()


def box_choices(request: HttpRequest, box_id: str) -> HttpResponse:
    b = _live_box(box_id)
    data = body(request)
    action = text(data, "op") or text(data, "action")
    uid = user_of(request).id
    try:
        if action == "add":
            add_choices(b.pk, text(data, "text"), uid)
        elif action in ("hide", "show"):
            set_choice_hidden(b.pk, text(data, "choice"), action == "hide", uid)
        elif action == "remove":
            remove_choice(b.pk, text(data, "choice"), uid)
        else:
            raise invalid("این کار را نمی‌شناسیم.")
    except BoxError as err:
        raise invalid(err.message, {"choice": err.message}) from None
    return ok({"box": box_json(CustomBox.objects.get(pk=b.pk))})


patients_view = route(GET=list_patients, POST=create)
patient_view = route(GET=show, PATCH=edit, DELETE=delete)
layout_view = route(GET=layout_page, PUT=layout_save_for("patient_form"), POST=layout_save_for("patient_form"))
