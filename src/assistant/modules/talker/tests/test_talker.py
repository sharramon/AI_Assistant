"""The Talker on its own, against the fake `claude`: tags, the session theme, the context warnings,
a reset, spoken input; and its defaults in its `module.toml`. With the Hub and a worker, it's tested
centrally (`tests/test_agents.py`, `tests/test_restart.py`, `tests/test_talker_agents.py`)."""

import asyncio
import tomllib

import pytest

from assistant.contracts import InputReceived, ResetRequested, ResponseReady, SessionTheme, SessionUsage
from assistant.core import App, loader
from assistant.modules.talker import TalkerModule
from assistant.modules.talker.module import split_tags
from assistant.testkit import FAKE, TIMEOUT, next_matching

# The old [modules.talker] in config/default.toml, before its defaults moved to module.toml.
OLD_SECTION = {
    "model": "sonnet",
    "turn_timeout": 120.0,
    "context_exchanges": 6,
    "context_warning": 150000,
    "transcript": "talker.jsonl",
    "restart_note": ".claude/state/reset-instructions.md",
    "restart_timeout": 120.0,
}


def test_its_defaults_are_in_its_module_toml_under_the_apps_section():
    # Read the file itself: the test-wide setup points a default restart_note into tmp.
    toml = tomllib.loads((loader.module_folder(TalkerModule) / "module.toml").read_text(encoding="utf-8"))
    assert toml["needs"] == [] and toml["packages"] == []
    assert {k: v for k, v in toml.items() if k not in ("needs", "packages")} == OLD_SECTION
    assert TalkerModule.manifest.needs == ()
    app = App([TalkerModule], {"modules": {"enabled": [], "talker": {"turn_timeout": 5.0}}, "core": {}})
    merged = app._config_of("talker")
    assert merged["turn_timeout"] == 5.0 and merged["model"] == "sonnet"  # yours wins, the rest unchanged


def test_split_tags():
    text, tags = split_tags("On it! <<WORK: write\ntwo poems>> I'll tell you. <<LOOK>>")
    assert text == "On it!  I'll tell you."
    assert tags == [("WORK", "write\ntwo poems"), ("LOOK", "")]
    assert split_tags("Okay, allowing it. <<ALLOW>>") == ("Okay, allowing it.", [("ALLOW", "")])
    assert split_tags("Just chatting.") == ("Just chatting.", [])
    assert split_tags("Hi! <<THEME: log folders>>") == ("Hi!", [("THEME", "log folders")])
    # A page opened for you always shows its path (so the chat offers its button), once.
    assert split_tags("Here it is. <<SHOW: C:\\d\\x.html>>")[0] == "Here it is.\nC:\\d\\x.html"
    assert split_tags("See C:\\d\\x.html <<SHOW: C:\\d\\x.html | \"Parts\" | Intro>>")[0] == "See C:\\d\\x.html"
    assert split_tags("<<SHOW: C:\\d\\x.html>>")[0] == "C:\\d\\x.html"


@pytest.mark.parametrize(("first", "theme"), [
    ("Hello <<THEME: session log folders>>", "session log folders"),
    ("Can you split the logs?", "Can you split the logs?"),  # no tag: the message itself
    ("Logs <<THEME: ?!>>", "Logs <<THEME: ?!>>"),  # an unusable tag: the message itself
])
async def test_talker_sends_the_session_theme_once(first, theme):
    config = {"modules": {"enabled": ["talker"], "talker": {"program": FAKE}}, "core": {}}
    app = App([TalkerModule], config)
    themes: asyncio.Queue[SessionTheme] = asyncio.Queue()
    replies: asyncio.Queue[ResponseReady] = asyncio.Queue()
    app.bus.subscribe(SessionTheme, themes.put)
    app.bus.subscribe(ResponseReady, replies.put)
    await app.start()
    try:
        # The fake Talker repeats what it's sent, so the input is its reply.
        app.bus.publish(InputReceived(text=first, source="test"))
        assert (await asyncio.wait_for(themes.get(), TIMEOUT)).text == theme
        app.bus.publish(InputReceived(text="Second <<THEME: other>>", source="test"))
        await next_matching(replies, lambda e: e.text == "Second")
        await asyncio.sleep(0.05)
        assert themes.empty()
    finally:
        await app.stop()


