"""Password hashes: one scrypt cost for every account, and the legacy Node hashes verified and
re-hashed (SPEC §3.6).

- KlerkScryptHasher is the preferred hasher for every new hash and every unknown user's dummy
check. It is Django's scrypt with the legacy cost (N=2^15, r=8, p=1) and an explicit 64 MiB
memory limit, so an unknown user, a legacy user and a new user all cost the same. -
NodeScryptPasswordHasher verifies the legacy Node hashes only (stored as
`node_scrypt$N$r$p$salt$hash`, with the salt and hash in base64). A correct sign-in re-hashes
them with KlerkScryptHasher (must_update is always True).

Passwords are hashed as UTF-8 with every lone surrogate replaced by U+FFFD, as Node does (see
password_bytes)."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import re
from functools import lru_cache
from typing import Any

from django.contrib.auth import hashers as django_hashers
from django.contrib.auth.hashers import BasePasswordHasher

# django-stubs 5.2.9 does not declare ScryptPasswordHasher, though Django 5.2 has it.
ScryptPasswordHasher = django_hashers.ScryptPasswordHasher  # type: ignore[attr-defined]
ALGORITHM = "node_scrypt"
# The one stored value for an account with no usable password (Django's own unusable marker starts
# with "!").
UNUSABLE_MARKER = "!klerk-unusable"
LEGACY_LOWER = (
    "scrypt"  # the prefix the Node code wrote; the migration tool renames it to ALGORITHM
)
LEGACY_N = 2**15
LEGACY_R = 8
LEGACY_P = 1
LEGACY_KEY_BYTES = 32
# One memory limit for every hash. Python's default (32 MiB) refuses N=2^15, r=8, which needs
# 128*N*r bytes.
MAXMEM = 64 * 1024 * 1024
# Bounds on a stored value: a damaged row cannot ask for gigabytes (legacy parseStored,
# src/auth.js:36-43).
_MAX_KEY_BYTES = 64
_MIN_SALT_BYTES = 8
_MIN_HASH_BYTES = 16
# Plain ASCII digits with no sign, no separator and no leading zero (`+32768`, ` 32768`, `3_2768`,
# Persian
# digits and `032768` are all refused).
_PLAIN_INT = re.compile(r"[1-9][0-9]*")


def password_bytes(text: str) -> bytes:
    """UTF-8 of the password, with every lone surrogate (U+D800..U+DFFF) replaced by U+FFFD, as Node
    writes it."""
    cleaned = "".join("�" if 0xD800 <= ord(ch) <= 0xDFFF else ch for ch in text)
    return cleaned.encode("utf-8")


def rename_legacy(stored: str) -> str:
    """The stored form a legacy row has (`scrypt$...`) as this module reads it (`node_scrypt$...`).

    Raises ValueError when the renamed value is not a complete legacy hash with sane settings
    (parse_stored)."""
    if not stored.startswith(LEGACY_LOWER + "$"):
        raise ValueError("not a legacy scrypt hash")
    renamed = ALGORITHM + stored[len(LEGACY_LOWER) :]
    if parse_stored(renamed) is None:
        raise ValueError("the legacy hash has settings or fields this release refuses")
    return renamed


def _strict_b64(text: str) -> bytes | None:
    """Base64 that decodes and encodes back to the same text (legacy strictBase64)."""
    try:
        raw = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        return None
    return raw if base64.b64encode(raw).decode("ascii") == text else None


def _in_range(value: int, low: int, high: int) -> bool:
    return low <= value <= high


def parse_stored(encoded: str) -> tuple[bytes, bytes, int, int, int] | None:
    """Return (salt, expected, N, r, p), or None for anything that is not a complete legacy hash
    with sane settings."""
    parts = encoded.split("$")
    if len(parts) != 6 or parts[0] != ALGORITHM:
        return None
    _, n_text, r_text, p_text, salt_text, hash_text = parts
    if not (salt_text and hash_text):
        return None
    if not (
        _PLAIN_INT.fullmatch(n_text)
        and _PLAIN_INT.fullmatch(r_text)
        and _PLAIN_INT.fullmatch(p_text)
    ):
        return None
    n, r, p = int(n_text), int(r_text), int(p_text)
    # The ranges of src/auth.js:36-43: N a power of two, bounded; r and p bounded.
    if not (_in_range(n, 2**10, 2**17) and n & (n - 1) == 0):
        return None
    if not (_in_range(r, 1, 16) and _in_range(p, 1, 4)):
        return None
    salt = _strict_b64(salt_text)
    expected = _strict_b64(hash_text)
    if salt is None or expected is None:
        return None
    if len(salt) < _MIN_SALT_BYTES or not (_MIN_HASH_BYTES <= len(expected) <= _MAX_KEY_BYTES):
        return None
    return salt, expected, n, r, p


def _derive(password: str, salt: bytes, n: int, r: int, p: int, length: int) -> bytes:
    return hashlib.scrypt(
        password_bytes(password), salt=salt, n=n, r=r, p=p, dklen=length, maxmem=MAXMEM
    )


@lru_cache(maxsize=1)
def _dummy_salt() -> bytes:
    return b"klerk-dummy-salt"


def encode_legacy(password: str, salt: bytes) -> str:
    """A legacy-format hash, for tests and fixtures. New hashes come from KlerkScryptHasher."""
    key = _derive(password, salt, LEGACY_N, LEGACY_R, LEGACY_P, LEGACY_KEY_BYTES)
    return "$".join(
        [
            ALGORITHM,
            str(LEGACY_N),
            str(LEGACY_R),
            str(LEGACY_P),
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(key).decode("ascii"),
        ]
    )


def verify_legacy(password: str, encoded: str) -> bool:
    parsed = parse_stored(encoded)
    if parsed is None:
        # A refused value still pays for one full scrypt: it does not reveal that the account
        # exists.
        _derive(password, _dummy_salt(), LEGACY_N, LEGACY_R, LEGACY_P, LEGACY_KEY_BYTES)
        return False
    salt, expected, n, r, p = parsed
    try:
        actual = _derive(password, salt, n, r, p, len(expected))
    except ValueError:
        return False  # the memory limit refuses these settings: no match, never an error page
    return hmac.compare_digest(actual, expected)


class KlerkScryptHasher(ScryptPasswordHasher):  # type: ignore[valid-type,misc]
    """The preferred hasher: Django's scrypt at the legacy cost, with password_bytes and one memory
    limit."""

    algorithm = "scrypt"
    work_factor = LEGACY_N
    block_size = LEGACY_R
    parallelism = LEGACY_P
    maxmem = MAXMEM

    def must_update(self, encoded: str) -> bool:
        """A value this hasher cannot parse gets the same answer as a mismatch: it must be
        updated."""
        try:
            return bool(super().must_update(encoded))
        except (AssertionError, TypeError, ValueError):
            return True

    def verify(self, password: str, encoded: str) -> bool:
        """A stored value that cannot be parsed or computed is a mismatch, never an exception.

        That covers an unrenamed legacy `scrypt$` row, a damaged field, and settings the memory
        limit refuses."""
        try:
            return bool(super().verify(password, encoded))
        except (AssertionError, TypeError, ValueError, MemoryError):
            return False

    def encode(
        self,
        password: str,
        salt: str,
        n: int | None = None,
        r: int | None = None,
        p: int | None = None,
    ) -> str:
        self._check_encode_args(password, salt)
        n = n or self.work_factor
        r = r or self.block_size
        p = p or self.parallelism
        digest = hashlib.scrypt(
            password_bytes(password),
            salt=salt.encode(),
            n=n,
            r=r,
            p=p,
            maxmem=self.maxmem,
            dklen=64,
        )
        hashed = base64.b64encode(digest).decode("ascii").strip()
        return f"{self.algorithm}${n}${salt}${r}${p}${hashed}"


class NodeScryptPasswordHasher(BasePasswordHasher):
    """Verifies the legacy Node hashes. Never preferred: every correct sign-in re-hashes the
    password."""

    algorithm = ALGORITHM

    def encode(self, password: str, salt: str, iterations: int | None = None) -> str:
        return encode_legacy(password, salt.encode("utf-8"))

    def verify(self, password: str, encoded: str) -> bool:
        return verify_legacy(password, encoded)

    def safe_summary(self, encoded: str) -> dict[Any, Any]:
        parts = encoded.split("$")
        return {"algorithm": self.algorithm, "N": parts[1] if len(parts) > 1 else "?"}

    def must_update(self, encoded: str) -> bool:
        return True

    def harden_runtime(self, password: str, encoded: str) -> None:
        return None
