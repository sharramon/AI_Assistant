"""One long-lived `claude -p` process, spoken to in stream-json lines over stdin and stdout."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any
from uuid import uuid4

# Stream-json lines can be large (whole file contents in tool calls).
_LINE_LIMIT = 16 * 1024 * 1024


def claude_command(
    *,
    model: str | None = None,
    tools: str = "",
    permission_mode: str | None = None,
    system_prompt: str | None = None,
    program: Sequence[str] = ("claude",),
) -> list[str]:
    """The command line for a stream-json `claude -p` session.

    `--strict-mcp-config` is always set: `--tools` alone still loads your
    claude.ai MCP connectors. `program` is replaceable so tests can run a fake.
    """
    command = [
        *program, "-p",
        "--input-format", "stream-json",
        "--output-format", "stream-json",
        "--verbose",
        "--strict-mcp-config",
        "--tools", tools,
    ]
    if model:
        command += ["--model", model]
    if permission_mode:
        command += ["--permission-mode", permission_mode]
    if system_prompt:
        command += ["--append-system-prompt", system_prompt]
    return command


class ClaudeSession:
    """Runs one `claude` process and knows nothing about tasks or agents.

    Every JSON line the process writes goes to `on_event`, in order. When the
    process ends on its own, `on_event` gets `{"type": "exit", "returncode": n}`.
    `on_event` may be set after construction, by whatever part consumes the
    events. `working` is true from `send` until the turn's `result` line.
    """

    def __init__(
        self,
        command: Sequence[str],
        cwd: str | Path | None = None,
        log: logging.Logger | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ):
        self._command = list(command)
        self.on_event = on_event
        self._cwd = cwd
        self._log = log or logging.getLogger(__name__)
        self._proc: asyncio.subprocess.Process | None = None
        self._tasks: list[asyncio.Task] = []
        self._closing = False
        self.working = False

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def start(self) -> None:
        """Launch the process. Raises FileNotFoundError if the program isn't installed."""
        if self.running:
            return
        # Resolve through PATH ourselves so Windows also finds .cmd/.exe shims.
        program = shutil.which(self._command[0]) or self._command[0]
        self._closing = False
        self.working = False
        self._proc = await asyncio.create_subprocess_exec(
            program, *self._command[1:],
            cwd=self._cwd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=_LINE_LIMIT,
        )
        self._tasks = [
            asyncio.create_task(self._read_stdout(self._proc), name="claude-session:stdout"),
            asyncio.create_task(self._read_stderr(self._proc), name="claude-session:stderr"),
        ]
        self._log.info("Started claude (pid %s)", self._proc.pid)

    async def send(self, text: str) -> None:
        """Send a user message, starting a turn. Raises RuntimeError if the process isn't running."""
        await self._write({"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": text}]}})
        self.working = True

    async def interrupt(self) -> None:
        """Interrupt the current turn, like Esc. The turn still ends with a `result` (an error)."""
        await self._write({
            "type": "control_request",
            "request_id": f"req_{uuid4().hex[:12]}",
            "request": {"subtype": "interrupt"},
        })

    async def close(self, timeout: float = 3.0) -> None:
        """Close stdin and wait for the process to exit; kill it if it doesn't."""
        proc, self._proc = self._proc, None
        self._closing = True
        self.working = False
        if proc is not None and proc.returncode is None:
            if proc.stdin and not proc.stdin.is_closing():
                proc.stdin.close()
            try:
                await asyncio.wait_for(proc.wait(), timeout)
            except TimeoutError:
                self._log.warning("claude (pid %s) didn't exit; killing it", proc.pid)
                proc.kill()
                await proc.wait()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    async def _write(self, obj: dict[str, Any]) -> None:
        if not self.running or self._proc.stdin is None:
            raise RuntimeError("The claude process is not running")
        self._proc.stdin.write((json.dumps(obj) + "\n").encode())
        await self._proc.stdin.drain()

    async def _read_stdout(self, proc: asyncio.subprocess.Process) -> None:
        assert proc.stdout is not None
        while raw := await proc.stdout.readline():
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                self._log.debug("Non-JSON line from claude: %r", raw[:200])
                continue
            if event.get("type") == "result":
                self.working = False
            self._emit(event)
        returncode = await proc.wait()
        self.working = False
        if not self._closing:
            self._log.warning("claude (pid %s) exited with %s", proc.pid, returncode)
            self._emit({"type": "exit", "returncode": returncode})

    async def _read_stderr(self, proc: asyncio.subprocess.Process) -> None:
        assert proc.stderr is not None
        while line := await proc.stderr.readline():
            self._log.warning("claude stderr: %s", line.decode(errors="replace").rstrip())

    def _emit(self, event: dict[str, Any]) -> None:
        if self.on_event is None:
            return
        try:
            self.on_event(event)
        except Exception:
            self._log.exception("on_event raised for a %s event", event.get("type"))
