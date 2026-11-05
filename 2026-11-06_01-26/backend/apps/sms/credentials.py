"""The clinic's SMS provider key, sealed with AES-256-GCM (src/lib/sms-credentials.js:25-37).

Format: `v1:` + base64(IV 12 bytes | tag 16 bytes | ciphertext). The legacy code writes the same
bytes. The `cryptography` library returns ciphertext then tag, so this module reorders them.

The key is `data/sms.key`: base64 of 32 random bytes. A missing or bad key file is "no key"
(None), never a crash. A tampered or short secret is refused (None)."""

from __future__ import annotations

import base64
import binascii
import os
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PREFIX = "v1:"
IV_BYTES = 12
TAG_BYTES = 16
KEY_BYTES = 32


def read_key(path: Path) -> bytes | None:
    """The key from the key file, or None when it is missing, unreadable or not 32 bytes after
    base64."""
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    try:
        key = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        return None
    return key if len(key) == KEY_BYTES else None


def ensure_key(path: Path) -> bytes | None:
    """The key, created on first use as legacy does (src/lib/sms-credentials.js:13-16):
    O_CREAT|O_EXCL, mode 0600, 32 random bytes base64. Two starts that race never overwrite each
    other: the loser reads the winner's key (or, while the winner is still writing, gets None and
    tries again later)."""
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return read_key(path)
    with os.fdopen(fd, "w", encoding="ascii") as handle:
        handle.write(base64.b64encode(os.urandom(KEY_BYTES)).decode("ascii"))
    return read_key(path)


def seal(plain: str, key: bytes) -> str:
    iv = os.urandom(IV_BYTES)
    out = AESGCM(key).encrypt(iv, plain.encode("utf-8"), None)
    ciphertext, tag = out[:-TAG_BYTES], out[-TAG_BYTES:]
    return PREFIX + base64.b64encode(iv + tag + ciphertext).decode("ascii")


def open_secret(secret: str, key: bytes) -> str | None:
    """The plain key, or None for a value that is not a sealed secret for this key."""
    if not secret.startswith(PREFIX):
        return None
    try:
        raw = base64.b64decode(secret[len(PREFIX) :], validate=True)
    except (binascii.Error, ValueError):
        return None
    if len(raw) < IV_BYTES + TAG_BYTES + 1:
        return None
    iv, tag, ciphertext = (
        raw[:IV_BYTES],
        raw[IV_BYTES : IV_BYTES + TAG_BYTES],
        raw[IV_BYTES + TAG_BYTES :],
    )
    try:
        plain = AESGCM(key).decrypt(iv, ciphertext + tag, None)
        return plain.decode("utf-8")
    except (InvalidTag, UnicodeDecodeError, ValueError):
        return None
