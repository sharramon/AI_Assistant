"""Terminal input/output: each line typed becomes an InputReceived event, and the
replies to those inputs (and uncorrelated replies) are printed. Type `exit` or
`quit` to shut down."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable

from assistant.contracts import (
    InputReceived,
    Manifest,
    Module,
    ModuleContext,
    ResponseReady,
    ShutdownRequested,
)

EXIT_WORDS = {"exit", "quit"}


class _StdinReader:
    """One daemon thread per process that reads stdin and hands lines to the active module.

    A blocking input() call can't be cancelled, so the thread outlives a
    deactivated module and is reused when the module is activated again. Lines
    typed while no module is attached are dropped.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._target: tuple[asyncio.AbstractEventLoop, Callable[[str], None]] | None = None
        self._thread: threading.Thread | None = None

    def attach(self, loop: asyncio.AbstractEventLoop, callback: Callable[[str], None]) -> None:
        with self._lock:
            self._target = (loop, callback)
            if self._thread is None:
                # Daemon, so it never keeps the process alive after shutdown.
                self._thread = threading.Thread(target=self._run, name="console-input", daemon=True)
                self._thread.start()

    def detach(self, callback: Callable[[str], None]) -> None:
        with self._lock:
            if self._target and self._target[1] == callback:
                self._target = None

    def _run(self) -> None:
        while True:
            try:
                line, at_eof = input().strip(), False
            except EOFError:
                line, at_eof = "exit", True
            with self._lock:
                target = self._target
                if at_eof:
                    self._thread = None
            if target:
                loop, callback = target
                try:
                    loop.call_soon_threadsafe(callback, line)
                except RuntimeError:  # the event loop has already closed
                    pass
            if at_eof:
                return


_stdin = _StdinReader()


class ConsoleIO(Module):
    manifest = Manifest(id="console_io")

    async def init(self, ctx: ModuleContext) -> None:
        self._ctx = ctx
        self._prompt = ctx.config.get("prompt", "> ")
        self._awaiting: set[str] = set()  # ids of inputs we sent and haven't seen a reply to
        ctx.subscribe(ResponseReady, self._on_response)

    async def start(self) -> None:
        _stdin.attach(asyncio.get_running_loop(), self._submit)
        print(self._prompt, end="", flush=True)

    async def stop(self) -> None:
        _stdin.detach(self._submit)

    def _submit(self, text: str) -> None:
        if text in EXIT_WORDS:
            self._ctx.publish(ShutdownRequested(reason="console exit"))
        elif not text:
            print(self._prompt, end="", flush=True)
        else:
            event = InputReceived(text=text, source=self.manifest.id)
            self._awaiting.add(event.id)
            self._ctx.publish(event)

    async def _on_response(self, event: ResponseReady) -> None:
        # Print replies to our own inputs, not those from other clients, and
        # uncorrelated ones: the assistant speaking first (e.g. "the task is done").
        if event.correlation_id is not None:
            if event.correlation_id not in self._awaiting:
                return
            self._awaiting.discard(event.correlation_id)
        print(event.text)
        print(self._prompt, end="", flush=True)
