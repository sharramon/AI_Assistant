"""Launch and talk to a local companion app (its own package, run with `python -m <module>`).

The convention it relies on (docs/architecture/reusable-parts.md, companion app checklist):
a ping path answering `{"app": "<name>", ...}`, a JSON HTTP API, and a JSON `POST` that quits it.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Any


def source_stamp(module: str) -> tuple[int, int] | None:
    """A fingerprint of `module`'s source: (newest `.py` mtime in ns, how many `.py` files),
    found without importing it. None if it can't be found."""
    try:
        spec = importlib.util.find_spec(module)
    except (ImportError, ValueError):
        return None
    if spec is None:
        return None
    if spec.submodule_search_locations:
        files = [f for folder in spec.submodule_search_locations for f in Path(folder).rglob("*.py")]
    else:
        files = [Path(spec.origin)] if spec.origin and spec.origin.endswith(".py") else []
    if not files:
        return None
    return max(f.stat().st_mtime_ns for f in files), len(files)


def package_root(module: str) -> Path | None:
    """The folder `module`'s top-level package is found in (on this process's import path), found
    without importing it: `src/` for an app there, a module's `app/` folder for an app inside its
    module. None if it can't be found."""
    try:
        spec = importlib.util.find_spec(module.partition(".")[0])
    except (ImportError, ValueError):
        return None
    if spec is None:
        return None
    if spec.submodule_search_locations:
        folders = list(spec.submodule_search_locations)
        return Path(folders[0]).parent if folders else None
    return Path(spec.origin).parent if spec.origin else None


def launch_env(module: str, base: dict[str, str] | None = None) -> dict[str, str]:
    """The environment to run `python -m module` with: `base` (default this process's) with the
    folder its package is found in (`package_root`) put first on `PYTHONPATH`, the rest kept, so
    the child imports the same package from the same place."""
    env = dict(os.environ if base is None else base)
    root = package_root(module)
    if root is not None:
        rest = [p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p and Path(p) != root]
        env["PYTHONPATH"] = os.pathsep.join([str(root), *rest])
    return env


