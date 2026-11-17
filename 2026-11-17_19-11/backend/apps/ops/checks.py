"""Django system check for the MySQL server settings the code relies on (SPEC §4, ADR-0012).

It refuses a database whose connection collation, server collation, schema default collation,
character set,
isolation level or sql_mode differs from what the migrations and the exact-text rules assume. It
runs with
`python manage.py check --database default`; the deploy script runs that before it starts the app.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.checks import Error, Tags, register
from django.core.checks import Warning as CheckWarning
from django.db import DatabaseError, connections

from klerk.settings.base import DB_COLLATION

REQUIRED_SQL_MODES = (
    "STRICT_TRANS_TABLES",
    "NO_ZERO_IN_DATE",
    "NO_ZERO_DATE",
    "ERROR_FOR_DIVISION_BY_ZERO",
    "NO_ENGINE_SUBSTITUTION",
    "ONLY_FULL_GROUP_BY",
)


def server_problems(cursor: Any, database: str) -> list[str]:
    """What is wrong with the server, as short messages. An empty list means it matches."""
    cursor.execute(
        "SELECT @@collation_server, @@collation_connection, @@character_set_server, "
        "@@transaction_isolation, @@sql_mode"
    )
    server_collation, connection_collation, charset, isolation, sql_mode = cursor.fetchone()
    cursor.execute(
        "SELECT DEFAULT_COLLATION_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s",
        [database],
    )
    schema_row = cursor.fetchone()
    schema_collation = schema_row[0] if schema_row else None
    problems: list[str] = []
    if server_collation != DB_COLLATION:
        problems.append(f"collation_server is {server_collation}, expected {DB_COLLATION}")
    if connection_collation != DB_COLLATION:
        problems.append(f"collation_connection is {connection_collation}, expected {DB_COLLATION}")
    if schema_collation != DB_COLLATION:
        problems.append(f"schema default collation is {schema_collation}, expected {DB_COLLATION}")
    if charset != "utf8mb4":
        problems.append(f"character_set_server is {charset}, expected utf8mb4")
    if isolation != "READ-COMMITTED":
        problems.append(f"transaction_isolation is {isolation}, expected READ-COMMITTED")
    modes = set(str(sql_mode).split(","))
    missing = [mode for mode in REQUIRED_SQL_MODES if mode not in modes]
    if missing:
        problems.append(f"sql_mode lacks {', '.join(missing)}")
    return problems


@register(Tags.database)
def mysql_server_check(app_configs: Any, databases: Any = None, **kwargs: Any) -> list[Any]:
    errors: list[Any] = []
    for alias in databases or []:
        connection = connections[alias]
        if connection.vendor != "mysql":
            continue
        database = str(settings.DATABASES[alias]["NAME"])
        try:
            with connection.cursor() as cursor:
                problems = server_problems(cursor, database)
        except DatabaseError as exc:
            errors.append(
                CheckWarning(f"MySQL server not checked: {exc}", id="klerk.W001", obj=alias)
            )
            continue
        for problem in problems:
            errors.append(Error(problem, id="klerk.E001", obj=alias))
    return errors
