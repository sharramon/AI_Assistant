"""Launch and talk to a local companion app (its own package, run with `python -m <module>`).

The convention it relies on (docs/architecture/reusable-parts.md, companion app checklist):
a ping path answering `{"app": "<name>", ...}`, a JSON HTTP API, and a JSON `POST` that quits it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import urllib.error
import urllib.request
from collections.abc import AsyncIterator, Sequence
from typing import Any


class CompanionApp:
    """One companion app: ping, launch if needed, call, read its event stream, quit if we launched it.

    `module` is the package to run (`python -m module`) and also the name its ping must answer
    with, unless `name` says otherwise.
    """

    def __init__(
        self,
        module: str,
        host: str,
        port: int,
        *,
        ping: str,
        args: Sequence[str] = (),
        start_timeout: float = 20.0,
        quit: str = "/api/quit",
        name: str | None = None,
        log: logging.Logger | Any | None = None,
    ) -> None:
        self.module = module
        self.name = name or module
        self.host = host
        self.port = port
        self.url = f"http://{host}:{port}"
        self.args = list(args)
        self._ping_path = ping
        self._quit_path = quit
        self._start_timeout = start_timeout
        self._log = log or logging.getLogger(__name__)
        self._proc: asyncio.subprocess.Process | None = None  # set only when we launched it
        self._starting = asyncio.Lock()

    @property
    def launched(self) -> bool:
        """Whether this object started the process (and it hasn't been stopped)."""
        return self._proc is not None

    @property
    def process(self) -> asyncio.subprocess.Process | None:
        """The process this object launched, if any."""
        return self._proc

    async def ping(self) -> bool:
        """Whether the app answers its ping with its own name."""
        try:
            return (await self.call("GET", self._ping_path, timeout=1)).get("app") == self.name
        except (OSError, ValueError, TimeoutError):
            return False

    async def ensure_running(self) -> bool:
        """Launch the app unless it already answers; wait until it does.

        Returns whether it launched it now. Raises `OSError` if the process exits early,
        `TimeoutError` if it doesn't answer within `start_timeout`.
        """
        async with self._starting:
            if await self.ping():
                return False
            kwargs: dict[str, Any] = {}
            if sys.platform == "win32":
                import subprocess

                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            self._proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", self.module, *self.args,
                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL, **kwargs,
            )
            self._log.info("Started %s at %s", self.name, self.url)
            async with asyncio.timeout(self._start_timeout):
                while not await self.ping():
                    if self._proc.returncode is not None:
                        raise OSError(f"{self.name} exited with code {self._proc.returncode}")
                    await asyncio.sleep(0.1)
            return True

    async def call(self, method: str, path: str, body: Any = None, *, timeout: float = 10) -> dict[str, Any]:
        """A JSON request to its HTTP API. Error responses are read as JSON too."""
        def call() -> dict[str, Any]:
            data = None if body is None else json.dumps(body).encode()
            request = urllib.request.Request(self.url + path, data=data, method=method)
            if data is not None:
                request.add_header("Content-Type", "application/json")
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    return json.loads(response.read() or b"{}")
            except urllib.error.HTTPError as exc:
                return json.loads(exc.read() or b"{}")

        return await asyncio.to_thread(call)

    async def events(self, path: str) -> AsyncIterator[dict[str, Any]]:
        """Read its event stream (server-sent events), one JSON event at a time, until it ends.

        Raises `OSError` if it can't connect, `ValueError` for an event that isn't JSON.
        """
        reader, writer = await asyncio.open_connection(self.host, self.port)
        try:
            writer.write(f"GET {path} HTTP/1.1\r\nHost: {self.host}:{self.port}\r\n\r\n".encode())
            await writer.drain()
            while line := await reader.readline():
                if line.startswith(b"data: "):
                    yield json.loads(line[6:])
        finally:
            writer.close()

    async def stop(self) -> None:
        """Quit it, only if this object launched it: `POST` quit, wait 5 s, then kill."""
        proc, self._proc = self._proc, None
        if proc is None or proc.returncode is not None:
            return
        try:
            await self.call("POST", self._quit_path, {})
            await asyncio.wait_for(proc.wait(), 5)
        except (OSError, ValueError, TimeoutError):
            proc.kill()
            await proc.wait()
