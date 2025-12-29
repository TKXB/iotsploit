from django.urls import path

from sat_toolkit.view_handlers.device_views import (
    cleanup_devices,
    device_info,
    get_all_devices,
    initialize_devices,
    list_devices,
    scan_all_devices,
    scan_specific_device,
)


urlpatterns = [
    path("device_info/", device_info, name="device_info"),
    path("get_all_devices/", get_all_devices, name="get_all_devices"),
    # DEPRECATED: Use scan_devices/ endpoint instead
    path("scan_all_devices/", scan_all_devices, name="scan_all_devices"),
    path("scan_device/<str:driver_name>/", scan_specific_device, name="scan_specific_device"),
    path("list_devices/", list_devices, name="list_devices"),
    path("initialize_devices/", initialize_devices, name="initialize_devices"),
    path("cleanup_devices/", cleanup_devices, name="cleanup_devices"),
]


