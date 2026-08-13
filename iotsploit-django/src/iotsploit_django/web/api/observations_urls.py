from django.urls import path

from iotsploit_django.view_handlers.observation_views import get_current_observations


urlpatterns = [
    path(
        "get_current_observations/",
        get_current_observations,
        name="get_current_observations",
    ),
]
