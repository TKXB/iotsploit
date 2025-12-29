from django.urls import path

from iotsploit_django.web import views
from sat_toolkit.view_handlers.firmware_views import (
    firmware_add,
    firmware_download,
    firmware_erase,
    firmware_flash,
    firmware_info,
    firmware_list,
    firmware_remove,
)


urlpatterns = [
    # Firmware management endpoints (order matters: specific before generic)
    path("firmware/list/", firmware_list, name="firmware_list"),
    path("firmware/add/", firmware_add, name="firmware_add"),
    path("firmware/remove/<str:name>/", firmware_remove, name="firmware_remove"),
    path("firmware/flash/", firmware_flash, name="firmware_flash"),
    path("firmware/download/", firmware_download, name="firmware_download_url"),
    path("firmware/erase/", firmware_erase, name="firmware_erase"),
    # Keep generic info endpoint last to avoid shadowing more specific routes
    path("firmware/<str:name>/", firmware_info, name="firmware_info"),
    # Firmware file download endpoints (legacy)
    path("download_firmware/", views.file_download, name="list_firmware_files"),
    path("download_firmware/<path:file_path>", views.file_download, name="download_firmware"),
]


