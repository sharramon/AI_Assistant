"""The permissions handler's first piece: saved grants, refusals and warnings, the access card
(allow, trim, deny, timeout, a changed list), the review, and the grant calls."""

import asyncio
from pathlib import Path

import pytest

from assistant.contracts import (
    AccessItem,
    AccessKind,
    AccessPending,
    AgentNotice,
    AnswerPermissionRequest,
    IAgentNames,
    InvokeTool,
    ITaskAgent,
    ListModules,
    Manifest,
    ModuleContext,
    ModuleProtocol,
    ModuleState,
    PermissionChanged,
    PermissionRequested,
    ReportKind,
    ReportTask,
    StartTask,
    Status,
)
from assistant.core import App
from assistant.core.permissions.rules import REPO, protected_paths, refusals, rule_warnings
from assistant.core.permissions.store import Grant, GrantStore, fingerprint
from assistant.modules.agent_hub import AgentHubModule
from tests.support import wait_until
from tests.test_multi_agent import FakeAgent, agent_module


def items_of(tmp_path: Path, chrome: bool = True) -> list[AccessItem]:
    found = [AccessItem(kind=AccessKind.WORKSPACE, target=str(tmp_path / "ws")),
             AccessItem(kind=AccessKind.READ, target=str(tmp_path / "jobs"))]  # fmt: skip
    return [*found, AccessItem(kind=AccessKind.CHROME)] if chrome else found


# --- the parts ---


def test_store_round_trip_and_fingerprint_ignores_order(tmp_path):
    a, b, c = items_of(tmp_path)
    assert fingerprint([a, b, c]) == fingerprint([c, a, b]) != fingerprint([a, b])
    path = tmp_path / "permissions.toml"
    store = GrantStore(path)
    grant = Grant("jobs", "jobs", fingerprint([a, b, c]), (a.key, b.key, c.key)).with_granted([c.key, a.key])
    store.put(grant)
    again = GrantStore(path).get("jobs", "jobs")
    assert again == grant and again.granted == (a.key, c.key) and again.date
    GrantStore(path).remove("jobs", "jobs")
    assert GrantStore(path).all() == []
    extra = AccessItem(kind=AccessKind.WRITE, target=str(tmp_path / "more"))
    added = grant.with_added([extra.key, a.key]).with_granted([a.key, extra.key])  # a is on the list already
    store.put(added)
    again = GrantStore(path).get("jobs", "jobs")
    assert again.added == (extra.key,) and again.granted == (a.key, extra.key)
    assert again.fingerprint == grant.fingerprint  # an unchanged config still matches


def test_protected_zone_is_refused_and_the_three_warnings(tmp_path):
    zone = protected_paths(tmp_path / "permissions.toml")
    write = lambda p: AccessItem(kind=AccessKind.WRITE, target=str(p))  # noqa: E731
    refused = refusals([write(REPO), write(REPO / "config" / "x"), write(tmp_path / "ok"),
                        AccessItem(kind=AccessKind.READ, target=str(REPO))], zone)  # fmt: skip
    assert set(refused) == {write(REPO).key, write(REPO / "config" / "x").key}  # reading is never refused
    python = AccessItem(kind=AccessKind.PYTHON, target="C:/py/python.exe")
    ws, outside, chrome = items_of(tmp_path)
    notes = rule_warnings([ws, outside, chrome, python])
    assert [n.items for n in notes] == [(ws.key, chrome.key), (outside.key, chrome.key), (python.key,)]
    assert rule_warnings([ws, outside]) == []


# --- the access card, through the app ---


def jobs_module(holder: dict, subject: str = "", agent: FakeAgent | None = None) -> type:
    class JobsModule(ModuleProtocol):
        manifest = Manifest(id="jobs", description="A fake agent module", permissions=("agent.access",),
                            provides=(ITaskAgent,) if agent else ())  # fmt: skip

        async def init(self, ctx: ModuleContext) -> None:
            self.ctx = ctx
            if agent:
                ctx.provide(ITaskAgent, agent)

        async def start(self) -> None:
            items = [AccessItem.from_key(k) for k in self.ctx.config["items"]]
            try:
                holder["granted"] = await self.ctx.permissions.request_set(items, "to look for jobs", subject)
            except AccessPending as exc:
                holder["pending"] = str(exc)
                raise
            if agent and (names := self.ctx.get_one(IAgentNames)):
                await names.claim(agent.agent_id, "jobs")
            if agent:
                self.ctx.permissions.own_agent(agent.agent_id, subject)

        async def stop(self) -> None:
            if agent and (names := self.ctx.get_one(IAgentNames)):
                names.release(agent.agent_id, "jobs")

    return JobsModule


async def start(modules: list[type], tmp_path: Path, items: list[AccessItem], **perms) -> tuple[App, list]:
    ids = [m.manifest.id for m in modules]
    config = {"modules": {"enabled": ids, "agent_hub": {"door": False}, "jobs": {"items": [i.key for i in items]}},
              "core": {"permissions": {"grants_file": str(tmp_path / "permissions.toml"), "reviewer": "", "you": ["temp_ui"], **perms}}}  # fmt: skip
    app = App(modules, config)
    events: list = []

    async def record(event):
        events.append(event)

    for kind in (PermissionRequested, PermissionChanged, AgentNotice):
        app.bus.subscribe(kind, record)
    await app.start()
    return app, events


