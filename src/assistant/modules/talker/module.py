"""The Talker: a fast `claude` session that talks with you and hands work to the Agent Hub.

Everything that should make it speak (your input, task updates, command
results) goes into one inbox, handled one `claude` turn at a time, so it never
talks over itself and event handlers return at once. Tags in its replies become
Hub commands.
"""

from __future__ import annotations

import asyncio
import re
from collections import deque
from dataclasses import dataclass
from typing import Any

from assistant.contracts import (
    CancelTask,
    GetTaskStatus,
    InputReceived,
    Manifest,
    Module,
    ModuleContext,
    ReportKind,
    ResponseReady,
    SendToTask,
    StartTask,
    TaskInfo,
    TaskUpdated,
)
from assistant.infra import ClaudeSession, claude_command

TALKER_PROMPT = """\
You are the voice of a personal AI assistant. Keep replies short and conversational, \
like speech. Plain text only, no markdown.

You can't do work yourself (no files, no tools). Anything substantial goes to the \
Main Assistant, who works in the background while you keep chatting. Control it by \
putting tags in your reply; the user never sees them:

- <<WORK: full description of the task>> start a task. Include everything it needs.
- <<LOOK>> check on the task. The status comes back to you as a [Status] message.
- <<ASK: text>> pass a question, an extra instruction, or the user's answer to its \
question to the running task. It stops briefly, answers, and carries on.
- <<PAUSE: text>> the same, but it stops after answering and waits until you ASK again.
- <<CANCEL>> drop the task.

Messages starting with [Task update: ...] or [Status] come from the system, not the \
user: tell the user what matters in a sentence or two. A [Task update: need] is a \
question for the user; ask it, and send their answer back with ASK.

Never claim work is done until a [Task update: done] arrives. Answer simple things \
yourself. Infer from context whether the user wants the task to continue, pause, or \
stop; never ask them for keywords or tags. Only one task runs at a time."""

TAG = re.compile(r"<<\s*(WORK|LOOK|ASK|PAUSE|CANCEL)\s*(?::(.*?))?>>", re.DOTALL)
# Task updates worth speaking about; progress stays with the Hub until you ask.
SPOKEN_UPDATES = {ReportKind.DONE, ReportKind.NEED, ReportKind.REPLY, ReportKind.FAILED}


def split_tags(reply: str) -> tuple[str, list[tuple[str, str]]]:
    """Split a Talker reply into the text to show and its (tag, argument) pairs, in order."""
    tags = [(m.group(1), (m.group(2) or "").strip()) for m in TAG.finditer(reply)]
    text = re.sub(r"[ \t]+\n", "\n", TAG.sub("", reply)).strip()
    return text, tags


@dataclass
class _Item:
    text: str
    input_id: str | None = None  # set when the item is your input; the reply is correlated to it
    conversation_id: str | None = None


