from django.urls import path

from iotsploit_django.web import views


urlpatterns = [
    # Tool status and management endpoints
    path("tools_status/", views.get_tools_status, name="get_tools_status"),
    path("tools/refresh/", views.refresh_tools, name="refresh_tools"),
    path("tools/<str:tool_name>/", views.get_tool_details, name="get_tool_details"),
    path("system_health/", views.get_system_health, name="get_system_health"),
]


