"""Sign-in with the username (ASCII-folded key, ADR-0012) and a password checked by Django's
hashers.

Used through django.contrib.auth.authenticate. An unknown or inactive user costs one full hash
check too."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from django.contrib.auth.hashers import check_password, is_password_usable, make_password

from apps.accounts.models import User
from apps.core.text import nocase_key


@lru_cache(maxsize=1)
def _unknown_hash() -> str:
    """A preferred-hasher hash for unknown users: a miss costs as much as a wrong password."""
    return make_password("klerk-unknown-user")


class KlerkBackend:
    def authenticate(
        self,
        request: Any = None,
        username: str | None = None,
        password: str | None = None,
        **_: Any,
    ) -> User | None:
        if username is None or password is None:
            return None
        user = User.objects.filter(username_key=nocase_key(username)).first()
        if user is None:
            check_password(password, _unknown_hash())
            return None
        # An inactive or hidden account, or one with no usable password, pays the same check
        # as an unknown user.
        if not user.active or user.deleted_at is not None or not is_password_usable(user.password):
            check_password(password, _unknown_hash())
            return None
        return user if user.check_password(password) else None

    def get_user(self, user_id: int) -> User | None:
        return User.objects.filter(pk=user_id, active=True, deleted_at__isnull=True).first()
