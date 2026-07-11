from __future__ import annotations

import os

import django
from django.apps import apps
from django.test import TestCase


IOT_FUZZER_HTTP_ROUTES = {
    "iot_fuzzer_start_campaign": "iot-fuzzer/testing/campaign/start/",
    "iot_fuzzer_stop_campaign": "iot-fuzzer/testing/campaign/stop/",
    "iot_fuzzer_pause_campaign": "iot-fuzzer/testing/campaign/pause/",
    "iot_fuzzer_reset_campaign": "iot-fuzzer/testing/campaign/reset/",
    "iot_fuzzer_campaign_status": "iot-fuzzer/testing/campaign/status/",
    "iot_fuzzer_campaign_statistics": "iot-fuzzer/testing/statistics/",
    "iot_fuzzer_test_groups": "iot-fuzzer/testing/test-groups/",
    "iot_fuzzer_protocol_types": "iot-fuzzer/configuration/protocols/types/",
    "iot_fuzzer_protocol_config": "iot-fuzzer/configuration/protocols/config/",
    "iot_fuzzer_save_protocol_config": "iot-fuzzer/configuration/protocols/config/save/",
    "iot_fuzzer_test_protocol_connection": "iot-fuzzer/configuration/protocols/test-connection/",
    "iot_fuzzer_get_saved_config": "iot-fuzzer/configuration/protocols/saved-config/",
    "iot_fuzzer_generator_types": "iot-fuzzer/configuration/generators/types/",
    "iot_fuzzer_generator_config": "iot-fuzzer/configuration/generators/config/",
    "iot_fuzzer_save_generator_config": "iot-fuzzer/configuration/generators/config/save/",
    "iot_fuzzer_templates_list": "iot-fuzzer/configuration/templates/list/",
    "iot_fuzzer_load_template": "iot-fuzzer/configuration/templates/load/",
    "iot_fuzzer_save_template": "iot-fuzzer/configuration/templates/save/",
    "iot_fuzzer_delete_template": "iot-fuzzer/configuration/templates/delete/",
    "iot_fuzzer_validate_configuration": "iot-fuzzer/configuration/validate/",
    "iot_fuzzer_test_groups_list": "iot-fuzzer/management/test-groups/list/",
    "iot_fuzzer_create_test_group": "iot-fuzzer/management/test-groups/create/",
    "iot_fuzzer_update_test_group": "iot-fuzzer/management/test-groups/update/<int:group_id>/",
    "iot_fuzzer_delete_test_group": "iot-fuzzer/management/test-groups/delete/<int:group_id>/",
    "iot_fuzzer_test_cases_list": "iot-fuzzer/management/test-cases/list/",
    "iot_fuzzer_create_test_case": "iot-fuzzer/management/test-cases/create/",
    "iot_fuzzer_update_test_case": "iot-fuzzer/management/test-cases/update/<int:case_id>/",
    "iot_fuzzer_delete_test_case": "iot-fuzzer/management/test-cases/delete/<int:case_id>/",
    "iot_fuzzer_move_test_case": "iot-fuzzer/management/test-cases/move/",
    "iot_fuzzer_build_protocol_frame": "iot-fuzzer/management/protocol-frames/build/",
    "iot_fuzzer_validate_protocol_frame": "iot-fuzzer/management/protocol-frames/validate/",
    "iot_fuzzer_protocol_frame_templates": "iot-fuzzer/management/protocol-frames/templates/",
    "iot_fuzzer_export_test_data": "iot-fuzzer/management/export/",
    "iot_fuzzer_import_test_data": "iot-fuzzer/management/import/",
    "iot_fuzzer_files_tree": "iot-fuzzer/results/files/tree/",
    "iot_fuzzer_file_content": "iot-fuzzer/results/files/content/<int:file_id>/",
    "iot_fuzzer_download_file": "iot-fuzzer/results/files/download/<int:file_id>/",
    "iot_fuzzer_logs_list": "iot-fuzzer/results/logs/list/",
    "iot_fuzzer_filter_logs": "iot-fuzzer/results/logs/filter/",
    "iot_fuzzer_results_summary": "iot-fuzzer/results/analysis/summary/",
    "iot_fuzzer_results_charts": "iot-fuzzer/results/analysis/charts/",
    "iot_fuzzer_export_results": "iot-fuzzer/results/analysis/export/",
    "iot_fuzzer_artifacts": "iot-fuzzer/results/artifacts/",
}


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

        routes = {
            name: pattern for name, pattern in _walk(list(api_urls.urlpatterns)) if name.startswith("iot_fuzzer_")
        }
        assert routes == IOT_FUZZER_HTTP_ROUTES

    def test_ws_contract_contains_iot_fuzzer_routes(self):
        from iotsploit_django import routing

        patterns = {str(p.pattern) for p in getattr(routing, "websocket_urlpatterns", [])}
        assert r"ws/iot-fuzzer/testing/$" in patterns
        assert r"ws/iot-fuzzer/results/$" in patterns
