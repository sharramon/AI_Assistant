"""Two passes in the voice service: the piece cutter, the voice-clean worker, the new protocol messages.

Fake engines and sources only, apart from one whisper test that skips without the real model.
"""

import os
import threading
import time
import types
from array import array

import pytest
from fastapi.testclient import TestClient

from assistant.modules.voice_in.tests.voice_client import LocalClient
from voice_service.audio import FakeSource, FileSource
from voice_service.config import ServiceConfig, final_engine_name, models_dir, whisper_folder
from voice_service.engines import EngineError, SttEngine, SttStream
from voice_service.engines.fake import FakeEngine
from voice_service.engines.whisper import WhisperEngine
from voice_service.pieces import PieceCutter
from voice_service.protocol import (
    Cleaned,
    Final,
    FinalPart,
    MicBack,
    MicDropped,
    Partial,
    Refining,
    Started,
    parse_service_message,
)
from voice_service.server import create_app
from voice_service.session import ListenSession

# --- the cutter: levels in, cuts out (100 ms chunks: pause 3, min 10, max 20, search 5) ---


def cutter() -> PieceCutter:
    return PieceCutter(
        chunk_ms=100, speech_rms=300, pause_seconds=0.3, min_seconds=1.0, max_seconds=2.0, cut_search_seconds=0.5
    )


def feed(c: PieceCutter, levels) -> list[int | None]:
    return [c.feed(level) for level in levels]


def test_a_pause_after_speech_cuts_and_a_shorter_one_doesnt():
    c = cutter()
    assert feed(c, [1000] * 10 + [0, 0]) == [None] * 12  # 0.2 s of quiet: no cut
    assert feed(c, [1000, 0, 0, 0]) == [None, None, None, 16]  # 0.3 s: cut at the end of the quiet
    assert not c.speech  # a new piece


def test_no_cut_before_the_minimum_length():
    c = cutter()
    assert feed(c, [1000] * 3 + [0] * 4 + [1000] * 2) == [None] * 9  # a pause at 0.7 s: too short to cut
    assert feed(c, [0, 0, 0]) == [None, None, 12]


def test_talk_with_no_pause_cuts_at_the_quietest_chunk_near_the_maximum():
    c = cutter()
    levels = [1000 + i for i in range(20)]
    levels[17] = 400  # the quietest of the last 0.5 s, still speech
    assert feed(c, levels) == [None] * 19 + [18]  # the cut goes after chunk 17; chunks 18 and 19 start the next piece
    assert c.speech
    assert feed(c, [1000] * 17) == [None] * 17
    assert c.feed(1000) is not None  # 20 chunks of speech in the new piece: forced again


def test_quiet_never_cuts_and_a_quiet_lead_in_doesnt_force_one():
    c = cutter()
    assert feed(c, [0] * 100) == [None] * 100 and not c.speech
    assert feed(c, [1000] * 5) == [None] * 5  # 10.5 s since the piece began, but only 0.5 s of speech


def test_from_config_and_reset():
    c = PieceCutter.from_config(ServiceConfig().pieces, chunk_ms=32, speech_rms=300)
    assert (c._pause, c._min, c._max, c._search) == (22, 125, 625, 94)
    c.feed(1000)
    c.reset()
    assert not c.speech


# --- fakes: a live engine that records its audio, a final engine that numbers its pieces ---


def loud(i: int) -> bytes:
    return array("h", [3000 + i] * 512).tobytes()  # 32 ms of speech, each chunk different


def quiet(i: int) -> bytes:
    return array("h", [i % 50] * 512).tobytes()  # 32 ms below speech_rms


WORDS = " ".join(f"w{i}" for i in range(60))


class LiveEngine(FakeEngine):
    """A word every 2 chunks; keeps every chunk it was given."""

    def __init__(self) -> None:
        super().__init__(WORDS)
        self.audio = bytearray()

    def new_stream(self) -> SttStream:
        stream, accept = super().new_stream(), None
        accept = stream.accept

        def record(pcm: bytes) -> None:
            self.audio += pcm
            accept(pcm)

        stream.accept = record
        return stream


