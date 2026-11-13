"""Usage tallies across parts: sub-agent tokens in ClaudeSession, the UsageLedger, closed agents (with the Hub),
the temp UI's total, and the Talker's line. Tokens only: no money figure anywhere. The usage module's own menu
is tested in its folder (`modules/usage/tests`)."""

import asyncio
import json

from assistant.contracts import InvokeTool, SessionUsage, Status
from assistant.core import App
from assistant.infra import ClaudeSession, UsageLedger, session_usage, subagent_usage
from assistant.modules.temp_ui import TempUIModule
from assistant.modules.usage import UsageModule
from assistant.testkit import FAKE, wait_until

SUB_ID = "main_assistant/general-purpose #a1b2"


def usage(agent_id: str, tokens: int = 0, **extra) -> SessionUsage:
    """A usage whose tokens are all fresh input, for easy sums."""
    return SessionUsage(agent_id=agent_id, context_tokens=0, input_tokens=tokens, **extra)


# --- ClaudeSession: a sub-agent's tokens from the turn's result ---


async def test_session_tallies_a_subagent_apart_from_its_own_calls():
    events: list[dict] = []
    session = ClaudeSession(FAKE, on_event=events.append)
    await session.start()
    try:
        await session.send("SUBAGENT please")
        await wait_until(lambda: any(e["type"] == "result" for e in events), 10)
        # Its own calls only: the sub-agent's streamed assistant line (999s) never counts.
        assert session.used == {"input": 4, "cache_write": 0, "cache_read": 998 + 100, "output": 25}
        assert session.context_tokens == 102  # the parent's latest call, not the sub-agent's
        # Every call of the sub-agent (the turn's model usage less the parent's own), not its last.
        assert session.subagents == {"a1b2": {"type": "general-purpose", "used": {
            "input": 6, "cache_write": 2874, "cache_read": 5000, "output": 40}}}

        own = session_usage("main_assistant", session)
        [sub] = subagent_usage("main_assistant", session)
        assert own.kind == "claude" and own.parent == "" and own.used_tokens == 4 + 1098 + 25
        assert own.session == session.id == sub.session and session.id
        assert (sub.agent_id, sub.parent, sub.kind) == (SUB_ID, "main_assistant", "subagent")
        assert sub.used_tokens == 7920 and sub.context_tokens == 0
        assert not hasattr(own, "cost_usd")
    finally:
        await session.close()


def _result(**models) -> dict:
    return {"type": "result", "usage": {"output_tokens": 0}, "model_usage_since_last_result": {
        "m": {"inputTokens": models.get("i", 0), "cacheCreationInputTokens": 0,
              "cacheReadInputTokens": models.get("r", 0), "outputTokens": 0}}}  # fmt: skip


def _returned(agent_id: str, last_read: int) -> dict:
    return {"type": "user", "tool_use_result": {"agentId": agent_id, "agentType": "Explore", "usage": {
        "input_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": last_read, "output_tokens": 0}}}


def test_a_turns_extra_tokens_are_shared_by_last_call_size_and_none_lost():
    session = ClaudeSession(["unused"])
    session.meter.line(_returned("a", 100))
    session.meter.line(_returned("b", 300))
    session.meter.line(_result(r=1001))  # no own calls this turn: all of it is the sub-agents'
    subs = session.subagents
    assert subs["a"]["used"]["cache_read"] == 250 and subs["b"]["used"]["cache_read"] == 751  # 1:3, none lost


def test_tokens_with_no_subagent_returning_go_under_unnamed():
    session = ClaudeSession(["unused"])
    session.meter.line(_result(r=500))  # e.g. a sub-agent cut off before it returned
    assert session.subagents == {"unnamed": {"type": "sub-agents and tools", "used": {
        "input": 0, "cache_write": 0, "cache_read": 500, "output": 0}}}
    session.meter.line(_result())  # a turn of nothing adds nothing
    assert session.subagents["unnamed"]["used"]["cache_read"] == 500


def test_without_per_turn_numbers_the_last_call_is_used():
    session = ClaudeSession(["unused"])
    session.meter.line(_returned("a", 100))
    session.meter.line({"type": "result", "usage": {"output_tokens": 0}})
    assert session.subagents["a"]["used"]["cache_read"] == 100


# --- UsageLedger ---


