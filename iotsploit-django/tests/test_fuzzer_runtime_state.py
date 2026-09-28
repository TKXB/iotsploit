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
from iotsploit_django.tools.iot_protocol_runtime import CoreObservationRecorder  # noqa: E402
from iotsploit_core.domain.observation import StartedScan  # noqa: E402

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


class RecordingObservationSink:
    def __init__(self):
        self.started = None
        self.completed = []
        self.failed = []

    def start_scans(self, **kwargs):
        self.started = kwargs
        return [StartedScan(scan_id="scan-1", scope=kwargs["scopes"][0])]

    def complete_scan(self, scan_id, facts, *, is_complete=True):
        self.completed.append((scan_id, facts, is_complete))

    def fail_scan(self, scan_id, error):
        self.failed.append((scan_id, error))


def test_core_failure_is_recorded_in_target_history():
    sink = RecordingObservationSink()
    recorder = CoreObservationRecorder(
        sink,
        campaign_id="campaign-1",
        target_id="target-1",
        target="NRF5340_XXAA_APP",
        probe_serial="1050298903",
    )
    observation = {"state": "lockup", "stop_reason": "CPU lockup", "crashed": True}

    recorder.observe(observation)

    assert sink.started["target_id"] == "target-1"
    assert sink.started["scopes"][0].scope_key == "jtag-core:NRF5340_XXAA_APP:1050298903"
    assert sink.completed[0][0] == "scan-1"
    assert sink.completed[0][1][0].value == observation
    assert sink.completed[0][2] is False
    assert sink.failed == []
