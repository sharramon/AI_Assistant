import asyncio

from assistant.contracts import Event
from assistant.core.bus import EventBus
from tests.support import wait_until


class Ping(Event):
    n: int = 0


class Other(Event):
    pass


async def test_delivers_to_matching_subscribers_only():
    bus = EventBus()
    pings, everything = [], []

    async def on_ping(e):
        pings.append(e)

    async def on_any(e):
        everything.append(e)

    bus.subscribe(Ping, on_ping)
    bus.subscribe(Event, on_any)
    bus.publish(Ping())
    bus.publish(Other())
    await wait_until(lambda: len(everything) == 2)
    assert len(pings) == 1
    await bus.close()


async def test_slow_subscriber_does_not_block_others():
    bus = EventBus()
    gate = asyncio.Event()
    fast = []

    async def slow(e):
        await gate.wait()

    async def quick(e):
        fast.append(e)

    bus.subscribe(Ping, slow)
    bus.subscribe(Ping, quick)
    bus.publish(Ping())
    await wait_until(lambda: len(fast) == 1)
    gate.set()
    await bus.close()


async def test_failing_subscriber_keeps_receiving_and_others_unaffected():
    bus = EventBus()
    attempts, received = [], []

    async def flaky(e):
        attempts.append(e.n)
        raise RuntimeError("boom")

    async def good(e):
        received.append(e.n)

    bus.subscribe(Ping, flaky)
    bus.subscribe(Ping, good)
    bus.publish(Ping(n=1))
    bus.publish(Ping(n=2))
    await wait_until(lambda: attempts == [1, 2] and received == [1, 2])
    await bus.close()


async def test_stuck_handler_is_cancelled_after_timeout():
    bus = EventBus(handler_timeout=0.05)
    seen = []

    async def handler(e):
        seen.append(e.n)
        if e.n == 1:
            await asyncio.sleep(10)

    bus.subscribe(Ping, handler)
    bus.publish(Ping(n=1))
    bus.publish(Ping(n=2))
    await wait_until(lambda: seen == [1, 2])
    await bus.close()


async def test_full_queue_drops_events():
    bus = EventBus(queue_size=1)
    seen = []

    async def handler(e):
        seen.append(e.n)

    bus.subscribe(Ping, handler)
    for n in range(3):  # published without yielding, so only the first fits
        bus.publish(Ping(n=n))
    await asyncio.sleep(0.05)
    assert seen == [0]
    await bus.close()


async def test_unsubscribe_stops_delivery():
    bus = EventBus()
    seen = []

    async def handler(e):
        seen.append(e)

    sub = bus.subscribe(Ping, handler)
    bus.unsubscribe(sub)
    bus.publish(Ping())
    await asyncio.sleep(0.02)
    assert seen == [] and sub.task.cancelled()
    await bus.close()
