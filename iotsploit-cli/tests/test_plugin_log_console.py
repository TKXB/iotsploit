"""The shell shows what a plugin says, not only what it asks.

Before this bridge existed the CLI configured ``iots.*`` loggers only, left root
empty at WARNING, and so discarded every record a plugin wrote. An operator
driving an interactive plugin typed a request and was shown nothing back until
the run ended.
"""

from __future__ import annotations

import io
import logging

import pytest

from iotsploit_cli.plugin_log_console import console_plugin_logs, transcript_handler

pytestmark = pytest.mark.unit

NAMESPACE = "iotsploit_exploits_cli_test"


@pytest.fixture(autouse=True)
def clean_namespace():
    logger = logging.getLogger(NAMESPACE)
    handlers, level = logger.handlers[:], logger.level
    logger.handlers[:] = []
    logger.setLevel(logging.NOTSET)
    yield
    logger.handlers[:] = handlers
    logger.setLevel(level)


def test_a_plugins_line_reaches_the_terminal():
    out = io.StringIO()
    with console_plugin_logs(out, logger_name=NAMESPACE):
        logging.getLogger(f"{NAMESPACE}.session").info("step 1 of 3: the device answered")
    assert out.getvalue().strip() == "step 1 of 3: the device answered"


def test_the_line_carries_no_logger_path_or_timestamp():
    # The transcript is the operator's record of the exchange. A logger name in
    # front of every response is longer than most of the responses.
    out = io.StringIO()
    with console_plugin_logs(out, logger_name=NAMESPACE):
        logging.getLogger(f"{NAMESPACE}.session").info("step 2 of 3: read back 40 bytes")
    printed = out.getvalue().strip()
    assert printed == "step 2 of 3: read back 40 bytes"
    assert NAMESPACE not in printed


def test_nothing_is_printed_after_the_command_ends():
    out = io.StringIO()
    with console_plugin_logs(out, logger_name=NAMESPACE):
        pass
    logging.getLogger(NAMESPACE).error("a later run, on a logger nobody attached")
    assert out.getvalue() == ""


def test_a_namespace_that_already_has_a_handler_is_left_alone():
    # A host that configured logging deliberately gets its own output, not two
    # copies of every line.
    existing = logging.StreamHandler(io.StringIO())
    logging.getLogger(NAMESPACE).addHandler(existing)
    out = io.StringIO()

    with console_plugin_logs(out, logger_name=NAMESPACE):
        logging.getLogger(NAMESPACE).warning("once")

    assert out.getvalue() == ""
    assert logging.getLogger(NAMESPACE).handlers == [existing]


def test_the_handler_prints_the_message_alone():
    stream = io.StringIO()
    handler = transcript_handler(stream)
    handler.handle(
        logging.LogRecord(NAMESPACE, logging.INFO, __file__, 1, "plain", None, None)
    )
    assert stream.getvalue() == "plain\n"


def test_a_line_is_printed_once_even_though_root_has_a_handler():
    """The regression this file exists to prevent a second time.

    The shell's own stack puts a console handler on the root logger. Making the
    plugin namespace verbose enough to be heard also makes it audible there, so
    without claiming the records the operator reads every response twice: once
    bare, once with a timestamp and a logger path in front of it.
    """
    host = io.StringIO()
    host_handler = logging.StreamHandler(host)
    logging.getLogger().addHandler(host_handler)
    out = io.StringIO()
    try:
        with console_plugin_logs(out, logger_name=NAMESPACE):
            logging.getLogger(f"{NAMESPACE}.session").info("printed once")
    finally:
        logging.getLogger().removeHandler(host_handler)

    assert out.getvalue().count("printed once") == 1
    assert host.getvalue() == ""


def test_the_host_hears_the_namespace_again_once_the_command_ends():
    host = io.StringIO()
    host_handler = logging.StreamHandler(host)
    logging.getLogger().addHandler(host_handler)
    try:
        with console_plugin_logs(io.StringIO(), logger_name=NAMESPACE):
            pass
        logging.getLogger(NAMESPACE).warning("a later run")
    finally:
        logging.getLogger().removeHandler(host_handler)

    assert "a later run" in host.getvalue()
