"""The agents' one MCP door: the relay claude starts, the hub's endpoint, the core behind it."""

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from assistant.contracts import IModuleDoor, PermissionMode, ReloadModule
from assistant.core import App
from assistant.infra import ClaudeSession, claude_command
from assistant.infra.mcp_door import READ_ONLY, TOKEN_HEADER, TOOL_NAMES
from assistant.modules.agent_hub import AgentHubModule
from assistant.modules.echo_orchestrator import EchoOrchestrator
from assistant.modules.main_assistant.module import build_command
from tests.support import wait_until


@pytest.fixture
async def app():
    config = {"modules": {"enabled": ["agent_hub", "echo_orchestrator"]}, "core": {}}
    app = App([AgentHubModule, EchoOrchestrator], config)
    await app.start()
    try:
        yield app
    finally:
        await app.stop()


class Relay:
    """The relay as claude runs it: `python -m assistant.infra.mcp_door`, JSON-RPC on stdio."""

    def __init__(self, server: dict) -> None:
        self.server, self.proc, self.next_id = server, None, 0

    async def __aenter__(self):
        env = {**os.environ, **self.server["env"]}
        self.proc = await asyncio.create_subprocess_exec(
            self.server["command"], *self.server["args"], env=env,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        )  # fmt: skip
        return self

    async def __aexit__(self, *exc):
        self.proc.stdin.close()
        await asyncio.wait_for(self.proc.wait(), 10)

    async def ask(self, method: str, params: dict | None = None) -> dict:
        self.next_id += 1
        message = {"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params or {}}
        self.proc.stdin.write((json.dumps(message) + "\n").encode())
        await self.proc.stdin.drain()
        reply = json.loads(await asyncio.wait_for(self.proc.stdout.readline(), 20))
        assert reply["id"] == self.next_id
        return reply

    async def call(self, tool: str, arguments: dict | None = None) -> dict:
        result = (await self.ask("tools/call", {"name": tool, "arguments": arguments or {}}))["result"]
        return json.loads(result["content"][0]["text"]) | {"isError": result["isError"]}


async def test_the_relay_reaches_the_menus_through_the_core(app):
    config = app.container.get_one(IModuleDoor).mcp_config()
    async with Relay(config["mcpServers"]["modules"]) as relay:
        init = await relay.ask("initialize", {"protocolVersion": "2025-06-18"})
        assert init["result"]["capabilities"] == {"tools": {}}
        relay.proc.stdin.write(b'{"jsonrpc": "2.0", "method": "notifications/initialized"}\n')  # no reply
        tools = (await relay.ask("tools/list"))["result"]["tools"]
        assert [t["name"] for t in tools] == ["list_modules", "show_menu", "use_item"]

        listed = await relay.call("list_modules")
        ids = [m["id"] for m in listed["value"]]
        assert {"agent_hub", "echo_orchestrator", "core"} <= set(ids) and not listed["isError"]
        menu = await relay.call("show_menu", {"module_id": "echo_orchestrator"})
        assert [item["name"] for item in menu["value"]] == ["echo.say"]
        said = await relay.call("use_item", {"name": "echo.say", "args": {"text": "hi"}})
        assert said["value"] == "Echo: hi" and not said["isError"]

        wrong = await relay.call("use_item", {"name": "echo.say", "args": {}})  # the menu checks the inputs
        assert wrong["isError"] and wrong["status"] == "invalid_arguments"
        missing = await relay.call("show_menu", {"module_id": "nope"})
        assert missing["isError"]


async def test_the_endpoint_wants_its_token(app):
    url = app.container.get_one(IModuleDoor).mcp_config()["mcpServers"]["modules"]["env"]["ASSISTANT_DOOR_URL"]
    host, port = url.removeprefix("http://").split(":")
    reader, writer = await asyncio.open_connection(host, int(port))
    body = b'{"tool": "list_modules"}'
    writer.write(b"POST /tool HTTP/1.1\r\n" + f"{TOKEN_HEADER}: wrong\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body)
    await writer.drain()
    assert (await reader.read()).startswith(b"HTTP/1.1 403")
    writer.close()


async def test_a_hub_reload_keeps_the_same_door(app):
    before = app.container.get_one(IModuleDoor).mcp_config()
    assert (await app.router.send(ReloadModule(module_id="agent_hub"))).is_ok
    assert app.container.get_one(IModuleDoor).mcp_config() == before  # a running session's relay keeps working


def test_the_worker_session_gets_the_door(tmp_path):
    door = {"mcpServers": {"modules": {"command": sys.executable}}}
    command = build_command({}, tmp_path, PermissionMode.MANUAL, door)
    assert json.loads(command[command.index("--mcp-config") + 1]) == door
    allowed = command[command.index("--allowedTools") + 1].split(",")
    assert set(READ_ONLY) <= set(allowed) and TOOL_NAMES[2] not in allowed  # use_item asks in Manual
    assert any("list_modules" in arg for arg in command)  # the prompt tells the worker about the door
    assert "--mcp-config" not in build_command({}, tmp_path, PermissionMode.MANUAL)


async def test_the_talker_session_gets_the_door():
    from assistant.modules.talker import TalkerModule
    from tests.test_agents import FAKE

    config = {"modules": {"enabled": ["agent_hub", "talker"], "talker": {"program": FAKE}}, "core": {}}
    app = App([AgentHubModule, TalkerModule], config)
    await app.start()
    try:
        command = app._lifecycle._active["talker"][0]._command()
        door = app.container.get_one(IModuleDoor).mcp_config()
        assert json.loads(command[command.index("--mcp-config") + 1]) == door
        assert set(TOOL_NAMES) <= set(command[command.index("--allowedTools") + 1].split(","))
    finally:
        await app.stop()


@pytest.mark.claude
async def test_real_claude_calls_a_menu_item_through_the_door(app, tmp_path):
    """Needs a logged-in claude CLI (a paid call): `pytest -m claude tests/test_mcp_door.py`."""
    door = app.container.get_one(IModuleDoor).mcp_config()
    events: list[dict] = []
    command = claude_command(model="sonnet", tools="", permission_mode="bypassPermissions",
                             allowed=list(TOOL_NAMES), mcp_config=door)  # fmt: skip
    session = ClaudeSession(command, on_event=events.append, cwd=Path(tmp_path))
    await session.start()
    await session.send("Use your modules tools: show the menu of echo_orchestrator, then use echo.say "
                       "with the text PONG. Reply with what it returned.")  # fmt: skip
    await wait_until(lambda: any(e["type"] == "result" for e in events), 120)
    assert "Echo: PONG" in events[-1]["result"]
    await session.close()
