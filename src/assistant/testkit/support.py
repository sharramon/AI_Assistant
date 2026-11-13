"""Test helpers and fake modules: a test config, waiting on a condition, a contract and a tool
provider for tests, and pre-saved grants so a module turns on with no card."""

from __future__ import annotations

import asyncio
from typing import Any

from assistant.contracts import Contract, IToolProvider, Manifest, ModuleContext, ModuleProtocol, Result, ToolSpec


class Speaker(Contract):
    """A single-provider contract for tests. Pretends to live in assistant.contracts."""

    __module__ = "assistant.contracts.testing"


def make_config(*enabled: str, **core: Any) -> dict[str, Any]:
    return {"modules": {"enabled": list(enabled)}, "core": core}


async def wait_until(predicate, timeout: float = 1.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.005)


class Calculator(ModuleProtocol, IToolProvider):
    manifest = Manifest(id="calculator", provides=(IToolProvider,))

    async def init(self, ctx: ModuleContext) -> None:
        ctx.provide(IToolProvider, self)

    def tools(self) -> list[ToolSpec]:
        return [ToolSpec(name="add", description="Add a and b")]

    async def invoke(self, name: str, args: dict[str, Any]) -> Result:
        try:
            return Result.ok(args["a"] + args["b"])
        except KeyError as exc:
            return Result.invalid_arguments(f"missing argument {exc}")


def free_port() -> int:
    """A free TCP port on 127.0.0.1, for a test server."""
    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def stand_in(module_id: str) -> type[ModuleProtocol]:
    """A bare module class with id `module_id` and nothing else, standing in for a module another
    one `needs` (job_search needs cv), so a test can start the one under test without the real one."""

    async def init(self, ctx: ModuleContext) -> None:
        pass

    return type(f"StandIn_{module_id}", (ModuleProtocol,), {"manifest": Manifest(id=module_id), "init": init})


def module_config(module_id: str, section: dict[str, Any] | None = None) -> dict[str, Any]:
    """The config module `module_id` sees, as the core builds it: its `module.toml` defaults (none
    if it has none) with `section` (its `[modules.<id>]`) merged over them. For `pre_grant`, whose
    list must match what the module asks for. Reads the defaults with the core's own reader."""
    import importlib

    from app_kit import merge
    from assistant.core import loader

    cls = loader.find_module_class(importlib.import_module(f"{loader.MODULES_PACKAGE}.{module_id}"), module_id)
    return merge(loader.module_defaults(cls), section or {})


def pre_grant(app: Any, module_id: str, subject: str, config: dict[str, Any], own_folder: bool | None = None) -> None:
    """Save a grant for `config`'s whole access list, so `module_id` turns on with no card.
    `own_folder`: the list has the module's own folder, as its `request_access` asks; None:
    every module but `task_agents` (whose helpers ask without it)."""
    from assistant.core.permissions.store import Grant, fingerprint
    from assistant.infra import access_items

    own = module_id != "task_agents" if own_folder is None else own_folder
    items = access_items(config, module_id if own else "")
    keys = tuple(i.key for i in items)
    app.permissions.store.put(Grant(module_id, subject, fingerprint(items), keys).with_granted(keys))


def pre_grant_kinds(app: Any, module_config: dict[str, Any], module_id: str = "task_agents") -> None:
    """Pre-grant every kind of the task_agents config (autostart or launched)."""
    from assistant.modules.task_agents.module import kind_configs

    for kind, config in kind_configs(module_config).items():
        pre_grant(app, module_id, kind, config)
