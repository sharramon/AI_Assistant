"""The permission mode (Manual / Auto): the command line per mode, the Hub's command and the
event, Manual at launch, the Talker limited to Manual, and the temp UI's button and cards."""

import asyncio
import json

from assistant.contracts import (
    InputReceived,
    ListAgents,
    PermissionMode,
    PermissionModeChanged,
    ReportKind,
    ResponseReady,
    SetPermissionMode,
    StartTask,
    Status,
    TaskState,
    TaskUpdated,
)
from assistant.core import App
from assistant.infra import ClaudeSession
from assistant.modules.agent_hub import AgentHubModule
from assistant.modules.main_assistant import MainAssistantModule
from assistant.modules.main_assistant.module import AUTO_BLOCKED, build_command
from assistant.modules.talker import TalkerModule
from assistant.modules.temp_ui import TempUIModule
from tests.support import wait_until
from tests.test_agents import FAKE, TIMEOUT, next_matching, report, start_hub
from tests.test_temp_ui import request, ui_port


def _arg(command: list[str], flag: str) -> str:
    return command[command.index(flag) + 1]


def test_each_mode_maps_to_its_command_line(tmp_path):
    config = {"allowed_commands": ["ruff check"]}
    manual = build_command(config, tmp_path, PermissionMode.MANUAL)
    auto = build_command(config, tmp_path, PermissionMode.AUTO)

    assert _arg(manual, "--permission-mode") == "acceptEdits"
    assert "--disallowedTools" not in manual
    assert "NEED: Risky:" not in _arg(manual, "--append-system-prompt")

    assert _arg(auto, "--permission-mode") == "bypassPermissions"
    assert set(AUTO_BLOCKED) == {"PowerShell(git push)", "PowerShell(git push *)", "Bash(git push)", "Bash(git push *)"}
    start = auto.index("--disallowedTools") + 1
    assert auto[start:start + len(AUTO_BLOCKED)] == list(AUTO_BLOCKED)  # separate arguments
    assert "NEED: Risky:" in _arg(auto, "--append-system-prompt")

    # Both keep the standing rules and the prompt tool, so a live switch to Manual asks again.
    for command in (manual, auto):
        assert "ruff check" in _arg(command, "--allowedTools")
        assert _arg(command, "--permission-prompt-tool") == "stdio"


async def test_session_reads_a_callable_command_on_every_start():
    calls = []

    def command() -> list[str]:
        calls.append(1)
        return FAKE

    session = ClaudeSession(command)
    for _ in range(2):
        await session.start()
        await session.close()
    assert len(calls) == 2


async def test_manual_at_launch_and_unknown_agents_refused(tmp_path):
    app, _ = await start_hub(tmp_path)
    try:
        assert (await app.router.send(ListAgents())).value[0].permission_mode is PermissionMode.MANUAL
        result = await app.router.send(SetPermissionMode(agent_id="nobody", mode=PermissionMode.AUTO))
        assert result.status is Status.INVALID_ARGUMENTS
        assert (await app.router.send(ListAgents())).value[0].permission_mode is PermissionMode.MANUAL
    finally:
        await app.stop()


async def test_switch_applies_now_or_from_the_next_task(tmp_path):
    transcript = tmp_path / "main_assistant.jsonl"
    app, updates = await start_hub(tmp_path, transcript=str(transcript))
    changes: asyncio.Queue[PermissionModeChanged] = asyncio.Queue()
    app.bus.subscribe(PermissionModeChanged, changes.put)

    async def switch(mode: PermissionMode) -> PermissionModeChanged:
        assert (await app.router.send(SetPermissionMode(agent_id="main_assistant", mode=mode))).is_ok
        return await asyncio.wait_for(changes.get(), TIMEOUT)

    try:
        # Idle: applies now, and the next session's command is built for Auto.
        assert (await switch(PermissionMode.AUTO)).applies == "now"
        assert (await app.router.send(ListAgents())).value[0].permission_mode is PermissionMode.AUTO
        module = app._lifecycle._active["main_assistant"][0]
        assert "bypassPermissions" in module._session._command_source()

        await app.router.send(StartTask(text="ASKME first"))  # starts in Auto, then waits
        await next_matching(updates, report(ReportKind.NEED))
        # Mid-task to Manual: the running session switches at once (a control request).
        assert (await switch(PermissionMode.MANUAL)).applies == "now"
        # Mid-task to Auto: its prompt is fixed, so only from the next task.
        assert (await switch(PermissionMode.AUTO)).applies == "next_task"
    finally:
        await app.stop()
    lines = [json.loads(line) for line in transcript.read_text(encoding="utf-8").splitlines()]
    controls = [ln["msg"]["request"] for ln in lines if ln["dir"] == "in" and ln["msg"]["type"] == "control_request"]
    assert controls == [{"subtype": "set_permission_mode", "mode": "acceptEdits"}]


