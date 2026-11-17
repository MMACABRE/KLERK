"""Writes a backup now (the same dump the worker makes at 03:00). deploy.sh calls it."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Writes a MySQL backup to DATA_DIR/backups now and prints its file name."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--before-restore", action="store_true",
                            help="the safety copy before a restore: its own file name, never today's nightly dump")

    def handle(self, *args: Any, **options: Any) -> None:
        from apps.ops.backup import backup_before_restore, backup_now

        try:
            path = backup_before_restore() if options["before_restore"] else backup_now()
        except RuntimeError as err:
            raise CommandError(f"backup failed: {err}") from err
        self.stdout.write(f"backup written: {path.name}")
