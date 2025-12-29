"""Root URLConf for iotsploit-django.

Stage-2 goal: migrate the *route aggregation layer* into `iotsploit_django`, while
keeping paths and names stable.
"""

from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    path("admin/", admin.site.urls),
    # Keep public prefix stable: previously the legacy URLConf mounted APIs
    # under `api/`. We preserve the same public shape here.
    path("api/", include("iotsploit_django.web.api.urls")),
]


