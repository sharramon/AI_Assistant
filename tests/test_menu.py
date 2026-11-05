"""A module's Menu: items declared on the class, read without starting it, called through InvokeTool."""

import pytest

from assistant.contracts import (
    DeactivateModule,
    InvokeTool,
    IToolProvider,
    Manifest,
    Menu,
    ModuleProtocol,
    Result,
    Status,
)
from assistant.core import App
from assistant.modules.echo_orchestrator import EchoOrchestrator
from assistant.modules.html_viewer import HtmlViewerModule
from tests.support import make_config

menu = Menu()


class Counter(ModuleProtocol):
    manifest = Manifest(id="counter", description="Counts")
    menu = menu

    async def init(self, ctx):
        self.count = 0

    @menu.item("counter.add", "Add to the count", {"by": {"type": "integer"}, "note": {"type": "string"}},
               required=["by"])
    async def add(self, by: int, note: str = "") -> Result:
        self.count += by
        return Result.ok(self.count)

    @menu.item("counter.peek", "The count")
    async def peek(self):
        return self.count  # a plain value becomes Result.ok


def test_the_menu_is_readable_without_starting_the_module():
    assert Counter.menu.names() == ["counter.add", "counter.peek"]
    spec = Counter.menu.specs()[0]
    assert spec.input_schema == {
        "type": "object",
        "properties": {"by": {"type": "integer"}, "note": {"type": "string"}},
        "required": ["by"],
    }
    assert ModuleProtocol.menu is None


@pytest.mark.parametrize("args, problem", [
    ({}, "needs 'by'"),
    ({"by": "2"}, "must be integer"),
    ({"by": True}, "must be integer"),
    ({"by": 1, "extra": 1}, "no argument 'extra'"),
])
def test_bad_arguments_are_named(args, problem):
    assert problem in Counter.menu.check("counter.add", args)


def test_a_bad_declaration_fails_at_import():
    bad = Menu()
    with pytest.raises(ValueError):
        bad.item("x.y", "two\nlines")
    with pytest.raises(ValueError):
        bad.item("x.y", "ok", {"a": {"type": "string"}}, required=["b"])
    bad.item("x.y", "ok")(lambda self: None)
    with pytest.raises(ValueError):
        bad.item("x.y", "again")


async def test_the_core_links_the_menu_to_the_running_copy_and_unlinks_it_on_stop():
    app = App([Counter], make_config("counter"))
    await app.start()
    assert (await app.router.send(InvokeTool(name="counter.add", args={"by": 2}))).value == 2
    assert (await app.router.send(InvokeTool(name="counter.peek"))).value == 2
    bad = await app.router.send(InvokeTool(name="counter.add", args={"by": "lots"}))
    assert bad.status is Status.INVALID_ARGUMENTS
    assert [s.name for p in app.container.get_all(IToolProvider) for s in p.tools()] == Counter.menu.names()

    assert (await app.router.send(DeactivateModule(module_id="counter"))).is_ok
    assert (await app.router.send(InvokeTool(name="counter.peek"))).status is Status.NOT_AVAILABLE
    await app.stop()


def test_the_viewer_menu_keeps_its_tools():
    assert HtmlViewerModule.menu.names() == ["viewer.open", "viewer.highlight", "viewer.tabs"]
    assert IToolProvider not in HtmlViewerModule.manifest.provides
    schemas = {s.name: s.input_schema for s in HtmlViewerModule.menu.specs()}
    assert schemas["viewer.open"]["required"] == ["path"]
    assert schemas["viewer.highlight"]["required"] == ["path", "text"]
    assert "can't be empty" in HtmlViewerModule.menu.check("viewer.highlight", {"path": "a.html", "text": "  "})


async def test_the_echo_stand_in_has_a_menu():
    app = App([EchoOrchestrator], make_config("echo_orchestrator"))
    await app.start()
    assert (await app.router.send(InvokeTool(name="echo.say", args={"text": "hi"}))).value == "Echo: hi"
    await app.stop()