def test_ledger_rolls_subagents_into_their_parent_without_counting_twice():
    ledger = UsageLedger()
    ledger.add(usage("main_assistant", 1000))
    ledger.add(usage(SUB_ID, 300, parent="main_assistant", kind="subagent"))
    ledger.add(usage("talker", 200))
    total = ledger.total()
    assert total["used_tokens"] == 1500 and total["agents"] == 2 and "cost_usd" not in total
    main, talker = ledger.by_agent()
    assert (main["agent_id"], talker["agent_id"]) == ("main_assistant", "talker")  # the Talker its own row
    assert main["used_tokens"] == 1000 and main["total"]["used_tokens"] == 1300
    [sub] = main["children"]
    assert (sub["name"], sub["kind"], sub["used_tokens"]) == ("general-purpose #a1b2", "subagent", 300)
    assert ledger.mine("main_assistant")["total"]["used_tokens"] == 1300


def test_ledger_keeps_the_latest_totals_so_a_lost_event_costs_nothing():
    ledger = UsageLedger()
    for tokens in (100, 250, 400):  # running totals; the 250 one may be lost or late
        ledger.add(usage("main_assistant", tokens))
    assert ledger.total()["used_tokens"] == 400
    skipped = UsageLedger()
    skipped.add(usage("main_assistant", 100))
    skipped.add(usage("main_assistant", 400))
    assert skipped.total() == ledger.total()


def test_ledger_keeps_what_a_restarted_session_had():
    ledger = UsageLedger()
    ledger.add(usage("main_assistant", 1000))
    ledger.add(usage("main_assistant", 0))  # no session id: numbers going down mean a new session
    ledger.add(usage("main_assistant", 300))
    assert ledger.total()["used_tokens"] == 1300


def test_ledger_banks_on_a_new_session_id_even_when_the_new_numbers_are_bigger():
    ledger = UsageLedger()
    ledger.add(usage("main_assistant", 100, session="s1"))
    ledger.add(usage("main_assistant", 500, session="s2"))  # a fresh session whose first report is bigger
    assert ledger.total()["used_tokens"] == 600
    ledger.add(usage("main_assistant", 700, session="s2"))  # same session: its latest total replaces
    assert ledger.total()["used_tokens"] == 800


def test_ledger_gives_an_unknown_agent_zeros_and_a_parent_that_hasnt_reported_a_row():
    ledger = UsageLedger()
    assert ledger.mine("nobody")["total"]["used_tokens"] == 0 and ledger.by_agent() == []
    ledger.add(usage("job_search_agent/search", 50, parent="job_search_agent", kind="tool"))
    [row] = ledger.by_agent()
    assert row["agent_id"] == "job_search_agent" and row["used_tokens"] == 0
    assert row["total"]["used_tokens"] == 50
    assert row["children"][0]["kind"] == "tool"


# --- the usage module ---


def usage_app(*more) -> App:
    enabled = ["usage", *(m.manifest.id for m in more)]
    config = {"modules": {"enabled": enabled, "temp_ui": {"port": 0, "window": "none"}}, "core": {}}
    return App([UsageModule, *more], config)


async def test_a_closed_agents_rows_say_closed_and_stay_in_the_total(tmp_path):
    from assistant.contracts import DeactivateModule
    from assistant.modules.agent_hub import AgentHubModule
    from assistant.testkit import agent_module

    main_module, _ = agent_module("main_assistant", (str(tmp_path / "main"),))
    helper_module, _ = agent_module("helper", (str(tmp_path / "jobs"),))
    config = {"modules": {"enabled": ["agent_hub", "main_assistant", "helper", "usage"],
                          "agent_hub": {"door": False}}, "core": {}}  # fmt: skip
    app = App([AgentHubModule, main_module, helper_module, UsageModule], config)
    await app.start()
    try:
        app.bus.publish(usage("main_assistant", 1000))
        app.bus.publish(usage("helper", 200))
        app.bus.publish(usage("talker:helper", 50, parent="helper"))  # the helper tab's Talker
        module = app._lifecycle._active["usage"][0]
        await wait_until(lambda: len(module._ledger.by_agent()) == 2)

        async def rows():
            return {r["agent_id"]: r for r in (await app.router.send(InvokeTool(name="usage.agents"))).value}

        assert not any(r["closed"] for r in (await rows()).values())
        assert (await app.router.send(DeactivateModule(module_id="helper"))).is_ok  # its tab closed
        listed = await rows()
        assert listed["helper"]["closed"] and listed["helper"]["children"][0]["closed"]  # its Talker too
        assert not listed["main_assistant"]["closed"]
        total = (await app.router.send(InvokeTool(name="usage.total"))).value
        assert total["used_tokens"] == 1250  # spent is spent
    finally:
        await app.stop()


