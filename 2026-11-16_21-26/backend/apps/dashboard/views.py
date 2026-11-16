"""Dashboard API (SPEC §5.2; legacy src/routes/dashboard.js)."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse

from apps.core.http import ok, route, user_of
from apps.dashboard.widgets import dashboard
from apps.patients.views import layout_reset_for, layout_save_for, layout_undo_for


def show(request: HttpRequest) -> HttpResponse:
    return ok(dashboard(user_of(request), request.GET.get("edit") == "1"))


dashboard_view = route(GET=show)
layout_view = route(PUT=layout_save_for("dashboard"), POST=layout_save_for("dashboard"))
undo_view = route(POST=layout_undo_for("dashboard"))
reset_view = route(POST=layout_reset_for("dashboard"))
