"""The usage module on its own: its `module.toml` (no defaults, needs nothing) and its menu
(`usage.total`, `usage.agents`, `usage.mine`). The tallies with other parts (ClaudeSession, the
UsageLedger, the Hub, the temp UI, the Talker) are tested centrally (`tests/test_usage.py`).
Uses only the shared test kit."""

from assistant.contracts import InvokeTool, SessionUsage
from assistant.core import App
from assistant.modules.usage import UsageModule
from assistant.testkit import module_config, wait_until

SUB_ID = "main_assistant/general-purpose #a1b2"


def usage(agent_id: str, tokens: int = 0, **extra) -> SessionUsage:
    """A usage whose tokens are all fresh input, for easy sums."""
    return SessionUsage(agent_id=agent_id, context_tokens=0, input_tokens=tokens, **extra)


def usage_app() -> App:
    return App([UsageModule], {"modules": {"enabled": ["usage"]}, "core": {}})


def test_its_module_toml_has_no_defaults_and_needs_nothing():
    assert module_config("usage") == {"needs": [], "packages": []}  # a core module never needs an add-on
    assert UsageModule.manifest.needs == ()

async def test_usage_menu_answers_total_agents_and_the_callers_own():
    app = usage_app()
    await app.start()
    try:
        app.bus.publish(usage("main_assistant", 1000))
        app.bus.publish(usage(SUB_ID, 300, parent="main_assistant", kind="subagent"))
        app.bus.publish(usage("talker", 200))

        async def call(name: str, caller: str = "", **args):
            return await app.router.send(InvokeTool(name=name, args=args, caller=caller))

        await wait_until(lambda: len(app._lifecycle._active["usage"][0]._ledger.by_agent()) == 2)
        total = await call("usage.total")
        assert total.value["used_tokens"] == 1500
        agents = (await call("usage.agents")).value
        assert [a["agent_id"] for a in agents] == ["main_assistant", "talker"]
        assert agents[0]["children"][0]["agent_id"] == SUB_ID
        mine = await call("usage.mine", caller="main_assistant")  # no arguments: the door's caller
        assert mine.value["total"]["used_tokens"] == 1300
        other = await call("usage.mine", caller="talker", agent_id="main_assistant")
        assert other.value["agent_id"] == "main_assistant"
    finally:
        await app.stop()