class PieceEngine(SttEngine):
    """The final engine: piece i comes back as "Piece{i}."; `fail`, `empty`, `slow` pick pieces to misbehave."""

    name = "pieces"
    live_partials = False

    def __init__(self, *, fail=(), empty=(), slow=(), slow_seconds=5.0, load_error=False) -> None:
        self.fail, self.empty, self.slow, self.slow_seconds = set(fail), set(empty), set(slow), slow_seconds
        self.load_error = load_error
        self.audio: list[bytes] = []
        self.prompts: list[str] = []
        self.cancelled: list[int] = []
        self.running = threading.Event()  # set while a slow piece runs

    def load(self) -> None:
        if self.load_error:
            raise EngineError("pieces: load failed")

    def new_stream(self) -> SttStream:
        return _PieceStream(self)


class _PieceStream(SttStream):
    def __init__(self, engine: PieceEngine) -> None:
        self.engine, self.audio, self.prompt = engine, bytearray(), ""
        self.stopped = threading.Event()
        self.index = -1

    def accept(self, pcm: bytes) -> None:
        self.audio += pcm

    def partial(self) -> str:
        return ""

    def set_prompt(self, text: str) -> None:
        self.prompt = text

    def cancel(self) -> None:
        self.engine.cancelled.append(self.index)
        self.stopped.set()

    def finish(self) -> str:
        e = self.engine
        self.index = len(e.audio)
        e.audio.append(bytes(self.audio))
        e.prompts.append(self.prompt)
        if self.index in e.fail:
            raise RuntimeError("pieces: failed")
        if self.index in e.slow:
            e.running.set()
            self.stopped.wait(e.slow_seconds)
        return "" if self.index in e.empty else f"Piece{self.index}."


# Two pieces cut at pauses, then a last one: 12 loud + 5 quiet, 12 loud + 5 quiet, 6 loud (40 chunks, 20 words).
TALK = [loud(i) for i in range(12)] + [quiet(i) for i in range(5)] + [loud(i) for i in range(12, 24)] + \
       [quiet(i) for i in range(5, 10)] + [loud(i) for i in range(24, 30)]  # fmt: skip
LIVE_TEXT = " ".join(f"w{i}" for i in range(20))


def make_config(**engine) -> ServiceConfig:
    return ServiceConfig.model_validate({
        "engine": {"name": "fake", "partial_interval_ms": 0, **engine},
        "audio": {"stall_seconds": 0},
        "pieces": {"pause_seconds": 0.1, "min_seconds": 0.3, "max_seconds": 1.0, "cut_search_seconds": 0.2},
    })  # fmt: skip


def make_client(final=None, *, live=None, source=None, config=None) -> TestClient:
    factory = source if callable(source) else (lambda: FakeSource(TALK if source is None else source))
    app = create_app(config or make_config(), live or LiveEngine(), factory, final_engine=final)
    return LocalClient(app)


def recv(ws):
    return parse_service_message(ws.receive_text())


def until(ws, kind, count=1):
    """Messages up to and including the `count`-th of type `kind`."""
    out, seen = [], 0
    while seen < count:
        out.append(recv(ws))
        seen += isinstance(out[-1], kind)
    return out


def start(ws, partials=True):
    ws.send_text('{"type": "start", "partials": %s}' % ("true" if partials else "false"))
    return recv(ws)


def stop(ws):
    ws.send_text('{"type": "stop"}')


def talk(ws, cleaned_before_stop=2):
    """Start, wait for the cleaned pieces cut while talking, stop; every message up to the final."""
    assert start(ws) == Started(clean_pieces=True)
    messages = until(ws, Cleaned, cleaned_before_stop)
    time.sleep(0.2)  # the last chunks reach the engine
    stop(ws)
    return messages + until(ws, Final)


def kinds(messages):
    return [type(m).__name__ for m in messages if not isinstance(m, Partial)]


# --- two passes: the main path ---


