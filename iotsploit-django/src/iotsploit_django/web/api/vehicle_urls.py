from django.urls import path

from iotsploit_django.view_handlers.vehicle_views import ota_info


urlpatterns = [
    path("ota_info/", ota_info, name="ota_info"),
]


