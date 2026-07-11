from __future__ import annotations

import json
import os
from unittest.mock import Mock, patch

import django
from django.apps import apps
from django.test import RequestFactory, SimpleTestCase


if not apps.ready:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
    django.setup()

from iotsploit_django.iot_fuzzer import views
from iotsploit_django.iot_fuzzer import views_campaign


ENDPOINT_METHODS = {
    "start_campaign": "POST",
    "stop_campaign": "POST",
    "pause_campaign": "POST",
    "reset_campaign": "POST",
    "get_campaign_status": "GET",
    "get_campaign_statistics": "GET",
    "get_test_groups": "GET",
    "get_protocol_types": "GET",
    "get_protocol_config": "GET",
    "save_protocol_config": "POST",
    "get_saved_config": "GET",
    "test_protocol_connection": "POST",
    "get_generator_types": "GET",
    "get_generator_config": "GET",
    "save_generator_config": "POST",
    "get_templates_list": "GET",
    "load_template": "POST",
    "save_template": "POST",
    "delete_template": "POST",
    "validate_configuration": "POST",
    "get_test_groups_list": "GET",
    "create_test_group": "POST",
    "update_test_group": "PUT",
    "delete_test_group": "DELETE",
    "get_test_cases_list": "GET",
    "create_test_case": "POST",
    "update_test_case": "PUT",
    "delete_test_case": "DELETE",
    "move_test_case": "POST",
    "build_protocol_frame": "POST",
    "validate_protocol_frame": "POST",
    "get_protocol_frame_templates": "GET",
    "export_test_data": "POST",
    "import_test_data": "POST",
    "get_files_tree": "GET",
    "get_file_content": "GET",
    "download_file": "GET",
    "get_logs_list": "GET",
    "filter_logs": "POST",
    "get_results_summary": "GET",
    "get_results_charts": "GET",
    "export_results": "POST",
    "get_artifacts": "GET",
}

ENDPOINT_ARGUMENTS = {
    "update_test_group": (1,),
    "delete_test_group": (1,),
    "update_test_case": (1,),
    "delete_test_case": (1,),
    "get_file_content": (1,),
    "download_file": (1,),
}


class TestIoTFuzzerCampaignResponses(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @staticmethod
    def payload(response):
        return json.loads(response.content)

    def test_every_endpoint_preserves_method_error_contract(self):
        request = self.factory.patch("/", data="{}", content_type="application/json")
        for name, method in ENDPOINT_METHODS.items():
            with self.subTest(endpoint=name):
                response = getattr(views, name)(request, *ENDPOINT_ARGUMENTS.get(name, ()))
                self.assertEqual(response.status_code, 405)
                self.assertEqual(
                    self.payload(response),
                    {"status": "error", "message": f"Only {method} method is allowed"},
                )

    def test_campaign_control_rejects_wrong_method(self):
        for view in (views.start_campaign, views.stop_campaign, views.pause_campaign, views.reset_campaign):
            with self.subTest(view=view.__name__):
                response = view(self.factory.get("/"))
                self.assertEqual(response.status_code, 405)
                self.assertEqual(
                    self.payload(response),
                    {"status": "error", "message": "Only POST method is allowed"},
                )

    def test_campaign_control_rejects_invalid_json(self):
        for view in (views.start_campaign, views.stop_campaign, views.pause_campaign, views.reset_campaign):
            with self.subTest(view=view.__name__):
                response = view(self.factory.post("/", data="{", content_type="application/json"))
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    self.payload(response),
                    {"status": "error", "message": "Invalid JSON format"},
                )

    def test_stop_pause_and_reset_success_envelopes(self):
        manager = Mock()
        manager.stop_campaign.return_value = {"state": "stopped"}
        manager.pause_campaign.return_value = {"state": "paused"}
        manager.reset_campaign.return_value = {"state": "reset"}
        cases = (
            (views.stop_campaign, manager.stop_campaign, "stopped", "Campaign stopped successfully"),
            (views.pause_campaign, manager.pause_campaign, "paused", "Campaign paused successfully"),
            (views.reset_campaign, manager.reset_campaign, "reset", "Campaign reset successfully"),
        )

        with patch.object(views_campaign.IoTFuzzerManager, "get_instance", return_value=manager):
            for view, operation, state, message in cases:
                with self.subTest(view=view.__name__):
                    response = view(
                        self.factory.post(
                            "/",
                            data=json.dumps({"campaign_id": "campaign-1"}),
                            content_type="application/json",
                        )
                    )
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(
                        self.payload(response),
                        {"status": "success", "result": {"state": state}, "message": message},
                    )
                    operation.assert_called_once_with("campaign-1")

    def test_campaign_status_success_envelope(self):
        manager = Mock()
        manager.get_campaign_status.return_value = {"state": "running", "progress": 25}

        with patch.object(views_campaign.IoTFuzzerManager, "get_instance", return_value=manager):
            response = views.get_campaign_status(self.factory.get("/", {"campaign_id": "campaign-1"}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.payload(response),
            {"status": "success", "campaign_status": {"state": "running", "progress": 25}},
        )

    def test_campaign_status_requires_campaign_id(self):
        response = views.get_campaign_status(self.factory.get("/"))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            self.payload(response),
            {"status": "error", "message": "Campaign ID is required"},
        )
