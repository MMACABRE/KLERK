"""Patient folders on disk: DATA_DIR/patients/P-000123/<files> (SPEC §3.8; legacy src/lib/files.js).

The folder is the source of truth for which files exist. Every path built from user input goes through
this module.
"""

from __future__ import annotations

import os
import re
import time
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from django.conf import settings

from apps.core.codes import is_code

MAX_NAME = 120
MAX_NAME_BYTES = 200
ZWNJ = "‌"


def data_dir() -> Path:
    return Path(settings.DATA_DIR)


def tmp_dir() -> Path:
    d = data_dir() / "tmp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def trash_dir() -> Path:
    return data_dir() / "trash"


def patient_dir(code: str) -> Path:
    if not is_code(code):
        raise ValueError("invalid patient code")
    return data_dir() / "patients" / code


def patient_dir_exists(code: str) -> bool:
    return patient_dir(code).exists()


def ensure_patient_dir(code: str) -> Path:
    d = patient_dir(code)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ext(name: str) -> str:
    """path.extname: the last '.' part, unless the name starts with it."""
    base = name.rsplit("/", 1)[-1]
    i = base.rfind(".")
    return base[i:] if i > 0 else ""


def _keep(ch: str) -> bool:
    cat = unicodedata.category(ch)
    return cat[0] in ("L", "M", "N") or ch in (ZWNJ, " ", ".", "_", "-")


def safe_name(original: object) -> str:
    name = unicodedata.normalize("NFC", "" if original is None else str(original))
    name = re.split(r"[\\/]", name)[-1]
    name = "".join(ch if _keep(ch) else "_" for ch in name)
    name = re.sub(r"\s+", " ", name)
    name = re.sub(r"_+", "_", name)
    name = re.sub(r"^[ .‌]+", "", name)
    name = re.sub(r"‌+(?=\.|$)", "", name, count=1).strip()
    if len(name) > MAX_NAME:
        ext = _ext(name)[:10]
        name = name[: MAX_NAME - len(ext)] + ext
    ext = _ext(name)[:10]
    while len(name.encode("utf-8")) > MAX_NAME_BYTES and len(name) > len(ext):
        name = name[: len(name) - len(ext)][:-1] + ext
    return name or "file"


def trash_name(stamp: str, name: str) -> str:
    full_ext = _ext(name)
    ext = full_ext[:10]
    base = name[: len(name) - len(full_ext)]
    while base and len(f"{stamp}-{base}{ext}".encode()) > 255:
        base = base[:-1]
    return f"{stamp}-{base}{ext}"


def unique_name(directory: Path, name: str) -> str:
    ext = _ext(name)
    base = name[: len(name) - len(ext)]
    candidate, i = name, 2
    while (directory / candidate).exists():
        candidate = f"{base}-{i}{ext}"
        i += 1
    return candidate


def resolve_patient_file(code: str, requested: object) -> Path | None:
    """The real path of one file in the patient folder, or None. Exactly one entry name; no symlinks."""
    if not is_code(code) or not isinstance(requested, str):
        return None
    if not requested or len(requested) > 255 or requested.startswith(".") or re.search(r"[/\\\0]", requested):
        return None
    directory = patient_dir(code).resolve()
    try:
        with os.scandir(directory) as it:
            entry = next((e for e in it if e.name == requested), None)
            if entry is None or not entry.is_file(follow_symlinks=False):
                return None
    except OSError:
        return None
    full = directory / requested
    return full if full.parent == directory else None


def list_patient_files(code: str) -> list[dict[str, Any]]:
    """Regular, non-hidden files in the patient folder, newest first."""
    directory = patient_dir(code)
    try:
        entries = list(os.scandir(directory))
    except FileNotFoundError:
        return []
    out = []
    for e in entries:
        if e.name.startswith(".") or not e.is_file(follow_symlinks=False):
            continue
        st = e.stat(follow_symlinks=False)
        out.append({
            "filename": e.name,
            "size": st.st_size,
            "modified": datetime.fromtimestamp(st.st_mtime, UTC).isoformat().replace("+00:00", "Z"),
        })
    out.sort(key=lambda f: str(f["modified"]), reverse=True)
    return out


def sweep_tmp(max_age_s: float = 24 * 3600, now: float | None = None) -> int:
    """Remove files in data/tmp older than max_age_s (uploads, staged imports left by a crash)."""
    directory = data_dir() / "tmp"
    now = time.time() if now is None else now
    removed = 0
    try:
        names = os.listdir(directory)
    except OSError:
        return 0
    for name in names:
        full = directory / name
        try:
            st = full.lstat()
            if full.is_file() and not full.is_symlink() and now - st.st_mtime > max_age_s:
                full.unlink()
                removed += 1
        except OSError:
            pass
    return removed


def stamp_now() -> str:
    """Trash stamp as legacy: the UTC ISO time with ':' and '.' replaced by '-' (2026-11-04T10-20-30-123Z)."""
    now = datetime.now(UTC)
    iso = now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"
    return iso.replace(":", "-").replace(".", "-")


def trash_patient_folder(code: str) -> None:
    """Move a deleted patient's whole folder to data/trash/<code>-<stamp>. A failure is only logged."""
    src = patient_dir(code)
    try:
        if src.exists():
            trash_dir().mkdir(parents=True, exist_ok=True)
            os.replace(src, trash_dir() / f"{code}-{stamp_now()}")
    except OSError as err:
        import logging

        logging.getLogger("klerk").error(
            "patient %s deleted, but its folder could not be moved to trash: %s", code, err.errno
        )


def move_to_trash(src: Path, code: str) -> Path:
    """Move one file into data/trash/<code>/ with a time stamp in front of its name."""
    target_dir = trash_dir() / code
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / trash_name(stamp_now(), src.name)
    os.replace(src, target)
    return target


def secure_data_dir() -> None:
    """umask 077 and mode 700 on the data folder (SPEC §3.8); a failed chmod only warns."""
    os.umask(0o077)
    d = data_dir()
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        import logging

        logging.getLogger("klerk").warning("could not set mode 700 on the data folder")
