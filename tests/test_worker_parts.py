"""The task agent's composed parts: PermissionGate, HandoffKeeper, LastLineTags, and ProfileAgent's session factory."""

from __future__ import annotations

import asyncio
import logging

from assistant.contracts import AddModule, PermissionMode, ReloadModule, ReportKind, Result, Task
from assistant.infra import HandoffKeeper, LastLineTags, PermissionGate, ProfileAgent
from assistant.infra.permission_gate import GIT_PUSH_BLOCKED, NO_TASK, describe_request, is_git_push
from assistant.infra.session_agent import add_module_request, reload_request


class _Session:
    def __init__(self):
        self.working = False
        self.answers: list[tuple] = []

    async def answer_permission(self, event, allow, message=None):
        self.answers.append((event, allow, message))


def _tool(name="Write", **tool_input):
    return {"type": "control_request", "request": {"subtype": "can_use_tool", "tool_name": name, "input": tool_input}}


_TASK = Task(id="t1", text="x")


def _gate(session, mode=PermissionMode.MANUAL, task=_TASK, timeout=60.0):
    seen = {"activity": [], "reports": [], "sent": []}
    background: list[asyncio.Task] = []

    async def send(text):
        seen["sent"].append(text)

    gate = PermissionGate(
        session, timeout=timeout, mode=lambda: mode, task=lambda: task,
        activity=seen["activity"].append, report=lambda kind, text: seen["reports"].append((kind, text)),
        send=send, spawn=lambda coro: background.append(asyncio.ensure_future(coro)),
        log=logging.getLogger("test"),
    )  # fmt: skip
    return gate, seen, background


async def test_gate_puts_a_tool_request_to_the_user_and_answers_once():
    session = _Session()
    gate, seen, _ = _gate(session)
    event = _tool(file_path="C:\\x.md")
    gate.on_tool_request(event, accepting=True)
    assert gate.request is event
    assert seen["reports"] == [(ReportKind.PERMISSION, "Write C:\\x.md")]
    assert (await gate.answer(True)).is_ok
    assert session.answers == [(event, True, None)]
    assert not (await gate.answer(True)).is_ok  # nothing open any more


async def test_gate_refuses_without_a_task_and_answers_itself_in_auto():
    session = _Session()
    gate, _, background = _gate(session)
    gate.on_tool_request(_tool(), accepting=False)
    auto, _, auto_background = _gate(session, mode=PermissionMode.AUTO)
    auto.on_tool_request(_tool("PowerShell", command="git push origin main"), accepting=True)
    auto.on_tool_request(_tool("PowerShell", command="git status"), accepting=True)
    await asyncio.gather(*background, *auto_background)
    assert [(allow, message) for _, allow, message in session.answers] == [
        (False, NO_TASK), (False, GIT_PUSH_BLOCKED), (True, None),
    ]
    assert auto.request is None


async def test_gate_approval_waits_and_delivers_after_the_turn():
    session = _Session()
    gate, seen, background = _gate(session)
    gate.ask("Reload x", lambda: asyncio.sleep(0, Result.ok("reloaded")))
    assert gate.approval_open() and gate.waiting
    session.working = True  # the outcome arrives during a turn
    assert (await gate.answer(True)).is_ok
    await asyncio.gather(*background)
    assert gate.waiting and seen["sent"] == []
    outcome = gate.take_after_turn()
    assert "Reload x: done. reloaded" in outcome
    assert not gate.waiting and gate.take_after_turn() is None


async def test_gate_answers_an_open_request_when_switched_to_auto():
    session = _Session()
    gate, _, _ = _gate(session)
    gate.on_tool_request(_tool(), accepting=True)
    assert await gate.answer_open_in_auto()
    assert gate.request is None and session.answers[0][1] is True


async def test_gate_denies_an_unanswered_request_after_its_timeout():
    session = _Session()
    gate, _, _ = _gate(session, timeout=0.01)
    gate.on_tool_request(_tool(), accepting=True)
    await asyncio.sleep(0.05)
    assert gate.request is None and session.answers[0][1] is False


def test_request_helpers():
    assert describe_request(_tool(command="ls")) == "Write ls"
    assert is_git_push(_tool("Bash", command="cd x && git  push"))
    assert not is_git_push(_tool("Write", command="git push"))


def test_handoff_keeper_counts_to_its_maximum():
    keeper = HandoffKeeper(max_handoffs=2)
    assert keeper.take() and keeper.progress("a.md") == "Handed off to a fresh session (1): a.md"
    assert keeper.take() and not keeper.take()
    assert "2 times" in keeper.too_many("b.md")
    keeper.reset()
    assert keeper.count == 0 and keeper.take() and keeper.take()
    assert keeper.renew() == 2 and keeper.count == 1  # the user's go-ahead: a fresh allowance
    assert keeper.take() and not keeper.take()
    assert "the user answered: go on" in HandoffKeeper.answered(2, "go on")
    assert "handoff-t9.md" in HandoffKeeper.reset_request("t9")
    assert "150k" in HandoffKeeper.reminder("150k", "150k", "t9")


def test_handoff_texts_carry_the_chrome_lines():
    """A fresh session can't reach the last one's Chrome tabs (chrome-tab-after-reset.md)."""
    from assistant.infra.agent_profile import BASICS_BLOCK
    from assistant.infra.handoff_keeper import HANDED_OFF
    from assistant.infra.session_agent import CONTEXT_AGAIN

    assert "Chrome tab" in HandoffKeeper.reset_request("t9")
    assert "Chrome tab" in HandoffKeeper.reminder("150k", "150k", "t9")
    assert "reopen the note's URLs" in HANDED_OFF.format(text="x", note="n.md")
    assert "reopen the note's URLs" in CONTEXT_AGAIN.format(notes="n")
    assert "Chrome tabs belong to your session" in BASICS_BLOCK


def test_last_line_tags_try_entries_in_order_and_pass_on():
    seen = []
    tags = LastLineTags().add("RELOAD:", lambda arg: bool(arg) and not seen.append(("reload", arg)))
    tags.add("NEED:", lambda arg: not seen.append(("need", arg)))
    assert tags.prefixes == ("RELOAD:", "NEED:")
    assert tags.dispatch("Done.\n**NEED: which one?**")
    assert not tags.dispatch("RELOAD:")  # the handler passed it on, and no other entry matched
    assert not tags.dispatch("All done.")
    assert seen == [("need", "which one?")]


def test_code_requests_from_last_lines():
    command, action = reload_request("`talker` now")
    assert isinstance(command, ReloadModule) and (command.module_id, command.now) == ("talker", True)
    assert "now (cuts in)" in action and reload_request("  ") is None
    added = add_module_request("weather")[0]
    assert isinstance(added, AddModule) and added.package == "weather"
    assert add_module_request("") is None


def test_profile_agent_builds_its_session_with_the_factory(tmp_path):
    made = []

    class _FakeSession:
        def __init__(self, command, **kwargs):
            self.command, self.kwargs = command, kwargs
            self.on_event = None
            made.append(self)

    class _Ctx:
        log = logging.getLogger("test")

    agent = ProfileAgent(_Ctx(), "worker", {"workspace": str(tmp_path)}, "prompt", session_factory=_FakeSession)
    assert made == [agent.session] and agent.session.kwargs["cwd"] == tmp_path.resolve()
    assert agent.session.on_event is not None  # the SessionTaskAgent took its events
