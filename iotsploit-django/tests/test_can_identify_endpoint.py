"""The Identify bus endpoint reports scored read-only samples distinctly."""

from __future__ import annotations

import json
import os

import django
import pytest
from django.apps import apps

if not apps.ready:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
    django.setup()

from django.test import RequestFactory  # noqa: E402

import iotsploit_django.view_handlers.can_views as views  # noqa: E402
from iotsploit_protocols.canbus.logfile import LogReadStats  # noqa: E402

pytestmark = pytest.mark.contract


def target():
    return {
        "target_id": "bench",
        "name": "Bench",
        "type": "vehicle",
        "buses": [
            {
                "bus_id": "body",
                "name": "Body CAN",
                "type": "can",
                "properties": {
                    "messages": [
                        {"frame_id": 0x100, "name": "A", "dlc": 1},
                        {"frame_id": 0x101, "name": "B", "dlc": 1},
                    ]
                },
            }
        ],
        "components": [],
    }


class Targets:
    def get_target(self, target_id):
        return target() if target_id == "bench" else None


def post(**overrides):
    body = {"target_id": "bench", "channel": "can0", "seconds": 1}
    body.update(overrides)
    return RequestFactory().post(
        "/api/identify_can_bus/",
        data=json.dumps(body),
        content_type="application/json",
    )


def test_a_clear_winner_is_returned_without_opening_real_hardware(monkeypatch):
    monkeypatch.setattr(views.TargetManager, "get_instance", staticmethod(Targets))
    monkeypatch.setattr(
        views,
        "observe_identities",
        lambda channel, seconds, fd: {(0x100, False), (0x101, False)},
    )

    response = views.identify_can_bus(post())
    payload = json.loads(response.content)

    assert response.status_code == 200
    assert payload["outcome"] == "winner"
    assert payload["best_bus_id"] == "body"
    assert payload["identities_heard"] == 2


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"target_id": ""}, "required"),
        ({"channel": ""}, "required"),
        ({"seconds": 31}, "at most 30"),
    ],
)
def test_invalid_requests_fail_before_listening(monkeypatch, overrides, message):
    monkeypatch.setattr(views.TargetManager, "get_instance", staticmethod(Targets))
    monkeypatch.setattr(
        views,
        "observe_identities",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("opened hardware")),
    )

    response = views.identify_can_bus(post(**overrides))

    assert response.status_code == 400
    assert message in json.loads(response.content)["message"]


def test_inspect_log_reports_format_and_named_channels(monkeypatch):
    monkeypatch.setattr(
        views,
        "scan_log",
        lambda path, max_frames: LogReadStats(
            format="candump", frames=12, channels_present={"can0", "vcan1"}
        ),
    )
    request = RequestFactory().post(
        "/api/inspect_can_log/",
        data=json.dumps({"path": "/uploads/capture.log"}),
        content_type="application/json",
    )

    response = views.inspect_can_log(request)
    payload = json.loads(response.content)

    assert response.status_code == 200
    assert payload["format"] == "candump"
    assert payload["channels_present"] == ["can0", "vcan1"]
    assert payload["frames"] == 12


def test_identify_log_preserves_a_candump_interface_name(monkeypatch):
    monkeypatch.setattr(views.TargetManager, "get_instance", staticmethod(Targets))
    monkeypatch.setattr(
        views,
        "scan_log",
        lambda path, channel, max_frames: LogReadStats(
            format="candump", frames=1, channels_present={"can0", "can1"}
        ),
    )
    seen_channels = []

    def identities(path, channel):
        seen_channels.append(channel)
        return {(0x100, False)}

    monkeypatch.setattr(views, "identities_from_log", identities)

    response = views.identify_can_bus(
        post(channel="", path="/uploads/capture.log", log_channel="can1")
    )
    payload = json.loads(response.content)

    assert response.status_code == 200
    assert payload["log_channel"] == "can1"
    assert seen_channels == ["can1"]
