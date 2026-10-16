"""Routes each command to its single handler, with timeouts and cooperative cancellation."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from assistant.contracts import Command, Result

log = logging.getLogger(__name__)

CommandHandler = Callable[[Command], Awaitable[Result]]


class CommandRouter:
    def __init__(self, default_timeout: float = 30.0, timeouts: dict[str, float] | None = None):
        self._default_timeout = default_timeout
        self._timeouts = timeouts or {}
        self._handlers: dict[type[Command], CommandHandler] = {}
        self._inflight: dict[str, tuple[Command, asyncio.Task]] = {}

    def register(self, command_type: type[Command], handler: CommandHandler) -> None:
        if command_type in self._handlers:
            raise ValueError(f"{command_type.__name__} already has a handler")
        self._handlers[command_type] = handler

    def unregister(self, command_type: type[Command], handler: CommandHandler) -> None:
        """Remove `handler`, but only if it is still the registered one."""
        if self._handlers.get(command_type) is handler:
            del self._handlers[command_type]

    async def send(self, command: Command, timeout: float | None = None) -> Result:
        """Run the command's handler and return its result. Never raises for handler problems.

        The timeout is, in order: `timeout`, the per-type value from config,
        then the default. On timeout the handler is cancelled.
        """
        name = type(command).__name__
        handler = self._handlers.get(type(command))
        if handler is None:
            return Result.not_available(f"No handler for {name}")
        if timeout is None:
            timeout = self._timeouts.get(name, self._default_timeout)

        task = asyncio.create_task(handler(command), name=f"command:{name}:{command.id}")
        self._inflight[command.id] = (command, task)
        task.add_done_callback(lambda _: self._inflight.pop(command.id, None))
        try:
            done, _ = await asyncio.wait({task}, timeout=timeout)
        except asyncio.CancelledError:
            # The sender itself was cancelled; don't leave the handler running.
            task.cancel()
            raise

        if not done:
            task.cancel()
            return Result.timed_out(f"{name} timed out after {timeout}s")
        if task.cancelled():
            return Result.cancelled(f"{name} was cancelled")
        exc = task.exception()
        if exc is not None:
            log.error("Handler for %s raised", name, exc_info=exc)
            return Result.failed(f"{type(exc).__name__}: {exc}")
        result = task.result()
        if not isinstance(result, Result):
            return Result.failed(f"Handler for {name} returned {type(result).__name__}, not Result")
        return result

    def cancel(self, correlation_id: str) -> int:
        """Cancel in-flight commands whose id or correlation id matches. Returns how many."""
        matches = [
            task
            for command, task in self._inflight.values()
            if correlation_id in (command.id, command.correlation_id)
        ]
        for task in matches:
            task.cancel()
        return len(matches)

    def cancel_all(self) -> int:
        tasks = [task for _, task in self._inflight.values()]
        for task in tasks:
            task.cancel()
        return len(tasks)
