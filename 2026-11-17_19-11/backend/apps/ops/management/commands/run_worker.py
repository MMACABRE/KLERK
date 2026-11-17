"""The worker (SPEC §7): one process, one loop, never overlapping jobs.

At start: umask 077, recover stuck SMS rows, sweep data/tmp, a backup if today has none. Then every 60 s the SMS
tick, at 03:00 (TZ) the nightly backup, every 6 h the tmp sweep. Between ticks it runs patient CSV imports in short
batches (apps.data_io.jobs) instead of sleeping. A second worker is refused by GET_LOCK('worker'), held on a
connection of its own (WorkerLock) because close_old_connections() closes the default one every tick.
SIGTERM finishes the current step and exits 0. A heartbeat file data/worker.heartbeat holds the last tick time.
"""

from __future__ import annotations

import logging
import signal
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import DatabaseError, close_old_connections, connection, connections
from django.utils import timezone

log = logging.getLogger("klerk.worker")

TICK_S = 60
SWEEP_EVERY_S = 6 * 3600
BACKUP_HOUR = 3


class WorkerLock:
    """GET_LOCK held on a dedicated connection that close_old_connections() never touches."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.conn: Any = None

    def acquire(self) -> bool:
        self.close()
        conn = connections.create_connection("default")
        try:
            with conn.cursor() as c:
                c.execute("SELECT GET_LOCK(%s, 0)", [self.name])
                row = c.fetchone()
        except DatabaseError:
            conn.close()
            raise
        if not row or row[0] != 1:
            conn.close()
            return False
        self.conn = conn
        return True

    def held(self) -> bool:
        if self.conn is None:
            return False
        try:
            with self.conn.cursor() as c:
                c.execute("SELECT IS_USED_LOCK(%s) = CONNECTION_ID()", [self.name])
                row = c.fetchone()
        except DatabaseError:
            return False
        return bool(row and row[0] == 1)

    def keep(self) -> bool:
        """True while this process holds the lock, taking it again after a lost connection."""
        if self.held():
            return True
        try:
            return self.acquire()
        except DatabaseError:
            return False

    def close(self) -> None:
        if self.conn is not None:
            try:
                self.conn.close()
            except DatabaseError:
                pass
            self.conn = None


def _report(err: BaseException) -> None:
    from apps.diagnostics.capture import report

    report(err, "worker")


def _sweep_diagnostics() -> None:
    from apps.diagnostics.store import sweep

    sweep()


def _next_backup(now: datetime) -> datetime:
    local = timezone.localtime(now)
    at = local.replace(hour=BACKUP_HOUR, minute=0, second=0, microsecond=0)
    return at if at > local else at + timedelta(days=1)


class Command(BaseCommand):
    help = "Runs the background worker: SMS every minute, nightly backup, tmp sweep."

    def handle(self, *args: Any, **options: Any) -> None:
        from apps.core.files import secure_data_dir, sweep_tmp
        from apps.data_io.jobs import run_batch as import_batch
        from apps.data_io.jobs import sweep_jobs
        from apps.diagnostics import capture, store
        from apps.ops.backup import backup_now, has_backup_for
        from apps.sms import engine

        store.set_process("worker")
        capture.install_hooks("worker")
        stop = {"now": False}

        def on_term(signum: int, frame: Any) -> None:
            stop["now"] = True

        signal.signal(signal.SIGTERM, on_term)
        signal.signal(signal.SIGINT, on_term)
        secure_data_dir()
        lock = WorkerLock(f"{connection.settings_dict['NAME']}:worker")
        if not lock.acquire():
            log.error("another worker holds the lock; exiting")
            return
        try:
            self._run(lock, stop, engine, backup_now, has_backup_for, import_batch, sweep_tmp, sweep_jobs)
        finally:
            lock.close()

    def _run(self, lock: WorkerLock, stop: dict[str, bool], engine: Any, backup_now: Any, has_backup_for: Any,
             import_batch: Any, sweep_tmp: Any, sweep_jobs: Any) -> None:
        heartbeat = Path(settings.DATA_DIR) / "worker.heartbeat"
        log.info("worker started")
        engine.recover_stuck()
        sweep_tmp()
        # A data folder the worker cannot read (wrong owner) must not stop the SMS loop: log it.
        try:
            missing = not has_backup_for()
        except OSError as err:
            log.error("backup check failed: %s", type(err).__name__)
            missing = False
        if missing:
            self._backup(backup_now)
        next_backup = _next_backup(timezone.now())
        next_sweep = time.monotonic() + SWEEP_EVERY_S
        while not stop["now"]:
            started = time.monotonic()
            close_old_connections()
            if not lock.keep():
                log.error("lost the worker lock and another worker holds it; exiting")
                raise SystemExit(1)
            try:
                result = engine.tick()
                if result.get("sent"):
                    s = result["sent"]
                    log.info("sms tick sent=%s failed=%s skipped=%s", s["sent"], s["failed"], s["skipped"])
            except Exception as err:  # noqa: BLE001
                log.error("sms tick failed: %s", type(err).__name__)
                _report(err)
            if timezone.now() >= next_backup:
                self._backup(backup_now)
                next_backup = _next_backup(timezone.now())
            if time.monotonic() >= next_sweep:
                sweep_tmp()
                sweep_jobs()
                _sweep_diagnostics()
                next_sweep = time.monotonic() + SWEEP_EVERY_S
            try:
                heartbeat.write_text(timezone.now().isoformat(), encoding="utf-8")
            except OSError:
                pass
            while not stop["now"] and time.monotonic() - started < TICK_S:
                if not self._import_batch(import_batch):
                    time.sleep(1)
        log.info("worker stopped")

    def _import_batch(self, import_batch: Any) -> bool:
        """One short batch of a patient CSV import (apps.data_io.jobs); False when no import waits."""
        try:
            return bool(import_batch())
        except Exception as err:  # noqa: BLE001 - the SMS loop must keep running
            log.error("import batch failed: %s", type(err).__name__)
            _report(err)
            close_old_connections()
            return False

    def _backup(self, backup_now: Any) -> None:
        try:
            log.info("backup written: %s", backup_now().name)
        except Exception as err:  # noqa: BLE001
            # The message is the mysqldump error line or an OS error (disk full, permission); a dump never
            # echoes rows on failure, unlike the mysql client during a restore.
            log.error("backup failed: %s: %s", type(err).__name__, str(err)[:200])
            _report(err)
