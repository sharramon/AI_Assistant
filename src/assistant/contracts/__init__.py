"""Stable contracts shared by the core and all modules. Depends on nothing else in the app."""

from assistant.contracts.control import (
    ActivateModule,
    DeactivateModule,
    ListModules,
    ModuleInfo,
    ModuleState,
    ModuleStateChanged,
)
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
from assistant.contracts.tools import InvokeTool, IToolProvider, ToolSpec

__all__ = [
    "ActivateModule",
    "Command",
    "Contract",
    "DeactivateModule",
    "Event",
    "InputReceived",
    "InvokeTool",
    "ListModules",
    "Manifest",
    "Message",
    "Module",
    "ModuleContext",
    "ModuleInfo",
    "ModuleState",
    "ModuleStateChanged",
    "ResponseReady",
    "Result",
    "ShutdownRequested",
    "Status",
    "IToolProvider",
    "ToolSpec",
]
