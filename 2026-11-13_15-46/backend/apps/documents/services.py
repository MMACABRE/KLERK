"""Documents: folder listing joined with metadata, upload, classify, delete to trash, photo
(legacy src/routes/documents.js). The folder on disk decides which files exist."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from django.core.files.uploadedfile import UploadedFile
from django.utils import timezone

from apps.core.audit import audit
from apps.core.files import _ext, claim_move, ensure_patient_dir, list_patient_files, safe_name, unique_name
from apps.core.jalali import fa_digits, parse_jalali
from apps.core.text import fa_key, normalize_text
from apps.core.uploads import EXT_TYPE, MAX_UPLOAD_BYTES, check_file, stage
from apps.documents.models import Document
from apps.patients.models import Patient

CATEGORIES = ["consent", "lab", "imaging", "surgery", "other"]
INLINE_TYPES = {"pdf", "jpg", "png"}
PHOTO_TYPES = {"jpg", "png"}
NEW_FILES_MAX = 10
NEW_FILES_BYTES = MAX_UPLOAD_BYTES

UPLOAD_MESSAGES = {
    "size": "حجم فایل بیش از ۳۰ مگابایت است.",
    "bad": "درخواست بارگذاری معتبر نیست.",
    "missing": "فایلی انتخاب نشده است.",
}
PHOTO_ERRORS = {
    "type": "عکس باید فایل JPG یا PNG باشد.",
    "size": "حجم عکس بیش از ۳۰ مگابایت است.",
    "missing": "فایلی انتخاب نشده است.",
    "bad": "درخواست بارگذاری معتبر نیست.",
}


class Checked:
    """An upload that passed every check, staged in data/tmp."""

    def __init__(self, tmp: Path, original: str, type_: str) -> None:
        self.tmp = tmp
        self.original = original
        self.type = type_

    def discard(self) -> None:
        try:
            self.tmp.unlink(missing_ok=True)
        except OSError:
            pass


def receive(f: UploadedFile | None) -> Checked:
    """Check and stage one upload. Raises ValueError(Persian message)."""
    if f is None:
        raise ValueError(UPLOAD_MESSAGES["missing"])
    type_, error = check_file(f)
    if error or type_ is None:
        raise ValueError(error or UPLOAD_MESSAGES["bad"])
    return Checked(stage(f), f.name or "", type_)


def receive_many(files: list[UploadedFile]) -> list[Checked]:
    if len(files) > NEW_FILES_MAX:
        raise ValueError(f"حداکثر {fa_digits(str(NEW_FILES_MAX))} فایل را می‌توان یک‌جا بارگذاری کرد.")
    if sum(f.size or 0 for f in files) > NEW_FILES_BYTES:
        raise ValueError(f"حجم همه‌ی فایل‌ها با هم بیش از {fa_digits('30')} مگابایت است.")
    for f in files:
        type_, error = check_file(f)
        if error:
            raise ValueError(f"{f.name}: {error}")
    return [Checked(stage(f), f.name or "", check_file(f)[0] or "") for f in files]


def store_upload(code: str, up: Checked) -> str:
    directory = ensure_patient_dir(code)
    name = safe_name(up.original)
    if EXT_TYPE.get(_ext(name).lower()) != up.type:
        name += f".{up.type}"
    return claim_move(up.tmp, directory, name, unique_name)


def validate_meta(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    def get(k: str) -> str:
        v = data.get(k)
        return normalize_text(v) if isinstance(v, str) else ""

    errors: dict[str, str] = {}
    category = get("category") or "other"
    if category not in CATEGORIES:
        errors["category"] = "طبقه‌بندی نامعتبر است."
    raw = get("docDate") or get("doc_date")
    doc_date: date | None = None
    if raw:
        doc_date = parse_jalali(raw)
        if doc_date is None:
            errors["docDate"] = "تاریخ را به شکل ۱۴۰۳/۰۵/۱۲ وارد کنید."
    title = get("title")
    notes = get("notes")
    if len(title) > 200:
        errors["title"] = "عنوان بیش از حد طولانی است."
    if len(notes) > 2000:
        errors["notes"] = "یادداشت بیش از حد طولانی است."
    return {"category": category, "doc_date": doc_date, "title": title or None, "notes": notes or None}, errors


def save_document(patient: Patient, up: Checked, meta: dict[str, Any], user_id: int | None,
                  placed: list[str] | None = None) -> str:
    """Move a checked upload into the folder and record its metadata. Call inside a transaction.
    `placed` gets the file name as soon as the file is in the folder, so a caller can undo it."""
    filename = store_upload(patient.code, up)
    if placed is not None:
        placed.append(filename)
    Document.objects.update_or_create(
        patient=patient, filename=filename,
        defaults={**meta, "uploaded_by_id": user_id, "uploaded_at": timezone.now()},
    )
    audit(user_id, "document_upload", patient.pk, up.type)
    return filename


def documents_for(patient: Patient, category: str = "", q: str = "") -> list[dict[str, Any]]:
    meta = {d.filename: d for d in Document.objects.filter(patient=patient)}
    needle = fa_key(q)
    out = []
    for f in list_patient_files(patient.code):
        row = meta.get(f["filename"])
        if category == "unclassified" and row:
            continue
        if category in CATEGORIES and (row is None or row.category != category):
            continue
        if needle and needle not in fa_key(f"{f['filename']} {row.title if row and row.title else ''}"):
            continue
        out.append({**f, "row": row})
    return out


def disposition(kind: str, name: str) -> str:
    from urllib.parse import quote

    ascii_name = "".join("_" if (ord(c) < 0x20 or ord(c) > 0x7E or c in '"\\') else c for c in name)
    utf8 = quote(name, safe="!-._~")  # encodeURIComponent minus ' ( ) * which are escaped too
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8}"
