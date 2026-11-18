"""Sets or prints the clinic name (legacy scripts/set-clinic-name.js). Only on the owner's request."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.core.settings_store import clinic_name, set_setting
from apps.core.text import normalize_text


class Command(BaseCommand):
    help = 'Set the clinic name: set_clinic_name "<name>" (no argument prints it).'

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("name", nargs="?")

    def handle(self, *args: Any, **o: Any) -> None:
        if o["name"] is None:
            self.stdout.write(clinic_name())
            return
        name = normalize_text(o["name"])[:120]
        if not name:
            raise CommandError("the name is empty")
        set_setting("clinic_name", name)
        self.stdout.write(f"clinic name set: {name}")