async def state(app: App, module_id: str) -> ModuleState:
    infos = (await app.router.send(ListModules())).value
    return next(i.state for i in infos if i.id == module_id)


def cards(events: list) -> list[PermissionRequested]:
    return [e for e in events if isinstance(e, PermissionRequested)]


async def test_allow_without_chrome_turns_it_on_and_the_next_launch_needs_no_card(tmp_path):
    holder: dict = {}
    items = items_of(tmp_path)
    app, events = await start([jobs_module(holder)], tmp_path, items)  # the registry orders them
    try:
        await wait_until(lambda: cards(events))
        card = cards(events)[0]
        assert "waits for your answer" in holder["pending"]
        assert await state(app, "jobs") is ModuleState.FAILED
        assert [i.key for i in card.items] == [i.key for i in items] and card.reviewed is None and card.rules
        assert [i.trimmable for i in card.items] == [False, True, True]
        bad = await app.router.send(AnswerPermissionRequest(request_id=card.request_id, allow=True, keep=("nope",)))
        assert bad.status is Status.INVALID_ARGUMENTS
        assert (await app.router.send(AnswerPermissionRequest(request_id=card.request_id, allow=True,
                                                              keep=(items[1].key,)))).is_ok  # fmt: skip
        await wait_until(lambda: holder.get("granted"))
        assert holder["granted"] == tuple(items[:2])  # the workspace always comes with it
        assert await state(app, "jobs") is ModuleState.ACTIVE
    finally:
        await app.stop()

    holder.clear()
    app, events = await start([jobs_module(holder)], tmp_path, items)
    try:
        assert holder["granted"] == tuple(items[:2]) and not cards(events)
        assert (await app.router.send(InvokeTool(name="permissions.grants"))).value[0]["matches"] is True
    finally:
        await app.stop()


async def test_deny_or_no_answer_leaves_it_off_and_a_changed_list_asks_again(tmp_path):
    holder: dict = {}
    app, events = await start([jobs_module(holder)], tmp_path, items_of(tmp_path))
    try:
        await wait_until(lambda: cards(events))
        await app.router.send(AnswerPermissionRequest(request_id=cards(events)[0].request_id, allow=False))
        await wait_until(lambda: any(isinstance(e, PermissionChanged) for e in events))
        assert "denied; it stays off" in events[-1].text and await state(app, "jobs") is ModuleState.FAILED
        assert (await app.router.send(InvokeTool(name="permissions.grants"))).value[0]["denied"] is True
    finally:
        await app.stop()

    app, events = await start([jobs_module(holder)], tmp_path, items_of(tmp_path, chrome=False),
                              answer_timeout=0.05)  # fmt: skip
    try:
        await wait_until(lambda: any(isinstance(e, PermissionChanged) for e in events))
        assert len(cards(events)) == 1  # a narrower list asks again too
        assert "no answer in time" in events[-1].text and "granted" not in holder
    finally:
        await app.stop()


@pytest.mark.parametrize("busy", [False, True])
async def test_the_review_adds_notes_or_marks_it_not_reviewed(tmp_path, busy):
    holder: dict = {}
    main_module, main = agent_module("main_assistant", (str(tmp_path / "main"),))
    main.busy = busy
    app, events = await start([AgentHubModule, main_module, jobs_module(holder)], tmp_path,
                              items_of(tmp_path), reviewer="main_assistant")  # fmt: skip
    try:
        if not busy:
            await wait_until(lambda: main.calls)
            assert "No further warnings." in main.calls[0][2]
            await main.ctx.send(ReportTask(task_id=main.calls[0][1], kind=ReportKind.DONE,
                                           text="- It could post your CV publicly.\nNo further warnings."))  # fmt: skip
        await wait_until(lambda: cards(events))
        card = cards(events)[0]
        assert card.reviewed is (not busy)
        reviews = [n.text for n in card.notes if n.source == "review"]
        assert reviews == ([] if busy else ["It could post your CV publicly."])
        assert [n.source for n in card.notes if n.source == "rule"] == ["rule", "rule"]
    finally:
        await app.stop()


# --- the grant calls ---


async def allowed_app(tmp_path: Path, holder: dict, agent: FakeAgent | None = None, hub: bool = False):
    modules = [*([AgentHubModule] if hub else []), jobs_module(holder, agent=agent)]
    app, events = await start(modules, tmp_path, items_of(tmp_path))
    await wait_until(lambda: cards(events))
    await app.router.send(AnswerPermissionRequest(request_id=cards(events)[0].request_id, allow=True,
                                                  keep=(items_of(tmp_path)[1].key,)))  # fmt: skip
    await wait_until(lambda: "granted" in holder)
    for _ in range(200):
        if await state(app, "jobs") is ModuleState.ACTIVE:
            break
        await asyncio.sleep(0.005)
    assert await state(app, "jobs") is ModuleState.ACTIVE
    return app, events


