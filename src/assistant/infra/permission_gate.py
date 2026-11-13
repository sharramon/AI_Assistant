"""A task agent's one open question to the user: a tool request its rules don't allow, or an
approval of an app action. Holds its timer, the Auto policy (allow all but `git push`), and the
approval's outcome until the task can read it. `SessionTaskAgent` composes one."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any

from assistant.contracts import PermissionMode, ReportKind, Result, Task

CODE_LOADED = (
    "[App] {action}: {outcome} Continue the task. If it failed, fix what's wrong and ask again, "
    "or end with NEED."
)
APPROVAL_PENDING = "Wait for the user's answer to the approval you asked for first."
GIT_PUSH_BLOCKED = "git push is blocked in Auto. If the task needs one, say so in your summary and the user pushes."
NO_TASK = "No task is running."
TIMED_OUT = "Nobody answered the permission request in time."
_SHELL_TOOLS = ("PowerShell", "Bash")
_GIT_PUSH = re.compile(r"\bgit\s+push\b")

Run = Callable[[], Awaitable[Result]]


class PermissionGate:
    """The open question to the user, at most one: a `can_use_tool` request from the session, or
    an approval (`{"run", "action"}`) the agent asked for. Both go to the user as a `permission`
    report (the same card); unanswered after `timeout` seconds, they're denied.

    In Auto (`mode()`), tool requests are answered here: allowed, except `git push`. An approval
    keeps the task waiting (`waiting`) until its outcome is delivered: the next message at once,
    or, if a turn is running, after it (`take_after_turn`).

    A task that ends waiting on its approval (`park`) leaves it here, tied to its id and out of the
    next task's way: `answer_parked` answers it, and its outcome goes to `parked(task_id, text)`
    (the agent hands it to the Hub), unless the task was given back meanwhile (`unpark`).

    It talks to its agent only through what it's given: `session` (answers and `working`),
    `task()` (the current task), `activity`, `report`, `send` (a message to the session),
    `parked` (a parked task's outcome) and `spawn` (run a coroutine in the background).
    """

    def __init__(
        self,
        session: Any,
        *,
        timeout: float,
        mode: Callable[[], PermissionMode],
        task: Callable[[], Task | None],
        activity: Callable[[str], None],
        report: Callable[[ReportKind, str], None],
        send: Callable[[str], Coroutine[Any, Any, None]],
        spawn: Callable[[Coroutine[Any, Any, Any]], None],
        log: logging.Logger,
        parked: Callable[[str, str], None] = lambda task_id, text: None,
    ) -> None:
        self._session = session
        self._timeout = timeout
        self._mode = mode
        self._task = task
        self._activity = activity
        self._report = report
        self._send = send
        self._spawn = spawn
        self._log = log
        self._request: dict[str, Any] | None = None
        self._timer: asyncio.Task | None = None
        self._waiting = False  # an approval's outcome is still due; the task waits for it
        self._after_turn: str | None = None  # an approval's outcome that came during a turn
        self._on_parked = parked
        self._parked: str | None = None  # the task that ended waiting on its approval
        self._parked_request: dict[str, Any] | None = None  # its approval, still unanswered
        self._parked_timer: asyncio.Task | None = None

    @property
    def parked(self) -> str | None:
        """The id of the task that ended waiting on its approval here, or None."""
        return self._parked

    def park(self, task_id: str) -> None:
        """`task_id` ends waiting (its agent drops it): an open approval, or one whose action
        still runs, stays here for it; anything else is cleared."""
        request = self._request if self.approval_open() else None
        if request is None and not self._waiting:
            self.clear()
            return
        self._drop_parked()
        self._parked, self._parked_request = task_id, request
        if request is not None:
            self._parked_timer, self._timer = self._timer, None
            self._request = None
        self.clear()

    def unpark(self, task_id: str) -> None:
        """`task_id` is given back to its agent before its approval's outcome came: the approval
        is the current task's again."""
        if self._parked != task_id:
            return
        if self._parked_request is not None:
            self.drop()
            self._request, self._timer = self._parked_request, self._parked_timer
        self._waiting = True
        self._parked, self._parked_request, self._parked_timer = None, None, None

    async def answer_parked(self, task_id: str, allow: bool) -> Result:
        """The user's answer to the approval a parked task left."""
        request = self._parked_request
        if self._parked != task_id or request is None:
            return Result.invalid_arguments(f"No permission request is open for {task_id!r}")
        if self._parked_timer is not None:
            self._parked_timer.cancel()
        self._parked_request, self._parked_timer = None, None
        self._approval_answered(request, allow, task_id)
        return Result.ok()

    def _drop_parked(self) -> None:
        if self._parked_timer is not None:
            self._parked_timer.cancel()
        self._parked, self._parked_request, self._parked_timer = None, None, None

    @property
    def request(self) -> dict[str, Any] | None:
        """The open question, or None."""
        return self._request

    @property
    def waiting(self) -> bool:
        """An approval's outcome is still due: a turn that ends meanwhile isn't the task's end."""
        return self._waiting

    def approval_open(self) -> bool:
        """The open question is an approval (it outlives a turn; a tool request doesn't)."""
        return self._request is not None and "run" in self._request

    def drop(self) -> None:
        """Forget the open question and stop its timer."""
        self._request = None
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def clear(self) -> None:
        """The task ended: nothing open, nothing due."""
        self.drop()
        self._waiting, self._after_turn = False, None

    def take_after_turn(self) -> str | None:
        """An approval's outcome that came during the turn, once; the task no longer waits."""
        outcome, self._after_turn = self._after_turn, None
        if outcome is not None:
            self._waiting = False
        return outcome

    def on_tool_request(self, event: dict[str, Any], accepting: bool) -> None:
        """The session wants a tool its rules don't allow: refuse it when no task takes questions
        (`accepting` False) or an approval is open, answer it in Auto, else put it to the user."""
        if not accepting:
            self._spawn(self._session.answer_permission(event, False, NO_TASK))
            return
        if self.approval_open():  # one question to the user at a time
            self._spawn(self._session.answer_permission(event, False, APPROVAL_PENDING))
            return
        if self._mode() is PermissionMode.AUTO:  # switched live: no card, the agent answers
            self._spawn(self.auto_answer(event))
            return
        self._open(event)
        self._activity(f"asks permission: {describe_request(event)}")
        self._report(ReportKind.PERMISSION, describe_request(event))

    def auto_answer(self, event: dict[str, Any]) -> Coroutine[Any, Any, None]:
        """Auto in a process started in Manual: allow the tool, except `git push`. Returns the
        answer to write (spawn or await it)."""
        what = describe_request(event)
        if is_git_push(event):
            self._activity(f"refused in Auto: {what}")
            return self._session.answer_permission(event, False, GIT_PUSH_BLOCKED)
        self._activity(f"allowed in Auto: {what}")
        return self._session.answer_permission(event, True)

    async def answer_open_in_auto(self) -> bool:
        """Switched to Auto: answer an open tool request the Auto way. True when one was answered."""
        if self._request is None or self.approval_open():
            return False
        request = self._request
        self.drop()
        try:
            await self.auto_answer(request)
        except Exception as exc:
            self._log.warning("Couldn't answer the open request in Auto: %s", exc)
            return False
        return True

    async def answer(self, allow: bool) -> Result:
        """The user's answer to the open question."""
        request = self._request
        if request is None:
            return Result.invalid_arguments("No permission request is open")
        self.drop()
        if "run" in request:  # an approval (a reload, an add, a helper launch), not a tool
            task = self._task()
            self._approval_answered(request, allow, task.id if task else "")
            return Result.ok()
        try:
            await self._session.answer_permission(request, allow)
        except Exception as exc:
            return Result.failed(f"Couldn't answer the permission request: {exc}")
        self._activity(f"permission {'allowed' if allow else 'denied'}: {describe_request(request)}")
        return Result.ok()

    def ask(self, action: str, run: Run) -> None:
        """Put `action` to the user (the same card as a tool); on Allow `run` runs. In Auto
        (this agent's own mode) there's no card: it runs at once. The one Auto check for
        approvals (a reload, an add, a helper launch)."""
        if self._mode() is PermissionMode.AUTO:
            self._activity(f"allowed in Auto: {action}")
            self.run_now(action, run)
            return
        request = {"run": run, "action": action}
        self._open(request)
        self._waiting = True
        self._activity(f"asks permission: {action}")
        self._report(ReportKind.PERMISSION, action)

    def run_now(self, action: str, run: Run) -> None:
        """Run an approved action at once (Auto); the task waits for its outcome."""
        self._waiting = True
        task = self._task()
        self._spawn(self._run_approved(run, action, task.id if task else ""))

    def _approval_answered(self, request: dict[str, Any], allow: bool, task_id: str) -> None:
        self._activity(f"permission {'allowed' if allow else 'denied'}: {request['action']}")
        if allow:
            self._spawn(self._run_approved(request["run"], request["action"], task_id))
        else:
            self._outcome(task_id, CODE_LOADED.format(action=request["action"], outcome="the user said no."))

    def _outcome(self, task_id: str, text: str) -> None:
        """An approval's outcome for `task_id`: to the session if it's the current task, to
        `parked` if it ended waiting on it; dropped if it ended otherwise."""
        if task_id and task_id == self._parked:
            self._parked, self._parked_request, self._parked_timer = None, None, None
            self._on_parked(task_id, text)
            return
        task = self._task()
        if task is not None and task.id == task_id:
            self.deliver(text)

    def deliver(self, text: str) -> None:
        """An approval's outcome: the next message now, or when the running turn ends."""
        if self._session.working:
            self._after_turn = text
            return
        self._waiting = False
        self._spawn(self._send(text))

    def _open(self, request: dict[str, Any]) -> None:
        self.drop()
        self._request = request
        self._timer = asyncio.create_task(self._expiry(request))

    async def _expiry(self, request: dict[str, Any]) -> None:
        await asyncio.sleep(self._timeout)
        if self._parked_request is request:  # its task ended waiting on it
            self._activity(f"permission timed out, denied: {request['action']}")
            self._outcome(self._parked or "", CODE_LOADED.format(action=request["action"],
                                                                 outcome="nobody answered in time."))  # fmt: skip
            return
        if self._request is not request:
            return
        self._request = None
        if "run" in request:
            self._activity(f"permission timed out, denied: {request['action']}")
            self.deliver(CODE_LOADED.format(action=request["action"], outcome="nobody answered in time."))
            return
        self._activity(f"permission timed out, denied: {describe_request(request)}")
        await self._session.answer_permission(request, False, TIMED_OUT)

    async def _run_approved(self, run: Run, action: str, task_id: str) -> None:
        self._activity(f"{action}…")
        try:
            result = await run()
        except Exception as exc:
            self._log.exception("%s failed", action)
            result = Result.failed(str(exc))
        said = f" {result.value}" if result.is_ok and isinstance(result.value, str) and result.value else ""
        outcome = f"done.{said}" if result.is_ok else f"failed: {result.error}"
        self._activity(f"{action}: {outcome}")
        self._outcome(task_id, CODE_LOADED.format(action=action, outcome=outcome))


def describe_request(event: dict[str, Any]) -> str:
    """`Write C:\\repo\\x.md` for a can_use_tool request."""
    request = event.get("request", {})
    return f"{request.get('tool_name', '?')} {summarize(request.get('input', {}))}"


def is_git_push(event: dict[str, Any]) -> bool:
    """A shell request whose command runs `git push` anywhere in it."""
    request = event.get("request", {})
    command = str(request.get("input", {}).get("command", ""))
    return request.get("tool_name") in _SHELL_TOOLS and bool(_GIT_PUSH.search(command))


def summarize(tool_input: dict[str, Any]) -> str:
    """A tool call's input in a few words: its path, pattern, command or URL, else its JSON."""
    for key in ("file_path", "path", "pattern", "command", "url"):
        if key in tool_input:
            return str(tool_input[key])
    return json.dumps(tool_input)[:80]
