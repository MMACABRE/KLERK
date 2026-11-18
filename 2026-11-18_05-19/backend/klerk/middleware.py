from collections.abc import Callable

from django.http import HttpRequest, HttpResponse


class AllowedHostMiddleware:
    """Checks every request's Host header against ALLOWED_HOSTS.

    `get_host()` raises DisallowedHost for an unknown host,
    and Django turns that into a 400 response.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.get_host()
        return self.get_response(request)
