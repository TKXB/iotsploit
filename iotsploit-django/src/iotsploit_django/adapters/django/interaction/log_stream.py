"""Forward a running plugin's log records to whoever is watching the execution.

The Control Panel's terminal card is fed only by execution events, and it
already renders a ``log`` event::

    case 'log':
      setState(() => _pushLine(level, '${event.payload['message']}'));

Nothing emitted one, so a plugin that logged its progress wrote into a stream
the UI never reads, and the only place an answer could be shown was the next
prompt's description -- inside the box asking the next question. This is the
bridge: for the life of one execution, records from the plugin namespace become
``log`` events on that execution's own socket, and land in the transcript next
to the request that produced them.

Scoped to the plugin namespace rather than to the root logger, because root in a
Celery worker also carries Django, Redis and channel-layer chatter, none of
which is the operator's transcript.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager

from .events import emit

#: Records from here and below are the operator's transcript.
PLUGIN_LOGGER = "iotsploit_exploits"

#: The levels the Control Panel knows how to colour. An unknown level renders in
#: the faint fallback rather than failing, but there is no reason to send one.
UI_LEVELS = {
    logging.DEBUG: "muted",
    logging.INFO: "info",
    logging.WARNING: "warn",
    logging.ERROR: "err",
    logging.CRITICAL: "err",
}


def ui_level(levelno: int) -> str:
    """The closest UI level at or below ``levelno``."""
    for threshold in sorted(UI_LEVELS, reverse=True):
        if levelno >= threshold:
            return UI_LEVELS[threshold]
    return "muted"


class ExecutionLogHandler(logging.Handler):
    """Sends each record to one execution's viewers as a ``log`` event."""

    def __init__(self, execution_id, level: int = logging.INFO):
        super().__init__(level)
        self.execution_id = execution_id
        #: Records the viewers never saw. Counted rather than swallowed, so a
        #: silent transcript can be told apart from a quiet one.
        self.dropped = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            emit(
                self.execution_id,
                "log",
                {"level": ui_level(record.levelno), "message": record.getMessage()},
            )
        except Exception:  # noqa: BLE001 - a logging handler must not raise
            # Deliberately not self.handleError: a viewer that cannot be
            # reached is not the plugin's problem, and a stack trace on stderr
            # for every record would be worse than silence.
            self.dropped += 1


@contextmanager
def stream_logs(execution_id, *, logger_name: str = PLUGIN_LOGGER, level: int = logging.INFO):
    """Send plugin log records to this execution's viewers, for its duration.

    The logger's level is raised for the duration when it would otherwise
    discard the records before any handler saw them, and put back afterwards.
    That is process-global state, which is safe here only because interactive
    executions run on their own queue at concurrency 1 -- one execution at a
    time, by design (see ``interaction_tasks``).
    """
    plugin_logger = logging.getLogger(logger_name)
    handler = ExecutionLogHandler(execution_id, level)
    previous_level = plugin_logger.level
    must_lower = plugin_logger.getEffectiveLevel() > level

    plugin_logger.addHandler(handler)
    if must_lower:
        plugin_logger.setLevel(level)
    try:
        yield handler
    finally:
        plugin_logger.removeHandler(handler)
        if must_lower:
            plugin_logger.setLevel(previous_level)
