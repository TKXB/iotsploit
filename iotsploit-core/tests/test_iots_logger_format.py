import itertools

from iotsploit_core.utils import iots_logger


_ids = itertools.count()


def _logger_name(prefix):
    return f"{prefix}_{next(_ids)}"


def _console_format(logger):
    return logger.handlers[0].formatter._fmt


def test_set_format_plain_applies_to_new_loggers():
    iots_logger.set_format("plain")

    logger = iots_logger.get_logger(_logger_name("plain"))

    assert _console_format(logger) == "%(message)s"
    iots_logger.set_format("standard")


def test_set_format_compact_updates_existing_loggers():
    iots_logger.set_format("standard")
    logger = iots_logger.get_logger(_logger_name("compact"))

    iots_logger.set_format("compact")

    assert _console_format(logger) == "%(levelname)s | %(message)s"
    iots_logger.set_format("standard")


def test_set_format_invalid_value_is_ignored():
    iots_logger.set_format("standard")
    logger = iots_logger.get_logger(_logger_name("invalid"))

    iots_logger.set_format("missing")

    assert _console_format(logger) == "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
