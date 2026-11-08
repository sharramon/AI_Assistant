"""The `rezi.*` items' work: Rezi's six tools through `McpClient`, writes through `ResumeGuard`.

- **Tool names and arguments** are Rezi's published ones (`TOOLS`). Its docs don't give the
  argument schemas, so `sign_in` lists the live tools and `check_tools` says what differs
  (a tool missing, a new one, an argument we send that the tool doesn't take). Each read item
  also takes `extra` arguments, passed through, for anything the live schema needs.
- **Writes:** `write_resume` with no id makes a new resume; its id comes from Rezi's answer, or
  else from the resume list before and after. The guard then allows updates of that id only.
  Writes run one at a time, and each is read back (`verify`) as Rezi's docs advise.
- **Errors** become `Result`s in `run`: not signed in → `not_available`, a guard refusal →
  `invalid_arguments`, Rezi's error → `failed`, no answer → `failed` (retryable).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import Any

from assistant.contracts import Result
from assistant.modules.cv.guard import ID_KEYS, GuardRefused, ResumeGuard
from assistant.modules.cv.mcp import (
    McpClient,
    NotSignedIn,
    OpenBrowser,
    ReziError,
    ReziUnreachable,
    ToolInfo,
    ToolOutput,
)

# Rezi's tools (rezi-io/rezi-mcp) and the arguments the items send to each (live schemas, 2026-11-07).
# Rezi's other live tools are never used: auto_apply_job (applies to jobs), duplicate_resume, the cover letters.
TOOLS: dict[str, tuple[str, ...]] = {
    "list_resumes": ("limit",),
    "read_resume": ("resume_id",),
    "get_resume_format": (),
    "write_resume": ("resume", "resume_id"),
    "search_jobs": ("role", "location"),
    "get_job_details": ("job_id",),
    "generate_keywords": ("resume_id",),
}
_PASSED = ("write_resume",)  # the caller gives a write's fields
LIST_LIMIT = 200  # Rezi's most; the guard's before/after needs every resume (its default is 10)
_NAME_KEYS = ("name", "title", "resume_name", "resumeName")


def _id_key(key: str) -> bool:
    return "".join(c for c in key.lower() if c.isalnum() or c == "_") in ID_KEYS


def resume_ids(data: Any) -> set[str]:
    """Every resume id in a `list_resumes` answer: the id of each object that has one (not looking inside it)."""
    ids: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            own = next((v for k, v in value.items() if _id_key(k) and isinstance(v, (str, int))
                        and not isinstance(v, bool)), None)  # fmt: skip
            if own is not None:
                ids.add(str(own))
                return
            for inner in value.values():
                walk(inner)
        elif isinstance(value, list):
            for inner in value:
                walk(inner)

    walk(data)
    return ids


def answer_id(data: Any) -> str | None:
    """The resume id in `write_resume`'s answer: at the top, or under `resume`."""
    for where in (data, data.get("resume") if isinstance(data, dict) else None):
        if isinstance(where, dict):
            for key, value in where.items():
                if _id_key(key) and isinstance(value, (str, int)) and not isinstance(value, bool) and str(value):
                    return str(value)
    return None


def check_tools(tools: list[ToolInfo]) -> dict[str, Any]:
    """The live tool list against `TOOLS`: `missing`, `new` (an export tool would show here) and
    `arguments` (per tool: an argument we send that it doesn't take, or one it requires we don't send)."""
    live = {t.name: t for t in tools}
    arguments: dict[str, dict[str, list[str]]] = {}
    for name, ours in TOOLS.items():
        if name not in live:
            continue
        schema = live[name].input_schema or {}
        takes = set(schema.get("properties", {}))
        required = set(schema.get("required", []))
        unknown = sorted(a for a in ours if takes and a not in takes)
        unsent = [] if name in _PASSED else sorted(required - set(ours))
        if unknown or unsent:
            arguments[name] = {"we_send": list(ours), "it_takes": sorted(takes), "it_requires": sorted(required)}
    return {"ok": not arguments and all(n in live for n in TOOLS), "missing": [n for n in TOOLS if n not in live],
            "new": sorted(set(live) - set(TOOLS)), "arguments": arguments}  # fmt: skip


def _out(output: ToolOutput) -> dict[str, Any]:
    """The tool's data, or its text when it isn't data."""
    return {"data": output.data} if output.data is not None else {"text": output.text}


async def run(item: str, work: Awaitable[dict[str, Any]]) -> Result:
    """One item's work as a `Result`, its errors mapped."""
    try:
        return Result.ok(await work)
    except GuardRefused as exc:
        return Result.invalid_arguments(f"{item}: {exc}")
    except NotSignedIn as exc:
        return Result.not_available(f"{item}: {exc}")
    except ReziUnreachable as exc:
        return Result.failed(f"{item}: {exc}", retryable=True)
    except ReziError as exc:
        return Result.failed(f"{item}: {exc}")


