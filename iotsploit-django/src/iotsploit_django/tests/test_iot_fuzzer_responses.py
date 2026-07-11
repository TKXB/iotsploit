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


class TestIoTFuzzerCampaignResponses(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @staticmethod
    def payload(response):
        return json.loads(response.content)

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

        with patch.object(views.IoTFuzzerManager, "get_instance", return_value=manager):
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

        with patch.object(views.IoTFuzzerManager, "get_instance", return_value=manager):
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
