"""Diagnostics files (ADR-0013 "Storage"): one JSON object per line under DATA_DIR/diagnostics/.

Each process writes its own files (`<kind>.<process>.jsonl`, process `web-<pid>` or `worker`), so gunicorn workers
never race on rotation; the reader merges every file of a kind by time. Every record gets `ts` (UTC ISO with
microseconds) and `id` (`<process>-<counter>`), which together order the records and make the paging cursor.

Nothing here may raise into the caller: a failing write is dropped.
"""

from __future__ import annotations

import base64
import json
import os
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from apps.core.files import data_dir

KINDS = ("errors", "logs", "client")
CAPS = {"errors": (5_000_000, 4), "logs": (5_000_000, 4), "client": (2_000_000, 3)}  # bytes per file, files kept
LOW_DISK_BYTES = 1_000_000_000  # under this, logs stop (errors and client errors go on)
KEEP_DAYS = 30

_lock = threading.Lock()
_counter = 0
_process = f"web-{os.getpid()}"


def set_process(name: str) -> None:
    """The worker calls set_process("worker") once at start."""
    global _process
    _process = name


def process_name() -> str:
    return _process


def folder() -> Path:
    return data_dir() / "diagnostics"


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def disk_free(path: Path | None = None) -> int | None:
    try:
        st = os.statvfs(path or data_dir())
    except (OSError, AttributeError):
        return None
    return st.f_bavail * st.f_frsize


def logs_paused() -> bool:
    free = disk_free()
    return free is not None and free < LOW_DISK_BYTES


def _rotate(path: Path, keep: int) -> None:
    for n in range(keep - 1, 0, -1):
        older = path.with_name(f"{path.name}.{n}")
        if older.exists():
            if n == keep - 1:
                older.unlink(missing_ok=True)
            else:
                older.replace(path.with_name(f"{path.name}.{n + 1}"))
    path.replace(path.with_name(f"{path.name}.1"))


def append(kind: str, record: dict[str, Any]) -> None:
    """Add `ts` and `id` and write one line. Swallows every error."""
    global _counter
    try:
        if kind == "logs" and logs_paused():
            return
        d = folder()
        d.mkdir(parents=True, exist_ok=True)
        with _lock:
            _counter += 1
            line = {"ts": now_iso(), "id": f"{_process}-{_counter}", **record}
            path = d / f"{kind}.{_process}.jsonl"
            cap, keep = CAPS[kind]
            if path.exists() and path.stat().st_size > cap:
                _rotate(path, keep)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(line, ensure_ascii=False, separators=(",", ":")) + "\n")
    except Exception:  # noqa: BLE001 - the recorder must never turn one error into two
        pass


def _files(kind: str) -> list[Path]:
    d = folder()
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir() if p.name.startswith(f"{kind}.") and ".jsonl" in p.name)


def _records(kind: str) -> Iterator[dict[str, Any]]:
    for path in _files(kind):
        try:
            with open(path, encoding="utf-8") as f:
                for raw in f:
                    try:
                        rec = json.loads(raw)
                    except ValueError:
                        continue  # a line cut by a crash
                    if isinstance(rec, dict) and isinstance(rec.get("ts"), str):
                        yield rec
        except OSError:
            continue


def _key(rec: dict[str, Any]) -> tuple[str, str]:
    return (str(rec.get("ts", "")), str(rec.get("id", "")))


def encode_cursor(rec: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(list(_key(rec))).encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[str, str] | None:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        ts, rid = json.loads(raw)
        return (str(ts), str(rid))
    except (ValueError, TypeError):
        return None


def read(kinds: tuple[str, ...], since: str | None, limit: int, process: str | None = None) -> dict[str, Any]:
    """Records of the given kinds after the cursor, merged and oldest first. `process` keeps one family: `web`,
    `worker` or `client`. `gap` is true when the cursor's record is gone and older than every kept record
    (rotation removed what came in between)."""
    after = decode_cursor(since) if since else None
    every = sorted((r for k in kinds for r in _records(k)), key=_key)
    if process:
        every = [r for r in every if r.get("process") == process]
    gap = bool(after and every and _key(every[0]) > after)
    items = [r for r in every if after is None or _key(r) > after][:limit]
    nxt = encode_cursor(items[-1]) if items else (since or "")
    return {"items": items, "next": nxt, "gap": gap}


def error_groups(since: str | None, limit: int) -> dict[str, Any]:
    """Error reports after the cursor, grouped by fingerprint: count, first and last seen, the latest sample."""
    page = read(("errors",), since, 100_000)
    groups: dict[str, dict[str, Any]] = {}
    for rec in page["items"]:
        fp = str(rec.get("fingerprint", ""))
        g = groups.get(fp)
        if g is None:
            groups[fp] = {"fingerprint": fp, "count": 1, "first_seen": rec["ts"], "last_seen": rec["ts"],
                          "sample": rec}
        else:
            g["count"] += 1
            g["last_seen"] = rec["ts"]
            g["sample"] = rec
    items = sorted(groups.values(), key=lambda g: g["last_seen"], reverse=True)[:limit]
    return {"items": items, "next": page["next"], "gap": page["gap"]}


def recent_error_count(seconds: int = 300) -> int:
    cutoff = datetime.fromtimestamp(time.time() - seconds, UTC).isoformat(timespec="microseconds").replace(
        "+00:00", "Z")
    return sum(1 for r in _records("errors") if r["ts"] >= cutoff)


def sweep(now: float | None = None) -> int:
    """Delete diagnostics files untouched for KEEP_DAYS (the worker runs it daily)."""
    cutoff = (now or time.time()) - KEEP_DAYS * 86400
    removed = 0
    for kind in KINDS:
        for p in _files(kind):
            try:
                if p.stat().st_mtime < cutoff:
                    p.unlink()
                    removed += 1
            except OSError:
                continue
    return removed
