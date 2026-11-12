"""MySQL locks for the races (SPEC §4.3), and the one lock order every service follows.

Lock order (round 15): `visit_slots` (named) -> patient row -> visit rows (ascending id) ->
payments -> catalog item row -> lots (ascending id) -> custom box rows (ascending id) -> layout
rows. The named lock `patient_code` (patient creation and code change) is taken before any of
these, on its own. A service takes only the steps it needs, but never takes an earlier step after
a later one; tests/test_lock_order.py checks this on the real SQL. Named locks never run inside
an outer transaction: GET_LOCK is taken first, then the transaction starts, so the row locks are
released by the commit and the name lock by RELEASE_LOCK after it.

A named lock belongs to the database session, so each thread or worker holds its own. Names are
prefixed with the database name, so two databases on one server never share a lock."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from django.db import connection
from django.db.models import Model, QuerySet

from apps.core.errors import LockBusy, NotFound

logger = logging.getLogger(__name__)

__all__ = ["LockBusy", "get_for_update", "named_lock"]


def _full_name(name: str) -> str:
    return f"{connection.settings_dict['NAME']}:{name}"


def _acquire(full: str, timeout_seconds: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT GET_LOCK(%s, %s)", [full, timeout_seconds])
        row = cursor.fetchone()
    if row is None or row[0] != 1:
        raise LockBusy(full)


def _release(full: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT RELEASE_LOCK(%s)", [full])
        row = cursor.fetchone()
    if row is None or row[0] != 1:
        raise RuntimeError(f"lock {full} was not held by this session")


def _release_quietly(full: str) -> None:
    """Used while another exception is already leaving: a failure here must not hide it."""
    try:
        _release(full)
    except Exception:  # noqa: BLE001 - the original exception is what the caller needs
        logger.warning("named lock %s could not be released", full)


@contextmanager
def named_lock(name: str, timeout_seconds: int = 10) -> Iterator[None]:
    if connection.in_atomic_block:
        raise RuntimeError(f"named lock {name!r} must not be taken inside a transaction")
    full = _full_name(name)
    _acquire(full, timeout_seconds)
    try:
        yield
    except BaseException:
        _release_quietly(full)
        raise
    else:
        _release(full)


def get_for_update[M: Model](queryset: QuerySet[M], pk: object, what: str) -> M:
    """Lock and return one row. A missing row is NotFound, never Model.DoesNotExist."""
    row = queryset.select_for_update().filter(pk=pk).first()
    if row is None:
        raise NotFound(f"{what} {pk} not found")
    return row
