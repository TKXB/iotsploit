from __future__ import annotations

import os

import django
from django.apps import apps
from django.test import TestCase


if not apps.ready:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
    django.setup()


class TestContractsStage55(TestCase):
    def test_http_contract_contains_iot_fuzzer_routes(self):
        from django.urls.resolvers import URLPattern, URLResolver
        from iotsploit_django.web.api import urls as api_urls

        def _walk(patterns, prefix: str = ""):
            out = []
            for p in patterns:
                if isinstance(p, URLPattern):
                    name = getattr(p, "name", None)
                    if name:
                        out.append((str(name), f"{prefix}{p.pattern}"))
                elif isinstance(p, URLResolver):
                    out.extend(_walk(list(p.url_patterns), prefix=f"{prefix}{p.pattern}"))
            return out

        names = {name for (name, _pattern) in _walk(list(api_urls.urlpatterns))}
        assert "iot_fuzzer_start_campaign" in names
        assert "iot_fuzzer_campaign_status" in names
        assert "iot_fuzzer_results_summary" in names

    def test_ws_contract_contains_iot_fuzzer_routes(self):
        from iotsploit_django import routing

        patterns = {str(p.pattern) for p in getattr(routing, "websocket_urlpatterns", [])}
        assert r"ws/iot-fuzzer/testing/$" in patterns
        assert r"ws/iot-fuzzer/results/$" in patterns