class TalkerModule(Module):
    manifest = Manifest(id="talker")

    async def init(self, ctx: ModuleContext) -> None:
        self._ctx = ctx
        self._turn_timeout = ctx.config.get("turn_timeout", 120.0)
        command = claude_command(
            model=ctx.config.get("model", "sonnet"),
            tools="",
            system_prompt=TALKER_PROMPT,
            program=ctx.config.get("program", ["claude"]),
        )
        self._session = ClaudeSession(command, cwd=ctx.config.get("cwd"), log=ctx.log, on_event=self._on_event)
        self._inbox: asyncio.Queue[_Item] = asyncio.Queue()
        self._history: deque[str] = deque(maxlen=2 * ctx.config.get("context_exchanges", 6))
        self._current_task_id: str | None = None
        self._turn: asyncio.Future[dict[str, Any]] | None = None
        self._loop_task: asyncio.Task | None = None
        ctx.subscribe(InputReceived, self._on_input)
        ctx.subscribe(TaskUpdated, self._on_task_updated)

    async def start(self) -> None:
        await self._session.start()
        self._loop_task = asyncio.create_task(self._run(), name="talker:inbox")

    async def stop(self) -> None:
        if self._loop_task:
            self._loop_task.cancel()
            await asyncio.gather(self._loop_task, return_exceptions=True)
        await self._session.close()

    async def _on_input(self, event: InputReceived) -> None:
        self._inbox.put_nowait(_Item(event.text, event.id, event.conversation_id))

    async def _on_task_updated(self, event: TaskUpdated) -> None:
        if event.task_id == self._current_task_id and event.kind in SPOKEN_UPDATES:
            self._inbox.put_nowait(_Item(f"[Task update: {event.kind}] {event.text}"))

    def _on_event(self, event: dict[str, Any]) -> None:
        if self._turn is None or self._turn.done():
            return
        if event.get("type") == "result":
            self._turn.set_result(event)
        elif event.get("type") == "exit":
            self._turn.set_exception(RuntimeError("The Talker's claude process exited"))

    async def _run(self) -> None:
        while True:
            item = await self._inbox.get()
            try:
                await self._handle(item)
            except Exception:
                self._ctx.log.exception("Talker turn failed")
                if item.input_id:
                    self._say("Sorry, something went wrong on my side.", item)

    async def _handle(self, item: _Item) -> None:
        result = await self._take_turn(item.text)
        text, tags = split_tags(result.get("result") or "")
        if result.get("is_error") and not text:
            text = "Sorry, something went wrong on my side."
        self._history.append(f"User: {item.text}" if item.input_id else item.text)
        if text:
            self._history.append(f"Assistant: {text}")
            self._say(text, item)
        for tag, argument in tags:
            await self._run_tag(tag, argument)

    async def _take_turn(self, text: str) -> dict[str, Any]:
        if not self._session.running:
            await self._session.start()
        self._turn = asyncio.get_running_loop().create_future()
        await self._session.send(text)
        try:
            return await asyncio.wait_for(asyncio.shield(self._turn), self._turn_timeout)
        except TimeoutError:
            self._ctx.log.warning("Talker turn took over %ss; interrupting", self._turn_timeout)
            await self._session.interrupt()
            return await asyncio.wait_for(self._turn, 10)

    async def _run_tag(self, tag: str, argument: str) -> None:
        ctx = self._ctx
        if tag == "WORK":
            result = await ctx.send(StartTask(text=argument, context="\n".join(self._history)))
            if result.is_ok:
                self._current_task_id = result.value
            else:
                self._status(f"The assistant couldn't take the task: {result.error}")
        elif tag == "LOOK":
            result = await ctx.send(GetTaskStatus(task_id=self._current_task_id))
            self._status(_describe(result.value) if result.is_ok else f"Couldn't get the status: {result.error}")
        elif self._current_task_id is None:
            self._status("There's no task to send that to.")
        elif tag in ("ASK", "PAUSE"):
            result = await ctx.send(SendToTask(task_id=self._current_task_id, text=argument, resume=tag == "ASK"))
            if not result.is_ok:
                self._status(f"Couldn't reach the task: {result.error}")
        elif tag == "CANCEL":
            result = await ctx.send(CancelTask(task_id=self._current_task_id))
            if not result.is_ok:
                self._status(f"Couldn't cancel the task: {result.error}")

    def _say(self, text: str, item: _Item) -> None:
        self._ctx.publish(ResponseReady(text=text, correlation_id=item.input_id, conversation_id=item.conversation_id))

    def _status(self, text: str) -> None:
        self._inbox.put_nowait(_Item(f"[Status] {text}"))


def _describe(tasks: list[TaskInfo]) -> str:
    if not tasks:
        return "No tasks."
    lines = []
    for task in tasks:
        lines.append(f"Task {task.id} is {task.state}: {task.text}")
        if task.question:
            lines.append(f"  Waiting for the answer to: {task.question}")
        lines += [f"  {report}" for report in task.recent[-3:]]
        if task.result and task.state.is_final:
            lines.append(f"  Result: {task.result}")
    return "\n".join(lines)
