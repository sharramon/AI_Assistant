"""AgentKit: the reset handler, grant handler and start sequence every agent module shares."""

from __future__ import annotations

import asyncio
import logging

import pytest

from assistant.contracts import AccessDenied, ITaskAgent, ResetRequested, Result
from assistant.infra import agent_kit
from assistant.infra.agent_kit import AgentKit


class _Ctx:
    log = logging.getLogger("test")

    def __init__(self):
        self.provided, self.withdrawn, self.subs = [], [], {}

    def subscribe(self, kind, handler):
        self.subs[kind] = handler

    def provide(self, contract, impl):
        self.provided.append((contract, impl))

    def withdraw(self, contract, impl):
        self.withdrawn.append((contract, impl))


class _Inner:
    def __init__(self, reset_ok=True):
        self.resets, self._ok = 0, reset_ok

    async def reset(self):
        self.resets += 1
        return Result.ok(None) if self._ok else Result.failed("no")


class _Agent:
    def __init__(self, agent_id, busy=None, fail_start=False):
        self.agent_id, self.agent, self._busy, self._fail = agent_id, _Inner(), busy, fail_start
        self.started = self.stopped = False
        self.access = None

    async def start(self):
        if self._fail:
            raise RuntimeError("taken")
        self.started = True

    async def stop(self):
        self.stopped = True

    def busy(self):
        return self._busy

    def set_access(self, config):
        self.access = config


def test_add_provides_and_reset_reaches_only_its_agent():
    ctx = _Ctx()
    kit = AgentKit(ctx)
    a, b = kit.add(_Agent("a")), kit.add(_Agent("b", busy="b is working on a task"))
    assert ctx.provided == [(ITaskAgent, a.agent), (ITaskAgent, b.agent)]
    asyncio.run(ctx.subs[ResetRequested](ResetRequested(agent_id="b")))
    asyncio.run(ctx.subs[ResetRequested](ResetRequested(agent_id="other")))
    assert (a.agent.resets, b.agent.resets) == (0, 1)
    assert kit.get("a") is a and kit.busy() == "b is working on a task"


def test_take_back_and_stop():
    ctx = _Ctx()
    kit = AgentKit(ctx)
    a, b = kit.add(_Agent("a")), kit.add(_Agent("b"))
    asyncio.run(kit.take_back(a))
    assert a.stopped and ctx.withdrawn == [(ITaskAgent, a.agent)] and kit.get("a") is None
    asyncio.run(kit.stop())
    assert b.stopped and kit.agents() == [] and kit.busy() is None


def test_open_asks_builds_provides_and_starts(monkeypatch):
    ctx, asked = _Ctx(), []

    async def fake_request(ctx_, config, subject="", reason="", wait=False):
        asked.append((subject, reason, wait))
        return {**config, "granted": True}

    monkeypatch.setattr(agent_kit, "request_access", fake_request)
    monkeypatch.setattr(agent_kit, "ProfileAgent", lambda c, i, conf, p, subject=None, **kw: _Agent(i))
    kit = AgentKit(ctx)
    agent = asyncio.run(kit.open("job", {"workspace": "w"}, "prompt", subject="job", reason="why"))
    assert agent.started and kit.get("job") is agent and asked == [("job", "why", False)]

    monkeypatch.setattr(agent_kit, "ProfileAgent", lambda c, i, conf, p, subject=None, **kw: _Agent(i, fail_start=True))
    with pytest.raises(RuntimeError):
        asyncio.run(kit.open("bad", {}, "prompt", subject="bad", reason="why"))
    assert kit.get("bad") is None and ctx.withdrawn  # a failed start is taken back


def test_follow_grant_hands_the_grant_to_its_agent(monkeypatch):
    ctx, watched = _Ctx(), {}
    monkeypatch.setattr(agent_kit, "watch_grant", lambda c, cb, subject=None: watched.update({subject: cb}))
    monkeypatch.setattr(agent_kit, "granted_config", lambda config, granted: {**config, "n": len(granted)})
    kit = AgentKit(ctx)
    kit.follow_grant("job", {"workspace": "w"})
    asyncio.run(watched["job"]("job", ()))  # not open yet: nothing to do
    agent = kit.add(_Agent("job"))
    asyncio.run(watched["job"]("job", ("x",)))
    assert agent.access == {"workspace": "w", "n": 1}

    def denied(config, granted):
        raise AccessDenied("workspace taken back")

    monkeypatch.setattr(agent_kit, "granted_config", denied)
    asyncio.run(watched["job"]("job", ()))  # logged, not raised
    assert agent.access == {"workspace": "w", "n": 1}
