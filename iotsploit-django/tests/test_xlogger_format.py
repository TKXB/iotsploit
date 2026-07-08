import logging

from iotsploit_django.tools.xlogger import xlog


def _stream_handlers(logger):
    return [handler for handler in logger.handlers if handler.__class__.__name__ == "StreamHandler"]


def test_xlogger_set_format_updates_terminal_handler_only():
    logger = xlog.get_logger("test_xlogger_format")

    xlog.set_format("plain")
    stream_handlers = _stream_handlers(logger)

    assert stream_handlers
    assert stream_handlers[0].formatter._fmt == "%(log_color)s%(message)s"

    ws_handlers = [handler for handler in logger.handlers if handler.__class__.__name__ == "_ConsoleBufferWSHandler"]
    assert ws_handlers
    assert ws_handlers[0].formatter is None

    xlog.set_format("standard")


def test_xlogger_set_format_updates_django_stdlib_stream_handlers():
    logger = logging.getLogger("iotsploit_django.tests.format")
    handler = logging.StreamHandler()
    logger.addHandler(handler)

    try:
        xlog.set_format("plain")

        assert handler.formatter._fmt == "%(message)s"
    finally:
        logger.removeHandler(handler)
        xlog.set_format("standard")
