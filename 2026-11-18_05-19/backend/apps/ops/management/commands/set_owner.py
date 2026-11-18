"""Moves the owner role to another active user (legacy scripts/set-owner.js). The old owner keeps the admin preset."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.core.perms import PRESETS, parse_perms


class Command(BaseCommand):
    help = "Make <username> the protected owner."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("username")

    def handle(self, *args: Any, **o: Any) -> None:
        user = User.objects.filter(username=o["username"], active=True, deleted_at__isnull=True).first()
        if user is None:
            raise CommandError(f'no active user "{o["username"]}"')
        admin = parse_perms(PRESETS["admin"]["perms"])
        with transaction.atomic():
            for old in User.objects.select_for_update().filter(is_owner=True):
                old.is_owner = False
                old.perms = admin
                old.save()
            user.is_owner = True
            user.perms = admin
            user.save()
        self.stdout.write(f'"{user.username}" (id {user.pk}) is now the owner.')