def test_pieces_are_cleaned_in_order_while_talking_and_the_final_joins_them():
    live, final = LiveEngine(), PieceEngine(slow={0}, slow_seconds=0.3)  # piece 0 is slow: piece 1 still comes after it
    with make_client(final, live=live) as client, client.websocket_connect("/ws/listen") as ws:
        messages = talk(ws)
    assert kinds(messages) == ["Cleaned", "Cleaned", "Refining", "Cleaned", "Final"]
    cleaned = [m for m in messages if isinstance(m, Cleaned)]
    assert [c.piece for c in cleaned] == [0, 1, 2]
    assert [(c.start, c.end) for c in cleaned] == [(0, 8), (8, 16), (16, 20)]  # back to back from word 0
    assert [c.text for c in cleaned] == ["Piece0.", "Piece1.", "Piece2."] and {c.fallback for c in cleaned} == {""}
    refining = next(m for m in messages if isinstance(m, Refining))
    assert (refining.text, refining.pending) == (LIVE_TEXT, 1)
    result = messages[-1]
    assert result.text == "Piece0. Piece1. Piece2." and result.complete
    assert result.parts == (FinalPart(text="Piece0."), FinalPart(text="Piece1."), FinalPart(text="Piece2."))
    assert b"".join(final.audio) == bytes(live.audio)  # nothing lost or doubled at a cut
    assert final.prompts == ["", "Piece0.", "Piece1."]  # each piece gets the previous piece's text


def test_without_the_prompt_setting_no_piece_gets_a_prompt():
    config = make_config()
    config.pieces.prompt_previous = False
    final = PieceEngine()
    with make_client(final, config=config) as client, client.websocket_connect("/ws/listen") as ws:
        talk(ws)
    assert final.prompts == ["", "", ""]


def test_a_failed_or_empty_piece_keeps_its_live_words_and_later_pieces_still_get_cleaned():
    with make_client(PieceEngine(fail={0}, empty={1})) as client, client.websocket_connect("/ws/listen") as ws:
        messages = talk(ws)
    cleaned = [m for m in messages if isinstance(m, Cleaned)]
    assert [(c.text, c.fallback) for c in cleaned] == [("", "failed"), ("", "empty"), ("Piece2.", "")]
    result = messages[-1]
    assert result.text == " ".join(f"w{i}" for i in range(16)) + " Piece2."
    assert [(p.cleaned, p.fallback) for p in result.parts] == [(False, "failed"), (False, "empty"), (True, "")]


# Two pieces cut at pauses, then quiet only: an odd chunk count, so the live engine's finish
# releases one more (lagging) word than its last partial, as Zipformer does at a stop.
SILENT_END = TALK[:34] + [quiet(10)]


def test_a_silent_last_piece_drops_its_lagging_word_when_the_final_engine_hears_nothing():
    final = PieceEngine(empty={2})  # whisper hears nothing in the silence after the last cut
    with make_client(final, source=SILENT_END) as client, client.websocket_connect("/ws/listen") as ws:
        messages = talk(ws)
    last = [m for m in messages if isinstance(m, Cleaned)][-1]
    assert (last.piece, last.text, last.fallback) == (2, "", "")  # settled as cleaned, with nothing
    result = messages[-1]
    assert result.text == "Piece0. Piece1."  # no raw word doubled after the cleaned text
    assert result.parts[-1] == FinalPart(text="")


def test_a_last_piece_with_speech_and_nothing_heard_still_keeps_its_live_words():
    with make_client(PieceEngine(empty={2})) as client, client.websocket_connect("/ws/listen") as ws:
        messages = talk(ws)
    result = messages[-1]
    assert result.text == "Piece0. Piece1. w16 w17 w18 w19"
    assert (result.parts[-1].cleaned, result.parts[-1].fallback) == (False, "empty")


def test_a_piece_still_running_at_the_timeout_keeps_its_live_words_and_is_cancelled():
    final = PieceEngine(slow={2})
    with make_client(final, config=make_config(final_timeout_seconds=0.5)) as client:
        with client.websocket_connect("/ws/listen") as ws:
            messages = talk(ws)
    assert final.cancelled == [2]
    last = [m for m in messages if isinstance(m, Cleaned)][-1]
    assert (last.piece, last.text, last.fallback) == (2, "", "timed_out")
    result = messages[-1]
    assert result.text == "Piece0. Piece1. w16 w17 w18 w19" and 400 <= result.latency_ms < 3000


