"""The Submit watch: the user's Submit in the CV Tool reaches the cv module with no agent in between.

While the CV Tool runs, the module reads its event stream (`CvTool.events`); each live `submitted`
event gets the job's result (`CvTool.result`) and hands it to `deliver` (the module's `_pass_submit`,
which publishes `cv.job_submitted`).
A Submit is never refused (2026-11-10).

Submits pressed while the module was down are never delivered by themselves (the user's rule,
2026-11-10): each time the watch starts it looks once at every submitted job (`CvTool.submitted`)
and, for one it hasn't seen, only `remind`s the user (one plain notice naming the job and the time),
leaving the decision to them. What it has seen is kept in `seen_path` (`submits_seen.json`, one key
per Submit: job id and time). With no such file yet (the first start), every Submit already there is
marked seen and nothing is reminded. No `seen_path` (no data folder): the same, every start.

The same stream carries the Send JD and CV to Rezi click (`rezi_request`, 2026-11-10): each live one
goes to `on_rezi` once per request id (the module tells cv_agent to start the First Draft). A click
made while the module was down sends nothing: the request stays pending on the job, and cv_agent
sees it in cv.tool_status. The Internal or Rezi pick sends no event.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from assistant.modules.cv.tool import CvTool, ToolError

REMINDER = ("While the cv module was off, you pressed Submit in the CV Tool on {what} at {at}. Nothing was "
            "sent to the job agent. To send it, ask for cv.tool_result on CV Tool job {job_id}; otherwise "
            "nothing happens.")  # fmt: skip


def submit_key(job_id: str, submitted_at: str) -> str:
    return f"{job_id}@{submitted_at}"


class SeenSubmits:
    """The Submits the module has seen, kept in one JSON file. `None` path: kept in memory only."""

    def __init__(self, path: Path | None) -> None:
        self._path = path
        self._keys: set[str] | None = None  # loaded at the first look

    def load(self) -> bool:
        """Read the file; False when there's none yet (the first start)."""
        if self._keys is not None:
            return True
        if self._path is None or not self._path.exists():
            self._keys = set()
            return False
        try:
            self._keys = set(json.loads(self._path.read_text(encoding="utf-8")).get("seen") or [])
        except (OSError, ValueError, AttributeError):
            self._keys = set()
            return False
        return True

    def __contains__(self, key: str) -> bool:
        return key in (self._keys or set())

    def add(self, *keys: str) -> None:
        if self._keys is None:
            self.load()
        assert self._keys is not None
        self._keys.update(keys)
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"seen": sorted(self._keys)}, indent=1), encoding="utf-8")
            tmp.replace(self._path)


class SubmitWatch:
    """Follows one CvTool's Submits while it runs; `follow()` is cheap to call again."""

    def __init__(self, tool: CvTool, deliver: Callable[[dict[str, Any]], Awaitable[str | None]], log: Any,
                 remind: Callable[[str], None] | None = None, seen_path: Path | None = None,
                 on_rezi: Callable[[dict[str, Any]], Awaitable[Any]] | None = None) -> None:  # fmt: skip
        self._tool, self._deliver, self._log = tool, deliver, log
        self._remind = remind or (lambda text: None)
        self._on_rezi = on_rezi
        self._rezi_seen: set[str] = set()  # request ids told, while the module runs
        self._seen = SeenSubmits(seen_path)
        self._task: asyncio.Task[None] | None = None

    def follow(self) -> None:
        """Start watching unless already watching."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._watch(), name="cv:submit_watch")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _watch(self) -> None:
        stream = self._tool.events()
        first = asyncio.ensure_future(anext(stream))  # the stream starts before the look, so a Submit between is seen
        try:
            await self._catch_up(await self._tool.submitted())
            item = await first
            while True:
                if item.get("kind") == "submitted":
                    await self._live(str(item.get("job_id") or ""), str(item.get("submitted_at") or ""))
                elif item.get("kind") == "rezi_request":
                    await self._rezi(item)
                item = await anext(stream)
        except StopAsyncIteration:
            pass  # the CV Tool quit; the next call to it starts the watch again
        except (OSError, ValueError, TimeoutError, ToolError) as exc:
            self._log.info("cv: stopped watching the CV Tool's Submits: %s", exc)
        finally:
            first.cancel()  # no-op once done; the gather takes its exception, if any
            await asyncio.gather(first, return_exceptions=True)
            await stream.aclose()

    async def _catch_up(self, jobs: list[dict[str, Any]]) -> None:
        """Submits made while the module was down: reminded once, never delivered."""
        found = [(str(j.get("job_id") or ""), str(j.get("submitted_at") or "")) for j in jobs]
        found = [(job_id, at) for job_id, at in found if job_id]
        if not await asyncio.to_thread(self._seen.load):  # the first start: everything there is old
            await asyncio.to_thread(self._seen.add, *(submit_key(*f) for f in found))
            return
        for job_id, at in found:
            if submit_key(job_id, at) in self._seen:
                continue
            await asyncio.to_thread(self._seen.add, submit_key(job_id, at))
            self._remind(REMINDER.format(what=await self._name(job_id), at=at or "an unknown time", job_id=job_id))

    async def _name(self, job_id: str) -> str:
        try:
            result = (await self._tool.result(job_id)).get("result") or {}
        except (OSError, ValueError, TimeoutError, ToolError):
            result = {}
        role, company = result.get("role"), result.get("company")
        return f"the CV for {role} at {company}" if role and company else f"job {job_id}"

    async def _rezi(self, item: dict[str, Any]) -> None:
        """A Send JD and CV to Rezi click while the module runs: to `on_rezi`, once per request."""
        rid = str(item.get("request_id") or "")
        if self._on_rezi is None or not item.get("job_id") or not rid or rid in self._rezi_seen:
            return
        self._rezi_seen.add(rid)
        try:
            await self._on_rezi(item)
        except Exception as exc:  # noqa: BLE001 - one failed telling never stops the watch
            self._log.warning("cv: couldn't tell about the Rezi request %s: %s", rid, exc)

    async def _live(self, job_id: str, submitted_at: str) -> None:
        """A Submit pressed while the module runs: delivered by itself."""
        if not job_id or submit_key(job_id, submitted_at) in self._seen:
            return
        await asyncio.to_thread(self._seen.add, submit_key(job_id, submitted_at))
        try:
            value = await self._tool.result(job_id)
        except (OSError, ValueError, TimeoutError, ToolError) as exc:
            self._log.warning("cv: couldn't read the Submit of %s: %s", job_id, exc)
            return
        if value.get("ready"):
            await self._deliver(value)
