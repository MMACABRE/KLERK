"""Creates a user from the command line (legacy scripts/create-user.js):
    python manage.py create_user <username> <owner|admin|staff> ["Display name"]
The password is asked twice (NEW_USER_PASSWORD env skips the prompt) and never appears in shell history."""

from __future__ import annotations

import getpass
import os
import re
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.lockout import password_problem
from apps.accounts.models import User
from apps.core.perms import PRESETS, parse_perms
from apps.core.text import nocase_key


class Command(BaseCommand):
    help = "Create a user: <username> <owner|admin|staff> [display name]"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("username")
        parser.add_argument("role", choices=["owner", "admin", "staff"])
        parser.add_argument("display_name", nargs="?", default="")

    def handle(self, *args: Any, **o: Any) -> None:
        username, role = o["username"], o["role"]
        if not re.fullmatch(r"[a-zA-Z0-9._-]{3,32}", username):
            raise CommandError("username: 3-32 latin letters, digits, . _ -")
        password = os.environ.get("NEW_USER_PASSWORD")
        if password is None:
            password = getpass.getpass("Password: ")
            if getpass.getpass("Repeat password: ") != password:
                raise CommandError("Passwords do not match.")
        problem = password_problem(password)
        if problem:
            raise CommandError(problem)
        preset = "staff" if role == "staff" else "admin"
        with transaction.atomic():
            if role == "owner" and User.objects.filter(is_owner=True).exists():
                raise CommandError("an owner already exists")
            if User.objects.filter(username_key=nocase_key(username)).exists():
                raise CommandError(f'User "{username}" already exists.')
            u = User(username=username, display_name=o["display_name"] or username, role=preset,
                     perms=parse_perms(PRESETS[preset]["perms"]), is_owner=role == "owner")
            u.set_password(password)
            u.save()
        self.stdout.write(f'Created {role} "{username}" (id {u.pk}).')
