"""The HTML viewer's handle in the app.

The viewer is its own app (`src/html_viewer`, run alone with `python -m html_viewer`); it
doesn't import the assistant. The two talk over its local HTTP API (this module → viewer)
and its event stream (viewer → this module). This module starts it on the first show
request and stops it when the app stops; a viewer you started yourself, it connects to and
leaves running. It:
- offers the tools `viewer.open` (open an HTML file in a tab), `viewer.highlight` (open it
  and highlight a quoted part), and `viewer.tabs`
- relays the viewer's open tabs and highlights as `ViewerTabsChanged`, for the Talker
- opens the files the Main Assistant names with `<<SHOW: path>>`, or highlights with
  `<<SHOW: path | "quoted text" | heading>>` (it can't call app tools)
- relays your snips as `ViewerClip`, with the image copied into the launch's log folder
"""

from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path
from typing import Any

from app_kit import CompanionApp
from assistant.contracts import (
    AgentActivity,
    IToolProvider,
    Manifest,
    ModuleContext,
    ModuleProtocol,
    Result,
    ToolSpec,
    ViewerClip,
    ViewerTabsChanged,
)
from assistant.infra.agent_tags import find_tags, parse_show

DEFAULT_PROFILE = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "AI_Assistant" / "html_viewer_window"


class HtmlViewerModule(ModuleProtocol):
    manifest = Manifest(
        id="html_viewer",
        description="View, edit, highlight and snip HTML; launches the viewer app",
        provides=(IToolProvider,),
        publishes=(ViewerTabsChanged, ViewerClip,),
        listens=(AgentActivity,),
    )

    async def init(self, ctx: ModuleContext) -> None:
        self._ctx = ctx
        host = ctx.config.get("host", "127.0.0.1")
        port = ctx.config.get("port", 8766)
        profile = Path(ctx.config.get("window_profile", DEFAULT_PROFILE)).resolve()
        args = ["--host", host, "--port", str(port), "--window", ctx.config.get("window", "app"),
                "--profile", str(profile)]
        for folder in ctx.config.get("generated", []):
            args += ["--generated", str(Path(folder).resolve())]
        self._app = CompanionApp(  # starts the viewer when needed; stops it only if it started it
            "html_viewer", host, port, ping="/api/ping", args=args,
            start_timeout=ctx.config.get("start_timeout", 10.0), log=ctx.log,
        )
        self._logs_dir = ctx.config.get("logs_dir", "logs")  # a folder, or a callable returning one
        self._relay_task: asyncio.Task | None = None
        self._shows: set[asyncio.Task] = set()
        ctx.provide(IToolProvider, _ViewerTools(self))
        ctx.subscribe(AgentActivity, self._on_activity)

    async def start(self) -> None:
        # Nothing to launch yet. A viewer you started yourself: follow its tabs from now on.
        if await self._ping():
            self._follow()

    async def stop(self) -> None:
        for task in [*self._shows, self._relay_task]:
            if task:
                task.cancel()
        await asyncio.gather(*self._shows, *[t for t in [self._relay_task] if t], return_exceptions=True)
        await self._app.stop()

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

    async def tabs(self) -> Result:
        if not await self._ping():
            return Result.ok([])
        answer = await self._call("GET", "/api/tabs")
        return Result.ok([
            {"path": t["path"], "active": t["active"], "unsaved": t["dirty"],
             "highlights": [h["text"] for h in t.get("highlights", [])]}
            for t in answer["tabs"]
        ])

    async def show_tag(self, argument: str) -> Result:
        """Run a SHOW tag's argument: open the file, or open it and highlight."""
        show = parse_show(argument)
        return await (self.highlight(*show) if show.quote else self.show(show.path))

    async def _on_activity(self, event: AgentActivity) -> None:
        # Starting the viewer can take seconds; don't hold up the event handler.
        for tag in find_tags(event.text, ("SHOW",)):
            if not tag.argument:
                continue
            task = asyncio.create_task(self._show_for_agent(tag.argument))
            self._shows.add(task)
            task.add_done_callback(self._shows.discard)

    async def _show_for_agent(self, argument: str) -> None:
        result = await self.show_tag(argument)
        if not result.is_ok:
            self._ctx.log.warning("Couldn't show %s: %s", argument, result.error)
        elif isinstance(result.value, dict) and result.value.get("found") is False:
            self._ctx.log.warning("Opened %s, but the text to highlight isn't on the page", argument)

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
        folder = Path(self._logs_dir() if callable(self._logs_dir) else self._logs_dir) / "snips"
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


class _ViewerTools(IToolProvider):
    """The module's tools, as a composed part (principle 12)."""

    def __init__(self, module: HtmlViewerModule) -> None:
        self._module = module

    def tools(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name="viewer.open",
                description="Open an HTML file in the HTML viewer (switches to its tab if it's open); "
                            "front: also bring the viewer window to the front (for the user's clicks)",
                input_schema={
                    "type": "object",
                    "properties": {"path": {"type": "string"}, "front": {"type": "boolean"}},
                    "required": ["path"],
                },
            ),
            ToolSpec(
                name="viewer.highlight",
                description="Open an HTML file in the viewer and highlight a short quote of its text, "
                            "optionally only in the section under a heading; scrolls to it",
                input_schema={
                    "type": "object",
                    "properties": {"path": {"type": "string"}, "text": {"type": "string"}, "heading": {"type": "string"},
                                   "front": {"type": "boolean"}},
                    "required": ["path", "text"],
                },
            ),
            ToolSpec(name="viewer.tabs", description="The files open in the HTML viewer, and their highlights"),
        ]

    async def invoke(self, name: str, args: dict[str, Any]) -> Result:
        if name in ("viewer.open", "viewer.highlight"):
            if not isinstance(args.get("path"), str) or not args["path"].strip():
                return Result.invalid_arguments(f"{name} needs a path")
        front = args.get("front") is True
        if name == "viewer.open":
            return await self._module.show(args["path"], front)
        if name == "viewer.highlight":
            if not isinstance(args.get("text"), str) or not args["text"].strip():
                return Result.invalid_arguments("viewer.highlight needs the text to highlight")
            heading = args.get("heading")
            return await self._module.highlight(
                args["path"], args["text"], heading if isinstance(heading, str) else None, front
            )
        return await self._module.tabs()
