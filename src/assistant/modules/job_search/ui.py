"""The job UI (the job project's `Recruiters/scripts/job_ui.py`, what `job_ui.cmd` runs): a local
server at 127.0.0.1:8781 with the Tracker, Job stack, Live search and Keywords pages.

`JobUi` launches it the way the cv module launches the CV Tool: `CompanionHandover` from
`app_kit`, kept across a reload. The job UI isn't one of our companion apps (no JSON ping, no
quit call, its own project), so it runs by its command line (`job_ui.cmd`'s: JobRadar's Python,
`-I`, the script) with `--no-browser`, its ping is any 200 answer from `/tracker`, and the module's
stop ends the server only if it launched it. Its window is opened here, on its own Edge profile
(`window_profile("job_ui")`), whether it was launched now or already running; each open first
closes the window already on that profile (`close_app_windows`: that window and nothing else),
so there's only ever one (the user's decision, 2026-11-10).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from app_kit import CompanionHandover
from app_kit.window import EDGE, close_app_windows, open_app_window, window_profile

HOST = "127.0.0.1"  # job_ui.py serves on this address only
PORT = 8781
PAGE = "/tracker"


def ui_settings(section: Any, workspace: str, python: str) -> dict[str, Any]:
    """The checked `[ui]` table: `script` (default `<workspace>/Recruiters/scripts/job_ui.py`),
    `python` (default the module's `python`, JobRadar's, as `job_ui.cmd` uses), `port` (8781),
    `page` (`/tracker`). ValueError if one is wrong."""
    if not isinstance(section, dict):
        raise ValueError(f"job_search: [ui] must be a table, not {section!r}")
    script = str(section.get("script") or (Path(workspace) / "Recruiters" / "scripts" / "job_ui.py" if workspace else ""))
    python = str(section.get("python") or python)  # either may be empty: job.open_ui says so, the agent still runs
    port = section.get("port", PORT)
    if not (isinstance(port, int) and not isinstance(port, bool) and 1 <= port <= 65535):
        raise ValueError(f"job_search: ui.port must be 1 to 65535, not {port!r}")
    page = str(section.get("page", PAGE))
    if not page.startswith("/"):
        raise ValueError(f"job_search: ui.page must start with /, not {page!r}")
    return {"script": script, "python": python, "port": port, "page": page}


class JobUi:
    """The job UI for the module: launched by `open` if it isn't running, handed to the next copy on
    a reload (`export`), ended at the module's stop if this module launched it."""

    def __init__(self, handover: Any, settings: dict[str, Any], log: Any = None) -> None:
        self._settings = settings
        self._log = log
        self._companion = CompanionHandover(
            handover, "job_ui", HOST, settings["port"], args=["--port", str(settings["port"]), "--no-browser"],
            command=[settings["python"], "-I", settings["script"]], ping=settings["page"], plain_ping=True,
            quit=None, label="job UI", log=log,
        )  # fmt: skip

    @property
    def url(self) -> str:
        return self._companion.app.url + self._settings["page"]

    async def running(self) -> bool:
        """Whether the job UI answers now (no launch)."""
        return await self._companion.app.ping()

    async def open(self) -> dict[str, Any]:
        """Start the job UI if it isn't answering, close its window if one is open, then open a
        fresh one on the page: one window, every time. OSError if the script is missing or exits
        early, TimeoutError if it doesn't answer."""
        if not any(Path(edge).is_file() for edge in EDGE):  # never a browser tab: its own window only
            raise OSError("Microsoft Edge isn't installed, and the job UI opens only in its own app window")
        if not self._settings["python"]:
            raise OSError("no Python for the job UI: set ui.python (or python) in [modules.job_search]")
        if not self._settings["script"] or not Path(self._settings["script"]).is_file():
            raise OSError(f"the job UI script {self._settings['script']} isn't there")
        launched = await self._companion.app.ensure_running()
        logs = {"log": self._log} if self._log is not None else {}
        profile = window_profile("job_ui")
        await asyncio.to_thread(close_app_windows, profile, **logs)  # none open: nothing to close
        window = open_app_window(self.url, profile, size="1400,950", **logs)
        return {"url": self.url, "launched": launched, "window": window is not None}

    def export(self) -> dict[str, Any] | None:
        return self._companion.export()

    async def stop(self) -> None:
        await self._companion.stop()
