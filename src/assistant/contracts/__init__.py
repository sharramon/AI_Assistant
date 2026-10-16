"""Stable contracts shared by the core and all modules. Depends on nothing else in the app."""

from assistant.contracts.messages import (
    Command,
    Event,
    InputReceived,
    Message,
    ResponseReady,
    Result,
    ShutdownRequested,
    Status,
)
from assistant.contracts.module import Contract, Manifest, Module, ModuleContext
from assistant.contracts.tools import InvokeTool, ToolProvider, ToolSpec

__all__ = [
    "Command",
    "Contract",
    "Event",
    "InputReceived",
    "InvokeTool",
    "Manifest",
    "Message",
    "Module",
    "ModuleContext",
    "ResponseReady",
    "Result",
    "ShutdownRequested",
    "Status",
    "ToolProvider",
    "ToolSpec",
]
