"""Where a plugin's own account of a run comes from, and how to listen to it.

Plugins log with plain ``logging.getLogger(__name__)``, so their records land
under one namespace and propagate to whatever the host has configured. That is
enough in a Celery worker, where the root logger already carries handlers, and
not enough anywhere else: a CLI shell configures ``iots.*`` loggers only, leaves
root at WARNING with no handlers, and therefore drops every INFO record a plugin
writes before it is even formatted.

So a host that wants the transcript has to ask for it. :func:`attach_plugin_logs`
is that request -- it adds one handler and, when the namespace would otherwise
discard the records unseen, lowers its level for the duration. What the handler
does with a record is the host's business: the GUI turns it into a websocket
event, the shell prints it.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

#: Records from here and below are the operator's transcript. Scoped to the
#: plugin namespace rather than root, because root in a Celery worker also
#: carries Django, Redis and channel-layer chatter, none of which is that.
PLUGIN_LOGGER = "iotsploit_exploits"


@contextmanager
def attach_plugin_logs(
    handler: logging.Handler,
    *,
    logger_name: str = PLUGIN_LOGGER,
    level: int = logging.INFO,
    exclusive: bool = False,
) -> Iterator[logging.Handler]:
    """Route plugin log records to ``handler`` for the length of the block.

    The logger's level is lowered only when it would otherwise discard the
    records before any handler saw them, and put back afterwards. That is
    process-global state, so it is safe only where one run is in flight at a
    time -- which is what the interactive queue's concurrency of 1 and a shell's
    single operator both guarantee.

    ``exclusive`` stops the records propagating to ancestor handlers while the
    block runs. It exists because lowering the level does not only feed the
    handler passed here: any handler already on an ancestor starts receiving the
    same records, and a host that has one -- a shell whose root logger carries a
    console handler, say -- then prints every line twice, once bare and once
    with a timestamp and logger path in front of it. Set it where this handler
    is meant to *be* the transcript; leave it alone where the records should
    also reach the host's ordinary logs, as they must in a worker.
    """
    plugin_logger = logging.getLogger(logger_name)
    previous_level = plugin_logger.level
    previous_propagate = plugin_logger.propagate
    must_lower = plugin_logger.getEffectiveLevel() > level

    plugin_logger.addHandler(handler)
    if must_lower:
        plugin_logger.setLevel(level)
    if exclusive:
        plugin_logger.propagate = False
    try:
        yield handler
    finally:
        plugin_logger.removeHandler(handler)
        if must_lower:
            plugin_logger.setLevel(previous_level)
        if exclusive:
            plugin_logger.propagate = previous_propagate
