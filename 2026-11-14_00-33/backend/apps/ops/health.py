"""System problems the owner should see on every page (critique S4).

`problems()` returns short codes; the Vue app turns each into one Persian sentence:
- `worker`: the worker heartbeat is older than `WORKER_STALE_S` (SMS, imports and the nightly backup stop).
- `backup`: the newest nightly dump is older than `BACKUP_STALE_H` hours, or there is none.
"""

from __future__ import annotations

import os
import time

from apps.core.files import data_dir
from apps.ops.backup import NAME_RE

WORKER_STALE_S = 180  # the worker writes its heartbeat every 60 s
BACKUP_STALE_H = 26  # the nightly dump runs at 03:00; two hours of slack


def worker_alive(now: float | None = None) -> bool:
    try:
        age = (now if now is not None else time.time()) - (data_dir() / "worker.heartbeat").stat().st_mtime
    except OSError:
        return False
    return age < WORKER_STALE_S


def last_backup_age_hours(now: float | None = None) -> float | None:
    """Age in hours of the newest nightly dump in data/backups, or None when there is none."""
    d = data_dir() / "backups"  # not backup_dir(): reading must not create the folder
    newest: float | None = None
    try:
        names = os.listdir(d)
    except OSError:
        return None
    for name in names:
        if not NAME_RE.match(name):
            continue
        try:
            mtime = (d / name).stat().st_mtime
        except OSError:
            continue
        newest = mtime if newest is None else max(newest, mtime)
    if newest is None:
        return None
    return ((now if now is not None else time.time()) - newest) / 3600


def problems(now: float | None = None) -> list[str]:
    out: list[str] = []
    if not worker_alive(now):
        out.append("worker")
    age = last_backup_age_hours(now)
    if age is None or age > BACKUP_STALE_H:
        out.append("backup")
    return out
