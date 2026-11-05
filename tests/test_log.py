"""The log handler: nothing on disk until the first message's theme, then one folder per app launch."""

import logging
from datetime import datetime

import pytest

from assistant.__main__ import use_log_session
from assistant.contracts import Manifest, ModuleProtocol
from assistant.core import App
from assistant.infra import ClaudeSession, LogSession, setup_logging, theme_slug
from tests.test_agents import FAKE

START = datetime(2026, 10, 26, 3, 6, 52)


@pytest.fixture
def root_logging():
    """setup_logging replaces the root logger's handlers; put them back afterwards."""
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    for handler in root.handlers:
        if handler not in handlers:
            handler.close()
    root.handlers[:] = handlers
    root.setLevel(level)


def test_theme_slug():
    assert theme_slug("Session log folders?!") == "session-log-folders"
    assert theme_slug("Can you split the logs per session, please?") == "can-you-split-the-logs"
    assert theme_slug('  C:\\bad/name:*?"<>|  ') == "c-bad-name"
    assert theme_slug("Ünïcode café") == "n-code-caf"
    assert theme_slug("?!...") == ""


def test_nothing_on_disk_until_the_theme(tmp_path):
    logs = LogSession(tmp_path / "logs", now=START)
    logs.sink("talker.jsonl").write("held\n")
    assert not (tmp_path / "logs").exists()
    assert logs.path is None and logs.folder() == tmp_path / "logs"

    logs.set_theme("Session log folders")
    assert logs.path == tmp_path / "logs" / "2026-10-26_03-06-52_session-log-folders"
    assert logs.folder() == logs.path
    logs.sink("talker.jsonl").write("after\n")
    assert (logs.path / "talker.jsonl").read_text(encoding="utf-8") == "held\nafter\n"
    assert logs.finish() == logs.path


def test_first_usable_theme_wins(tmp_path):
    logs = LogSession(tmp_path, now=START)
    logs.set_theme("!!!")
    assert logs.path is None
    logs.set_theme("session log folders")
    logs.set_theme("something else")
    assert logs.finish().name == "2026-10-26_03-06-52_session-log-folders"


def test_two_launches_in_one_second_get_their_own_folders(tmp_path):
    first, second = LogSession(tmp_path, now=START), LogSession(tmp_path, now=START)
    first.set_theme("same theme")
    second.set_theme("same theme")
    assert second.path.name == "2026-10-26_03-06-52-2_same-theme"


class _Writer(ModuleProtocol):
    manifest = Manifest(id="writer", description="Writes through ctx.logs")

    async def init(self, ctx):
        self.ctx = ctx


def test_app_log_and_transcripts_land_in_the_folder(tmp_path, root_logging):
    config = {
        "logging": {"dir": str(tmp_path / "logs"), "file": "assistant.log"},
        "modules": {"enabled": ["writer"], "writer": {"transcript": "talker.jsonl"}},
    }
    logs = use_log_session(config)
    assert "file" not in config["logging"]
    assert config["modules"]["writer"] == {"transcript": "talker.jsonl"}  # nothing put into config
    ctx = App([_Writer], config, logs=logs)._make_context(_Writer.manifest)
    assert ctx.logs.sink("talker.jsonl") is logs.sink("talker.jsonl")
    assert ctx.logs.folder() == tmp_path / "logs"

    setup_logging(config["logging"], [logs.handler])
    logging.getLogger("assistant.test").info("before the first message")
    ctx.logs.sink(ctx.config["transcript"]).write("{}\n")
    logs.set_theme("Session log folders")
    logging.getLogger("assistant.test").info("after the first message")
    logs.finish()

    text = (logs.path / "assistant.log").read_text(encoding="utf-8")
    assert "before the first message" in text and "after the first message" in text
    assert (logs.path / "talker.jsonl").read_text(encoding="utf-8") == "{}\n"
    assert ctx.logs.folder() == logs.path


def test_without_a_log_session_ctx_logs_gives_paths_under_the_logs_dir(tmp_path):
    config = {"logging": {"dir": str(tmp_path / "logs")}, "modules": {"enabled": []}}
    ctx = App([_Writer], config)._make_context(_Writer.manifest)
    assert ctx.logs.folder() == tmp_path / "logs"
    assert ctx.logs.sink("talker.jsonl") == tmp_path / "logs" / "talker.jsonl"


def test_a_session_without_chat_leaves_nothing(tmp_path, root_logging):
    logs = LogSession(tmp_path / "logs", now=START)
    setup_logging({}, [logs.handler])
    logging.getLogger("assistant.test").info("started")
    logs.sink("talker.jsonl").write("{}\n")
    assert logs.finish() is None
    assert not (tmp_path / "logs").exists()


def test_a_session_without_chat_keeps_its_warnings_in_no_chat_log(tmp_path, root_logging):
    logs = LogSession(tmp_path / "logs", now=START)
    setup_logging({}, [logs.handler])
    logging.getLogger("assistant.test").info("started")
    logging.getLogger("assistant.test").error("claude is missing")
    assert logs.finish() is None
    assert [p.name for p in (tmp_path / "logs").iterdir()] == ["no-chat.log"]
    text = (tmp_path / "logs" / "no-chat.log").read_text(encoding="utf-8")
    assert text.startswith("--- 2026-10-26_03-06-52: no chat ---\n")
    assert "started" in text and "claude is missing" in text


async def test_session_writes_its_transcript_to_a_sink(tmp_path):
    logs = LogSession(tmp_path, now=START)
    session = ClaudeSession(FAKE, transcript=logs.sink("talker.jsonl"))
    await session.start()
    await session.send("hello")
    await session.close()
    logs.set_theme("hello")
    assert '"dir": "in"' in (logs.path / "talker.jsonl").read_text(encoding="utf-8")
