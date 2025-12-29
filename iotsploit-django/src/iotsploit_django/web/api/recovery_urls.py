from django.urls import path

from iotsploit_django.web import views


urlpatterns = [
    # Recovery operation endpoints
    path("recovery/drivers/", views.list_recovery_drivers, name="list_recovery_drivers"),
    path("recovery/<str:driver_name>/", views.execute_recovery, name="execute_recovery"),
]


