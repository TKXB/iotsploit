"""Plugin log records reaching the execution's own viewers.

The rule this protects: the Control Panel terminal is fed only by execution
events. A plugin that logs its progress is writing for the operator, so those
records have to become ``log`` events on that execution's socket -- otherwise
the only surface a plugin can write to is the next prompt's description, which
is the box asking the next question, not a transcript.
"""

from __future__ import annotations

import logging
import os

import django
import pytest
from django.apps import apps

if not apps.ready:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "iotsploit_django.settings.dev")
    django.setup()

from iotsploit_django.adapters.django.interaction import log_stream

pytestmark = [pytest.mark.django, pytest.mark.unit]

EXECUTION = "11111111-2222-3333-4444-555555555555"


@pytest.fixture
def emitted(monkeypatch):
    """Every event the bridge sends, as (execution_id, event, payload)."""
    sent: list[tuple] = []
    monkeypatch.setattr(
        log_stream, "emit", lambda eid, event, payload: sent.append((eid, event, payload))
    )
    return sent


@pytest.fixture(autouse=True)
def _restore_plugin_logger():
    """The bridge touches a process-global logger; put it back either way."""
    plugin_logger = logging.getLogger(log_stream.PLUGIN_LOGGER)
    before_level = plugin_logger.level
    before_handlers = list(plugin_logger.handlers)
    yield
    plugin_logger.setLevel(before_level)
    plugin_logger.handlers[:] = before_handlers


def test_a_plugin_record_becomes_a_log_event_on_its_execution(emitted):
    with log_stream.stream_logs(EXECUTION):
        logging.getLogger("iotsploit_exploits.example.session").info(
            "step 2 of 5: the device answered"
        )

    assert emitted == [
        (
            EXECUTION,
            "log",
            {"level": "info", "message": "step 2 of 5: the device answered"},
        )
    ]


def test_records_from_outside_the_plugin_namespace_are_left_alone(emitted):
    with log_stream.stream_logs(EXECUTION):
        logging.getLogger("django.db.backends").info("SELECT 1")
        logging.getLogger("redis").warning("reconnecting")

    assert emitted == []


def test_the_bridge_is_removed_when_the_execution_ends(emitted):
    plugin_logger = logging.getLogger(log_stream.PLUGIN_LOGGER)
    handlers_before = len(plugin_logger.handlers)

    with log_stream.stream_logs(EXECUTION):
        pass
    logging.getLogger("iotsploit_exploits.example.session").info("after the run")

    assert len(plugin_logger.handlers) == handlers_before
    assert emitted == []


def test_an_info_record_survives_a_quieter_logger(emitted):
    # A plugin logger left at WARNING would drop the transcript before any
    # handler saw it, so the bridge lowers it for the duration and restores it.
    plugin_logger = logging.getLogger(log_stream.PLUGIN_LOGGER)
    plugin_logger.setLevel(logging.WARNING)

    with log_stream.stream_logs(EXECUTION):
        logging.getLogger("iotsploit_exploits.example.session").info("still heard")

    assert [payload["message"] for _, _, payload in emitted] == ["still heard"]
    assert plugin_logger.level == logging.WARNING


def test_a_viewer_that_cannot_be_reached_does_not_break_the_run(monkeypatch):
    def exploding_emit(*args, **kwargs):
        raise RuntimeError("no channel layer")

    monkeypatch.setattr(log_stream, "emit", exploding_emit)

    with log_stream.stream_logs(EXECUTION) as handler:
        # The run must carry on: a disconnected viewer is not the plugin's
        # problem, and logging.raiseExceptions would make it stderr noise.
        logging.getLogger("iotsploit_exploits.example.session").info("unheard")

    assert handler.dropped == 1


@pytest.mark.parametrize(
    ("levelno", "expected"),
    [
        (logging.DEBUG, "muted"),
        (logging.INFO, "info"),
        (logging.WARNING, "warn"),
        (logging.ERROR, "err"),
        (logging.CRITICAL, "err"),
        (logging.INFO + 1, "info"),  # between levels, rounds down
        (1, "muted"),  # below DEBUG
    ],
)
def test_levels_map_onto_the_ones_the_panel_can_colour(levelno, expected):
    assert log_stream.ui_level(levelno) == expected
