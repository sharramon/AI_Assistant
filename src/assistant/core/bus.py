"""In-process publish/subscribe with isolated, bounded delivery per subscriber."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from assistant.contracts import Event

log = logging.getLogger(__name__)

EventHandler = Callable[[Event], Awaitable[None]]


class Subscription:
    """Delivers matching events to one handler, in order, from a bounded queue.

    Each subscription has exactly one worker task, so a slow or failing handler
    only delays its own events, and the number of tasks never grows with traffic.
    """

    def __init__(
        self,
        event_type: type[Event],
        handler: EventHandler,
        owner: str,
        queue_size: int,
        handler_timeout: float | None,
    ):
        self.event_type = event_type
        self.owner = owner
        self._handler = handler
        self._handler_timeout = handler_timeout
        self._queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=queue_size)
        self.task = asyncio.create_task(self._deliver(), name=f"events:{owner}:{event_type.__name__}")

    def offer(self, event: Event) -> bool:
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            return False
        return True

    async def _deliver(self) -> None:
        while True:
            event = await self._queue.get()
            try:
                async with asyncio.timeout(self._handler_timeout):
                    await self._handler(event)
            except TimeoutError:
                log.warning(
                    "%s: handler for %s exceeded %ss and was cancelled",
                    self.owner, type(event).__name__, self._handler_timeout,
                )
            except Exception:
                log.exception("%s: handler for %s raised", self.owner, type(event).__name__)


class EventBus:
    def __init__(self, queue_size: int = 100, handler_timeout: float | None = 10.0):
        self._queue_size = queue_size
        self._handler_timeout = handler_timeout
        self._subs: list[Subscription] = []

    def subscribe(self, event_type: type[Event], handler: EventHandler, owner: str = "core") -> Subscription:
        """Receive every event that is an instance of `event_type` (so `Event` receives all)."""
        sub = Subscription(event_type, handler, owner, self._queue_size, self._handler_timeout)
        self._subs.append(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        """Stop delivery. Events still queued for this subscription are dropped."""
        if sub in self._subs:
            self._subs.remove(sub)
        sub.task.cancel()

    def publish(self, event: Event) -> None:
        """Queue the event for each matching subscriber and return immediately."""
        for sub in self._subs:
            if isinstance(event, sub.event_type) and not sub.offer(event):
                log.warning("Dropped %s for %s: queue full", type(event).__name__, sub.owner)

    async def close(self) -> None:
        subs, self._subs = self._subs, []
        for sub in subs:
            sub.task.cancel()
        await asyncio.gather(*(sub.task for sub in subs), return_exceptions=True)
