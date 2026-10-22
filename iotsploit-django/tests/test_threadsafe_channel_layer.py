from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest

from iotsploit_django.adapters.django.threadsafe_channel_layer import (
    ThreadSafeInMemoryChannelLayer,
)

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def test_worker_thread_events_arrive_in_order_under_load():
    async def exercise():
        layer = ThreadSafeInMemoryChannelLayer()
        channel = await layer.new_channel()
        await layer.group_add("execution", channel)

        def send_from_worker():
            for sequence in range(100):
                layer.group_send_threadsafe(
                    "execution", {"type": "event", "sequence": sequence}
                )

        with ThreadPoolExecutor(max_workers=1) as executor:
            worker = asyncio.get_running_loop().run_in_executor(executor, send_from_worker)
            received = [await layer.receive(channel) for _ in range(100)]
            await worker
        return received

    messages = asyncio.run(exercise())
    assert [message["sequence"] for message in messages] == list(range(100))
