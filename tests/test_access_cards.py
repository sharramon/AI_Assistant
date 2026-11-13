"""The access card for the real agent modules: job_search and task_agents ask for their list when
turned on, the card opens, Allow saves the grant and turns the module on, and the grant calls
(`permissions.revoke`) act at once for you and wait for a card for an agent. Also how the Talker
words a card and how the temp UI shows one."""

import asyncio

from assistant.contracts import (
    AccessItem,
    AccessKind,
    ActivateModule,
    AnswerPermissionRequest,
    InvokeTool,
    ITaskAgent,
    ListModules,
    ModuleState,
    PermissionChanged,
    PermissionRequested,
    Status,
)
from assistant.core import App
from assistant.modules.agent_hub import AgentHubModule
from assistant.modules.job_search import JobSearchModule
from assistant.modules.talker.module import access_card_text
from assistant.modules.task_agents import TaskAgentsModule
from assistant.modules.temp_ui import TempUIModule
from assistant.testkit import FAKE, agent_module, module_config, pre_grant, stand_in, wait_until
from tests.test_temp_ui import post, read_events, ui_port

# --- helpers ---


def job_section(tmp_path, **extra) -> dict:
    return {"program": FAKE, "workspace": str(tmp_path / "CV"), **extra}


async def job_app(tmp_path, section: dict | None = None, enabled: bool = False):
    """The Hub, a stand-in for cv (job_search needs it) and job_search; job_search is off unless
    `enabled`. Returns the section as the module sees it (its module.toml under it), for `pre_grant`."""
    section = section or job_section(tmp_path)
    ids = ["agent_hub", *(["job_search"] if enabled else [])]
    config = {"modules": {"enabled": ids, "agent_hub": {"door": False}, "job_search": section},
              "core": {"permissions": {"you": ["temp_ui"]}}}  # as config/default.toml sets it
    app = App([AgentHubModule, stand_in("cv"), JobSearchModule], config)
    events: list = []

    async def record(event):
        events.append(event)

    for kind in (PermissionRequested, PermissionChanged):
        app.bus.subscribe(kind, record)
    return app, events, module_config("job_search", section)


async def state(app: App, module_id: str) -> ModuleState:
    infos = (await app.router.send(ListModules())).value
    return next(i.state for i in infos if i.id == module_id)


def cards(events: list) -> list[PermissionRequested]:
    return [e for e in events if isinstance(e, PermissionRequested)]


async def answer(app: App, card: PermissionRequested, allow: bool = True):
    return await app.router.send(AnswerPermissionRequest(request_id=card.request_id, allow=allow))


async def wait_state(app: App, module_id: str, wanted: ModuleState) -> None:
    for _ in range(400):
        if await state(app, module_id) is wanted:
            return
        await asyncio.sleep(0.005)
    raise AssertionError(f"{module_id} never reached {wanted}")


# --- job_search ---


async def test_no_grant_fails_the_activation_with_a_card_and_allow_turns_it_on(tmp_path):
    app, events, section = await job_app(tmp_path)
    await app.start()
    try:
        result = await app.router.send(ActivateModule(module_id="job_search"))
        assert not result.is_ok and "waits for your answer" in result.error
        await wait_until(lambda: cards(events))
        card = cards(events)[0]
        assert (card.module_id, card.subject, card.action) == ("job_search", "job_search_agent", "access")
        assert card.items[0].kind is AccessKind.WORKSPACE and not card.items[0].trimmable
        assert await state(app, "job_search") is ModuleState.FAILED
        assert app.permissions.store.get("job_search", "job_search_agent") is None

        assert (await answer(app, card)).is_ok
        await wait_state(app, "job_search", ModuleState.ACTIVE)
        saved = app.permissions.store.get("job_search", "job_search_agent")
        assert saved is not None and not saved.denied and saved.granted[0] == card.items[0].key
        assert any(a.info().agent_id == "job_search_agent" for a in app.container.get_all(ITaskAgent))
    finally:
        await app.stop()


async def test_a_saved_unchanged_list_starts_with_no_card_and_a_changed_list_asks_again(tmp_path):
    app, events, section = await job_app(tmp_path, enabled=True)
    pre_grant(app, "job_search", "job_search_agent", section)
    await app.start()
    try:
        assert await state(app, "job_search") is ModuleState.ACTIVE and not cards(events)
    finally:
        await app.stop()

    # The same saved grant, but the list now has a folder more: it asks again.
    changed = job_section(tmp_path, read_dirs=[str(tmp_path / "more")])
    app, events, _ = await job_app(tmp_path, changed)
    pre_grant(app, "job_search", "job_search_agent", section)
    await app.start()
    try:
        result = await app.router.send(ActivateModule(module_id="job_search"))
        assert not result.is_ok and "waits for your answer" in result.error
        await wait_until(lambda: cards(events))
        assert any(i.kind is AccessKind.READ for i in cards(events)[0].items)
    finally:
        await app.stop()


