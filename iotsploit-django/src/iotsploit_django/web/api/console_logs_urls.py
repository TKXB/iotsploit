from django.urls import path

from sat_toolkit.view_handlers.console_logs_views import (
    clear_console_logs,
    control_console_reader,
    get_console_logs,
)


urlpatterns = [
    path("console_logs/", get_console_logs, name="get_console_logs"),
    path("console_logs/clear/", clear_console_logs, name="clear_console_logs"),
    path("console_logs/control/", control_console_reader, name="control_console_reader"),
]


