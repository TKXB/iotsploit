"""API URL aggregation (stage-2).

This module intentionally contains *only* URL composition.
"""

from django.urls import include, path

urlpatterns = [
    path("", include("iotsploit_django.web.api.misc_urls")),
    path("", include("iotsploit_django.web.api.ai_urls")),
    path("", include("iotsploit_django.web.api.console_logs_urls")),
    path("", include("iotsploit_django.web.api.devices_urls")),
    path("", include("iotsploit_django.web.api.vehicle_urls")),
    path("", include("iotsploit_django.web.api.targets_urls")),
    path("", include("iotsploit_django.web.api.observations_urls")),
    path("", include("iotsploit_django.web.api.plugins_urls")),
    path("", include("iotsploit_django.web.api.interaction_urls")),
    path("", include("iotsploit_django.web.api.firmware_urls")),
    path("", include("iotsploit_django.web.api.files_urls")),
    path("", include("iotsploit_django.web.api.tools_urls")),
    path("", include("iotsploit_django.web.api.recovery_urls")),
    # IoT fuzzer sub-domain
    path("", include("iotsploit_django.iot_fuzzer.urls")),
]


