"""A host has to ask for a plugin's log records, or they are thrown away.

The failure this guards against is silent by construction: nothing raises, no
handler is called, and the records vanish inside ``Logger.isEnabledFor`` before
a formatter ever runs. That is exactly what the shell did for every interactive
plugin -- prompt shown, answer taken, response discarded.
"""

from __future__ import annotations

import logging

import pytest

from iotsploit_core.core.plugin_logging import PLUGIN_LOGGER, attach_plugin_logs

pytestmark = pytest.mark.unit

NAMESPACE = "iotsploit_exploits_test_namespace"


@pytest.fixture(autouse=True)
def clean_namespace():
    """Leave the test logger exactly as it was found."""
    logger = logging.getLogger(NAMESPACE)
    handlers, level = logger.handlers[:], logger.level
    yield logger
    logger.handlers[:] = handlers
    logger.setLevel(level)


class Collector(logging.Handler):
    def __init__(self):
        super().__init__(logging.INFO)
        self.messages: list[str] = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def test_the_namespace_is_the_one_plugins_actually_log_under():
    # Plugins log with logging.getLogger(__name__) from inside the exploits
    # package; a constant that drifts from that name silences all of them.
    assert PLUGIN_LOGGER == "iotsploit_exploits"


def test_records_reach_the_handler_inside_the_block():
    collector = Collector()
    with attach_plugin_logs(collector, logger_name=NAMESPACE):
        logging.getLogger(f"{NAMESPACE}.example").info("step 1 of 3: the device answered")
    assert collector.messages == ["step 1 of 3: the device answered"]


def test_an_info_record_survives_a_logger_that_would_have_dropped_it():
    # The shell's condition: nothing configured, so the effective level is the
    # root's WARNING and INFO never reaches a handler.
    logging.getLogger(NAMESPACE).setLevel(logging.NOTSET)
    logging.getLogger().setLevel(logging.WARNING)
    collector = Collector()

    logging.getLogger(NAMESPACE).info("dropped, nobody is listening")
    with attach_plugin_logs(collector, logger_name=NAMESPACE):
        logging.getLogger(NAMESPACE).info("heard")

    assert collector.messages == ["heard"]


def test_the_level_goes_back_afterwards():
    logger = logging.getLogger(NAMESPACE)
    logger.setLevel(logging.ERROR)
    with attach_plugin_logs(Collector(), logger_name=NAMESPACE):
        assert logger.level == logging.INFO
    assert logger.level == logging.ERROR


def test_a_logger_already_verbose_enough_is_left_alone():
    logger = logging.getLogger(NAMESPACE)
    logger.setLevel(logging.DEBUG)
    with attach_plugin_logs(Collector(), logger_name=NAMESPACE):
        assert logger.level == logging.DEBUG
    assert logger.level == logging.DEBUG


def test_the_handler_is_detached_even_when_the_run_raises():
    collector = Collector()
    with pytest.raises(RuntimeError):
        with attach_plugin_logs(collector, logger_name=NAMESPACE):
            raise RuntimeError("the plugin blew up")

    logging.getLogger(NAMESPACE).error("after the run")
    assert collector.messages == []
    assert collector not in logging.getLogger(NAMESPACE).handlers
