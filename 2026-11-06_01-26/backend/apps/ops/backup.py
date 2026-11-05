"""Database backups (SPEC §8): mysqldump | gzip into data/backups, newest 14 kept.

Credentials go through a --defaults-extra-file written mode 600 in the temp folder, never on the command line.
A dump is written under a .partial name and renamed when complete.
"""

from __future__ import annotations

import gzip
import os
import re
import shutil
import subprocess  # nosec B404 - fixed argument list, no shell
import tempfile
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import IO

from django.conf import settings
from django.utils import timezone

KEEP_BACKUPS = 14
NAME_RE = re.compile(r"^klerk-\d{4}-\d{2}-\d{2}\.sql\.gz$")


def backup_dir() -> Path:
    d = Path(settings.DATA_DIR) / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


@contextmanager
def _defaults_file() -> Iterator[str]:
    db = settings.DATABASES["default"]
    fd, path = tempfile.mkstemp(prefix="klerk-my-", suffix=".cnf")
    try:
        os.chmod(path, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("[client]\n")
            f.write(f"user={db['USER']}\n")
            f.write(f"password={db['PASSWORD']}\n")
            f.write(f"host={db['HOST']}\n")
            f.write(f"port={db['PORT']}\n")
        yield path
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def dump_to(out: IO[bytes]) -> None:
    """Write a plain SQL dump of the database to `out`. Raises RuntimeError when mysqldump fails."""
    db = settings.DATABASES["default"]
    exe = shutil.which("mysqldump")
    if exe is None:
        raise RuntimeError("mysqldump not found")
    with _defaults_file() as cnf:
        # Oracle's mysqldump 8.4 (deploy/backend.Dockerfile). MariaDB's would write values for
        # generated columns, which MySQL refuses on restore.
        args: list[str] = [
            exe, f"--defaults-extra-file={cnf}", "--single-transaction", "--quick", "--routines", "--triggers",
            "--hex-blob", "--no-tablespaces", "--default-character-set=utf8mb4", "--set-gtid-purged=OFF",
            str(db["NAME"]),
        ]
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)  # nosec B603
        assert proc.stdout is not None
        shutil.copyfileobj(proc.stdout, out, 1024 * 1024)
        _, err = proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"mysqldump exit {proc.returncode}: {err.decode('utf-8', 'replace')[:200]}")


def _write_gz(final: Path) -> Path:
    partial = final.with_name(f"{final.name}.{os.getpid()}-{uuid.uuid4().hex[:8]}.partial")
    try:
        fd = os.open(partial, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=6) as gz:
            dump_to(gz)  # type: ignore[arg-type]
        os.replace(partial, final)
    finally:
        partial.unlink(missing_ok=True)
    return final


def backup_now(now: datetime | None = None) -> Path:
    now = timezone.localtime(now or timezone.now())
    d = backup_dir()
    final = _write_gz(d / f"klerk-{now:%Y-%m-%d}.sql.gz")
    names = sorted((n for n in os.listdir(d) if NAME_RE.match(n)), reverse=True)
    for n in names[KEEP_BACKUPS:]:
        (d / n).unlink(missing_ok=True)
    for n in os.listdir(d):
        p = d / n
        if n.endswith(".partial") and time.time() - p.stat().st_mtime > 24 * 3600:
            p.unlink(missing_ok=True)
    return final


def backup_before_wipe(now: datetime | None = None) -> Path:
    now = timezone.localtime(now or timezone.now())
    return _write_gz(backup_dir() / f"klerk-{now:%Y-%m-%d-%H%M%S}-before-wipe.sql.gz")


def has_backup_for(now: datetime | None = None) -> bool:
    now = timezone.localtime(now or timezone.now())
    return (backup_dir() / f"klerk-{now:%Y-%m-%d}.sql.gz").exists()
