"""The only errors a service raises (SPEC §4.3, round 15 item 5).

A service turns every ORM or database failure into one of these, so a view can map them to
HTTP answers without knowing the ORM. A service may also raise TypeError for a wrong argument type.

- NotFound: the row a change needs is gone (deleted by someone else, or never existed).
- Conflict: the change clashes with the current state (overlap, stock short, payments,
  a code already taken).
- Invalid: the request breaks a rule that does not depend on the state (amount must be
  positive, a bad value).
- LockBusy: a named lock could not be taken in time.
"""

from __future__ import annotations


class ServiceError(Exception):
    """Base class of every domain error a service raises. ErrorMiddleware answers with `status` (else one from the
    subclass), `message_fa` (else a generic text) and `code` (else the class name)."""

    message_fa: str | None = None
    code: str | None = None


class LockBusy(ServiceError):
    """A named lock could not be taken within the timeout."""


class NotFound(ServiceError):
    """The row a change needs does not exist any more."""


class Conflict(ServiceError):
    """The change clashes with the current state."""


class Invalid(ServiceError):
    """The request breaks a rule that does not depend on the state."""
