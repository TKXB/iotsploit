"""Durable interaction adapter.

Implements the plugin interaction port for a worker that is not the process
holding the operator's screen. The question goes into the database, the answer
comes back out of it, and polling is the whole mechanism: one indexed single-row
query every half second while a run is waiting.

Polling rather than a Redis notification is deliberate. It is one code path
instead of two, it cannot lose a wake-up, and it keeps working if the stack ever
collapses to a single process. See plan decision 1.
"""

from __future__ import annotations

import logging
import time

from asgiref.sync import sync_to_async
from django.utils import timezone

from iotsploit_core.ports.interaction import (
    InteractionCancelled,
    InteractionTimeout,
    Prompt,
    PromptSugar,
    guard_sync_call,
)
from iotsploit_django.adapters.django.interaction import service
from iotsploit_django.adapters.django.interaction.models import (
    ExecutionStatus,
    InputRequest,
    PluginExecution,
    RequestStatus,
)

logger = logging.getLogger(__name__)

POLL_SECONDS = 0.5
CANCEL_CHECK_SECONDS = 1.0


class DurableInteractionAdapter(PromptSugar):
    """Ask through the database, wait for someone to answer."""

    def __init__(self, execution_id, *, poll_seconds: float = POLL_SECONDS):
        self.execution_id = execution_id
        self.poll_seconds = poll_seconds
        self._last_cancel_check = 0.0

    # -- port ------------------------------------------------------------
    def request(self, prompt: Prompt):
        guard_sync_call("request")
        return self._ask(prompt)

    async def arequest(self, prompt: Prompt):
        return await sync_to_async(self._ask, thread_sensitive=False)(prompt)

    def check_cancelled(self) -> None:
        # Rate limited: plugins are encouraged to call this inside tight loops.
        now = time.monotonic()
        if now - self._last_cancel_check < CANCEL_CHECK_SECONDS:
            return
        self._last_cancel_check = now
        self._raise_if_cancelled()

    async def acheck_cancelled(self) -> None:
        await sync_to_async(self.check_cancelled, thread_sensitive=False)()

    # -- internals -------------------------------------------------------
    def _ask(self, prompt: Prompt):
        request = service.create_request(self.execution_id, prompt)
        logger.info("Execution %s is waiting on %s (%s)",
                    self.execution_id, request.request_id, prompt.kind)

        while True:
            time.sleep(self.poll_seconds)

            row = InputRequest.objects.filter(
                request_id=request.request_id
            ).values("status", "answer_value").first()

            if row is None:                       # execution deleted underneath us
                raise InteractionCancelled("The execution no longer exists.")

            status = row["status"]
            if status == RequestStatus.ANSWERED:
                PluginExecution.objects.filter(
                    execution_id=self.execution_id
                ).update(status=ExecutionStatus.RUNNING)
                return row["answer_value"]

            if status == RequestStatus.CANCELLED:
                raise InteractionCancelled("The run was cancelled while waiting.")

            if status == RequestStatus.EXPIRED:
                raise InteractionTimeout("Nobody answered in time.")

            if timezone.now() >= request.expires_at:
                service.expire_request(request.request_id)
                raise InteractionTimeout(
                    f"Nobody answered '{prompt.title}' within "
                    f"{int(prompt.timeout)}s."
                )

            self._raise_if_cancelled()

    def _raise_if_cancelled(self) -> None:
        status = PluginExecution.objects.filter(
            execution_id=self.execution_id
        ).values_list("status", flat=True).first()
        if status in (ExecutionStatus.CANCELLED, ExecutionStatus.EXPIRED):
            raise InteractionCancelled("The run was cancelled.")
