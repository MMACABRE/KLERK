"""The worker (SPEC §7): one process, one loop, never overlapping jobs.

At start: umask 077, recover stuck SMS rows, sweep data/tmp, a backup if today has none. Then every 60 s the SMS
tick, at 03:00 (TZ) the nightly backup, every 6 h the tmp sweep. A second worker is refused by GET_LOCK('worker').
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
from django.db import close_old_connections, connection
from django.utils import timezone

log = logging.getLogger("klerk.worker")

TICK_S = 60
SWEEP_EVERY_S = 6 * 3600
BACKUP_HOUR = 3


def _next_backup(now: datetime) -> datetime:
    local = timezone.localtime(now)
    at = local.replace(hour=BACKUP_HOUR, minute=0, second=0, microsecond=0)
    return at if at > local else at + timedelta(days=1)


class Command(BaseCommand):
    help = "Runs the background worker: SMS every minute, nightly backup, tmp sweep."

    def handle(self, *args: Any, **options: Any) -> None:
        from apps.core.files import secure_data_dir, sweep_tmp
        from apps.ops.backup import backup_now, has_backup_for
        from apps.sms import engine

        stop = {"now": False}

        def on_term(signum: int, frame: Any) -> None:
            stop["now"] = True

        signal.signal(signal.SIGTERM, on_term)
        signal.signal(signal.SIGINT, on_term)
        secure_data_dir()
        with connection.cursor() as c:
            c.execute("SELECT GET_LOCK(%s, 0)", [f"{connection.settings_dict['NAME']}:worker"])
            row = c.fetchone()
        if not row or row[0] != 1:
            log.error("another worker holds the lock; exiting")
            return
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
            try:
                result = engine.tick()
                if result.get("sent"):
                    s = result["sent"]
                    log.info("sms tick sent=%s failed=%s skipped=%s", s["sent"], s["failed"], s["skipped"])
            except Exception as err:  # noqa: BLE001
                log.error("sms tick failed: %s", type(err).__name__)
            if timezone.now() >= next_backup:
                self._backup(backup_now)
                next_backup = _next_backup(timezone.now())
            if time.monotonic() >= next_sweep:
                sweep_tmp()
                next_sweep = time.monotonic() + SWEEP_EVERY_S
            try:
                heartbeat.write_text(timezone.now().isoformat(), encoding="utf-8")
            except OSError:
                pass
            while not stop["now"] and time.monotonic() - started < TICK_S:
                time.sleep(1)
        log.info("worker stopped")

    def _backup(self, backup_now: Any) -> None:
        try:
            log.info("backup written: %s", backup_now().name)
        except Exception as err:  # noqa: BLE001
            # The message is the mysqldump error line or an OS error (disk full, permission); a dump never
            # echoes rows on failure, unlike the mysql client during a restore.
            log.error("backup failed: %s: %s", type(err).__name__, str(err)[:200])
