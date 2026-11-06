from django.db import DatabaseError, connection
from django.http import HttpRequest, HttpResponse
from django.views.decorators.http import require_GET


@require_GET
def health(request: HttpRequest) -> HttpResponse:
    """`ok` (200) only when the default database answers SELECT 1; otherwise 503."""
    row: tuple[object, ...] | None
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            row = cursor.fetchone()
    except DatabaseError:
        row = None
    if row != (1,):
        return HttpResponse("unavailable", status=503, content_type="text/plain")
    return HttpResponse("ok", content_type="text/plain")
