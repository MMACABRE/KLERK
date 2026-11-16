"""Documents and photo API (SPEC §5.4; legacy src/routes/documents.js). Files are served only here."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from django.db import IntegrityError, transaction
from django.http import FileResponse, HttpRequest, HttpResponse
from django.http.response import HttpResponseBase
from django.utils import timezone

from apps.core.audit import audit
from apps.core.files import _ext, move_to_trash, resolve_patient_file
from apps.core.http import ApiError, body, id_of, invalid, not_found, ok, route, text, user_of
from apps.core.models import AuditLog
from apps.core.text import normalize_text
from apps.core.uploads import EXT_TYPE, MIME
from apps.documents.models import Document, DocumentFolder
from apps.documents.services import (
    FOLDER_MAX,
    FOLDER_MESSAGES,
    INLINE_TYPES,
    MOVE_MAX,
    PHOTO_TYPES,
    disposition,
    documents_for,
    folder_name,
    folder_of,
    folder_summary,
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
    folder = request.GET.get("folder", "")[:16]
    return ok({
        "patient": {"code": p.code, "firstName": p.first_name, "lastName": p.last_name},
        "category": category, "q": q, "folder": folder,
        "docs": [doc_item(d) for d in documents_for(p, category, q, folder)],
        **folder_summary(p, documents_for(p)),
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
        try:
            meta["folder"] = folder_of(p, data.get("folder"))  # SPEC 14.5.1: the selection's shared folder
        except LookupError:
            raise not_found(NOT_FOUND) from None
        try:
            with transaction.atomic():
                name = save_document(p, up, meta, me.id)
        except IntegrityError:  # the folder was deleted meanwhile
            raise not_found(NOT_FOUND) from None
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
    if "folder" in data:  # without the key the folder stays as it is (SPEC §14.5.3)
        try:
            meta["folder"] = folder_of(p, data["folder"])
        except LookupError:
            raise not_found(NOT_FOUND) from None
    try:
        with transaction.atomic():
            row = Document.objects.filter(patient=p, filename=filename).first()
            if row is None:
                Document.objects.create(patient=p, filename=filename, uploaded_by_id=me.id, **meta)
            else:
                for k, v in meta.items():
                    setattr(row, k, v)
                row.save()
            audit(me.id, "document_edit", p.pk)
    except IntegrityError:  # the folder was deleted meanwhile
        raise not_found(NOT_FOUND) from None
    return ok()


# ---- folders (SPEC §14.5.4). Folder names are patient data: never in the audit detail. -------------------------

def _bar(p: Patient) -> dict[str, object]:
    return folder_summary(p, documents_for(p))


def _folder_error(key: str) -> ApiError:
    return invalid(FOLDER_MESSAGES[key], {"name": FOLDER_MESSAGES[key]})


def create_folder(request: HttpRequest, code: str) -> HttpResponse:
    me = user_of(request)
    p = _patient(code)
    name, err = folder_name(body(request).get("name"))
    if err:
        raise _folder_error(err)
    try:
        with transaction.atomic():
            Patient.objects.select_for_update().filter(pk=p.pk).first()  # one folder count at a time per patient
            if DocumentFolder.objects.filter(patient=p).count() >= FOLDER_MAX:
                raise _folder_error("limit")
            if DocumentFolder.objects.filter(patient=p, name=name).exists():
                raise _folder_error("taken")
            f = DocumentFolder.objects.create(patient=p, name=name, created_by_id=me.id)
            audit(me.id, "folder_create", p.pk)
    except IntegrityError:
        raise _folder_error("taken") from None
    return ok({"id": f.pk, "name": f.name, **_bar(p)}, 201)


def _folder(p: Patient, fid: str) -> DocumentFolder:
    f = DocumentFolder.objects.filter(patient=p, pk=id_of(fid)).first()
    if f is None:
        raise not_found(NOT_FOUND)
    return f


def rename_folder(request: HttpRequest, code: str, fid: str) -> HttpResponse:
    me = user_of(request)
    p = _patient(code)
    f = _folder(p, fid)
    name, err = folder_name(body(request).get("name"))
    if err:
        raise _folder_error(err)
    if DocumentFolder.objects.filter(patient=p, name=name).exclude(pk=f.pk).exists():
        raise _folder_error("taken")
    try:
        with transaction.atomic():
            DocumentFolder.objects.filter(pk=f.pk).update(name=name)
            audit(me.id, "folder_rename", p.pk)
    except IntegrityError:
        raise _folder_error("taken") from None
    return ok({"id": f.pk, "name": name, **_bar(p)})


def delete_folder(request: HttpRequest, code: str, fid: str) -> HttpResponse:
    """The folder goes; its documents stay and show under «بدون پوشه». No file is touched."""
    me = user_of(request)
    p = _patient(code)
    f = _folder(p, fid)
    with transaction.atomic():
        Document.objects.filter(patient=p, folder=f).update(folder=None)
        f.delete()
        audit(me.id, "folder_delete", p.pk)
    return ok(_bar(p))


def move_docs(request: HttpRequest, code: str) -> HttpResponse:
    """POST {filenames: [...], folder: id|null}: move documents into a folder or out of every folder. Each file must
    be in the patient's folder on disk; a file with no metadata row gets one."""
    me = user_of(request)
    p = _patient(code)
    data = body(request)
    names = data.get("filenames")
    if not isinstance(names, list) or not names or len(names) > MOVE_MAX or not all(isinstance(n, str) for n in names):
        raise invalid(FIX, {"filenames": FIX})
    try:
        folder = folder_of(p, data.get("folder"))
    except LookupError:
        raise not_found(NOT_FOUND) from None
    found = []
    for n in dict.fromkeys(names):
        full = resolve_patient_file(p.code, n)
        if not full:
            raise not_found(NOT_FOUND)
        found.append(full.name)
    try:
        with transaction.atomic():
            if folder is not None and not DocumentFolder.objects.select_for_update().filter(pk=folder.pk).exists():
                raise not_found(NOT_FOUND)
            have = set(Document.objects.filter(patient=p, filename__in=found).values_list("filename", flat=True))
            Document.objects.bulk_create([
                Document(patient=p, filename=n, uploaded_by_id=me.id, folder=folder) for n in found if n not in have
            ], ignore_conflicts=True)
            Document.objects.filter(patient=p, filename__in=found).update(folder=folder)
            audit(me.id, "document_edit", p.pk, f"move {len(found)}")
    except IntegrityError:
        raise not_found(NOT_FOUND) from None
    return ok({"moved": len(found), **_bar(p)})


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
folders_view = route(POST=create_folder)
folder_view = route(POST=rename_folder, DELETE=delete_folder)
file_view = route(GET=get_file, DELETE=delete_file)
photo_view = route(GET=get_photo, POST=set_photo, DELETE=remove_photo)