async def test_revoke_from_you_turns_it_off_and_from_an_agent_waits_for_a_card(tmp_path):
    app, events, section = await job_app(tmp_path, enabled=True)
    pre_grant(app, "job_search", "job_search_agent", section)
    await app.start()
    try:
        agent_call = InvokeTool(name="permissions.revoke", args={"module_id": "job_search"}, caller="main_assistant")
        asked = await app.router.send(agent_call)
        assert asked.is_ok and "asked the user on a card" in asked.value.lower()
        await wait_until(lambda: cards(events))
        card = cards(events)[0]
        assert card.action == "revoke" and card.caller == "main_assistant"
        assert await state(app, "job_search") is ModuleState.ACTIVE
        assert app.permissions.store.get("job_search", "job_search_agent") is not None  # nothing changed yet

        assert (await answer(app, card)).is_ok
        await wait_state(app, "job_search", ModuleState.INACTIVE)
        assert app.permissions.store.get("job_search", "job_search_agent") is None
    finally:
        await app.stop()

    app, events, section = await job_app(tmp_path, enabled=True)
    pre_grant(app, "job_search", "job_search_agent", section)
    await app.start()
    try:
        mine = await app.router.send(InvokeTool(name="permissions.revoke", args={"module_id": "job_search"},
                                                caller="temp_ui"))  # fmt: skip
        assert mine.is_ok and "job_search turned off" in mine.value and not cards(events)
        assert await state(app, "job_search") is ModuleState.INACTIVE
    finally:
        await app.stop()


# --- task_agents ---


async def test_two_autostart_kinds_open_two_cards_and_copies_share_a_kinds_grant(tmp_path):
    main_module, _ = agent_module("main_assistant", (str(tmp_path / "main"),))
    kinds = {k: {"program": FAKE, "workspace": str(tmp_path / k), "autostart": True, **extra}
             for k, extra in (("helper", {"instances": 2}), ("writer", {}))}  # fmt: skip
    config = {"modules": {"enabled": ["agent_hub", "main_assistant"], "agent_hub": {"door": False},
                          "task_agents": {"agents": kinds}}, "core": {}}  # fmt: skip
    app = App([AgentHubModule, main_module, TaskAgentsModule], config)
    events: list = []

    async def record(event):
        events.append(event)

    app.bus.subscribe(PermissionRequested, record)
    await app.start()
    try:
        result = await app.router.send(ActivateModule(module_id="task_agents"))
        assert not result.is_ok
        await wait_until(lambda: len(cards(events)) == 2)
        assert sorted(c.subject for c in cards(events)) == ["helper", "writer"]  # one per kind, not per copy
        assert app.permissions.open_cards() == 2
        for card in cards(events):
            assert (await answer(app, card)).is_ok
        await wait_state(app, "task_agents", ModuleState.ACTIVE)
        ids = {a.info().agent_id for a in app.container.get_all(ITaskAgent)}
        assert {"helper", "helper_2", "writer"} <= ids
        assert {g.subject for g in app.permissions.store.of("task_agents")} == {"helper", "writer"}
    finally:
        await app.stop()


# --- the Talker and the temp UI ---


def sample_card(**over) -> PermissionRequested:
    items = (AccessItem(kind=AccessKind.WORKSPACE, target="C:/x/ws"), AccessItem(kind=AccessKind.CHROME))
    base = dict(request_id="r1", module_id="job_search", subject="job_search_agent", action="access",
                reason="the job agent", items=items, reviewed=False)  # fmt: skip
    return PermissionRequested(**{**base, **over})


def test_the_talker_words_a_card_with_its_labels_and_not_reviewed():
    card = sample_card()
    text = access_card_text(card)
    assert "job_search → job_search_agent asks for its access list (the job agent)." in text
    assert all(i.label in text for i in card.items) and "Not reviewed" in text
    assert "Not reviewed" not in access_card_text(sample_card(reviewed=True))


async def test_temp_ui_shows_the_card_and_lists_the_grants():
    config = {"modules": {"enabled": ["temp_ui"], "temp_ui": {"port": 0, "window": "none"}}, "core": {}}
    app = App([TempUIModule], config)
    await app.start()
    try:
        app.bus.publish(sample_card())
        item = (await read_events(ui_port(app), 1))[1]
        assert (item["pane"], item["kind"]) == ("talker", "access")
        assert [i["trimmable"] for i in item["card"]["items"]] == [False, True]
        listed = await post(ui_port(app), "/grants", {"action": "list"})
        assert listed["ok"] is True and listed["value"] == []
    finally:
        await app.stop()


async def test_a_bad_answer_is_refused_without_a_card():
    app = App([], {"modules": {"enabled": []}, "core": {}})
    await app.start()
    try:
        result = await app.router.send(AnswerPermissionRequest(request_id="nope", allow=True))
        assert result.status is Status.INVALID_ARGUMENTS
    finally:
        await app.stop()
