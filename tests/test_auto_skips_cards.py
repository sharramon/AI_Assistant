"""Rule 1 of auto-skips-cards: an agent in Auto gets no permission cards. The handler reads each
worker and Talker pair's own mode (`_in_auto`, with `ListAgents`); the agent's gate runs an
approval at once in Auto. Manual, unknown callers and a failed lookup still get the card."""

import asyncio
import logging

import pytest

from assistant.contracts import (
    AccessItem,
    AccessKind,
    AccessPending,
    ActivateModule,
    AgentInfo,
    ListAgents,
    PermissionMode,
    PermissionRequested,
    ReportKind,
    Result,
)
from assistant.core.directory import CoreMenu
from assistant.core.permissions.handler import ACTING_FOR, PermissionsHandler
from assistant.core.permissions.store import Grant, fingerprint
from assistant.infra.permission_gate import PermissionGate
from tests.support import wait_until

AGENTS = [AgentInfo(agent_id="job", description="", permission_mode=PermissionMode.AUTO),
          AgentInfo(agent_id="mgr", description="", permission_mode=PermissionMode.MANUAL)]  # fmt: skip


def handler_of(tmp_path, broken: bool = False):
    published, sent = [], []

    async def send(command):
        sent.append(command)
        if isinstance(command, ListAgents):
            if broken:
                raise RuntimeError("no hub")
            return Result.ok(AGENTS)
        return Result.ok([])

    handler = PermissionsHandler(send, published.append, lambda t: None, tmp_path / "permissions.toml",
                                 reviewer="", you=("ui",))  # fmt: skip
    return handler, published, sent


def cards(published):
    return [e for e in published if isinstance(e, PermissionRequested)]


def chrome() -> AccessItem:
    return AccessItem(kind=AccessKind.CHROME)


async def test_a_message_in_auto_is_allow_once_with_no_card(tmp_path):
    handler, published, _ = handler_of(tmp_path)
    assert await handler.ask("agent_hub", "job", chrome(), "message mgr")
    assert await handler.ask("agent_hub", "talker:job", chrome())  # the pair's Talker: the same mode
    await asyncio.sleep(0)
    assert cards(published) == [] and handler.store.all() == []  # nothing saved
    await handler.close()


@pytest.mark.parametrize("caller", ["mgr", "nobody", "talker", "ui"])
async def test_manual_unknown_or_you_still_get_the_card(tmp_path, caller):
    handler, published, _ = handler_of(tmp_path)
    asking = asyncio.create_task(handler.ask("agent_hub", caller, chrome()))
    await wait_until(lambda: cards(published))
    asking.cancel()
    await handler.close()


async def test_a_failed_mode_lookup_shows_the_card(tmp_path):
    handler, published, _ = handler_of(tmp_path, broken=True)
    asking = asyncio.create_task(handler.ask("agent_hub", "job", chrome()))
    await wait_until(lambda: cards(published))
    asking.cancel()
    await handler.close()


async def test_an_access_list_turned_on_by_an_auto_agent_has_no_card_and_saves_nothing(tmp_path):
    handler, published, _ = handler_of(tmp_path)
    items = [AccessItem(kind=AccessKind.WORKSPACE, target=str(tmp_path / "ws")), chrome()]
    token = ACTING_FOR.set("job")
    try:
        assert await handler.request_set("cv", "cv", items) == tuple(items)
    finally:
        ACTING_FOR.reset(token)
    assert cards(published) == [] and handler.store.all() == []
    token = ACTING_FOR.set("mgr")  # Manual: the card, as before
    try:
        with pytest.raises(AccessPending):
            await handler.request_set("cv", "cv", items)
    finally:
        ACTING_FOR.reset(token)
    await wait_until(lambda: cards(published))
    await handler.close()


async def test_grant_request_and_revoke_in_auto_are_carried_out_at_once(tmp_path):
    handler, published, _ = handler_of(tmp_path)
    item = chrome()
    handler.store.put(Grant("jobs", "jobs", fingerprint([item]), (item.key,)))
    handler.own_agent("jobs", "job", "jobs")
    result = await handler.grant("jobs", [item.key], caller="job")
    assert result.is_ok and handler.store.get("jobs", "jobs").granted == (item.key,)
    extra = AccessItem(kind=AccessKind.READ, target=str(tmp_path / "more"))
    assert (await handler.request("job", [extra])).is_ok
    assert extra.key in handler.store.get("jobs", "jobs").granted
    assert (await handler.revoke("jobs", caller="job")).is_ok and handler.store.get("jobs", "jobs") is None
    await asyncio.sleep(0)
    assert cards(published) == []
    await handler.close()


async def test_modules_on_says_who_turned_the_module_on():
    seen = []

    async def send(command):
        if isinstance(command, ActivateModule):
            seen.append(ACTING_FOR.get())
        return Result.ok()

    menu = CoreMenu(send, permissions=None)
    await menu.menu.call(menu, "modules.on", {"module_id": "cv"}, caller="job")
    assert seen == ["job"] and ACTING_FOR.get() == ""


class _Session:
    working = False

    async def answer_permission(self, *args):
        pass


def gate_of(mode: PermissionMode):
    reports, ran, tasks = [], [], []

    async def send(text):
        pass

    gate = PermissionGate(_Session(), timeout=5, mode=lambda: mode, task=lambda: None, activity=lambda t: None,
                          report=lambda kind, text: reports.append(kind), send=send,
                          spawn=lambda c: tasks.append(asyncio.ensure_future(c)), log=logging.getLogger("t"))  # fmt: skip

    async def run():
        ran.append(True)
        return Result.ok()

    return gate, run, reports, ran, tasks


async def test_an_approval_in_auto_runs_at_once_and_manual_asks():
    gate, run, reports, ran, tasks = gate_of(PermissionMode.AUTO)
    gate.ask("reload cv", run)
    await asyncio.gather(*tasks)
    assert ran == [True] and reports == [] and gate.request is None
    gate, run, reports, ran, _ = gate_of(PermissionMode.MANUAL)
    gate.ask("reload cv", run)
    assert ran == [] and reports == [ReportKind.PERMISSION] and gate.request is not None
    gate.drop()
