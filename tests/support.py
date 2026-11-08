"""Shared test helpers and fake modules."""

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


def pre_grant(app: Any, module_id: str, subject: str, config: dict[str, Any]) -> None:
    """Save a grant for `config`'s whole access list, so `module_id` turns on with no card."""
    from assistant.core.permissions.store import Grant, fingerprint
    from assistant.infra import access_items

    items = access_items(config)
    keys = tuple(i.key for i in items)
    app.permissions.store.put(Grant(module_id, subject, fingerprint(items), keys).with_granted(keys))


def pre_grant_kinds(app: Any, module_config: dict[str, Any], module_id: str = "task_agents") -> None:
    """Pre-grant every kind of the task_agents config (autostart or launched)."""
    from assistant.modules.task_agents.module import kind_configs

    for kind, config in kind_configs(module_config).items():
        pre_grant(app, module_id, kind, config)
