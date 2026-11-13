"""Voice notes v1: the page, its Record button, and the second press winning against the chat's mic."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from assistant.contracts import (
    ActivateModule,
    DeactivateModule,
    InputReceived,
    IVoice,
    ListeningState,
    VoiceDestination,
    VoiceState,
    VoiceTranscript,
)
from assistant.core import App, StartupError
from assistant.modules.temp_ui import TempUIModule
from assistant.modules.voice_in.tests.test_voice_in import CHUNK, TEXT, Probe, Recorder, Service
from assistant.modules.voice_notes import VoiceNotesModule
from assistant.testkit import FakeVoiceIn, next_item, post, request


def port_of(app: App, module_id: str) -> int:
    return int(app._lifecycle._active[module_id][0].url.rsplit(":", 1)[1].strip("/"))


def voice(match):
    return lambda i: i.get("kind") == "voice" and match(i)


def final(i) -> bool:
    return i.get("kind") == "final"


async def events_of(app: App, module_id: str):
    reader, writer = await request(port_of(app, module_id), b"GET /events HTTP/1.1\r\n\r\n")
    await next_item(reader, voice(lambda i: True))  # the current state, on connect
    return reader, writer


NONE = {"window": "none", "port": 0}


# --- with a fake voice_in ---


async def test_record_sends_the_text_to_the_page_only_and_ignores_other_sessions():
    config = {"modules": {"enabled": ["voice_notes", "voice_in"], "voice_notes": NONE}, "core": {}}
    app = App([VoiceNotesModule, FakeVoiceIn], config)
    await app.start()
    port = port_of(app, "voice_notes")
    try:
        reader, writer = await request(port, b"GET / HTTP/1.1\r\n\r\n")
        assert b"Voice notes" in await reader.read()
        writer.close()
        events, writer = await events_of(app, "voice_notes")
        fake = app._lifecycle._active["voice_in"][0]
        assert (await post(port, "/record", {"on": True}))["ok"]
        await next_item(events, voice(lambda i: i["state"] == "listening"))
        assert fake.commands[0].send_as_input is False

        # The chat's session isn't followed; this one's partial is the live line.
        app.bus.publish(VoiceState(state=ListeningState.STARTING, correlation_id="chat"))
        app.bus.publish(VoiceTranscript(session_id="chat", text="not mine", correlation_id="chat"))
        app.bus.publish(VoiceTranscript(session_id=fake.session, text="hello", correlation_id=fake.session))
        item = await next_item(events, voice(lambda i: i["text"]))
        assert (item["text"], item["settled"]) == ("hello", 0)
        # The cleaned start's length comes with the live text, for the page to show it as notes.
        app.bus.publish(VoiceTranscript(session_id=fake.session, text="hello wor", settled_chars=5, correlation_id=fake.session))
        item = await next_item(events, voice(lambda i: i["text"] == "hello wor"))
        assert set(item) == {"kind", "state", "detail", "text", "settled"} and item["settled"] == 5

        assert (await post(port, "/record", {"on": False}))["ok"]
        assert (await next_item(events, final))["text"] == "hello there"
        idle = await next_item(events, voice(lambda i: i["state"] == "idle"))
        assert (idle["text"], idle["settled"]) == ("", 0)
        writer.close()
    finally:
        await app.stop()


async def test_an_empty_final_reaches_the_page_so_it_drops_the_stretch():
    config = {"modules": {"enabled": ["voice_notes", "voice_in"], "voice_notes": NONE}, "core": {}}
    app = App([VoiceNotesModule, FakeVoiceIn], config)
    await app.start()
    port = port_of(app, "voice_notes")
    try:
        events, writer = await events_of(app, "voice_notes")
        fake = app._lifecycle._active["voice_in"][0]
        assert (await post(port, "/record", {"on": True}))["ok"]
        await next_item(events, voice(lambda i: i["state"] == "listening"))
        app.bus.publish(VoiceTranscript(session_id=fake.session, text="", final=True, correlation_id=fake.session))
        assert (await next_item(events, final))["text"] == ""
        writer.close()
    finally:
        await app.stop()


def test_the_page_keeps_the_tail_out_of_saved_and_copied_text():
    page = Path("src/assistant/modules/voice_notes/page.html").read_text(encoding="utf-8")
    assert 'contenteditable="plaintext-only"' in page and "#notes .tail" in page
    assert "font-style: italic" in page.split("#notes .tail", 1)[1].split("}", 1)[0]
    assert "showStretch(v.text, v.settled)" in page  # the voice item's `settled` drives the split
    assert "writeText(plain())" in page and "setItem(KEY, plain())" in page  # plain() skips the tail


def test_voice_notes_needs_the_voice_contract():
    with pytest.raises(StartupError, match="requires IVoice"):
        App([VoiceNotesModule], {"modules": {"enabled": ["voice_notes"], "voice_notes": NONE}, "core": {}})


async def test_turning_voice_notes_on_turns_voice_input_on_first():
    config = {"modules": {"enabled": [], "voice_notes": NONE}, "core": {}}
    app = App([VoiceNotesModule, FakeVoiceIn], config)
    await app.start()
    try:
        assert (await app.router.send(ActivateModule(module_id="voice_notes"))).is_ok
        assert {"voice_in", "voice_notes"} <= set(app._lifecycle._active)
        # voice_in can't go while voice notes needs it
        assert not (await app.router.send(DeactivateModule(module_id="voice_in"))).is_ok
        events, writer = await events_of(app, "voice_notes")
        assert (await post(port_of(app, "voice_notes"), "/record", {"on": True}))["ok"]
        await next_item(events, voice(lambda i: i["state"] == "listening"))
        writer.close()
    finally:
        await app.stop()


def test_voice_notes_imports_no_other_module_and_no_core():
    tree = ast.parse(Path("src/assistant/modules/voice_notes/module.py").read_text(encoding="utf-8"))
    names = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    names |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not {n for n in names if n.startswith(("assistant.modules", "assistant.core", "assistant.infra"))}


# --- with the real voice_in and the voice service on fake audio: the second press wins ---


@pytest.fixture
async def both():
    """temp_ui, voice_notes and the real voice_in on the voice service with fake audio."""
    svc = Service(source=[CHUNK] * 6)
    section = {"host": "127.0.0.1", "port": svc.port, "reply_timeout": 3.0, "cleanup": False}
    modules = {"enabled": ["temp_ui", "voice_notes", "voice_in"], "temp_ui": NONE, "voice_notes": NONE, "voice_in": section}
    app = App([TempUIModule, VoiceNotesModule, Probe], {"modules": modules, "core": {}})
    rec = Recorder(app)
    await app.start()
    try:
        yield app, rec
    finally:
        await app.stop()
        svc.close()


async def test_two_sessions_through_the_contract_each_get_only_their_own_text(both):
    app, rec = both
    voice = app.container.get_one(IVoice)
    assert (await voice.listen("first", VoiceDestination.CALLER)).is_ok
    await rec.wait(lambda r: said(r, "first"))
    assert (await voice.listen("second", VoiceDestination.TALKER)).is_ok  # the second wins
    await rec.wait(lambda r: any(s.reason == "taken_over" for s in r.of(VoiceState) if s.correlation_id == "first"))

    # The first caller's stop ends nothing of the second's.
    assert (await voice.finish("first")).value == {"text": "", "ended": True}
    assert Probe.last._session is not None and Probe.last._session.id == "second"

    await rec.wait(lambda r: any(t.text == TEXT for t in r.of(VoiceTranscript) if t.correlation_id == "second"))
    assert (await voice.finish("second")).value["text"] == TEXT
    assert [t.text for t in rec.of(VoiceTranscript) if t.correlation_id == "first" and t.final] == [""]
    await rec.wait(lambda r: r.of(InputReceived))
    assert [i.text for i in rec.of(InputReceived)] == [TEXT]  # only the TALKER session reaches the Talker


def started(rec: Recorder) -> list[str]:
    return [s.correlation_id for s in rec.of(VoiceState) if s.state is ListeningState.STARTING]


def said(rec: Recorder, sid: str) -> bool:
    return any(t.text and t.correlation_id == sid for t in rec.of(VoiceTranscript))


async def test_notes_pressed_while_the_chat_mic_is_on(both):
    app, rec = both
    chat_port, notes_port = port_of(app, "temp_ui"), port_of(app, "voice_notes")
    chat, chat_writer = await events_of(app, "temp_ui")
    notes, notes_writer = await events_of(app, "voice_notes")
    try:
        await post(chat_port, "/mic", {"on": True})
        await rec.wait(lambda r: started(r) and said(r, started(r)[0]))
        assert (await post(notes_port, "/record", {"on": True}))["ok"]
        cancelled = await next_item(chat, voice(lambda i: i["state"] == "idle"))
        assert cancelled["detail"] == "cancelled: another part of the app took the mic" and cancelled["available"]
        notes_sid = started(rec)[1]
        await rec.wait(lambda r: said(r, notes_sid))

        # The cancelled side sends no stop: the notes recording carries on.
        assert (await post(chat_port, "/mic", {"on": False}))["ok"]
        assert Probe.last._session is not None and Probe.last._session.id == notes_sid

        await rec.wait(lambda r: any(t.text == TEXT for t in r.of(VoiceTranscript) if t.correlation_id == notes_sid))
        assert (await post(notes_port, "/record", {"on": False}))["ok"]
        assert (await next_item(notes, final))["text"] == TEXT
        assert rec.of(InputReceived) == []  # the chat's words were dropped; the notes' never go to the Talker
    finally:
        chat_writer.close()
        notes_writer.close()


async def test_chat_mic_pressed_while_notes_is_on(both):
    app, rec = both
    chat_port, notes_port = port_of(app, "temp_ui"), port_of(app, "voice_notes")
    notes, notes_writer = await events_of(app, "voice_notes")
    try:
        await post(notes_port, "/record", {"on": True})
        await rec.wait(lambda r: started(r) and said(r, started(r)[0]))
        assert (await post(chat_port, "/mic", {"on": True}))["ok"]
        cancelled = await next_item(notes, voice(lambda i: i["state"] == "idle"))
        assert cancelled["detail"] == "cancelled: another part of the app took the mic"
        chat_sid = started(rec)[1]

        # The cancelled side sends no stop: the chat recording carries on.
        assert (await post(notes_port, "/record", {"on": False}))["ok"]
        assert Probe.last._session is not None and Probe.last._session.id == chat_sid

        await rec.wait(lambda r: any(t.text == TEXT for t in r.of(VoiceTranscript) if t.correlation_id == chat_sid))
        assert (await post(chat_port, "/mic", {"on": False}))["ok"]
        await rec.wait(lambda r: r.of(InputReceived))
        assert [i.text for i in rec.of(InputReceived)] == [TEXT]  # only the chat's text reaches the Talker
        # The notes' cancelled session ended with an empty final only: nothing for the page.
        notes_sid = started(rec)[0]
        assert [t.text for t in rec.of(VoiceTranscript) if t.correlation_id == notes_sid and t.final] == [""]
    finally:
        notes_writer.close()