async def test_a_helper_tabs_talker_is_warned_about_its_own_pair():
    # A low line: the fake Talker's own 2k context passes it after one turn.
    config = {"modules": {"enabled": ["talker"], "talker": {"program": FAKE, "context_warning": 1_000}}, "core": {}}
    app = App([TalkerModule], config)
    replies: asyncio.Queue[ResponseReady] = asyncio.Queue()
    app.bus.subscribe(ResponseReady, replies.put)
    await app.start()
    try:
        app.bus.publish(InputReceived(text="hi", source="test", agent_id="cv_agent"))
        own = await next_matching(replies, lambda e: e.text.startswith("[Status] Your own"))
        assert own.agent_id == "cv_agent"  # said in the helper's tab, about its own Talker
        app.bus.publish(SessionUsage(agent_id="cv_agent", context_tokens=2_000))
        worker = await next_matching(replies, lambda e: e.text.startswith("[Status] cv_agent's context"))
        assert worker.agent_id == "cv_agent" and "It has been reminded" in worker.text
    finally:
        await app.stop()


async def test_talker_sees_both_usages_and_warns_once():
    config = {"modules": {"enabled": ["talker"], "talker": {"program": FAKE, "context_warning": 150_000}}, "core": {}}
    app = App([TalkerModule], config)
    replies: asyncio.Queue[ResponseReady] = asyncio.Queue()
    app.bus.subscribe(ResponseReady, replies.put)
    await app.start()
    try:
        # The fake Talker repeats what it's sent (with SHOWUSAGE, the [Usage] line too).
        app.bus.publish(InputReceived(text="SHOWUSAGE hi", source="test"))
        first = await next_matching(replies, lambda e: "hi" in e.text)
        assert first.text.startswith(
            "[Usage] worker: not started · you: context 0k (last call), used 0k (incl. resent cache)")
        assert "~$" not in first.text

        def worker(context: int) -> SessionUsage:
            return SessionUsage(agent_id="main_assistant", context_tokens=context,
                                cache_read_tokens=2_300_000, output_tokens=5_000)

        # Past the warning: the Talker is told once, and sees both numbers, kept apart.
        app.bus.publish(worker(152_000))
        warning = await next_matching(replies, lambda e: e.text.startswith("[Status]"))
        assert warning.text.startswith("[Status] The worker's context is at 152k tokens, past the 150k warning")
        assert "It has been reminded to find a reset point" in warning.text
        app.bus.publish(worker(160_000))  # still over: no second warning
        app.bus.publish(InputReceived(text="SHOWUSAGE how full?", source="test"))
        line = (await next_matching(replies, lambda e: "how full?" in e.text)).text.splitlines()[0]
        assert line.startswith("[Usage] worker: context 160k (last call), used 2.3M (incl. resent cache) · "
                               "you: context 2k (last call), used ")

        # Back under (a reset or a fresh session), then over again: warned again.
        app.bus.publish(worker(0))
        app.bus.publish(worker(151_000))
        again = await next_matching(replies, lambda e: e.text.startswith("[Status]"))
        assert "151k tokens" in again.text
        await asyncio.sleep(0.1)
        assert replies.empty()
    finally:
        await app.stop()


async def test_talker_reset_keeps_recent_exchanges():
    config = {"modules": {"enabled": ["talker"], "talker": {"program": FAKE}}, "core": {}}
    app = App([TalkerModule], config)
    replies: asyncio.Queue[ResponseReady] = asyncio.Queue()
    app.bus.subscribe(ResponseReady, replies.put)
    await app.start()
    try:
        # The fake Talker repeats what it's sent, so its replies show its prompts.
        app.bus.publish(InputReceived(text="hello there", source="test"))
        await next_matching(replies, lambda e: e.text == "hello there")

        app.bus.publish(ResetRequested(agent_id="talker"))
        app.bus.publish(InputReceived(text="still there?", source="test"))
        after = await next_matching(replies, lambda e: "still there?" in e.text)
        assert after.text.startswith("[Context] Your session was just reset")
        assert "User: hello there" in after.text
    finally:
        await app.stop()


async def test_talker_marks_spoken_input():
    config = {"modules": {"enabled": ["talker"], "talker": {"program": FAKE}}, "core": {}}
    app = App([TalkerModule], config)
    replies: asyncio.Queue[ResponseReady] = asyncio.Queue()
    app.bus.subscribe(ResponseReady, replies.put)
    await app.start()
    try:
        # The fake Talker repeats what it's sent: voice input comes marked, typed input doesn't.
        app.bus.publish(InputReceived(text="HELLO MIKE", source="voice"))
        spoken = await next_matching(replies, lambda e: "HELLO MIKE" in e.text)
        assert spoken.text == "[Spoken] HELLO MIKE"
        app.bus.publish(InputReceived(text="typed hello", source="temp_ui"))
        typed = await next_matching(replies, lambda e: "typed hello" in e.text)
        assert typed.text == "typed hello"
    finally:
        await app.stop()
