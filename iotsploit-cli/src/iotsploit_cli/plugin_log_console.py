#!/usr/bin/env python
"""Put a running plugin's own log records on the shell's terminal.

The GUI has fed plugin logs into the execution transcript since the interaction
port existed; the shell has not, and not by choice. ``iots_logger`` builds
``iots.*`` loggers that carry their own handler and do not propagate, so it
never gives the root logger one -- root stays empty at WARNING, and a plugin
logging its progress at INFO under ``iotsploit_exploits`` had those records
discarded before any formatter ran. An operator driving an interactive plugin
from the shell saw the prompt, typed a request, and was shown nothing back until
the run ended and the result was dumped.

This is the shell's half of the same bridge the Celery task uses, differing only
in where a record goes: to stderr, alongside the shell's own output, so the
answer appears under the request that asked for it.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

from iotsploit_core.core.plugin_logging import PLUGIN_LOGGER, attach_plugin_logs

#: Plugin lines are the operator's transcript, not the shell's own commentary,
#: so they carry the message alone -- a timestamp and a logger path in front of
#: ``1001 -> 5001003201F4`` is three quarters noise.
TRANSCRIPT_FORMAT = "%(message)s"


def transcript_handler(stream=None, *, level: int = logging.INFO) -> logging.Handler:
    """A stderr handler that prints plugin records and nothing else."""
    handler = logging.StreamHandler(stream)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(TRANSCRIPT_FORMAT))
    return handler


@contextmanager
def console_plugin_logs(
    stream=None,
    *,
    logger_name: str = PLUGIN_LOGGER,
    level: int = logging.INFO,
) -> Iterator[logging.Handler]:
    """Show plugin log records on the terminal for the length of the block.

    A no-op when the namespace already has a handler of its own: the shell is
    importable from a host that configured logging deliberately, and doubling
    every line is worse than the shell staying quiet.
    """
    if logging.getLogger(logger_name).handlers:
        yield logging.NullHandler()
        return

    handler = transcript_handler(stream, level=level)
    with attach_plugin_logs(handler, logger_name=logger_name, level=level):
        try:
            yield handler
        finally:
            handler.flush()


__all__ = ["PLUGIN_LOGGER", "console_plugin_logs", "transcript_handler"]
