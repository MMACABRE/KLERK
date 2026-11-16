import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import SECRET_KEY

if not SECRET_KEY:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set for the prod settings")

DEBUG = False

# Caddy terminates TLS and forwards plain HTTP to gunicorn with X-Forwarded-Proto.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Strict"

# The SPA reads the CSRF cookie to send X-CSRFToken, so it cannot be HttpOnly.
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "Strict"

_DOMAIN = os.environ.get("DOMAIN", "")
if _DOMAIN:
    ALLOWED_HOSTS = [_DOMAIN]
    CSRF_TRUSTED_ORIGINS = [f"https://{_DOMAIN}"]
