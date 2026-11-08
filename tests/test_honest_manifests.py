"""Chunk 11 (principle 17): manifests declare everything a module uses.

`Manifest.uses` for call-time lookups with no start order, `ScopedContext` logging an
undeclared subscription or lookup once, the agent modules' shared declarations, and
`AgentStateChanged.change` for a helper that opens or closes.
"""

from __future__ import annotations

import logging

import pytest

from assistant.contracts import (
    AgentStateChanged,
    IAgentNames,
    IModuleDoor,
    InputReceived,
    ITaskAgent,
    Manifest,
    ModuleStateChanged,
    ResponseReady,
)
from assistant.core.bus import EventBus
from assistant.core.container import Container
from assistant.core.context import ScopedContext
from assistant.core.registry import StartupError, resolve_modules
from assistant.core.router import CommandRouter
from assistant.infra import AGENT_LISTENS, AGENT_PUBLISHES, AGENT_SENDS, AGENT_USES
from assistant.modules.cv import CvModule
from assistant.modules.job_search import JobSearchModule
from assistant.modules.main_assistant import MainAssistantModule
from assistant.modules.task_agents import TaskAgentsModule


def make_ctx(manifest: Manifest, name: str = "honest") -> ScopedContext:
    return ScopedContext(manifest, CommandRouter(), EventBus(), Container(), {}, logging.getLogger(name))


async def nothing(_event) -> None:
    return None


def test_uses_defaults_to_nothing() -> None:
    assert Manifest(id="plain").uses == ()


async def test_declared_use_logs_nothing(caplog: pytest.LogCaptureFixture) -> None:
    ctx = make_ctx(Manifest(id="good", listens=(InputReceived,), uses=(IModuleDoor,), optional=(ITaskAgent,)))
    with caplog.at_level(logging.WARNING):
        ctx.subscribe(InputReceived, nothing)
        assert ctx.get_one(IModuleDoor) is None
        assert ctx.get_all(ITaskAgent) == []
    assert not caplog.records
    ctx.close()


async def test_undeclared_use_is_logged_once_and_still_works(caplog: pytest.LogCaptureFixture) -> None:
    ctx = make_ctx(Manifest(id="sloppy"))
    with caplog.at_level(logging.WARNING):
        ctx.subscribe(ResponseReady, nothing)
        ctx.subscribe(ResponseReady, nothing)
        assert ctx.get_one(IAgentNames) is None
        assert ctx.get_all(IAgentNames) == []
    messages = [r.getMessage() for r in caplog.records]
    assert messages == [
        "sloppy uses ResponseReady without declaring it in its manifest (listens)",
        "sloppy uses IAgentNames without declaring it in its manifest (requires / optional / uses)",
    ]
    assert len(ctx._subscriptions) == 2  # not refused
    ctx.close()


def test_uses_must_be_contracts_and_add_no_start_order() -> None:
    class NotAContract:
        pass

    class Bad:
        manifest = Manifest(id="bad", uses=(NotAContract,))  # type: ignore[arg-type]
        menu = None

    with pytest.raises(StartupError, match="not a contract"):
        resolve_modules([Bad], ["bad"])

    class Provider:
        manifest = Manifest(id="provider", provides=(IModuleDoor,), optional=(ITaskAgent,))
        menu = None

    class User:
        manifest = Manifest(id="user", provides=(ITaskAgent,), uses=(IModuleDoor,))
        menu = None

    # With `optional` both ways this would be circular; `uses` adds no edge.
    order = resolve_modules([Provider, User], ["provider", "user"])
    assert [cls.manifest.id for cls in order] == ["user", "provider"]


@pytest.mark.parametrize("module", [MainAssistantModule, JobSearchModule, CvModule, TaskAgentsModule])
def test_agent_modules_declare_what_their_agents_use(module) -> None:
    m = module.manifest
    assert set(AGENT_USES) <= set(m.uses)
    assert set(AGENT_SENDS) <= set(m.sends)
    assert set(AGENT_PUBLISHES) <= set(m.publishes)
    assert set(AGENT_LISTENS) <= set(m.listens)
    assert ModuleStateChanged in m.listens


def test_agent_state_changed_says_what_changed() -> None:
    assert AgentStateChanged(agent_id="a", busy=True, working=False).change == "state"
    assert AgentStateChanged(agent_id="a", busy=False, working=False, change="closed").change == "closed"
    with pytest.raises(ValueError):
        AgentStateChanged(agent_id="a", busy=False, working=False, change="gone")
