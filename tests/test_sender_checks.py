"""Restructuring R2 (decision D3): the sender is stamped on every command, `sends` and `publishes`
are strict, the control commands come only from you (and the few others each names), a
`ModuleEvent` only through `publish_named` (G15), and the local pages refuse other hosts (G10).
Plus a static check that every module's literal `ctx.send(X(...))` / `ctx.publish(X(...))` is declared."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

import assistant.contracts as contracts
from assistant.contracts import (
    AddModule,
    AnswerPermissionRequest,
    Command,
    Event,
    ITaskAgent,
    Manifest,
    ModuleContext,
    ModuleEvent,
    ModuleProtocol,
    ReloadModule,
    Result,
)
from assistant.core import App, loader
from assistant.testkit import make_config

MODULES = Path(next(iter(importlib.import_module("assistant.modules").__path__)))


class Ping(Command):
    text: str = ""


class Pinged(Event):
    pass


class Receiver(ModuleProtocol):
    manifest = Manifest(id="receiver", handles=(Ping,))
    seen: list[str] = []

    async def init(self, ctx: ModuleContext) -> None:
        for kind in self.manifest.handles:
            ctx.handle(kind, self._got)

    async def _got(self, command: Command) -> Result:
        self.seen.append(f"{type(command).__name__}:{command.sent_by}")
        return Result.ok()


def _sender(module_id: str, sends=(), publishes=(), provides=()) -> type:
    class Sender(ModuleProtocol):
        manifest = Manifest(id=module_id, sends=sends, publishes=publishes, provides=provides)

        async def init(self, ctx: ModuleContext) -> None:
            self.ctx = ctx

    return Sender


async def _app(*senders: type, you=(), relays=()):
    Receiver.seen = []
    modules = [Receiver, *senders]
    config = make_config(*(m.manifest.id for m in modules), permissions={"you": list(you), "relays": list(relays)})
    app = App(modules, config)
    await app.start()
    return app


def _instance(app: App, module_id: str):
    return app._lifecycle._active[module_id][0]


async def test_the_sender_is_stamped_and_the_core_is_core() -> None:
    app = await _app(_sender("a", sends=(Ping,)))
    try:
        ctx = _instance(app, "a").ctx
        assert (await ctx.send(Ping(sent_by="forged"))).is_ok
        assert (await app.router.send(Ping())).is_ok
        assert Receiver.seen == ["Ping:a", "Ping:core"]
    finally:
        await app.stop()


async def test_an_undeclared_send_is_refused_and_an_undeclared_publish_dropped() -> None:
    app = await _app(_sender("a"))
    heard: list[Event] = []
    app.bus.subscribe(Pinged, heard.append)
    try:
        ctx = _instance(app, "a").ctx
        result = await ctx.send(Ping())
        assert not result.is_ok and "manifest.sends" in result.error and Receiver.seen == []
        ctx.publish(Pinged())
        with pytest.raises(ValueError, match="publish_named"):
            ctx.publish(ModuleEvent(name="a.x", source="someone_else"))
    finally:
        await app.stop()
    assert heard == []


async def test_control_commands_come_only_from_you_a_relay_or_an_agent() -> None:
    every = (AnswerPermissionRequest, ReloadModule, AddModule)  # SetPermissionMode is not one: see test_callers
    app = await _app(_sender("ui", sends=every), _sender("talk", sends=every), _sender("plain", sends=every),
                     _sender("agent", sends=every, provides=(ITaskAgent,)), you=["ui"], relays=["talk"])  # fmt: skip
    try:
        def ctx(m):
            return _instance(app, m).ctx

        async def refused(who: str, command: Command) -> bool:  # refused at the send, before any handler
            return "control command" in ((await ctx(who).send(command)).error or "")

        answer = AnswerPermissionRequest(request_id="no-such-card", allow=True)  # the core: "no such card"
        reload, add = ReloadModule(module_id="nobody"), AddModule(package="nobody")
        assert not await refused("ui", answer) and not await refused("talk", answer)
        assert await refused("plain", answer) and await refused("agent", answer)
        assert not await refused("agent", reload) and not await refused("agent", add) and not await refused("ui", add)
        assert await refused("plain", reload) and await refused("talk", add)
    finally:
        await app.stop()


# The static check: every literal send and publish in a module's code is in its manifest.

CTX = ("ctx", "_ctx")


def _literal_calls(file: Path) -> list[tuple[int, str, str]]:
    """(line, "send" | "publish", class name) for each `<...ctx>.send(X(...))` / `.publish(X(...))`."""
    found = []
    for node in ast.walk(ast.parse(file.read_text(encoding="utf-8-sig"))):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.args):
            continue
        owner, arg = node.func.value, node.args[0]
        owner_name = owner.attr if isinstance(owner, ast.Attribute) else getattr(owner, "id", "")
        if node.func.attr in ("send", "publish") and owner_name in CTX and isinstance(arg, ast.Call) \
                and isinstance(arg.func, ast.Name):  # fmt: skip
            found.append((node.lineno, node.func.attr, arg.func.id))
    return found


def _module_ids() -> list[str]:
    return sorted(p.name for p in MODULES.iterdir() if (p / "module.toml").is_file())


@pytest.mark.parametrize("module_id", _module_ids())
def test_every_literal_send_and_publish_is_declared(module_id: str) -> None:
    cls = loader.find_module_class(importlib.import_module(f"assistant.modules.{module_id}"), module_id)
    declared = {"send": cls.manifest.sends, "publish": cls.manifest.publishes}
    missing = []
    for file in (MODULES / module_id).rglob("*.py"):
        if {"tests", "app", "workspace", "__pycache__"} & set(file.relative_to(MODULES).parts):
            continue
        for line, how, name in _literal_calls(file):
            kind = getattr(contracts, name, None)
            if isinstance(kind, type) and not issubclass(kind, tuple(declared[how])):
                missing.append(f"{file.relative_to(MODULES).as_posix()}:{line}: {how} {name}")
    assert not missing, f"{module_id}'s manifest doesn't list: {missing}"
