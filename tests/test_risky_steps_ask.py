"""Restructuring item 0: risky steps really ask, in Manual and Auto alike.

The core menu's `modules.add`, `modules.remove`, `modules.reload` and `modules.off` with
dependents are marked `ask="always"`: the one gate in `dispatch_tool` shows a `confirm` card,
and Auto never skips it. Only a caller that is you clicking (`[core.permissions] you`) runs at
once. An item marked `ask="risky"` is skipped for a caller in Auto.
"""

import pytest

from assistant.contracts import (
    AgentNotice,
    AnswerPermissionRequest,
    InvokeTool,
    ListModules,
    Manifest,
    Menu,
    ModuleProtocol,
    ModuleState,
    PermissionRequested,
    Result,
    Status,
)
from assistant.core import App
from assistant.core.permissions import PermissionsPort
from assistant.modules.talker.session import access_card_text
from assistant.testkit import Speaker, make_config, wait_until

YOU = "ui"
AGENT = "main_assistant"


class SpeakerImpl(ModuleProtocol, Speaker):
    manifest = Manifest(id="speaker", description="Says things", provides=(Speaker,))

    async def init(self, ctx):
        ctx.provide(Speaker, self)

    def say(self, text):
        return text


class NeedsSpeaker(ModuleProtocol):
    manifest = Manifest(id="needs_speaker", requires=(Speaker,))

    async def init(self, ctx):
        pass


risky_menu = Menu()


class Risky(ModuleProtocol):
    manifest = Manifest(id="risky", description="Has a lesser risky item")
    menu = risky_menu

    async def init(self, ctx):
        pass

    @risky_menu.item("risky.go", "Do a lesser risky thing", ask="risky")
    async def go(self) -> Result:
        return Result.ok("went")


async def _app(auto: bool = False):
    app = App([SpeakerImpl, NeedsSpeaker, Risky], make_config("speaker", "needs_speaker", "risky",
                                                              permissions={"you": [YOU], "answer_timeout": 5}))
    cards: list[PermissionRequested] = []
    notices: list[AgentNotice] = []

    async def card(e):
        cards.append(e)

    async def notice(e):  # the Hub's stand-in: AgentNotice is a command now
        notices.append(e)
        return Result.ok()

    app.bus.subscribe(PermissionRequested, card)
    app.router.register(AgentNotice, notice)

    async def in_auto(caller):  # no Agent Hub here: say which callers are in Auto
        return auto and caller == AGENT

    app.permissions._in_auto = in_auto
    await app.start()
    return app, cards, notices


async def _call(app, name, caller=AGENT, **args):
    return await app.router.send(InvokeTool(name=name, args=args, caller=caller))


async def _states(app):
    return {m.id: m.state for m in (await app.router.send(ListModules())).value}


async def _answer(app, card, allow):
    return await app.router.send(AnswerPermissionRequest(request_id=card.request_id, allow=allow))


@pytest.mark.parametrize("auto", [False, True], ids=["manual", "auto"])
async def test_every_risky_core_item_shows_a_confirm_card(auto):
    app, cards, notices = await _app(auto)
    try:
        calls = [
            ("modules.off", {"module_id": "speaker", "with_dependents": True}),
            ("modules.reload", {"module_id": "speaker"}),
            ("modules.add", {"package": "assistant.modules.echo_orchestrator"}),
            ("modules.remove", {"module_id": "needs_speaker", "settings": "keep"}),
        ]
        for n, (name, args) in enumerate(calls, 1):
            result = await _call(app, name, **args)
            assert result.is_ok and "Asked the user on a card" in result.value, (name, result)
            await wait_until(lambda n=n: len(cards) == n)
            assert cards[-1].action == "confirm" and cards[-1].caller == AGENT and name in cards[-1].reason
            assert cards[-1].items == ()
            assert "asks you to confirm" in access_card_text(cards[-1])
        states = await _states(app)
        assert states["speaker"] is ModuleState.ACTIVE and states["needs_speaker"] is ModuleState.ACTIVE
        assert "echo_orchestrator" not in states  # nothing ran yet
        assert app.permissions.open_cards() == 4

        # Deny runs nothing; the caller is told.
        for card in cards[:3]:
            assert (await _answer(app, card, False)).is_ok
        await wait_until(lambda: len(notices) == 3)
        assert all(n.agent_id == AGENT and "said no" in n.text for n in notices)
        states = await _states(app)
        assert "echo_orchestrator" not in states and states["speaker"] is ModuleState.ACTIVE

        # Allow runs the call itself; the caller is told the outcome.
        assert (await _answer(app, cards[3], True)).is_ok
        await wait_until(lambda: len(notices) == 4)
        assert "allowed" in notices[-1].text
        assert "needs_speaker" not in await _states(app)
    finally:
        await app.stop()


