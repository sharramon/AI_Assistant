"""The Agent Hub's delivery: a message for an agent that never interrupts a turn (`DeliverMessage`).

An idle agent gets the message at once: into its open task if it has one (that also answers a
question it waits on), else as a new task. An agent in a turn, or one not running, gets it later:
the message waits here and `flush` (on every agent or module state change) tries again. Messages
to one agent keep their order: once one waits, later ones queue behind it.

What waits is handed over on a Hub reload (`export`); an app restart loses it.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass

from assistant.contracts import DeliverMessage, ITaskAgent, Result, SendToTask, StartTask, Status

from .tasks import TaskBoard

FAILED = "failed: "


@dataclass(frozen=True)
class Waiting:
    """One message not delivered yet: its agent, its full text (with the sender's line). With
    `task_id`: an answer for that task's question (as typed), sent there while it's still open."""

    agent_id: str
    text: str
    sender: str
    task_id: str = ""


def message_text(sender: str, text: str) -> str:
    """What the agent reads: `[Message from <sender>] <text>`."""
    return f"[Message from {sender or 'a module'}] {text}"


class Delivery:
    """Delivers `DeliverMessage`s through the task board, in order, never into a running turn.

    `agent(id)` finds a running agent. `waiting`: what a previous copy left (its `export`)."""

    def __init__(self, board: TaskBoard, agent: Callable[[str], ITaskAgent | None], log: logging.Logger,
                 waiting: list[dict] | None = None) -> None:  # fmt: skip
        self._board, self._agent, self._log = board, agent, log
        self._waiting: list[Waiting] = [Waiting(**w) for w in waiting or ()]
        self._lock = asyncio.Lock()

    async def deliver(self, command: DeliverMessage) -> Result:
        item = Waiting(agent_id=command.agent_id, text=message_text(command.sender, command.text),
                       sender=command.sender)  # fmt: skip
        async with self._lock:
            if any(w.agent_id == item.agent_id for w in self._waiting):  # keep the order
                how = None
            else:
                how = await self._try(item)
            if how is None:
                self._waiting.append(item)
                self._log.info("A message from %s for %s waits (in a turn or not running)", item.sender, item.agent_id)
                return Result.ok("pending")
        if how.startswith(FAILED):
            return Result.failed(how.removeprefix(FAILED))
        return Result.ok(how)

    async def later(self, agent_id: str, task_id: str, text: str) -> Result:
        """An answer for `task_id`'s question whose agent is in a turn or not running: it waits,
        behind that agent's other messages, and goes in when the agent is free."""
        async with self._lock:
            self._waiting.append(Waiting(agent_id=agent_id, text=text, sender="", task_id=task_id))
        self._log.info("An answer for %s's task %s waits for it to be free", agent_id, task_id)
        return Result.ok("pending")

    async def flush(self, _event: object = None) -> None:
        """Try every waiting message again, stopping at an agent's first that can't go yet."""
        if not self._waiting:
            return
        async with self._lock:
            blocked: set[str] = set()
            for item in list(self._waiting):
                if item.agent_id in blocked:
                    continue
                how = await self._try(item)
                if how is None:
                    blocked.add(item.agent_id)
                    continue
                self._waiting.remove(item)
                self._log.info("A waiting message from %s for %s: %s", item.sender, item.agent_id, how)

    def export(self) -> list[dict]:
        """What still waits, for the next copy of the Hub."""
        return [asdict(w) for w in self._waiting]

    def waiting(self, agent_id: str | None = None) -> list[Waiting]:
        return [w for w in self._waiting if agent_id is None or w.agent_id == agent_id]

    async def _try(self, item: Waiting) -> str | None:
        """Deliver now if the agent is running and between turns: `message <id>`, `task <id>`, or
        `failed: <why>` (dropped). None: not now (it waits)."""
        agent = self._agent(item.agent_id)
        if agent is None or agent.info().active:
            return None
        if item.task_id:  # an answer: into its task while that's open, else as a new task
            record = self._board.get(item.task_id)
            record = record if record is not None and not record.state.is_final else None
        else:
            record = self._board.open_task_of(item.agent_id)
        if record is not None:
            sent = await self._board.send(SendToTask(task_id=record.id, text=item.text))
            if sent.is_ok:
                return f"message {record.id}"
            if sent.status is not Status.NOT_AVAILABLE:
                return f"{FAILED}{sent.error}"
            # not available: the board closed a record the agent no longer held; a new task below
        started = await self._board.start(StartTask(text=item.text, agent_id=item.agent_id))
        if started.is_ok:
            return f"task {started.value}"
        if started.status is Status.NOT_AVAILABLE:  # busy, the cap, a folder clash: later
            return None
        return f"{FAILED}{started.error}"