async def call(app: App, name: str, caller: str, **args):
    return await app.router.send(InvokeTool(name=name, args=args, caller=caller))


async def test_grant_and_revoke_from_you(tmp_path):
    holder: dict = {}
    agent = FakeAgent("jobs_agent", (str(tmp_path / "ws"),))
    app, events = await allowed_app(tmp_path, holder, agent, hub=True)
    try:
        await wait_until(lambda: app.container.get_one(IAgentNames).taken().get("jobs_agent") == "jobs")
        chrome = AccessItem(kind=AccessKind.CHROME).key
        assert (await call(app, "permissions.grant", "temp_ui", module_id="jobs", items=["nope"])).status \
            is Status.INVALID_ARGUMENTS
        granted = await call(app, "permissions.grant", "temp_ui", module_id="jobs", items=[chrome])
        assert "applies from its next session" in granted.value
        assert chrome in (await call(app, "permissions.grants", "temp_ui")).value[0]["granted"]

        assert (await app.router.send(StartTask(text="look", agent_id="jobs_agent"))).is_ok
        revoked = await call(app, "permissions.revoke", "temp_ui", module_id="jobs")
        assert revoked.value == "jobs turned off; its running task was stopped."
        assert ("cancel",) == agent.calls[-1][:1]
        assert await state(app, "jobs") is ModuleState.INACTIVE
        assert (await call(app, "permissions.grants", "temp_ui")).value == []
    finally:
        await app.stop()


async def test_an_agents_grant_or_revoke_waits_for_your_card(tmp_path):
    holder: dict = {}
    app, events = await allowed_app(tmp_path, holder)
    try:
        chrome = AccessItem(kind=AccessKind.CHROME).key
        asked = await call(app, "permissions.grant", "main_assistant", module_id="jobs", items=[chrome])
        assert "asked the user on a card" in asked.value.lower()
        await wait_until(lambda: len(cards(events)) == 2)
        card = cards(events)[1]
        assert card.action == "grant" and card.caller == "main_assistant"
        assert chrome not in (await call(app, "permissions.grants", "x")).value[0]["granted"]  # not yet
        await app.router.send(AnswerPermissionRequest(request_id=card.request_id, allow=False))
        await wait_until(lambda: any(isinstance(e, AgentNotice) for e in events))
        assert "denied" in events[-1].text and events[-1].agent_id == "main_assistant"

        await call(app, "permissions.revoke", "main_assistant", module_id="jobs")
        await wait_until(lambda: len(cards(events)) == 3)
        assert await state(app, "jobs") is ModuleState.ACTIVE  # an agent can't take access away on its own
        await app.router.send(AnswerPermissionRequest(request_id=cards(events)[2].request_id, allow=True))
        await wait_until(lambda: sum(isinstance(e, AgentNotice) for e in events) == 2)
        assert events[-1].text == "jobs turned off."
        assert await state(app, "jobs") is ModuleState.INACTIVE
    finally:
        await app.stop()


async def test_with_no_saved_grant_the_card_shows(tmp_path):
    holder: dict = {}
    app, events = await start([jobs_module(holder)], tmp_path, items_of(tmp_path))
    try:
        await wait_until(lambda: cards(events))
        assert "granted" not in holder and app.permissions.open_cards() == 1
    finally:
        await app.stop()


async def test_an_agent_asks_for_more_access_itself(tmp_path):
    from assistant.infra import granted_config

    holder: dict = {}
    agent = FakeAgent("jobs_agent", (str(tmp_path / "ws"),))
    app, events = await allowed_app(tmp_path, holder, agent, hub=True)
    try:
        await wait_until(lambda: app.container.get_one(IAgentNames).taken().get("jobs_agent") == "jobs")
        refused = await call(app, "permissions.request", "main_assistant", read=[str(tmp_path / "x")])
        assert refused.status is Status.NOT_AVAILABLE and "no access list" in refused.error
        more = AccessItem(kind=AccessKind.WRITE, target=str((tmp_path / "more").resolve()))
        asked = await call(app, "permissions.request", "jobs_agent", write=[str(tmp_path / "more")], reason="drafts")
        assert asked.is_ok and "asked the user on a card" in asked.value.lower()
        await wait_until(lambda: len(cards(events)) == 2)
        card = cards(events)[1]
        assert card.action == "grant" and [i.key for i in card.items] == [more.key]
        await app.router.send(AnswerPermissionRequest(request_id=card.request_id, allow=True, keep=(more.key,)))
        await wait_until(lambda: more.key in (app.permissions.grants()[0]["granted"]))
        row = app.permissions.grants()[0]
        assert row["added"] == [more.key]
        granted = tuple(AccessItem.from_key(k) for k in row["granted"])
        config = {"workspace": str(tmp_path / "ws"), "read_dirs": [str(tmp_path / "jobs")]}
        assert granted_config(config, granted)["write_dirs"] == [more.target]  # beyond the config's list
        again = await call(app, "permissions.request", "jobs_agent", write=[str(tmp_path / "more")])
        assert again.value == "You already have all of these"
    finally:
        await app.stop()