async def test_you_run_at_once_and_safe_calls_never_card():
    app, cards, _ = await _app(auto=False)
    try:
        # Plain off (no dependents) and a bad argument never reach a card.
        assert (await _call(app, "modules.off", module_id="needs_speaker")).is_ok
        bad = await _call(app, "modules.remove", module_id="speaker", settings="x")
        assert bad.status is Status.INVALID_ARGUMENTS
        # You clicking runs at once.
        off = await _call(app, "modules.off", caller=YOU, module_id="speaker", with_dependents=True)
        assert off.is_ok and "Asked" not in str(off.value)
        assert (await _states(app))["speaker"] is not ModuleState.ACTIVE
        assert cards == []
    finally:
        await app.stop()


async def test_a_risky_mark_is_skipped_in_auto_only():
    app, cards, _ = await _app(auto=False)
    try:
        asked = await _call(app, "risky.go")
        assert "Asked the user on a card" in asked.value
        await wait_until(lambda: len(cards) == 1)
    finally:
        await app.stop()
    app, cards, _ = await _app(auto=True)
    try:
        assert (await _call(app, "risky.go")).value == "went"
        assert cards == []
    finally:
        await app.stop()


class CallsRisky(ModuleProtocol):
    """A module calling a risky item from its own code (R5: the gate is on InvokeTool itself)."""

    manifest = Manifest(id="calls_risky", description="Calls risky.go from code", sends=(InvokeTool,))

    running: list["CallsRisky"] = []

    async def init(self, ctx):
        self.ctx = ctx
        CallsRisky.running.append(self)

    async def go(self):
        return await self.ctx.send(InvokeTool(name="risky.go", args={}))


async def test_a_risky_item_called_from_code_or_by_the_talker_cards_in_manual():
    """R5 (D4, G14): no road skips the gate. A module's own `ctx.send(InvokeTool)` (its caller
    stamped as itself) and the Talker (never in Auto) both get a card; a caller the core's
    Callers port holds in Auto runs a `risky` item at once."""
    from assistant.contracts import PermissionMode

    app = App([Risky, CallsRisky], make_config("risky", "calls_risky", permissions={"you": [YOU]}))
    cards: list[PermissionRequested] = []

    async def card(e):
        cards.append(e)

    app.bus.subscribe(PermissionRequested, card)
    await app.start()
    try:
        module = CallsRisky.running[-1]
        assert "Asked the user on a card" in (await module.go()).value
        await wait_until(lambda: len(cards) == 1)
        assert cards[0].caller == "calls_risky"
        assert "Asked the user on a card" in (await _call(app, "risky.go", caller="talker")).value
        await wait_until(lambda: len(cards) == 2)
        app.callers.set_mode(AGENT, PermissionMode.AUTO)
        assert (await _call(app, "risky.go")).value == "went"
        assert len(cards) == 2
    finally:
        await app.stop()


async def test_confirm_with_wait_returns_the_steps_result():
    """The agent's RELOAD: / ADD_MODULE: line goes this way (`wait=True`): the outcome comes back."""
    import asyncio

    app, cards, notices = await _app(auto=True)  # Auto never skips a confirm card
    try:
        port = PermissionsPort("main_assistant", app.permissions)
        task = asyncio.create_task(port.confirm("list the modules", ListModules(), caller=AGENT, wait=True))
        await wait_until(lambda: len(cards) == 1)
        await _answer(app, cards[0], True)
        result = await task
        assert result.is_ok and {m.id for m in result.value} >= {"speaker", "needs_speaker"}
        task = asyncio.create_task(port.confirm("list the modules", ListModules(), caller=AGENT, wait=True))
        await wait_until(lambda: len(cards) == 2)
        await _answer(app, cards[1], False)
        result = await task
        assert result.status is Status.FAILED and "said no" in result.error
        assert notices == []  # it awaited the result itself: no note
    finally:
        await app.stop()


async def test_a_bare_port_runs_the_step():
    async def step():
        return Result.ok("ran")

    assert (await PermissionsPort("x").confirm("do it", step)).value == "ran"
