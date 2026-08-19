"""Server-to-client events for one execution.

Events are notifications, not a replayable log. A client that misses one
refetches the execution state endpoint, which is why there is no sequence
number to reconcile.
"""

from __future__ import annotations

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone

logger = logging.getLogger(__name__)


def group_name(execution_id) -> str:
    return f"plugin_execution_{execution_id}"


def emit(execution_id, event: str, payload: dict | None = None) -> None:
    """Push one event to whoever is watching this execution.

    Never raises. A viewer that is not connected, or a channel layer that is
    unavailable, must not fail the run -- the database is the source of truth
    and the client can always refetch.
    """
    message = {
        "execution_id": str(execution_id),
        "event": event,
        "ts": timezone.now().isoformat(),
        "payload": payload or {},
    }
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(
            group_name(execution_id),
            {"type": "execution_event", "message": message},
        )
    except Exception:  # noqa: BLE001 - reporting must never break a run
        logger.debug("Could not emit %s for %s", event, execution_id, exc_info=True)
