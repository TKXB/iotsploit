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


def test_reliable_replay_waits_for_a_slow_consumer_and_delivers_the_final_batch():
    async def exercise():
        layer = ThreadSafeInMemoryChannelLayer(capacity=2)
        channel = await layer.new_channel()
        await layer.group_add("replay", channel)

        def produce():
            async def send():
                for sequence in range(200):
                    await layer.group_send_reliable(
                        "replay", {"type": "event", "sequence": sequence, "final": sequence == 199}
                    )
            asyncio.run(send())

        worker = asyncio.create_task(asyncio.to_thread(produce))
        messages = []
        for _ in range(200):
            messages.append(await asyncio.wait_for(layer.receive(channel), timeout=5))
            await asyncio.sleep(0.001)
        await worker
        return messages

    messages = asyncio.run(exercise())

    assert [message["sequence"] for message in messages] == list(range(200))
    assert messages[-1]["final"] is True


def test_reliable_send_unblocks_when_a_full_queue_subscriber_disconnects():
    async def exercise():
        layer = ThreadSafeInMemoryChannelLayer(capacity=1)
        channel = await layer.new_channel()
        await layer.group_add("replay", channel)
        await layer.group_send_reliable("replay", {"type": "event"})
        blocked = asyncio.create_task(layer.group_send_reliable("replay", {"type": "final"}))
        await asyncio.sleep(0)
        assert not blocked.done()

        await layer.group_discard("replay", channel)
        await asyncio.wait_for(blocked, timeout=1)

    asyncio.run(exercise())
