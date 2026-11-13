# Backend image (ADR-0011: pinned base, hash-locked requirements). Three targets:
#   dev   - compiler and CI tools (requirements-dev.txt); docker-compose.dev.yml bind-mounts the code over /app.
#   prod  - runtime only (requirements.txt): no compiler, no pytest/mypy/ruff/pip-tools. docker-compose.yml.
#   build - internal: compiles mysqlclient for prod.
# Both runtime targets carry Oracle's mysqldump 8.4, taken from the same pinned MySQL image the database runs. The
# Debian client is MariaDB's: its dumps of MySQL 8.4 carry values for generated columns (sms_messages.reminder_key)
# and cannot be restored. A restore uses the `mysql` client inside the MySQL container.
FROM mysql:8.4.13 AS mysql-client

FROM python:3.13.18-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

FROM base AS build
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential pkg-config default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
# Every package must match its hash; nothing is resolved at build time.
RUN pip install --require-hashes --no-deps --prefix=/install -r requirements.txt

FROM base AS dev
# mysqlclient builds from source: it needs a compiler and the MySQL client headers.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential pkg-config default-libmysqlclient-dev libssl3 libstdc++6 zlib1g \
    && rm -rf /var/lib/apt/lists/*
COPY --from=mysql-client /usr/bin/mysqldump /usr/local/bin/mysqldump
COPY requirements.txt requirements-dev.txt ./
RUN pip install --require-hashes --no-deps -r requirements-dev.txt
RUN useradd --create-home --uid 10001 app && mkdir -p /data && chown app:app /data
COPY . .
USER app
EXPOSE 8000
CMD ["gunicorn", "klerk.wsgi:application", "--bind", "0.0.0.0:8000"]

FROM base AS prod
# libmariadb3: the shared library mysqlclient links to. The other three: what mysqldump links to.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libmariadb3 libssl3 libstdc++6 zlib1g \
    && rm -rf /var/lib/apt/lists/*
COPY --from=mysql-client /usr/bin/mysqldump /usr/local/bin/mysqldump
COPY --from=build /install /usr/local
RUN useradd --create-home --uid 10001 app && mkdir -p /data && chown app:app /data
COPY manage.py ./
COPY klerk ./klerk
COPY apps ./apps
# The one-time SQLite -> MySQL copier for the cutover (docs/DEPLOY-AGENT-CUTOVER.md).
COPY tools/migrate_sqlite.py ./tools/migrate_sqlite.py
ENV DJANGO_SETTINGS_MODULE=klerk.settings.prod \
    DATA_DIR=/data
USER app
EXPOSE 8000
# Schema changes run before the server starts; migrate is a no-op when nothing is new.
CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn klerk.wsgi:application --bind 0.0.0.0:8000 --worker-class gthread --workers 2 --threads 4 --timeout 120 --access-logfile -"]