class CompanionApp:
    """One companion app: ping, launch if needed, call, read its event stream, quit if we launched it.

    `module` is the package to run (`python -m module`) and also the name its ping must answer
    with, unless `name` says otherwise. `code_changed()` says whether its source changed since
    this object started using it, so a reloading module can quit it (`stop(adopted=True)`) and
    the next start runs the new code.

    An app outside the convention (a script of another project, like the job UI): `command` is its
    whole command line instead of `python -m module` (`args` still follow it; `code_changed()` is
    then always False), `plain_ping=True` takes any 200 answer to the ping path as alive (no
    `{"app": ...}` check), and `quit=None` means it has no quit call: `stop` ends the process.
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
        quit: str | None = "/api/quit",
        name: str | None = None,
        log: logging.Logger | Any | None = None,
        command: Sequence[str] | None = None,
        plain_ping: bool = False,
    ) -> None:
        self.module = module
        self.name = name or module
        self.host = host
        self.port = port
        self.url = f"http://{host}:{port}"
        self.args = list(args)
        self.command = list(command) if command else None
        self._plain_ping = plain_ping
        self._ping_path = ping
        self._quit_path = quit
        self._start_timeout = start_timeout
        self._log = log or logging.getLogger(__name__)
        self._proc: asyncio.subprocess.Process | None = None  # set only when we launched it
        self._starting = asyncio.Lock()
        self._stamp: tuple[int, int] | None = None  # its source when we launched or first used it
        self.last_answer: dict[str, Any] = {}  # the last ping's answer ({} if it didn't answer)

    @property
    def launched(self) -> bool:
        """Whether this object started the process (and it hasn't been stopped)."""
        return self._proc is not None

    @property
    def process(self) -> asyncio.subprocess.Process | None:
        """The process this object launched, if any."""
        return self._proc

    async def ping(self) -> bool:
        """Whether the app answers its ping with its own name. Its answer stays in `last_answer`
        (a ping path that reports more, like the voice service's `/health`, needs no second call).
        With `plain_ping`, any 200 answer counts, and `last_answer` is `{"status": 200}`."""
        if self._plain_ping:
            ok = await asyncio.to_thread(self._answers_200)
            self.last_answer = {"status": 200} if ok else {}
            return ok
        try:
            answer = await self.call("GET", self._ping_path, timeout=1)
        except (OSError, ValueError, TimeoutError):
            answer = {}
        ok = answer.get("app") == self.name
        self.last_answer = answer if ok else {}
        return ok

    def _answers_200(self) -> bool:
        try:
            with urllib.request.urlopen(self.url + self._ping_path, timeout=1) as response:
                return response.status == 200
        except (OSError, ValueError):
            return False

    def _source(self) -> tuple[int, int] | None:
        return None if self.command else source_stamp(self.module)

    async def ensure_running(self) -> bool:
        """Launch the app unless it already answers; wait until it does.

        Returns whether it launched it now; `last_answer` holds its ping's answer either way.
        Raises `OSError` if the process exits early,
        `TimeoutError` if it doesn't answer within `start_timeout`.
        """
        async with self._starting:
            if await self.ping():
                if self._stamp is None:  # adopted: our best guess at the code it runs
                    self._stamp = self._source()
                return False
            self._stamp = self._source()
            kwargs: dict[str, Any] = {}
            if sys.platform == "win32":
                import subprocess

                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            program = self.command or [sys.executable, "-m", self.module]
            if not self.command:  # the folder its package is found in, first on PYTHONPATH
                kwargs["env"] = launch_env(self.module)
            self._proc = await asyncio.create_subprocess_exec(
                *program, *self.args,
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

    def code_changed(self) -> bool:
        """Whether its source changed since this object launched it (or first found it running)."""
        return self._stamp is not None and self._source() != self._stamp

    async def stop(self, adopted: bool = False) -> None:
        """Quit it if this object launched it: `POST` quit, wait 5 s, then kill. With
        `adopted=True`, also quit one it found already running (`POST` quit, then wait up to
        5 s for its ping to stop answering). With no quit call (`quit=None`): end the process it
        launched at once, and leave one it found running."""
        proc, self._proc = self._proc, None
        self._stamp = None
        if self._quit_path is None:
            if proc is not None and proc.returncode is None:
                proc.kill()
                await proc.wait()
            return
        if proc is None and adopted and await self.ping():
            try:
                await self.call("POST", self._quit_path, {})
                async with asyncio.timeout(5):
                    while await self.ping():
                        await asyncio.sleep(0.1)
            except (OSError, ValueError, TimeoutError):
                self._log.warning("%s at %s didn't quit", self.name, self.url)
            return
        if proc is None or proc.returncode is not None:
            return
        try:
            await self.call("POST", self._quit_path, {})
            await asyncio.wait_for(proc.wait(), 5)
        except (OSError, ValueError, TimeoutError):
            proc.kill()
            await proc.wait()


class CompanionHandover:
    """A thin module's companion app, kept across the module's reload.

    The old copy's `export()` hands the running `CompanionApp` to the new copy (its window, tabs
    or loaded model stay), unless the app's own code changed: then it returns None and `stop()`
    quits the app (even one it found running), so the new copy launches the new code. The new
    copy takes it over only if it would launch it the same way (same module, host, port, args);
    otherwise it makes its own. `app` is the `CompanionApp` to use.
    """

    def __init__(
        self, handover: Any, module: str, host: str, port: int, *, args: Sequence[str] = (),
        label: str | None = None, log: logging.Logger | Any | None = None, **app_kwargs: Any,
    ) -> None:  # fmt: skip
        """`handover`: the module's `ctx.handover`; `label`: how the logs name the app;
        `app_kwargs`: the rest of `CompanionApp`'s arguments (`ping`, `quit`, `start_timeout`)."""
        self._log = log or logging.getLogger(__name__)
        self._label = label or module
        self.key = (module, host, port, tuple(args), tuple(app_kwargs.get("command") or ()))
        self._handed_over = False
        self._restart = False  # the app's code changed: quit it at stop
        given = handover if isinstance(handover, dict) else {}
        if given.get("app_key") == self.key and given.get("app") is not None:
            self.app: CompanionApp = given["app"]
            self._log.info("Kept the running %s from before the reload", self._label)
        else:
            self.app = CompanionApp(module, host, port, args=args, log=log, **app_kwargs)

    def export(self) -> dict[str, Any] | None:
        """For the module's `export_state`: the app for the new copy, or None if its code changed."""
        if self.app.code_changed():
            self._log.info("The %s's code changed; it restarts with the new code", self._label)
            self._restart = True
            return None
        self._handed_over = True
        return {"app": self.app, "app_key": self.key}

    async def stop(self) -> None:
        """For the module's `stop`: quit the app unless it was handed over (`CompanionApp.stop`)."""
        if not self._handed_over:
            await self.app.stop(adopted=self._restart)