def test_force_on_send_still_cleans_pieces_but_sends_no_live_text():
    with make_client(PieceEngine()) as client, client.websocket_connect("/ws/listen") as ws:
        assert start(ws, partials=False) == Started(partials=False, clean_pieces=True)
        time.sleep(0.5)
        stop(ws)
        messages = until(ws, Final)
    assert kinds(messages) == ["Refining", "Final"] and len(messages) == 2
    assert messages[0] == Refining(text="", pending=1)  # two pieces were already cleaned in the background
    assert messages[-1].text == "Piece0. Piece1. Piece2."


def test_a_mic_drop_ends_a_piece_and_no_audio_is_lost(monkeypatch):
    monkeypatch.setattr(ListenSession, "retry_seconds", 0.01)
    sources = iter([FakeSource(TALK[:12], lose_after=12), FakeSource(TALK[12:])])
    live, final = LiveEngine(), PieceEngine()
    with make_client(final, live=live, source=lambda: next(sources)) as client:
        with client.websocket_connect("/ws/listen") as ws:
            messages = talk(ws)
    assert any(isinstance(m, MicDropped) for m in messages) and any(isinstance(m, MicBack) for m in messages)
    assert kinds(messages)[-2:] == ["Cleaned", "Final"]
    assert [m.end for m in messages if isinstance(m, Cleaned)] == [6, 16, 20]  # the drop cut after 12 chunks
    assert b"".join(final.audio) == bytes(live.audio)


# --- no pieces ---


def test_one_engine_sends_no_cleaned_and_no_refining():
    with make_client(None) as client, client.websocket_connect("/ws/listen") as ws:
        assert start(ws) == Started()
        time.sleep(0.2)
        stop(ws)
        messages = until(ws, Final)
    assert kinds(messages) == ["Final"] and messages[-1].text == LIVE_TEXT and messages[-1].parts == ()
    assert client.get("/health").json()["final"] == ""


def test_a_final_engine_that_fails_to_load_leaves_one_engine():
    with make_client(PieceEngine(load_error=True)) as client:
        deadline = time.monotonic() + 5
        while client.get("/health").json()["final_error"] is None and time.monotonic() < deadline:
            time.sleep(0.02)
        health = client.get("/health").json()
        assert (health["final"], health["final_ready"], health["ready"]) == ("pieces", False, True)
        assert "load failed" in health["final_error"]
        with client.websocket_connect("/ws/listen") as ws:
            assert start(ws) == Started(clean_pieces=False)
            time.sleep(0.2)
            stop(ws)
            assert kinds(until(ws, Final)) == ["Final"]


def test_a_live_engine_without_live_text_cant_have_a_final_engine():
    class OnSend(FakeEngine):
        live_partials = False

    with make_client(PieceEngine(), live=OnSend()) as client, client.websocket_connect("/ws/listen") as ws:
        assert start(ws) == Started(partials=False, clean_pieces=False)
        assert client.get("/health").json()["final"] == ""


def test_a_mic_lost_for_good_drops_the_queue():
    final = PieceEngine(slow={0})
    config = make_config()
    config.audio.mic_recovery_seconds = 0
    with make_client(final, config=config, source=lambda: FakeSource(TALK, interval=0.01, lose_after=20)) as client:
        with client.websocket_connect("/ws/listen") as ws:
            assert start(ws) == Started(clean_pieces=True)
            messages = until(ws, Final)
    assert "Refining" not in kinds(messages)
    assert messages[-1].complete is False and messages[-1].parts == ()
    assert final.running.wait(2) and final.cancelled == [0]


# --- discard (the socket closes) ---


