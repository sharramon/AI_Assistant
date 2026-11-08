"""The HTML viewer's handle in the app.

The viewer is its own app (`src/html_viewer`, run alone with `python -m html_viewer`); it
doesn't import the assistant. The two talk over its local HTTP API (this module → viewer)
and its event stream (viewer → this module). This module starts it on the first show
request and stops it when the app stops; a viewer you started yourself, it connects to and
leaves running. It:
- has a menu: `viewer.open` (open an HTML file in a tab), `viewer.highlight` (open it and
  highlight a quoted part), and `viewer.tabs`; the core offers it through `InvokeTool`
- relays the viewer's open tabs and highlights as `ViewerTabsChanged`, for the Talker
- relays your snips as `ViewerClip`, with the image copied into the launch's log folder
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

from app_kit import CompanionHandover
from app_kit.window import window_profile
from assistant.contracts import (
    Manifest,
    Menu,
    ModuleContext,
    ModuleProtocol,
    Result,
    ViewerClip,
    ViewerTabsChanged,
)

DEFAULT_PROFILE = window_profile("html_viewer")

menu = Menu()
_PATH = {"type": "string", "minLength": 1}


class HtmlViewerModule(ModuleProtocol):
    manifest = Manifest(
        id="html_viewer",
        description="View, edit, highlight and snip HTML; launches the viewer app",
        publishes=(ViewerTabsChanged, ViewerClip,),
    )
    menu = menu

    async def init(self, ctx: ModuleContext) -> None:
        self._ctx = ctx
        host = ctx.config.get("host", "127.0.0.1")
        port = int(ctx.config.get("port", 8766))
        profile = Path(ctx.config.get("window_profile", DEFAULT_PROFILE)).resolve()
        args = ["--host", host, "--port", str(port), "--window", ctx.config.get("window", "app"),
                "--profile", str(profile)]
        for folder in ctx.config.get("generated", []):
            args += ["--generated", str(Path(folder).resolve())]
        # A reload hands over the running viewer (its tabs stay), if it would be launched the same way.
        # The app starts the viewer when needed and stops it only if it started it.
        self._companion = CompanionHandover(
            ctx.handover, "html_viewer", host, port, args=args, label="viewer", log=ctx.log,
            ping="/api/ping", start_timeout=ctx.config.get("start_timeout", 10.0),
        )  # fmt: skip
        self._app = self._companion.app
        self._relay_task: asyncio.Task | None = None

    async def start(self) -> None:
        # Nothing to launch yet. A viewer you started yourself: follow its tabs from now on.
        if await self._ping():
            self._follow()

    async def stop(self) -> None:
        if self._relay_task:
            self._relay_task.cancel()
            await asyncio.gather(self._relay_task, return_exceptions=True)
        await self._companion.stop()

    def export_state(self) -> dict | None:
        """For a reload: the viewer app (an `app_kit` object) goes to the new copy, so its window
        and tabs stay, unless the viewer's own code changed: then `stop` quits it and the new copy
        launches the new code when it next shows a page (`CompanionHandover`)."""
        return self._companion.export()

    @menu.item("viewer.open", "Open an HTML file in the HTML viewer (switches to its tab if it's open); "
                              "front: also bring the viewer window to the front (for the user's clicks)",
               {"path": _PATH, "front": {"type": "boolean"}}, required=["path"])
    async def show(self, path: str, front: bool = False) -> Result:
        """Open `path` in a viewer tab, starting the viewer first if it isn't running.

        `front`: bring the viewer window to the front (your click), not for agents' own pages.
        """
        file = Path(path.strip().strip("\"'")).expanduser().resolve()
        if not file.is_file():
            return Result.invalid_arguments(f"No such file: {file}")
        try:
            await self._ensure_running()
            answer = await self._call("POST", "/api/open", {"path": str(file), "front": front})
        except (OSError, TimeoutError) as exc:
            return Result.failed(f"The HTML viewer isn't available: {exc}", retryable=True)
        return Result.ok(answer) if answer.get("ok") else Result.failed(answer.get("error") or "unknown error")

    @menu.item("viewer.highlight", "Open an HTML file in the viewer and highlight a short quote of its text, "
                                   "optionally only in the section under a heading; scrolls to it",
               {"path": _PATH, "text": {"type": "string", "minLength": 1}, "heading": {"type": "string"},
                "front": {"type": "boolean"}}, required=["path", "text"])
    async def highlight(self, path: str, text: str, heading: str | None = None, front: bool = False) -> Result:
        """Open `path` and highlight the quoted `text` (in `heading`'s section, if given).

        Ok with `found` false when the text isn't on the page: the file is open, nothing marked.
        """
        file = Path(path.strip().strip("\"'")).expanduser().resolve()
        if not file.is_file():
            return Result.invalid_arguments(f"No such file: {file}")
        try:
            await self._ensure_running()
            answer = await self._call(
                "POST", "/api/highlight", {"path": str(file), "text": text, "heading": heading, "front": front}
            )
        except (OSError, TimeoutError) as exc:
            return Result.failed(f"The HTML viewer isn't available: {exc}", retryable=True)
        if not answer.get("ok"):
            return Result.failed(answer.get("error") or "unknown error")
        return Result.ok({k: answer[k] for k in ("tab", "path", "found", "matches") if k in answer})

    @menu.item("viewer.tabs", "The files open in the HTML viewer, and their highlights")
    async def tabs(self) -> Result:
        if not await self._ping():
            return Result.ok([])
        try:
            answer = await self._call("GET", "/api/tabs")
        except (OSError, TimeoutError) as exc:  # it went away since the ping
            return Result.failed(f"The HTML viewer isn't available: {exc}", retryable=True)
        return Result.ok([
            {"path": t["path"], "active": t["active"], "unsaved": t["dirty"],
             "highlights": [h["text"] for h in t.get("highlights", [])]}
            for t in answer["tabs"]
        ])


    # --- the viewer process ---

    async def _ensure_running(self) -> None:
        await self._app.ensure_running()
        self._follow()

    async def _ping(self) -> bool:
        return await self._app.ping()

    async def _call(self, method: str, path: str, body: Any = None) -> dict[str, Any]:
        return await self._app.call(method, path, body)

    # --- tabs → ViewerTabsChanged ---

    def _follow(self) -> None:
        if self._relay_task is None or self._relay_task.done():
            self._relay_task = asyncio.create_task(self._relay(), name="html_viewer:relay")

    async def _relay(self) -> None:
        """Read the viewer's event stream; publish each change of its tabs, and each snip."""
        last = None
        try:
            async for item in self._app.events("/api/events"):
                if item.get("kind") == "snip":
                    await self._relay_snip(item)
                    continue
                if item.get("kind") != "tabs":
                    continue
                active = next((t["path"] for t in item["tabs"] if t["active"]), None)
                marks = tuple((t["path"], h["text"]) for t in item["tabs"] for h in t.get("highlights", []))
                tabs = (tuple(t["path"] for t in item["tabs"]), active, marks)
                if tabs != last:
                    last = tabs
                    self._ctx.publish(ViewerTabsChanged(tabs=tabs[0], active=active, highlights=marks))
        except (OSError, ValueError):
            pass

    async def _relay_snip(self, item: dict[str, Any]) -> None:
        # The viewer's copy is temporary; keep one with this launch's logs.
        folder = self._ctx.logs.folder() / "snips"
        image = folder / Path(item["path"]).name

        def keep() -> None:
            folder.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item["path"], image)

        try:
            await asyncio.to_thread(keep)
        except OSError as exc:
            self._ctx.log.warning("Couldn't keep the snip %s: %s", item["path"], exc)
            image = Path(item["path"])
        self._ctx.publish(ViewerClip(id=item["id"], image_path=str(image), file=item["file"], heading=item.get("heading")))
