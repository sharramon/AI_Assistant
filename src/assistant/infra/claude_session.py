"""One long-lived `claude -p` process, spoken to in stream-json lines over stdin and stdout."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import shutil
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO
from uuid import uuid4

from assistant.infra.log import LogSink
from assistant.infra.usage_meter import USAGE_FIELDS, UsageMeter

__all__ = ["USAGE_FIELDS", "ClaudeSession", "claude_command", "path_rule"]

# Stream-json lines can be large (whole file contents in tool calls).
_LINE_LIMIT = 16 * 1024 * 1024


def claude_command(
    *,
    model: str | None = None,
    tools: str = "",
    permission_mode: str | None = None,
    allowed: Sequence[str] = (),
    disallowed: Sequence[str] = (),
    permission_prompts: bool = False,
    system_prompt: str | None = None,
    program: Sequence[str] = ("claude",),
    mcp_config: dict | None = None,
    chrome: bool = False,
) -> list[str]:
    """The command line for a stream-json `claude -p` session.

    `chrome` adds `--chrome`, the Claude in Chrome tools on your logged-in browser (the job agent).

    `--strict-mcp-config` is always set: `--tools` alone still loads your
    claude.ai MCP connectors. `allowed` are permission rules such as
    `Read(//c/repo/**)` (see `path_rule`). `disallowed` rules (e.g.
    `PowerShell(git push *)`) are refused outright, even under
    `bypassPermissions` (checked against the real `claude`, 2026-11-02). With
    `permission_prompts`, anything the rules don't allow arrives as a
    `can_use_tool` control request instead of being refused; answer it with
    `ClaudeSession.answer_permission`. `program` is replaceable so tests can run a fake.
    `mcp_config` (e.g. the module door's, `IModuleDoor.mcp_config()`) becomes `--mcp-config`;
    with `--strict-mcp-config` it's the only MCP server the session sees.
    """
    command = [
        *program, "-p",
        "--input-format", "stream-json",
        "--output-format", "stream-json",
        "--verbose",
        "--strict-mcp-config",
        "--tools", tools,
    ]
    if mcp_config:
        command += ["--mcp-config", json.dumps(mcp_config)]
    if chrome:
        command += ["--chrome"]
    if model:
        command += ["--model", model]
    if permission_mode:
        command += ["--permission-mode", permission_mode]
    if allowed:
        command += ["--allowedTools", ",".join(allowed)]
    if disallowed:
        command += ["--disallowedTools", *disallowed]
    if permission_prompts:
        command += ["--permission-prompt-tool", "stdio"]
    if system_prompt:
        command += ["--append-system-prompt", system_prompt]
    return command


def path_rule(tool: str, folder: str | Path) -> str:
    """A permission rule for everything under `folder`, e.g. `Edit(//c/repo/docs/**)`.

    `claude` matches absolute paths in POSIX form with a leading `//`; on
    Windows `C:\\repo` becomes `//c/repo`. `Read` rules cover Read, Glob, and
    Grep; `Edit` rules cover Edit and Write.
    """
    posix = Path(folder).resolve().as_posix()
    if len(posix) > 1 and posix[1] == ":":  # Windows drive: C:/x -> /c/x
        posix = f"/{posix[0].lower()}{posix[2:]}"
    return f"{tool}(/{posix.rstrip('/')}/**)"


class ClaudeSession:
    """Runs one `claude` process and knows nothing about tasks or agents.

    `command` is the command line, or a callable returning it, called on every
    `start`, so each new process gets the settings of that moment (e.g. the
    permission mode). Every JSON line the process writes goes to `on_event`, in
    order. When the process ends on its own, `on_event` gets
    `{"type": "exit", "returncode": n}`.
    `on_event` may be set after construction, by whatever part consumes the
    events. `working` is true from `send` until the turn's `result` line.

    Its tokens are counted by a `UsageMeter` (`meter`), which sees each line before
    `on_event` does: `context_tokens` (the latest call's input size, 0 after `start`),
    `used` (every own call since construction, across restarts) and `subagents` read it.
    `id` is new for each `ClaudeSession` object (not each process), so a usage tally
    can tell a fresh session from a restarted process.

    With `transcript`, every line in and out (and stderr) is appended to that
    file as JSON lines: `{"t": time, "dir": "in" | "out" | "stderr", "msg": ...}`.
    `transcript` may also be a `LogSink` (from `LogSession.sink`), which holds the
    lines until the session's log folder exists.

    `env` adds variables to the process's environment (on top of this app's), e.g. so a
    Claude Code hook can tell this process apart from your own sessions.
    """

    def __init__(
        self,
        command: Sequence[str] | Callable[[], Sequence[str]],
        cwd: str | Path | None = None,
        log: logging.Logger | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
        transcript: str | Path | LogSink | None = None,
        env: Mapping[str, str] | None = None,
    ):
        self._command_source = command if callable(command) else list(command)
        self.on_event = on_event
        self._cwd = cwd
        self._env = dict(env) if env else None
        self._log = log or logging.getLogger(__name__)
        # A LogSink is written to as is; a path is opened on start and closed on close.
        self._transcript_path = Path(transcript) if isinstance(transcript, (str, Path)) and transcript else None
        self._transcript: TextIO | LogSink | None = transcript if isinstance(transcript, LogSink) else None
        self._proc: asyncio.subprocess.Process | None = None
        self._tasks: list[asyncio.Task] = []
        self._closing = False
        self.working = False
        self.meter = UsageMeter()
        self.id = uuid4().hex

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    @property
    def context_tokens(self) -> int:
        """The input size of the latest call (cached or not): what every further call resends."""
        return self.meter.context_tokens

    @property
    def used(self) -> dict[str, int]:
        """Tokens by kind (`input`, `cache_write`, `cache_read`, `output`), every call so far."""
        return self.meter.used

    @property
    def subagents(self) -> dict[str, dict[str, Any]]:
        """Each sub-agent's tokens since construction, by its `agentId` (`UsageMeter.subagents`)."""
        return self.meter.subagents

    async def start(self) -> None:
        """Launch the process. Raises FileNotFoundError if the program isn't installed."""
        if self.running:
            return
        source = self._command_source
        command = list(source() if callable(source) else source)
        # Resolve through PATH ourselves so Windows also finds .cmd/.exe shims.
        program = shutil.which(command[0]) or command[0]
        self._closing = False
        self.working = False
        self.meter.restarted()
        if self._transcript_path and self._transcript is None:
            self._transcript_path.parent.mkdir(parents=True, exist_ok=True)
            self._transcript = self._transcript_path.open("a", encoding="utf-8")
        self._proc = await asyncio.create_subprocess_exec(
            program, *command[1:],
            cwd=self._cwd,
            env={**os.environ, **self._env} if self._env else None,
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

    async def send(self, text: str, images: Sequence[str | Path] = ()) -> None:
        """Send a user message, starting a turn. Raises RuntimeError if the process isn't running.

        `images` are PNG or JPEG files sent with the text, so the model sees them. The
        transcript records their paths, not their data.
        """
        content: list[dict[str, Any]] = []
        logged: list[dict[str, Any]] = []
        for image in images:
            path = Path(image)
            kind = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
            data = base64.b64encode(path.read_bytes()).decode()
            content.append({"type": "image", "source": {"type": "base64", "media_type": kind, "data": data}})
            logged.append({"type": "image", "path": str(path)})
        content.append({"type": "text", "text": text})
        message = {"type": "user", "message": {"role": "user", "content": content}}
        await self._write(message, record={**message, "message": {"role": "user", "content": logged + content[-1:]}})
        self.working = True

    async def interrupt(self) -> None:
        """Interrupt the current turn, like Esc. The turn still ends with a `result` (an error)."""
        await self._control({"subtype": "interrupt"})

    async def set_permission_mode(self, mode: str) -> None:
        """Switch the running process's `--permission-mode` (e.g. to `acceptEdits`), as the
        Agent SDK does. Takes effect from the next tool use; the prompt stays as it started.
        Raises RuntimeError if the process isn't running."""
        await self._control({"subtype": "set_permission_mode", "mode": mode})

    async def answer_permission(
        self, request: dict[str, Any], allow: bool, message: str = "The user denied this."
    ) -> None:
        """Answer a `can_use_tool` control request (the whole event, as passed to `on_event`)."""
        if allow:
            decision = {"behavior": "allow", "updatedInput": request["request"].get("input", {})}
        else:
            decision = {"behavior": "deny", "message": message}
        await self._write({
            "type": "control_response",
            "response": {"subtype": "success", "request_id": request["request_id"], "response": decision},
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
        # Let the readers reach the end of the pipes, so the process's pipes close now and
        # not at garbage collection (a restart would leak them otherwise); cancel any that hang.
        if self._tasks:
            await asyncio.wait(self._tasks, timeout=1.0)
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        if self._transcript_path and self._transcript:
            self._transcript.close()
            self._transcript = None

    async def _control(self, request: dict[str, Any]) -> None:
        await self._write({"type": "control_request", "request_id": f"req_{uuid4().hex[:12]}", "request": request})

    async def _write(self, obj: dict[str, Any], record: dict[str, Any] | None = None) -> None:
        if not self.running or self._proc.stdin is None:
            raise RuntimeError("The claude process is not running")
        self._record("in", record or obj)
        self._proc.stdin.write((json.dumps(obj) + "\n").encode())
        await self._proc.stdin.drain()

    def _record(self, direction: str, msg: Any) -> None:
        if self._transcript:
            line = {"t": datetime.now().isoformat(timespec="milliseconds"), "dir": direction, "msg": msg}
            self._transcript.write(json.dumps(line, ensure_ascii=False) + "\n")
            if self._transcript_path:
                self._transcript.flush()  # a LogSink flushes itself

    async def _read_stdout(self, proc: asyncio.subprocess.Process) -> None:
        assert proc.stdout is not None
        while raw := await proc.stdout.readline():
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                self._log.debug("Non-JSON line from claude: %r", raw[:200])
                continue
            self._record("out", event)
            if self._closing:  # leftovers while closing: logged, not acted on
                continue
            if event.get("type") == "result":
                self.working = False
            self.meter.line(event)
            self._emit(event)
        returncode = await proc.wait()
        self.working = False
        if not self._closing:
            self._log.warning("claude (pid %s) exited with %s", proc.pid, returncode)
            self._emit({"type": "exit", "returncode": returncode})

    async def _read_stderr(self, proc: asyncio.subprocess.Process) -> None:
        assert proc.stderr is not None
        while line := await proc.stderr.readline():
            text = line.decode(errors="replace").rstrip()
            self._record("stderr", text)
            self._log.warning("claude stderr: %s", text)

    def _emit(self, event: dict[str, Any]) -> None:
        if self.on_event is None:
            return
        try:
            self.on_event(event)
        except Exception:
            self._log.exception("on_event raised for a %s event", event.get("type"))
