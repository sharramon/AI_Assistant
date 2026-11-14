"""The access-list review (decision D6): the core asks with `ReviewAccessList`, the Hub runs it.

The core's permissions handler never starts a task. Before an access card shows, it sends
`ReviewAccessList` with the list and its warnings; the Hub starts a normal task on the named
reviewer agent (the Main Assistant by default, from `[core.permissions] reviewer`), waits for its
end up to the command's `timeout`, and sends the reply lines back with `AddCardNotes`. A busy
reviewer answers `not_available` at once (the card says "not reviewed"); a late one is cancelled
and the card shows "not reviewed" too.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from assistant.contracts import (
    AddCardNotes,
    CancelTask,
    Command,
    Result,
    ReviewAccessList,
    StartTask,
    TaskState,
    TaskUpdated,
)

REVIEW_PROMPT = """\
Review an access list before the user answers it on a card. Use no tools and ask no questions.
Reply with one short line per risk the warnings below don't already cover (what it could do, and \
with which items), or exactly `No further warnings.` Nothing else.

Who asks: {who}{reason}
The list:
{items}
Warnings already on the card:
{warnings}"""

NO_FURTHER = "no further warnings"
LINE_CAP = 300


def review_lines(text: str) -> tuple[str, ...]:
    """The reviewer's reply as note lines: bullets stripped, `No further warnings.` dropped."""
    lines = [line.strip().lstrip("-* ").strip() for line in (text or "").splitlines()]
    return tuple(line[:LINE_CAP] for line in lines if line and NO_FURTHER not in line.lower())


class Reviewer:
    """Runs reviews as tasks on the board. `start` / `cancel`: the board's; `send`: the module's
    `ctx.send` (for `AddCardNotes`). `on_task_updated` is fed every `TaskUpdated` the board publishes."""

    def __init__(self, start: Callable[[StartTask], Awaitable[Result]],
                 cancel: Callable[[CancelTask], Awaitable[Result]],
                 send: Callable[[Command], Awaitable[Result]], log: logging.Logger) -> None:  # fmt: skip
        self._start, self._cancel, self._send, self._log = start, cancel, send, log
        self._ends: dict[str, asyncio.Future] = {}
        self._work: set[asyncio.Task] = set()

    async def review(self, command: ReviewAccessList) -> Result:
        prompt = REVIEW_PROMPT.format(
            who=command.who, reason=f" ({command.reason})" if command.reason else "",
            items="\n".join(f"- {i}" for i in command.items) or "- (nothing)",
            warnings="\n".join(f"- {w}" for w in command.warnings) or "- (none)",
        )  # fmt: skip
        started = await self._start(StartTask(text=prompt, agent_id=command.reviewer))
        if not started.is_ok:
            return Result.not_available(f"No review: {started.error}")
        task_id = str(started.value)
        self._ends.setdefault(task_id, asyncio.get_running_loop().create_future())
        work = asyncio.create_task(self._finish(command, task_id))
        self._work.add(work)
        work.add_done_callback(self._work.discard)
        return Result.ok(task_id)

    def on_task_updated(self, event: TaskUpdated) -> None:
        end = self._ends.get(event.task_id)
        if end is not None and event.state.is_final and not end.done():
            end.set_result((event.state, event.text))

    async def close(self) -> None:
        for work in list(self._work):
            work.cancel()
        await asyncio.gather(*self._work, return_exceptions=True)

    async def _finish(self, command: ReviewAccessList, task_id: str) -> None:
        try:
            state, text = await asyncio.wait_for(self._ends[task_id], command.timeout)
        except TimeoutError:
            await self._cancel(CancelTask(task_id=task_id))
            self._log.info("%s's list is not reviewed: no answer in %gs", command.who, command.timeout)
            state, text = TaskState.CANCELLED, ""
        finally:
            self._ends.pop(task_id, None)
        done = state is TaskState.DONE
        result = await self._send(AddCardNotes(request_id=command.request_id,
                                               notes=review_lines(text) if done else (), reviewed=done))  # fmt: skip
        if not result.is_ok:
            self._log.info("The review of %s's list came too late: %s", command.who, result.error)
