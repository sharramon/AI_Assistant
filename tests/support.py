"""Shared test helpers and fake modules."""

from __future__ import annotations

import asyncio
from typing import Any

from assistant.contracts import Contract, IToolProvider, Manifest, Module, ModuleContext, Result, ToolSpec


class Speaker(Contract):
    """A single-provider contract for tests. Pretends to live in assistant.contracts."""

    __module__ = "assistant.contracts.testing"


def make_config(*enabled: str, **core: Any) -> dict[str, Any]:
    return {"modules": {"enabled": list(enabled)}, "core": core}


async def wait_until(predicate, timeout: float = 1.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.005)


class Calculator(Module, IToolProvider):
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