class ReziTools:
    """The items' work over one `McpClient` and the module's `ResumeGuard`."""

    def __init__(self, client: McpClient, guard: ResumeGuard, open_browser: OpenBrowser | None = None) -> None:
        self.client = client
        self.guard = guard
        self.open_browser = open_browser  # None: the system browser
        self._write = asyncio.Lock()
        self._signing: asyncio.Task[dict[str, Any]] | None = None

    def status(self) -> dict[str, Any]:
        """Signed in or not, days left, the resumes made here, and the last sign-in's state. Never connects."""
        return self.client.status() | self.guard.as_value() | {"sign_in": self.sign_in_state()}

    def sign_in_state(self) -> dict[str, Any] | None:
        """The background sign-in: None (none started), waiting, done (with the tools and check) or failed."""
        task = self._signing
        if task is None:
            return None
        if not task.done():
            return {"state": "waiting", "next": "finish signing in to Rezi in the browser"}
        if task.cancelled():
            return {"state": "failed", "error": "cancelled"}
        if (exc := task.exception()) is not None:
            return {"state": "failed", "error": str(exc), "kind": type(exc).__name__}
        return {"state": "done"} | task.result()

    async def start_sign_in(self, force: bool = False, timeout: float = 300.0, wait: float = 20.0) -> dict[str, Any]:
        """Sign in as a task of its own, so the module door's time limit can't cut it off. Waits up to
        `wait` seconds: the sign-in's answer if it ends by then (its errors raised), else `waiting`.
        A sign-in already waiting is waited on again: no second browser."""
        if self._signing is None or self._signing.done():
            self._signing = asyncio.create_task(self.sign_in(force, timeout), name="rezi.sign_in")
        task = self._signing
        await asyncio.wait({task}, timeout=wait)
        if task.done():
            return task.result()
        return self.client.status() | {"signing_in": True, "sign_in": self.sign_in_state(),
                                       "next": "finish in the browser, then rezi.status"}  # fmt: skip

    def cancel_sign_in(self) -> None:
        if self._signing is not None and not self._signing.done():
            self._signing.cancel()

    async def sign_in(self, force: bool = False, timeout: float = 300.0) -> dict[str, Any]:
        status = await self.client.sign_in(self.open_browser, force=force, timeout=timeout)
        try:
            tools = await self.client.list_tools()
        except (ReziError, ReziUnreachable) as exc:
            return status | {"tools": None, "tools_error": str(exc)}
        schemas = {t.name: t.input_schema for t in tools if t.name in TOOLS}  # the live arguments of the tools cv uses
        return status | {"tools": [t.name for t in tools], "check": check_tools(tools), "schemas": schemas}

    async def _list(self) -> ToolOutput:
        return await self.client.call("list_resumes", {"limit": LIST_LIMIT})

    async def list_resumes(self) -> dict[str, Any]:
        return _out(await self._list()) | self.guard.as_value()

    async def read_resume(self, resume_id: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        output = await self.client.call("read_resume", {**(extra or {}), "resume_id": resume_id})
        value = _out(output) | {"created_here": self.guard.owns(resume_id)}
        if output.data is not None:
            from assistant.modules.cv.rezi_json import read_rezi

            try:
                content, skipped = read_rezi(output.data)
                value |= {"sections": {n: list(lines) for n, lines in content.sections.items()}, "skipped": skipped}
            except ValueError as exc:
                value |= {"sections": None, "sections_error": str(exc)}
        return value

    async def get_resume_format(self) -> dict[str, Any]:
        return _out(await self.client.call("get_resume_format"))

    async def write_resume(self, fields: dict[str, Any], resume_id: str | None = None,
                           verify: bool = True) -> dict[str, Any]:  # fmt: skip
        async with self._write:
            self.guard.check_write(resume_id, fields)
            before = resume_ids((await self._list()).data) if resume_id is None else set()
            arguments = {"resume": dict(fields)} | ({"resume_id": resume_id} if resume_id else {})
            output = await self.client.call("write_resume", arguments)
            value: dict[str, Any] = {"created": resume_id is None, "answer": _out(output)}
            new = resume_id
            if resume_id is None:
                new = answer_id(output.data)
                if new is None:
                    made = resume_ids((await self._list()).data) - before
                    new = made.pop() if len(made) == 1 else None
                if new is not None and new in before:
                    value["warning"] = f"Rezi answered with {new!r}, an existing resume: not taken as made here"
                    new = None
                elif new is None:
                    value["warning"] = ("Rezi made a resume but its id wasn't found: updates of it are refused; "
                                        "find it with rezi.list_resumes")  # fmt: skip
                else:
                    self.guard.created(new, next((str(fields[k]) for k in _NAME_KEYS if fields.get(k)), ""))
            value["resume_id"] = new
            if verify and new is not None:
                value["read_back"] = await self.read_resume(new)  # with its sections, to check against the CV
        return value

    async def write_cv(self, sections: dict[str, Any], name: str, resume_id: str | None = None, job_title: str = "",
                       job_company: str = "", job_description: str = "", verify: bool = True) -> dict[str, Any]:  # fmt: skip
        """A CV's sections written as a Rezi resume (`write_rezi`): new, or an update of one made
        here (its entries replaced, not added to). Adds `left_out`: lines Rezi has no field for."""
        from assistant.modules.cv.content import CvContent
        from assistant.modules.cv.rezi_json import write_rezi

        content = CvContent(sections={k: tuple(v) for k, v in sections.items()})  # ValueError: an unknown section
        existing = None
        if resume_id is not None:
            self.guard.check_write(resume_id, {})  # refuse before reading a resume not made here
            existing = (await self.client.call("read_resume", {"resume_id": resume_id})).data
        resume, left_out = write_rezi(content, name, job_title, job_company, job_description, existing)
        return await self.write_resume(resume, resume_id, verify) | {"left_out": left_out}

    async def generate_keywords(self, resume_id: str) -> dict[str, Any]:
        """Rezi's keywords for the JD saved on a resume (its jobDescription). Only a resume made here:
        the tool may save them on the resume."""
        self.guard.check_write(resume_id, {})
        return _out(await self.client.call("generate_keywords", {"resume_id": resume_id}))

    async def search_jobs(self, role: str, location: str = "", extra: dict[str, Any] | None = None) -> dict[str, Any]:
        arguments = {**(extra or {}), "role": role} | ({"location": location} if location else {})
        return _out(await self.client.call("search_jobs", arguments))

    async def get_job_details(self, job_id: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        return _out(await self.client.call("get_job_details", {**(extra or {}), "job_id": job_id}))
