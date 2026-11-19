from django.urls import path

from iotsploit_django.view_handlers.observation_views import (
    delete_observation_facts,
    get_current_observations,
    record_observations,
)


urlpatterns = [
    path(
        "get_current_observations/",
        get_current_observations,
        name="get_current_observations",
    ),
    path(
        "delete_observation_facts/",
        delete_observation_facts,
        name="delete_observation_facts",
    ),
    path(
        "record_observations/",
        record_observations,
        name="record_observations",
    ),
]
