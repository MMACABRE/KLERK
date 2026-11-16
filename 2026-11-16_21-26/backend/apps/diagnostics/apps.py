from django.apps import AppConfig


class DiagnosticsConfig(AppConfig):
    name = "apps.diagnostics"
    label = "diagnostics"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from django.core.signals import got_request_exception

        from apps.diagnostics import capture

        got_request_exception.connect(capture.on_request_exception, dispatch_uid="klerk-diagnostics")
        capture.install_log_handler()
