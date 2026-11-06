"""Settings shared by every environment.

Secrets and database access come from environment variables only.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Empty means "not configured": dev and prod refuse to start without DJANGO_SECRET_KEY.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
DEBUG = False
ALLOWED_HOSTS = [
    host
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host
]

INSTALLED_APPS = [
    "django.contrib.sessions",
    "apps.ops",
    "apps.core",
    "apps.accounts",
    "apps.finance",
    "apps.patients",
    "apps.documents",
    "apps.visits",
    "apps.billing",
    "apps.storage",
    "apps.sms",
    "apps.search",
    "apps.dashboard",
    "apps.data_io",
    "apps.printing",
]

# The custom user model is set before the first migration (SPEC §4.1). Nothing else uses
# django.contrib.auth.
AUTH_USER_MODEL = "accounts.User"
# One cost for every account (SPEC §3.6): the preferred hasher is the scrypt tuned to the legacy
# cost;
# the Node hashes are verified and re-hashed at sign-in. No PBKDF2.
PASSWORD_HASHERS = [
    "apps.accounts.hashers.KlerkScryptHasher",
    "apps.accounts.hashers.NodeScryptPasswordHasher",
]
AUTHENTICATION_BACKENDS = ["apps.accounts.backends.KlerkBackend"]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Order matters: AllowedHostMiddleware runs before any view, so an unknown Host gets 400 here.
    # Add CommonMiddleware below this line: its redirects must not run for unknown hosts.
    "klerk.middleware.AllowedHostMiddleware",
    "apps.core.middleware.HeadersMiddleware",
    "apps.core.middleware.ErrorMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "apps.core.middleware.SameOriginMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "apps.accounts.session.SessionUserMiddleware",
    "apps.core.gate.GateMiddleware",
]

ROOT_URLCONF = "klerk.urls"

WSGI_APPLICATION = "klerk.wsgi.application"

# NO PAD binary: 'a' and 'a ' differ, and 'A' differs from 'a', as in the legacy database (ADR-0012).
DB_COLLATION = "utf8mb4_0900_bin"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.environ.get("MYSQL_DATABASE", "klerk"),
        "USER": os.environ.get("MYSQL_USER", "klerk"),
        "PASSWORD": os.environ.get("MYSQL_PASSWORD", ""),
        "HOST": os.environ.get("MYSQL_HOST", "mysql"),
        "PORT": os.environ.get("MYSQL_PORT", "3306"),
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": f"SET NAMES utf8mb4 COLLATE {DB_COLLATION}",
        },
        # KLERK_TEST_DB lets parallel test runs use separate databases (dev grant: test_klerk%).
        "TEST": {"CHARSET": "utf8mb4", "COLLATION": DB_COLLATION, "NAME": os.environ.get("KLERK_TEST_DB") or None},
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = "fa"
TIME_ZONE = "Asia/Tehran"
USE_I18N = True
USE_TZ = True

# Data folder: patients/, backups/, trash/, tmp/, sms.key (SPEC §3.8). Never served by Caddy.
DATA_DIR = Path(os.environ.get("DATA_DIR", str(BASE_DIR / "data"))).resolve()
try:  # uploads stream to data/tmp; Django's system check needs the folder to exist
    (DATA_DIR / "tmp").mkdir(parents=True, exist_ok=True)
except OSError:
    pass

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": [], "autoescape": True},
    }
]

# Sessions (SPEC §3.4): cookie `sid`, DB backend, absolute 8 h, idle 30 min (apps.accounts.session).
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_NAME = "sid"
SESSION_COOKIE_AGE = 8 * 3600
SESSION_SAVE_EVERY_REQUEST = False
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Strict"
SESSION_COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "1") == "1"
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
CSRF_COOKIE_SAMESITE = "Strict"
CSRF_COOKIE_HTTPONLY = False
CSRF_HEADER_NAME = "HTTP_X_CSRFTOKEN"
CSRF_FAILURE_VIEW = "apps.core.http.csrf_failure"
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o]

X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

DATA_UPLOAD_MAX_MEMORY_SIZE = 200 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 200
FILE_UPLOAD_MAX_MEMORY_SIZE = 2_621_440
FILE_UPLOAD_TEMP_DIR = str(DATA_DIR / "tmp")
FILE_UPLOAD_PERMISSIONS = 0o600

# Client IP: X-Forwarded-For is read only when the TCP peer is in these networks (Caddy, SPEC §3.5).
TRUSTED_PROXY_NETS = [
    n for n in os.environ.get(
        "TRUSTED_PROXY_NETS",
        "127.0.0.0/8,::1/128,169.254.0.0/16,fe80::/10,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,fc00::/7",
    ).split(",") if n
]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False}},
}
