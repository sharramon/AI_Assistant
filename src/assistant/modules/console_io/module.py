"""Terminal input/output: each line typed becomes an InputReceived event, and the
replies to those inputs are printed. Type `exit` or `quit` to shut down."""

from __future__ import annotations

import asyncio
import threading

from assistant.contracts import (
    InputReceived,
    Manifest,
    Module,
    ModuleContext,
    ResponseReady,
    ShutdownRequested,
)

EXIT_WORDS = {"exit", "quit"}


class ConsoleIO(Module):
    manifest = Manifest(id="console_io")

    async def init(self, ctx: ModuleContext) -> None:
        self._ctx = ctx
        self._prompt = ctx.config.get("prompt", "> ")
        self._awaiting: set[str] = set()  # ids of inputs we sent and haven't seen a reply to
        ctx.subscribe(ResponseReady, self._on_response)

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        # A daemon thread, because a blocking input() call can't be cancelled
        # and must not keep the process alive after shutdown.
        threading.Thread(target=self._read_lines, args=(loop,), name="console-input", daemon=True).start()
        print(self._prompt, end="", flush=True)

    def _read_lines(self, loop: asyncio.AbstractEventLoop) -> None:
        while True:
            try:
                line = input().strip()
            except EOFError:
                line = "exit"
            try:
                loop.call_soon_threadsafe(self._submit, line)
            except RuntimeError:  # the event loop has already closed
                return
            if line in EXIT_WORDS:
                return

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
        # Only print replies to our own inputs, not those from other clients.
        if event.correlation_id not in self._awaiting:
            return
        self._awaiting.discard(event.correlation_id)
        print(event.text)
        print(self._prompt, end="", flush=True)
