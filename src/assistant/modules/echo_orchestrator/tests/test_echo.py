"""echo_orchestrator's own tests: the echo, `/tools`, and its one menu item. Uses only the shared test kit."""

import asyncio

from assistant.contracts import InputReceived, InvokeTool, ResponseReady
from assistant.core import App
from assistant.modules.echo_orchestrator import EchoOrchestrator
from assistant.testkit import make_config


async def ask(app: App, text: str) -> str:
    replies: asyncio.Queue[ResponseReady] = asyncio.Queue()
    app.bus.subscribe(ResponseReady, replies.put)
    app.bus.publish(InputReceived(text=text, source="test"))
    return (await asyncio.wait_for(replies.get(), 1)).text


async def test_it_echoes_and_lists_the_tools():
    app = App([EchoOrchestrator], make_config("echo_orchestrator"))
    await app.start()
    try:
        assert await ask(app, "hi") == "Echo: hi"
        assert "echo.say" in (await ask(app, "/tools")).removeprefix("Tools: ").split(", ")
    finally:
        await app.stop()


async def test_its_menu_item_says_the_text():
    assert EchoOrchestrator.menu.names() == ["echo.say"]
    app = App([EchoOrchestrator], make_config("echo_orchestrator"))
    await app.start()
    try:
        assert (await app.router.send(InvokeTool(name="echo.say", args={"text": "hi"}))).value == "Echo: hi"
    finally:
        await app.stop()
