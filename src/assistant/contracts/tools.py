"""Tools: capabilities the AI (or any module) can invoke by name."""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from assistant.contracts.messages import Command, Result
from assistant.contracts.module import Contract


class ToolSpec(BaseModel):
    """Describes one tool. `input_schema` is a JSON Schema for the arguments."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}})


class InvokeTool(Command):
    """Run the tool called `name`. Routed by the core to whichever provider offers it."""

    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class ToolProvider(Contract):
    """A module that offers tools. Any number of modules may provide this."""

    multiple = True

    @abstractmethod
    def tools(self) -> list[ToolSpec]:
        """The tools currently offered. Called on every lookup, so it may change at runtime."""

    @abstractmethod
    async def invoke(self, name: str, args: dict[str, Any]) -> Result:
        """Run tool `name`. Return `Result.invalid_arguments` for bad args."""
