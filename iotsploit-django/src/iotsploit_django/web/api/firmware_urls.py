from django.urls import path

from iotsploit_django.view_handlers.firmware_views import (
    firmware_info,
    firmware_list,
)


urlpatterns = [
    # Firmware registry endpoints (order matters: specific before generic)
    path("firmware/list/", firmware_list, name="firmware_list"),
    # Keep generic info endpoint last to avoid shadowing more specific routes
    path("firmware/<str:name>/", firmware_info, name="firmware_info"),
]
