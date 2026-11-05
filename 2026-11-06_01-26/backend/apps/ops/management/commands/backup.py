"""Writes a backup now (the same dump the worker makes at 03:00). deploy.sh calls it."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Writes a MySQL backup to DATA_DIR/backups now and prints its file name."

    def handle(self, *args: Any, **options: Any) -> None:
        from apps.ops.backup import backup_now

        try:
            path = backup_now()
        except RuntimeError as err:
            raise CommandError(f"backup failed: {err}") from err
        self.stdout.write(f"backup written: {path.name}")
