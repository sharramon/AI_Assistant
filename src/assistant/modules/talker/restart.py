"""The main tab's restart, one job in its own class (principle 18): `RestartFlow`.

A `<<RESTART>>` (main tab only) asks the worker for reset instructions (a reply ending
`RESTART_READY`), saves them to `restart_note` with the app's own state section under them (the
tab you were in, every agent and its mode, the open tasks and their questions, what a restart
does), and publishes `ShutdownRequested(restart=True)`; the launcher starts the app again. At the
next start the note is the main tab's first input, then it's deleted. Any stop that isn't a
restart deletes it too.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from assistant.contracts import ListAgents, ReportKind, ShutdownRequested, TaskState, TaskUpdated
from assistant.infra import last_line

if TYPE_CHECKING:
    from assistant.modules.talker.module import TalkerModule

RESTART_READY = "RESTART_READY"  # the last line of the worker's reset instructions
WRITE_RESET_NOTE = (
    "The user asked to restart the app. Stop at a safe point and don't carry on with the task. "
    "If the task has a change note in docs/next-steps/, first write what's done and what's left into it. "
    "Then reply with short reset instructions for the next launch: what was being worked on, what is "
    "done, what is left, and which notes to read (their paths). Also list every change in the "
    "Pending changes table of docs/next-steps/README.md that is built and waiting on a restart: this "
    "restart loads them, so give each one's note path and the hand checks now due. Say which helper "
    "agents you started and what for, if any. The app adds the open tabs, agents, modes and tasks "
    f"itself. End your reply with the line `{RESTART_READY}`."
)
APP_STATE_HEAD = "What the app had open at the restart (written by the app):"
AFTER_RESTART = (
    "After this restart: every agent starts in Manual again (only the user switches one to Auto, "
    "with the button). No task carries over: each task above ended with the restart, so the work "
    "goes on only from these instructions. Helpers opened by name (the + button or a launch) are "
    "gone; reopen one by name when the user wants it. Helpers that start with the app are back, "
    "idle. Usage counts start again from zero. Changes that were waiting on this restart are now "
    "loaded: their hand checks are due."
)
TASK_TEXT_MAX = 200  # characters of a task's text in the state section
RESTART_WAITING = (
    "The task is waiting on the user ({question}), so I didn't restart. Ask the user whether "
    "to restart anyway; if yes, use the RESTART tag with the argument anyway."
)
FALLBACK_NOTE = (
    "The Main Assistant didn't write reset instructions ({why}). The conversation before the "
    "restart, newest last:\n{history}"
)
RESTART_INPUT = "[Restart] The app was just restarted. Reset instructions from the last session:\n"
WORKER_ENDS = (ReportKind.REPLY, ReportKind.DONE, ReportKind.FAILED)


class RestartFlow:
    """The restart of the app from the main tab. `talker` is the module: its `ctx`, `worker_id`,
    `focus`, `main` (the main tab's session), `name`, `task_of` and `hub`. `note`: where the reset
    instructions are saved (None: restarts carry no note). `timeout`: seconds to wait for them."""

    def __init__(self, talker: TalkerModule, note: Path | None, timeout: float) -> None:
        self._talker = talker
        self.note = note
        self._timeout = timeout
        self._timer: asyncio.Task | None = None  # set while waiting for the worker's note
        self.restarting = False  # ShutdownRequested(restart=True) sent: keep the note for the next launch

    @property
    def waiting(self) -> bool:
        return self._timer is not None

    def first_input(self) -> str | None:
        """The last launch's note, as the main tab's first input, if it restarted."""
        if self.note and self.note.is_file():
            return RESTART_INPUT + self.note.read_text(encoding="utf-8").strip()
        return None

    def used(self) -> None:
        """The note was sent: it's used once."""
        if self.note:
            self.note.unlink(missing_ok=True)

    async def close(self) -> None:
        """The module stops: no more waiting; a note is only for the launch right after a restart."""
        if self._timer:
            self._timer.cancel()
            await asyncio.gather(self._timer, return_exceptions=True)
        if self.note and not self.restarting:
            self.note.unlink(missing_ok=True)

    async def ask(self, anyway: bool) -> None:
        """Ask the worker for reset instructions: a message to its task, or a small task of its own.
        The restart follows its `RESTART_READY` reply, or `timeout` with a note of our own."""
        talker = self._talker
        if self._timer is not None or self.restarting:
            return  # already on its way
        task = None
        if (task_id := talker.task_of(talker.worker_id)) is not None:
            status = await talker.hub("hub.status", task_id=task_id)
            if status.is_ok and status.value and not status.value[0].state.is_final:
                task = status.value[0]
        if task is not None and task.state is TaskState.WAITING_FOR_INPUT and not anyway:
            talker.main.status(RESTART_WAITING.format(question=task.question_line or "a question"))
            return
        if task is not None:
            result = await talker.hub("hub.send", text=WRITE_RESET_NOTE, task_id=task.id, pause=True)
        else:
            result = await talker.hub("hub.start", text=WRITE_RESET_NOTE, agent_id=talker.worker_id,
                                      context=self.history_text())  # fmt: skip
        if not result.is_ok:
            await self.restart(FALLBACK_NOTE.format(why=f"couldn't reach it: {result.error}",
                                                    history=self.history_text()))  # fmt: skip
            return
        self._timer = asyncio.create_task(self._fallback(), name="talker:restart")

    async def on_worker_update(self, event: TaskUpdated, agent: str) -> bool:
        """While waiting: the worker's reply with the note (or its failure) restarts the app.
        True when it did, so the update isn't spoken."""
        if self._timer is None or agent != self._talker.worker_id or event.kind not in WORKER_ENDS:
            return False
        if event.kind is ReportKind.FAILED:
            await self.restart(FALLBACK_NOTE.format(why=f"its task failed: {event.text}", history=self.history_text()))
            return True
        if last_line(event.text, RESTART_READY) is not None:
            await self.restart("\n".join(event.text.strip().splitlines()[:-1]))  # without the RESTART_READY line
            return True
        return False

    async def _fallback(self) -> None:
        await asyncio.sleep(self._timeout)
        self._timer = None
        await self.restart(FALLBACK_NOTE.format(why=f"no answer in {self._timeout:g}s", history=self.history_text()))

    async def restart(self, note: str) -> None:
        """Save the reset instructions for the next launch, with the app's own state section
        under them, then ask the app to restart."""
        if self.restarting:
            return
        if self._timer is not None and self._timer is not asyncio.current_task():
            self._timer.cancel()
        self._timer = None
        self.restarting = True
        ctx = self._talker.ctx
        if self.note:
            text = (note.strip() or self.history_text()) + "\n\n" + await self.app_state()
            self.note.parent.mkdir(parents=True, exist_ok=True)
            self.note.write_text(text + "\n", encoding="utf-8")
        ctx.log.info("Restarting; reset instructions saved to %s", self.note)
        ctx.publish(ShutdownRequested(reason="restart", restart=True))

    async def app_state(self) -> str:
        """Facts for the next launch: the tab you were in, every agent with its mode, each open
        task with its question, then what a restart does. Never stops a restart."""
        talker = self._talker
        focus = talker.focus
        lines = [APP_STATE_HEAD, f"- The user was in {talker.name(focus)}'s tab ({focus})."]
        try:
            agents = await talker.ctx.send(ListAgents())
            status = await talker.hub("hub.status")
            tasks = [t for t in (status.value or []) if not t.state.is_final and t.text != WRITE_RESET_NOTE] \
                if status.is_ok else []  # fmt: skip
            for info in agents.value if agents.is_ok and isinstance(agents.value, list) else []:
                working = ", working" if info.working else ""
                about = f" ({info.description})" if info.description else ""
                lines.append(f"- {info.agent_id}{about}: {info.permission_mode.value}{working}")
                for task in (t for t in tasks if t.agent_id == info.agent_id):
                    text = " ".join(task.text.split())
                    text = text if len(text) <= TASK_TEXT_MAX else text[:TASK_TEXT_MAX] + "..."
                    line = f"  - task {task.id} ({task.state.value}): {text}"
                    if task.question:
                        line += f"; waiting on the user: {task.question_line}"
                        line += " (behind its tab's !)" if task.held else ""
                    lines.append(line)
        except Exception as exc:  # noqa: BLE001 - the restart goes on without the details
            talker.ctx.log.warning("Couldn't read the agents for the restart note: %s", exc)
            lines.append(f"- The agents and tasks couldn't be read ({exc}).")
        return "\n".join([*lines, "", AFTER_RESTART])

    def history_text(self) -> str:
        return "\n".join(self._talker.main.history)