async def test_talker_can_switch_back_to_manual_never_to_auto(tmp_path):
    config = {
        "modules": {
            "enabled": ["agent_hub", "main_assistant", "talker"],
            "main_assistant": {"program": FAKE, "workspace": str(tmp_path)},
            "talker": {"program": FAKE},
        },
        "core": {},
    }
    app = App([AgentHubModule, MainAssistantModule, TalkerModule], config)
    replies: asyncio.Queue[ResponseReady] = asyncio.Queue()
    changes: asyncio.Queue[PermissionModeChanged] = asyncio.Queue()
    app.bus.subscribe(ResponseReady, replies.put)
    app.bus.subscribe(PermissionModeChanged, changes.put)
    await app.start()
    try:
        # The fake Talker repeats what it's sent, so the input is its reply.
        app.bus.publish(InputReceived(text="Sure. <<MODE: auto>>", source="test"))
        refused = await next_matching(replies, lambda e: e.text.startswith("[Status]"))
        assert "Only the user can switch the Main Assistant to Auto" in refused.text
        assert changes.empty()
        assert (await app.router.send(ListAgents())).value[0].permission_mode is PermissionMode.MANUAL

        # You switch to Auto with the button; the Talker hears it once, with your next message.
        await app.router.send(SetPermissionMode(agent_id="main_assistant", mode=PermissionMode.AUTO))
        await asyncio.wait_for(changes.get(), TIMEOUT)
        app.bus.publish(InputReceived(text="Back to manual <<MODE: manual>>", source="test"))
        reply = await next_matching(replies, lambda e: "Back to manual" in e.text)
        assert reply.text.startswith("[Mode] worker: auto\n")
        assert (await asyncio.wait_for(changes.get(), TIMEOUT)).mode is PermissionMode.MANUAL
        assert (await app.router.send(ListAgents())).value[0].permission_mode is PermissionMode.MANUAL
    finally:
        await app.stop()


async def _connect_items(port: int) -> list[dict]:
    """What /events sends on connect, up to its last state item, the worker's mode."""
    reader, writer = await request(port, b"GET /events HTTP/1.1\r\n\r\n")
    items: list[dict] = []
    async with asyncio.timeout(TIMEOUT):
        while not items or items[-1].get("kind") != "mode":
            line = await reader.readline()
            if line.startswith(b"data: "):
                items.append(json.loads(line[6:]))
    writer.close()
    return items


async def test_temp_ui_button_mode_and_risky_card(tmp_path):
    config = {
        "modules": {
            "enabled": ["agent_hub", "main_assistant", "temp_ui"],
            "main_assistant": {"program": FAKE, "workspace": str(tmp_path)},
            "temp_ui": {"port": 0, "window": "none"},
        },
        "core": {},
    }
    app = App([AgentHubModule, MainAssistantModule, TempUIModule], config)
    await app.start()
    port = ui_port(app)
    ui = app._lifecycle._active["temp_ui"][0]
    try:
        assert (await _connect_items(port))[-1] == {"kind": "mode", "mode": "manual", "applies": "now"}

        body = json.dumps({"mode": "auto"}).encode()
        reader, writer = await request(
            port, b"POST /permission-mode HTTP/1.1\r\nContent-Length: %d\r\n\r\n%s" % (len(body), body)
        )
        assert json.loads((await reader.read()).split(b"\r\n\r\n", 1)[1])["ok"] is True
        writer.close()

        app.bus.publish(TaskUpdated(
            task_id="t1", state=TaskState.WAITING_FOR_INPUT, kind=ReportKind.NEED, text="Risky: delete the old logs",
        ))
        await wait_until(lambda: any(i["kind"] == "risky" for i in ui._history), TIMEOUT)

        items = await _connect_items(port)
        assert items[-1] == {"kind": "mode", "mode": "auto", "applies": "now"}
        talker = {i["kind"]: i for i in items if i.get("pane") == "talker"}
        assert talker["note"]["text"] == "Main Assistant: Auto, no permission prompts"
        assert talker["risky"]["text"] == "delete the old logs" and talker["risky"]["task_id"] == "t1"
        worker = [i["text"] for i in items if i.get("pane") == "worker" and i["kind"] == "task"]
        assert "permission mode: auto" in worker
        assert "task t1 paused: risky step: delete the old logs" in worker
    finally:
        await app.stop()
