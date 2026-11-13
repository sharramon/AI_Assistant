"""Start on use: a tool call turns on the module that is off and has the tool, if its config allows;
and `StartProvider` does the same by contract, so a caller (the SHOW tags, temp_ui) names no module."""

import asyncio

from assistant.contracts import (
    AgentActivity,
    DeactivateModule,
    InvokeTool,
    IPageOpener,
    Manifest,
    Menu,
    ModuleContext,
    ModuleProtocol,
    Result,
    StartProvider,
    Status,
    Task,
)
from assistant.core import App
from assistant.infra import NO_PAGE_VIEWER, SessionTaskAgent
from assistant.testkit import StubContext, StubSession

menu = Menu()


class Opener(IPageOpener):
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def open(self, path, quote=None, heading=None, front=False):
        self.calls.append((path, quote, heading, front))
        return Result.ok({"opened": path})


class Pages(ModuleProtocol):
    manifest = Manifest(id="pages", description="a viewer stand-in", provides=(IPageOpener,))
    menu = menu
    starts = 0
    fail = False

    async def init(self, ctx: ModuleContext) -> None:
        self._ctx = ctx

    async def start(self) -> None:
        self._ctx.provide(IPageOpener, Opener())
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


async def test_start_provider_turns_on_the_module_that_provides_the_contract():
    app = make_app()
    await app.start()
    try:
        assert app.container.get_one(IPageOpener) is None
        assert (await app.router.send(StartProvider(contract="IPageOpener"))).is_ok
        assert "pages" in app._lifecycle._active and app.container.get_one(IPageOpener) is not None
        again = await app.router.send(StartProvider(contract="IPageOpener"))  # already on: nothing to start
        assert again.status is Status.NOT_AVAILABLE and Pages.starts == 1
        assert (await app.router.send(DeactivateModule(module_id="pages"))).is_ok
        assert app.container.get_one(IPageOpener) is None  # withdrawn with the module
    finally:
        await app.stop()


async def test_start_provider_only_for_modules_that_allow_it():
    app = make_app(start_on_use=False)
    await app.start()
    try:
        result = await app.router.send(StartProvider(contract="IPageOpener"))
        assert result.status is Status.NOT_AVAILABLE and Pages.starts == 0
        nobody = await app.router.send(StartProvider(contract="INobody"))
        assert nobody.status is Status.NOT_AVAILABLE
    finally:
        await app.stop()


async def test_start_provider_gives_a_failed_start():
    app = make_app()
    Pages.fail = True
    await app.start()
    try:
        result = await app.router.send(StartProvider(contract="IPageOpener"))
        assert result.status is Status.FAILED and "no window" in result.error
    finally:
        await app.stop()


async def test_task_agent_opens_its_show_tags_through_the_page_opener():
    session, ctx, opener = StubSession(), StubContext(), Opener()
    ctx.provided[IPageOpener] = opener
    agent = SessionTaskAgent(session, ctx, "worker", "a worker")
    assert (await agent.assign(Task(id="t1", text="build it"))).is_ok
    text = 'Done.\n<<SHOW: C:\\d\\a.html>>\n<<SHOW: C:\\d\\b.html | "the core" | Parts>>'
    session.on_event({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})
    await asyncio.sleep(0.05)
    assert sorted(opener.calls) == [
        ("C:\\d\\a.html", None, None, False),
        ("C:\\d\\b.html", "the core", "Parts", False),
    ]
    await agent.close()


async def test_task_agent_reports_a_show_with_no_page_viewer():
    session, ctx, published = StubSession(), StubContext(), []
    ctx.publish = published.append

    async def send(command):
        return Result.not_available("nobody starts on use") if isinstance(command, StartProvider) else Result.ok()

    ctx.send = send
    agent = SessionTaskAgent(session, ctx, "worker", "a worker")
    assert (await agent.assign(Task(id="t1", text="build it"))).is_ok
    session.on_event({"type": "assistant", "message": {"content": [{"type": "text", "text": "<<SHOW: C:\\a.html>>"}]}})
    await asyncio.sleep(0.05)
    notes = [e.text for e in published if isinstance(e, AgentActivity) and e.text.startswith("couldn't show")]
    assert notes == [f"couldn't show C:\\a.html: {NO_PAGE_VIEWER}"]
    await agent.close()


async def test_a_real_app_opens_a_show_page_with_its_provider_off():
    """End to end: the provider is off; the agent's SHOW starts it through StartProvider."""

    class Shower(ModuleProtocol):
        manifest = Manifest(id="shower", uses=(IPageOpener,), sends=(StartProvider,))

        async def init(self, ctx: ModuleContext) -> None:
            type(self).ctx = ctx

    Pages.starts, Pages.fail = 0, False
    app = App([Pages, Shower], {"modules": {"enabled": ["shower"], "pages": {"start_on_use": True}}, "core": {}})
    await app.start()
    try:
        from assistant.infra import show_page

        outcome = await show_page(Shower.ctx, r'C:\d\a.html | "words"')
        assert outcome.result.is_ok and outcome.result.value == {"opened": r"C:\d\a.html"} and Pages.starts == 1
    finally:
        await app.stop()
