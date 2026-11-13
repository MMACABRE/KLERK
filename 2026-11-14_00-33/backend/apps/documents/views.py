"""Documents and photo API (SPEC §5.4; legacy src/routes/documents.js). Files are served only here."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from django.db import transaction
from django.http import FileResponse, HttpRequest, HttpResponse
from django.http.response import HttpResponseBase
from django.utils import timezone

from apps.core.audit import audit
from apps.core.files import _ext, move_to_trash, resolve_patient_file
from apps.core.http import ApiError, body, invalid, not_found, ok, route, text, user_of
from apps.core.models import AuditLog
from apps.core.text import normalize_text
from apps.core.uploads import EXT_TYPE, MIME
from apps.documents.models import Document
from apps.documents.services import (
    INLINE_TYPES,
    PHOTO_TYPES,
    disposition,
    documents_for,
    receive,
    save_document,
    store_upload,
    validate_meta,
)
from apps.patients.models import Patient
from apps.patients.views import doc_item, find_patient

NOT_FOUND = "پرونده یا فایل مورد نظر پیدا نشد."
FIX = "لطفاً خطاهای مشخص‌شده را برطرف کنید."
INLINE_AUDIT_WINDOW = timedelta(minutes=10)


def _patient(code: str) -> Patient:
    try:
        return find_patient(code)
    except ApiError:
        raise not_found(NOT_FOUND) from None


def list_docs(request: HttpRequest, code: str) -> HttpResponse:
    p = _patient(code)
    category = request.GET.get("category", "")
    q = normalize_text(request.GET.get("q", "")[:100])
    return ok({
        "patient": {"code": p.code, "firstName": p.first_name, "lastName": p.last_name},
        "category": category, "q": q,
        "docs": [doc_item(d) for d in documents_for(p, category, q)],
    })


def upload(request: HttpRequest, code: str) -> HttpResponse:
    me = user_of(request)
    p = _patient(code)
    data = body(request)
    try:
        up = receive(request.FILES.get("file"))
    except ValueError as err:
        raise invalid(str(err), {"file": str(err)}) from None
    try:
        meta, errors = validate_meta(data)
        if errors:
            raise invalid(FIX, errors)
        with transaction.atomic():
            name = save_document(p, up, meta, me.id)
    finally:
        up.discard()
    return ok({"filename": name}, 201)


def classify(request: HttpRequest, code: str) -> HttpResponse:
    me = user_of(request)
    p = _patient(code)
    data = body(request)
    filename = text(data, "filename")
    if not resolve_patient_file(p.code, filename):
        raise not_found(NOT_FOUND)
    meta, errors = validate_meta(data)
    if errors:
        raise invalid(FIX, errors)
    with transaction.atomic():
        row = Document.objects.filter(patient=p, filename=filename).first()
        if row is None:
            Document.objects.create(patient=p, filename=filename, uploaded_by_id=me.id, **meta)
        else:
            for k, v in meta.items():
                setattr(row, k, v)
            row.save()
        audit(me.id, "document_edit", p.pk)
    return ok()


def delete_file(request: HttpRequest, code: str, name: str) -> HttpResponse:
    me = user_of(request)
    p = _patient(code)
    full = resolve_patient_file(p.code, name)
    if not full:
        raise not_found(NOT_FOUND)
    move_to_trash(full, p.code)
    with transaction.atomic():
        Document.objects.filter(patient=p, filename=full.name).delete()
        if p.photo == full.name:
            Patient.objects.filter(pk=p.pk).update(photo=None, updated_at=timezone.now(), updated_by_id=me.id)
        audit(me.id, "document_delete", p.pk, EXT_TYPE.get(_ext(full.name).lower(), "other"))
    return ok()


def _send(full: Path, type_: str | None, disp: str | None) -> FileResponse:
    response = FileResponse(open(full, "rb"), content_type=MIME.get(type_ or "", "application/octet-stream"))
    if disp:
        response["Content-Disposition"] = disp
    response["Content-Security-Policy"] = "sandbox"
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def get_file(request: HttpRequest, code: str, name: str) -> HttpResponseBase:
    me = user_of(request)
    p = _patient(code)
    full = resolve_patient_file(p.code, name)
    if not full:
        raise not_found(NOT_FOUND)
    type_ = EXT_TYPE.get(_ext(full.name).lower())
    inline = request.GET.get("inline") == "1" and type_ in INLINE_TYPES
    detail = type_ or "other"
    # A download always writes a row. An inline view (thumbnails, the preview pane) writes one per user, patient
    # and file type per window, so a gallery does not flood the log. No request header can skip it.
    if not inline or not AuditLog.objects.filter(
        user_id=me.id, action="document_download", patient_id=p.pk, detail=detail,
        ts__gte=timezone.now() - INLINE_AUDIT_WINDOW,
    ).exists():
        audit(me.id, "document_download", p.pk, detail)
    return _send(full, type_, disposition("inline" if inline else "attachment", full.name))


def get_photo(request: HttpRequest, code: str) -> HttpResponseBase:
    p = Patient.objects.filter(code=code).first()
    full = resolve_patient_file(p.code, p.photo) if p and p.photo else None
    type_ = EXT_TYPE.get(_ext(full.name).lower()) if full else None
    if not full or type_ not in PHOTO_TYPES:
        return HttpResponse(status=404)
    return _send(full, type_, None)


def set_photo(request: HttpRequest, code: str) -> HttpResponse:
    me = user_of(request)
    p = _patient(code)
    f = request.FILES.get("file")
    try:
        up = receive(f)
    except ValueError as err:
        key = "missing" if f is None else "size" if (f.size or 0) > 30 * 1024 * 1024 else "type"
        raise invalid(str(err), {"photo": key}) from None
    try:
        if up.type not in PHOTO_TYPES:
            raise invalid("عکس باید فایل JPG یا PNG باشد.", {"photo": "type"})
        filename = store_upload(p.code, up)
        with transaction.atomic():
            Document.objects.update_or_create(
                patient=p, filename=filename,
                defaults={"category": "other", "title": "عکس پروفایل", "doc_date": None, "notes": None,
                          "uploaded_by_id": me.id, "uploaded_at": timezone.now()},
            )
            Patient.objects.filter(pk=p.pk).update(photo=filename, updated_at=timezone.now(), updated_by_id=me.id)
            audit(me.id, "photo_set", p.pk, up.type)
    finally:
        up.discard()
    return ok()


def remove_photo(request: HttpRequest, code: str) -> HttpResponse:
    me = user_of(request)
    p = _patient(code)
    with transaction.atomic():
        Patient.objects.filter(pk=p.pk).update(photo=None, updated_at=timezone.now(), updated_by_id=me.id)
        audit(me.id, "photo_remove", p.pk)
    return ok()


documents_view = route(GET=list_docs, POST=upload)
file_view = route(GET=get_file, DELETE=delete_file)
photo_view = route(GET=get_photo, POST=set_photo, DELETE=remove_photo)
