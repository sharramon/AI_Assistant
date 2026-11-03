"""The temporary two-pane UI: the page, posting input, and the event stream."""

import asyncio
import json

from assistant.contracts import (
    AgentActivity,
    InputReceived,
    ReportKind,
    ResponseReady,
    TaskState,
    TaskUpdated,
)
from assistant.core import App
from assistant.modules.temp_ui import TempUIModule


async def request(port: int, raw: bytes) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(raw)
    await writer.drain()
    return reader, writer


async def read_events(port: int, count: int) -> list[dict]:
    """The first `count` items on /events, after its leading `hello`."""
    reader, writer = await request(port, b"GET /events HTTP/1.1\r\n\r\n")
    items = []
    async with asyncio.timeout(2):
        while len(items) < count + 1:
            line = await reader.readline()
            if line.startswith(b"data: "):
                items.append(json.loads(line[6:]))
    writer.close()
    assert items[0]["kind"] == "hello" and items[0]["launch"]
    return items


def ui_port(app: App) -> int:
    return int(app._lifecycle._active["temp_ui"][0].url.rsplit(":", 1)[1].strip("/"))


async def test_each_launch_has_its_own_id():
    # The page closes itself when the id changes on reconnect (a relaunch opened a fresh window).
    launches = []
    for _ in range(2):
        config = {"modules": {"enabled": ["temp_ui"], "temp_ui": {"port": 0, "window": "none"}}, "core": {}}
        app = App([TempUIModule], config)
        await app.start()
        try:
            first, again = await read_events(ui_port(app), 0), await read_events(ui_port(app), 0)
            assert first[0]["launch"] == again[0]["launch"]
            launches.append(first[0]["launch"])
        finally:
            await app.stop()
    assert launches[0] != launches[1]


async def test_page_input_and_events():
    config = {"modules": {"enabled": ["temp_ui"], "temp_ui": {"port": 0, "window": "none"}}, "core": {}}
    app = App([TempUIModule], config)
    inputs: asyncio.Queue[InputReceived] = asyncio.Queue()
    app.bus.subscribe(InputReceived, inputs.put)
    await app.start()
    port = int(app._lifecycle._active["temp_ui"][0].url.rsplit(":", 1)[1].strip("/"))
    try:
        reader, writer = await request(port, b"GET / HTTP/1.1\r\nHost: x\r\n\r\n")
        page = await reader.read()
        assert b"200 OK" in page and b"Main Assistant" in page
        writer.close()

        body = json.dumps({"text": "hello"}).encode()
        reader, writer = await request(
            port, b"POST /say HTTP/1.1\r\nContent-Length: %d\r\n\r\n%s" % (len(body), body)
        )
        assert b"204" in await reader.read()
        writer.close()
        said = await asyncio.wait_for(inputs.get(), 2)
        assert said.text == "hello" and said.source == "temp_ui"

        app.bus.publish(ResponseReady(text="hi there"))
        app.bus.publish(AgentActivity(agent_id="main_assistant", text="→ Write poems.txt"))
        items = (await read_events(port, 3))[1:]
        assert [(i["pane"], i["kind"]) for i in items] == [("talker", "you"), ("talker", "talker"), ("worker", "tool")]
    finally:
        await app.stop()


async def test_permission_card_on_talker_side():
    config = {"modules": {"enabled": ["temp_ui"], "temp_ui": {"port": 0, "window": "none"}}, "core": {}}
    app = App([TempUIModule], config)
    await app.start()
    port = int(app._lifecycle._active["temp_ui"][0].url.rsplit(":", 1)[1].strip("/"))
    try:
        app.bus.publish(
            TaskUpdated(task_id="t1", state=TaskState.WAITING_FOR_INPUT, kind=ReportKind.PERMISSION, text="Bash rm x")
        )
        app.bus.publish(TaskUpdated(task_id="t1", state=TaskState.RUNNING, text="permission allowed"))
        items = (await read_events(port, 4))[1:]
        # The Allow / Deny card and its answer go to the Talker pane; the worker pane only logs them.
        assert [(i["pane"], i["kind"]) for i in items] == [
            ("talker", "permission"),
            ("worker", "task"),
            ("talker", "answered"),
            ("worker", "task"),
        ]
        assert items[0]["task_id"] == "t1" and items[0]["text"] == "Bash rm x"
        assert "asks permission: Bash rm x" in items[1]["text"]
        assert "permission allowed" in items[3]["text"]
    finally:
        await app.stop()