@pytest.mark.parametrize("while_finishing", [False, True])
def test_closing_the_socket_cancels_the_running_piece_and_frees_the_slot(while_finishing):
    slow = 2 if while_finishing else 1
    final = PieceEngine(slow={slow})
    with make_client(final) as client:
        with client.websocket_connect("/ws/listen") as ws:
            assert start(ws) == Started(clean_pieces=True)
            until(ws, Cleaned, slow)
            if while_finishing:
                time.sleep(0.2)
                stop(ws)
                until(ws, Refining)
            assert final.running.wait(2)
        deadline = time.monotonic() + 3
        while final.cancelled != [slow] and time.monotonic() < deadline:
            time.sleep(0.02)
        assert final.cancelled == [slow]
        with client.websocket_connect("/ws/listen") as ws:
            assert start(ws) == Started(clean_pieces=True)


# --- config ---


def test_final_engine_name():
    def name(engine: dict) -> str:
        return final_engine_name(ServiceConfig.model_validate({"engine": engine}))

    assert ServiceConfig().engine.final == "whisper" and ServiceConfig().engine.final_timeout_seconds == 20.0
    assert name({}) == "whisper"
    assert name({"final": ""}) == "" and name({"name": "whisper", "final": "whisper"}) == ""
    assert name({"name": "whisper", "final": "zipformer"}) == "zipformer"  # create_app refuses it (no live text)


def _write(path, text: str, bump: int) -> None:
    path.write_text(text, encoding="utf-8")
    stamp = time.time_ns() + bump * 10**9
    os.utime(path, ns=(stamp, stamp))


def test_a_pieces_change_applies_without_a_restart_and_a_final_change_restarts(tmp_path):
    path, quit_event = tmp_path / "voice.toml", threading.Event()
    base = '[engine]\nname = "fake"\npartial_interval_ms = 0\n'
    _write(path, base, 0)
    config = make_config()
    app = create_app(config, LiveEngine(), lambda: FakeSource([]), config_path=path, watch_seconds=0.05)
    app.state.on_quit = quit_event.set
    with TestClient(app):
        _write(path, base + "[pieces]\npause_seconds = 0.5\n", 1)
        assert not quit_event.wait(0.4)
        assert config.pieces.pause_seconds == 0.5
        _write(path, base + 'final = ""\n[pieces]\npause_seconds = 0.5\n', 2)
        assert quit_event.wait(3)


# --- whisper: cancel and the prompt ---


def test_whisper_cancel_stops_between_segments_and_the_prompt_is_passed():
    pytest.importorskip("numpy")
    calls, stream_box = [], {}

    def segments():
        yield types.SimpleNamespace(text=" One.")
        stream_box["stream"].cancel()  # cancelled while decoding
        yield types.SimpleNamespace(text=" Two.")

    class Model:
        def transcribe(self, samples, **options):
            calls.append(options)
            return segments(), None

    engine = WhisperEngine(".", ServiceConfig().engine.whisper)
    engine._model = Model()
    stream = stream_box["stream"] = engine.new_stream()
    stream.set_prompt(" Before this. ")
    stream.accept(bytes(1024))
    assert stream.finish() == ""
    assert calls[0]["initial_prompt"] == "Before this."
    assert engine.new_stream().finish() == ""  # no audio
    cancelled_early = engine.new_stream()
    cancelled_early.accept(bytes(1024))
    cancelled_early.cancel()
    assert cancelled_early.finish() == "" and len(calls) == 1  # never decoded


def _real_whisper():
    config = ServiceConfig()
    folder = models_dir(config) / whisper_folder(config.engine.whisper.model)
    wav = models_dir(config) / config.engine.zipformer.model / "test_wavs" / "0.wav"
    if not (folder / "model.bin").is_file() or not wav.is_file():
        pytest.skip("the whisper model or the test recording isn't installed")
    pytest.importorskip("faster_whisper")
    engine = WhisperEngine(folder, config.engine.whisper)
    engine.load()
    return engine, b"".join(FileSource(wav).chunks)


def test_real_whisper_cancel_during_finish_drops_the_text():
    # faster-whisper decodes a 30 s window at once, so a piece (at most 20 s) can't be cut short:
    # cancel only makes finish throw the text away. The session doesn't wait for it.
    engine, audio = _real_whisper()
    stream = engine.new_stream()
    stream.accept(audio)
    timer = threading.Timer(0.2, stream.cancel)
    timer.start()
    text = stream.finish()
    timer.cancel()
    assert text == ""
