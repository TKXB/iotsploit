from __future__ import annotations

import os

import django
import pytest
from django.apps import apps

if not apps.ready:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
    django.setup()

from iotsploit_django.adapters.django.iot_fuzzer.models import FuzzingCampaign  # noqa: E402
from iotsploit_django.tools.iot_fuzzer_manager import IoTFuzzerManager  # noqa: E402

pytestmark = [pytest.mark.django, pytest.mark.integration]


def _state(campaign_id):
    return {
        "id": campaign_id,
        "config": {
            "campaign_name": "Repeated name",
            "protocol_type": "can",
            "protocol_config": {"device_path": "can0"},
            "generator_config": {},
        },
        "status": "starting",
        "created_at": "2026-09-01T00:00:00+00:00",
        "started_at": None,
        "execs_done": 0,
    }


def test_campaign_runs_keep_distinct_uuid_owned_state(db):
    manager = object.__new__(IoTFuzzerManager)
    manager.store_campaign_state("run-one", _state("run-one"))
    manager.store_campaign_state("run-two", _state("run-two"))

    manager.update_campaign_state("run-two", {"status": "running", "execs_done": 12})

    assert FuzzingCampaign.objects.filter(name="Repeated name").count() == 2
    assert manager.get_campaign_state("run-one")["execs_done"] == 0
    assert manager.get_campaign_state("run-two")["execs_done"] == 12
    assert set(manager.get_active_campaigns()) == {"run-one", "run-two"}
