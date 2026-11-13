"""Start on use: a tool call turns on the module that is off and has the tool, if its config allows."""

import asyncio

from assistant.contracts import (
    AgentActivity,
    DeactivateModule,
    InvokeTool,
    Manifest,
    Menu,
    ModuleContext,
    ModuleProtocol,
    Result,
    Status,
    Task,
)
from assistant.core import App
from assistant.infra import SessionTaskAgent
from assistant.testkit import StubContext, StubSession

menu = Menu()


class Pages(ModuleProtocol):
    manifest = Manifest(id="pages", description="a viewer stand-in")
    menu = menu
    starts = 0
    fail = False

    async def init(self, ctx: ModuleContext) -> None:
        pass

    async def start(self) -> None:
        type(self).starts += 1
        await asyncio.sleep(0.05)  # long enough for a second call to arrive meanwhile
        if type(self).fail:
            raise RuntimeError("no window")

    @menu.item("pages.open", "Open a page", {"path": {"type": "string"}}, required=["path"])
    async def open(self, path: str) -> Result:
        return Result.ok({"opened": path})


def make_app(start_on_use: bool = True) -> App:
    Pages.starts, Pages.fail = 0, False
    return App([Pages], {"modules": {"enabled": [], "pages": {"start_on_use": start_on_use}}, "core": {}})


async def test_a_tool_call_turns_its_module_on():
    app = make_app()
    await app.start()
    try:
        result = await app.router.send(InvokeTool(name="pages.open", args={"path": "a.html"}))
        assert result.is_ok and result.value == {"opened": "a.html"}
        assert "pages" in app._lifecycle._active and Pages.starts == 1
    finally:
        await app.stop()


async def test_only_modules_that_allow_it_start():
    app = make_app(start_on_use=False)
    await app.start()
    try:
        result = await app.router.send(InvokeTool(name="pages.open", args={"path": "a.html"}))
        assert result.status is Status.NOT_AVAILABLE and Pages.starts == 0
        unknown = await app.router.send(InvokeTool(name="nobody.has", args={}))
        assert unknown.status is Status.NOT_AVAILABLE
    finally:
        await app.stop()


async def test_calls_while_it_is_starting_start_it_once():
    app = make_app()
    await app.start()
    try:
        results = await asyncio.gather(*[
            app.router.send(InvokeTool(name="pages.open", args={"path": f"{n}.html"})) for n in range(3)
        ])
        assert all(r.is_ok for r in results) and Pages.starts == 1
    finally:
        await app.stop()


async def test_a_failed_start_gives_its_error_and_the_next_call_tries_again():
    app = make_app()
    Pages.fail = True
    await app.start()
    try:
        result = await app.router.send(InvokeTool(name="pages.open", args={"path": "a.html"}))
        assert result.status is Status.FAILED and "couldn't start" in result.error and "no window" in result.error
        Pages.fail = False
        assert (await app.router.send(InvokeTool(name="pages.open", args={"path": "a.html"}))).is_ok
        assert Pages.starts == 2
    finally:
        await app.stop()


async def test_a_module_you_turned_off_starts_again_on_use():
    app = make_app()
    await app.start()
    try:
        assert (await app.router.send(InvokeTool(name="pages.open", args={"path": "a.html"}))).is_ok
        assert (await app.router.send(DeactivateModule(module_id="pages"))).is_ok
        assert (await app.router.send(InvokeTool(name="pages.open", args={"path": "b.html"}))).is_ok
        assert Pages.starts == 2
    finally:
        await app.stop()


async def test_task_agent_opens_its_show_tags_through_invoke_tool():
    session, ctx, sent = StubSession(), StubContext(), []

    async def send(command):
        sent.append(command)
        return Result.ok({})

    ctx.send = send
    agent = SessionTaskAgent(session, ctx, "worker", "a worker")
    assert (await agent.assign(Task(id="t1", text="build it"))).is_ok
    text = 'Done.\n<<SHOW: C:\\d\\a.html>>\n<<SHOW: C:\\d\\b.html | "the core" | Parts>>'
    session.on_event({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})
    await asyncio.sleep(0.05)
    tools = [(c.name, c.args) for c in sent if isinstance(c, InvokeTool)]
    assert tools == [
        ("viewer.open", {"path": "C:\\d\\a.html"}),
        ("viewer.highlight", {"path": "C:\\d\\b.html", "text": "the core", "heading": "Parts"}),
    ]
    await agent.close()


async def test_task_agent_reports_a_show_that_failed():
    session, ctx, published = StubSession(), StubContext(), []
    ctx.publish = published.append

    async def send(command):
        return Result.failed("The html_viewer module couldn't start: no window") if isinstance(command, InvokeTool) \
            else Result.ok()

    ctx.send = send
    agent = SessionTaskAgent(session, ctx, "worker", "a worker")
    assert (await agent.assign(Task(id="t1", text="build it"))).is_ok
    session.on_event({"type": "assistant", "message": {"content": [{"type": "text", "text": "<<SHOW: C:\\a.html>>"}]}})
    await asyncio.sleep(0.05)
    notes = [e.text for e in published if isinstance(e, AgentActivity) and e.text.startswith("couldn't show")]
    assert notes == ["couldn't show C:\\a.html: The html_viewer module couldn't start: no window"]
    await agent.close()
