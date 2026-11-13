"""Server specs and live stats (ADR-0013 "Stats and specs"). Standard library only.

Every /proc and cgroup read goes through `read_text(path)`, which joins the path to ROOT, so tests point ROOT at a
fixture tree. Container values come from cgroup v2; host values (labelled `host`) from /proc.
"""

from __future__ import annotations

import os
import platform
import sys
import time
from pathlib import Path
from typing import Any

from django.db import DatabaseError, connection

from apps.core.files import data_dir
from apps.diagnostics import store
from apps.diagnostics.capture import version

ROOT = Path("/")


def read_text(path: str) -> str | None:
    try:
        return (ROOT / path.lstrip("/")).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _int(text: str | None) -> int | None:
    if text is None:
        return None
    text = text.strip()
    return int(text) if text.isdigit() else None


def _kv(text: str | None) -> dict[str, int]:
    out: dict[str, int] = {}
    for line in (text or "").splitlines():
        parts = line.replace(":", " ").split()
        if len(parts) >= 2 and parts[1].isdigit():
            out[parts[0]] = int(parts[1])
    return out


def container() -> dict[str, Any]:
    cpu_max = (read_text("/sys/fs/cgroup/cpu.max") or "").split()
    quota = None
    if len(cpu_max) == 2 and cpu_max[0].isdigit() and cpu_max[1].isdigit():
        quota = round(int(cpu_max[0]) / int(cpu_max[1]), 2)
    mem_stat = _kv(read_text("/sys/fs/cgroup/memory.stat"))
    cpu_stat = _kv(read_text("/sys/fs/cgroup/cpu.stat"))
    return {
        "memory_max": _int(read_text("/sys/fs/cgroup/memory.max")),  # None means no limit ("max")
        "memory_current": _int(read_text("/sys/fs/cgroup/memory.current")),
        "memory_anon": mem_stat.get("anon"), "memory_file": mem_stat.get("file"),
        "cpu_quota": quota, "cpu_usage_usec": cpu_stat.get("usage_usec"),
        "cpu_throttled_usec": cpu_stat.get("throttled_usec"),
        "cpus_usable": getattr(os, "process_cpu_count", os.cpu_count)(),
    }


def host() -> dict[str, Any]:
    mem = _kv(read_text("/proc/meminfo"))
    load = (read_text("/proc/loadavg") or "").split()
    uptime = (read_text("/proc/uptime") or "").split()
    return {
        "mem_total_kb": mem.get("MemTotal"), "mem_available_kb": mem.get("MemAvailable"),
        "swap_total_kb": mem.get("SwapTotal"), "swap_free_kb": mem.get("SwapFree"),
        "load": [float(x) for x in load[:3]] if len(load) >= 3 else None,
        "uptime_s": int(float(uptime[0])) if uptime else None, "cpus": os.cpu_count(),
    }


def process() -> dict[str, Any]:
    statm = (read_text("/proc/self/statm") or "").split()
    try:
        fds = len(os.listdir(ROOT / "proc/self/fd"))
    except OSError:
        fds = None
    page = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096
    return {"pid": os.getpid(), "rss_bytes": int(statm[1]) * page if len(statm) > 1 else None, "open_fds": fds}


def disk() -> dict[str, Any]:
    try:
        st = os.statvfs(data_dir())
        return {"free_bytes": st.f_bavail * st.f_frsize, "total_bytes": st.f_blocks * st.f_frsize}
    except (OSError, AttributeError):
        return {"free_bytes": None, "total_bytes": None}


MYSQL_STATUS = ("Threads_connected", "Threads_running", "Slow_queries", "Uptime", "Questions",
                "Innodb_buffer_pool_pages_total", "Innodb_buffer_pool_pages_free", "Innodb_buffer_pool_reads",
                "Innodb_buffer_pool_read_requests", "Aborted_connects")


def mysql() -> dict[str, Any]:
    try:
        with connection.cursor() as c:
            c.execute("SHOW GLOBAL STATUS")
            status = {k: v for k, v in c.fetchall() if k in MYSQL_STATUS}
            c.execute("SHOW GLOBAL VARIABLES WHERE Variable_name IN ('version', 'max_connections', "
                      "'innodb_buffer_pool_size')")
            variables = {k: v for k, v in c.fetchall()}
        return {"reachable": True, "status": status, "variables": variables}
    except DatabaseError as err:
        return {"reachable": False, "error": type(err).__name__}


def warnings(c: dict[str, Any], d: dict[str, Any], db: dict[str, Any]) -> list[str]:
    from apps.ops.health import problems

    out = list(problems())
    if d["free_bytes"] is not None and d["total_bytes"] and d["free_bytes"] < d["total_bytes"] * 0.10:
        out.append("disk_low")
    if c["memory_max"] and c["memory_current"] and c["memory_current"] > c["memory_max"] * 0.90:
        out.append("memory_high")
    if store.recent_error_count() > 20:
        out.append("errors_burst")
    if not db["reachable"]:
        out.append("db_unreachable")
    if store.logs_paused():
        out.append("logs_paused_low_disk")
    return out


def stats() -> dict[str, Any]:
    c, d, db = container(), disk(), mysql()
    return {"time": store.now_iso(), "container": c, "host": host(), "process": process(), "disk": d, "mysql": db,
            "errors_last_5_min": store.recent_error_count(), "warnings": warnings(c, d, db)}


def _os_release() -> str | None:
    for line in (read_text("/etc/os-release") or "").splitlines():
        if line.startswith("PRETTY_NAME="):
            return line.split("=", 1)[1].strip().strip('"')
    return None


def _dir_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                continue
    return total


def specs() -> dict[str, Any]:
    import django

    db = mysql()
    uname = platform.uname()
    started = time.monotonic()
    size = _dir_size(data_dir())
    return {
        **version(), "python": sys.version.split()[0], "django": django.get_version(),
        "mysql": db.get("variables", {}).get("version"), "kernel": f"{uname.system} {uname.release}",
        "machine": uname.machine, "os_image": _os_release(), "time_zone": os.environ.get("TZ") or time.tzname[0],
        "container": container(), "host_cpus": os.cpu_count(),
        "data_dir_bytes": size, "data_dir_scan_ms": round((time.monotonic() - started) * 1000),
    }
