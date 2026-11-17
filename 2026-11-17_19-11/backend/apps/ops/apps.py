from typing import Any

from django.apps import AppConfig
from django.db.backends.signals import connection_created


def _set_connection_collation(sender: Any, connection: Any, **kwargs: Any) -> None:
    """Every MySQL session uses the exact-text collation (ADR-0012).

    mysqlclient applies `charset` after `init_command`, which resets the connection collation to the
    charset
    default (utf8mb4_0900_ai_ci). So the collation is set here, once per new connection.
    """
    if connection.vendor != "mysql":
        return
    from klerk.settings.base import DB_COLLATION

    with connection.cursor() as cursor:
        cursor.execute(f"SET NAMES utf8mb4 COLLATE {DB_COLLATION}")


class OpsConfig(AppConfig):
    name = "apps.ops"
    default_auto_field = "django.db.models.BigAutoField"
    label = "ops"

    def ready(self) -> None:
        connection_created.connect(_set_connection_collation, dispatch_uid="klerk-collation")
        from apps.core.files import secure_data_dir
        from apps.ops import checks  # noqa: F401  (registers the MySQL server system check)

        secure_data_dir()  # umask 077 and mode 700 on the data folder, for backend and worker (SPEC §3.8)
