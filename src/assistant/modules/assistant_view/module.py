"""Terminal 2: a view-only console window showing what the agents are doing.

Opens a new console running `viewer.py` and writes text lines to its stdin.
Closing the window only stops the view; deactivating the module closes it.
Windows only for now (a new console window per process).
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys

from assistant.contracts import (
    AgentActivity,
    AgentStateChanged,
    Manifest,
    Module,
    ModuleContext,
    TaskUpdated,
)


class AssistantViewModule(Module):
    manifest = Manifest(id="assistant_view")

    async def init(self, ctx: ModuleContext) -> None:
        self._ctx = ctx
        self._proc: asyncio.subprocess.Process | None = None
        ctx.subscribe(AgentActivity, self._on_activity)
        ctx.subscribe(AgentStateChanged, self._on_state)
        ctx.subscribe(TaskUpdated, self._on_task)

    async def start(self) -> None:
        if os.name != "nt":
            raise RuntimeError("assistant_view needs Windows (it opens a new console window)")
        self._proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "assistant.modules.assistant_view.viewer",
            stdin=asyncio.subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )

    async def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None or proc.returncode is not None:
            return
        if proc.stdin:
            proc.stdin.close()
        try:
            await asyncio.wait_for(proc.wait(), 2)
        except TimeoutError:
            proc.kill()
            await proc.wait()

    async def _on_activity(self, event: AgentActivity) -> None:
        await self._show(f"[{event.agent_id}] {event.text}")

    async def _on_state(self, event: AgentStateChanged) -> None:
        state = "working" if event.working else "busy, waiting" if event.busy else "idle"
        await self._show(f"--- {event.agent_id}: {state}")

    async def _on_task(self, event: TaskUpdated) -> None:
        if event.kind is not None or event.state.is_final or event.text == "started":
            text = f": {event.text}" if event.text else ""
            await self._show(f"=== task {event.task_id} {event.kind or event.state}{text}")

    async def _show(self, text: str) -> None:
        if self._proc is None or self._proc.stdin is None or self._proc.stdin.is_closing():
            return
        try:
            self._proc.stdin.write((text.replace("\r", "") + "\n\n").encode("utf-8"))
            await self._proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            self._ctx.log.info("Terminal 2 was closed")
            self._proc.stdin.close()
