"""Upload rules (D19; legacy src/lib/uploads.js): PDF, JPG, PNG, DICOM only, 1 byte to 30 MB, and the first
bytes must match the extension. Files are never decoded. A file lands in data/tmp first and is moved into
the patient folder only after every check (os.replace on the same disk)."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from django.core.files.uploadedfile import UploadedFile

from apps.core.files import _ext, claim_move, ensure_patient_dir, safe_name, tmp_dir

MAX_UPLOAD_BYTES = 30 * 1024 * 1024
HEAD_BYTES = 132
EXT_TYPE = {".pdf": "pdf", ".jpg": "jpg", ".jpeg": "jpg", ".png": "png", ".dcm": "dcm"}
MIME = {"pdf": "application/pdf", "jpg": "image/jpeg", "png": "image/png", "dcm": "application/dicom"}

MSG_HEIC = "فرمت HEIC پشتیبانی نمی‌شود. عکس را به JPG تبدیل کنید و دوباره بارگذاری کنید."
MSG_TYPE = "فقط فایل‌های PDF، JPG، PNG و DCM مجاز است."
MSG_EMPTY = "فایل خالی است."
MSG_BIG = "حجم فایل بیش از ۳۰ مگابایت است."
MSG_MAGIC = "محتوای فایل با پسوند آن نمی‌خواند."


def detect_type(head: bytes) -> str | None:
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(head) >= 132 and head[128:132] == b"DICM":
        return "dcm"
    return None


def check_upload(original_name: str, size: int, head: bytes) -> tuple[str | None, str | None]:
    """(type, None) when the file is allowed, else (None, Persian error)."""
    ext = _ext(str(original_name or "")).lower()
    if ext in (".heic", ".heif"):
        return None, MSG_HEIC
    expected = EXT_TYPE.get(ext)
    if not expected:
        return None, MSG_TYPE
    if not size:
        return None, MSG_EMPTY
    if size > MAX_UPLOAD_BYTES:
        return None, MSG_BIG
    if detect_type(head) != expected:
        return None, MSG_MAGIC
    return expected, None


def _head(f: UploadedFile) -> bytes:
    f.seek(0)
    head: bytes = f.read(HEAD_BYTES)
    f.seek(0)
    return head


def check_file(f: UploadedFile) -> tuple[str | None, str | None]:
    return check_upload(f.name or "", f.size or 0, _head(f))


def stage(f: UploadedFile) -> Path:
    """Write an upload to data/tmp/<uuid> (mode 600)."""
    target = tmp_dir() / uuid.uuid4().hex
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as out:
        f.seek(0)
        for chunk in f.chunks():
            out.write(chunk)
    return target


def place(staged: Path, code: str, original_name: str, name: str | None = None) -> str:
    """Move a staged file into the patient folder under a safe, unique name. Returns the name."""
    directory = ensure_patient_dir(code)
    return claim_move(staged, directory, name or safe_name(original_name))


def discard(paths: Any) -> None:
    for p in paths:
        try:
            Path(p).unlink(missing_ok=True)
        except OSError:
            pass
