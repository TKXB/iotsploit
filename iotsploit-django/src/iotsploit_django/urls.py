"""Root URLConf for iotsploit-django.

Stage-2 goal: migrate the *route aggregation layer* into `iotsploit_django`, while
keeping paths and names stable. Views still live in `sat_toolkit` for now.
"""

from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    path("admin/", admin.site.urls),
    # Keep public prefix stable: previously `sat_django_entry.urls` mounted `sat_toolkit`
    # under `api/`. We preserve the same public shape here.
    path("api/", include("iotsploit_django.web.api.urls")),
]


