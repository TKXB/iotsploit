from django.urls import path

from iotsploit_django.web import views


urlpatterns = [
    # New endpoint to list all URLs
    path("list_urls/", views.list_urls, name="list_urls"),
    # Logging configuration
    path("set_log_level/", views.set_log_level, name="set_log_level"),
    # Additional endpoints
    path("active_channels/", views.active_channels, name="active_channels"),
]