async def test_temp_ui_shows_the_ledgers_total_and_rows():
    app = usage_app(TempUIModule)
    await app.start()
    try:
        port = int(app._lifecycle._active["temp_ui"][0].url.rsplit(":", 1)[1].strip("/"))
        app.bus.publish(usage("main_assistant", 1000))
        app.bus.publish(usage(SUB_ID, 300, parent="main_assistant", kind="subagent"))
        ui = app._lifecycle._active["temp_ui"][0]
        await wait_until(lambda: (ui._tally.get("total") or {}).get("used_tokens") == 1300, 3)
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"GET /events HTTP/1.1\r\n\r\n")
        await writer.drain()
        async with asyncio.timeout(3):
            while not (line := await reader.readline()).startswith(b'data: {"kind": "tally"'):
                pass
        writer.close()
        tally = json.loads(line[6:])
        assert tally["available"] and tally["total"]["used_tokens"] == 1300 and "cost_usd" not in tally["total"]
        assert tally["agents"][0]["children"][0]["name"] == "general-purpose #a1b2"
    finally:
        await app.stop()


async def test_temp_ui_keeps_every_agents_context_by_id_so_a_tab_shows_its_own_pair():
    app = usage_app(TempUIModule)
    await app.start()
    try:
        ui = app._lifecycle._active["temp_ui"][0]
        app.bus.publish(SessionUsage(agent_id="main_assistant", context_tokens=40_000))
        app.bus.publish(SessionUsage(agent_id="talker", context_tokens=9_000))
        app.bus.publish(SessionUsage(agent_id="helper", context_tokens=70_000))
        app.bus.publish(SessionUsage(agent_id="talker:helper", context_tokens=5_000, parent="helper"))
        app.bus.publish(SessionUsage(agent_id="helper/Explore #x", context_tokens=1, parent="helper", kind="subagent"))
        await wait_until(lambda: len(ui._usage) == 4, 3)
        assert {a: i["context"] for a, i in ui._usage.items()} == {
            "main_assistant": 40_000, "talker": 9_000, "helper": 70_000, "talker:helper": 5_000}
    finally:
        await app.stop()


async def test_temp_ui_says_when_the_usage_module_is_off():
    config = {"modules": {"enabled": ["temp_ui"], "temp_ui": {"port": 0, "window": "none"}}, "core": {}}
    app = App([TempUIModule, UsageModule], config)
    await app.start()
    try:
        ui = app._lifecycle._active["temp_ui"][0]
        assert not ui._tally["available"] and "off" in ui._tally["why"]
        off = await app.router.send(InvokeTool(name="usage.total"))
        assert off.status is Status.NOT_AVAILABLE
    finally:
        await app.stop()


async def test_talkers_usage_line_has_the_focused_agent_with_its_subagents_and_every_agents_total():
    from assistant.modules.talker import TalkerModule

    config = {"modules": {"enabled": ["usage", "talker"], "talker": {"program": FAKE}}, "core": {}}
    app = App([UsageModule, TalkerModule], config)
    replies = asyncio.Queue()
    from assistant.contracts import InputReceived, ResponseReady

    app.bus.subscribe(ResponseReady, replies.put)
    await app.start()
    try:
        app.bus.publish(SessionUsage(agent_id="main_assistant", context_tokens=150_000, cache_read_tokens=2_000_000))
        app.bus.publish(usage(SUB_ID, 300_000, parent="main_assistant", kind="subagent"))
        ledger = app._lifecycle._active["usage"][0]._ledger
        await wait_until(lambda: ledger.mine("main_assistant")["total"]["used_tokens"] == 2_300_000)
        app.bus.publish(InputReceived(text="SHOWUSAGE hi", source="test"))
        async with asyncio.timeout(10):
            while "hi" not in (reply := await replies.get()).text:
                pass
        line = reply.text.splitlines()[0]
        assert line.startswith("[Usage] worker: context 150k (last call), used 2.3M (incl. resent cache) · "
                               "you: context ")
        assert line.endswith(" · all agents: used 2.3M") and "~$" not in line  # the Talker's own counted once
    finally:
        await app.stop()
