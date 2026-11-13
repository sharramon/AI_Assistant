"""The voice service app (voice_in's app/voice_service) with the fake engine and fake sources: no mic, no model, no network."""

import io
import os
import subprocess
import sys
import tarfile
import threading
import time
import tomllib
import types
import wave
from array import array

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app_kit.companion import launch_env
from assistant.modules.voice_in.tests.voice_client import LocalClient
from voice_service.audio import FakeSource, FileSource
from voice_service.config import DEFAULT_CONFIG, ServiceConfig, load_service_config, models_dir
from voice_service.download import download_model
from voice_service.engines import EngineError, load_engine
from voice_service.engines.fake import FakeEngine
from voice_service.engines.whisper import WhisperEngine
from voice_service.engines.zipformer import ZipformerEngine
from voice_service.protocol import (
    Error,
    ErrorCode,
    Final,
    MicBack,
    MicDropped,
    Partial,
    Started,
    parse_service_message,
)
from voice_service.server import create_app
from voice_service.session import ListenSession, rms
from voice_service.transcribe import transcribe

CHUNK = bytes(1024)  # 32 ms of silence: 512 frames of PCM16


def make_config(**audio) -> ServiceConfig:
    audio = {"stall_seconds": 0, **audio}  # fake sources go quiet after their chunks: no stall watchdog unless asked
    return ServiceConfig.model_validate({"engine": {"name": "fake", "partial_interval_ms": 0}, "audio": audio})


def make_client(engine=None, source=None, config=None) -> TestClient:
    engine = engine or FakeEngine("hello big world")
    factory = source if callable(source) else (lambda: FakeSource(source or []))
    return LocalClient(create_app(config or make_config(), engine, factory))


def recv(ws):
    return parse_service_message(ws.receive_text())


def until(ws, kind):
    """Messages up to and including the first of type `kind`."""
    out = []
    while not out or not isinstance(out[-1], kind):
        out.append(recv(ws))
    return out


def wait_health(client, check, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        health = client.get("/health").json()
        if check(health):
            return health
        time.sleep(0.02)
    raise AssertionError(f"health never matched: {health}")


def start(ws):
    ws.send_text('{"type": "start"}')
    return recv(ws)


def stop(ws):
    ws.send_text('{"type": "stop"}')


# --- /health, /quit ---


def test_health_before_and_after_the_model_loads():
    gate = threading.Event()
    with make_client(FakeEngine(load_gate=gate)) as client:
        assert client.get("/health").json() == {
            "app": "voice_service", "engine": "fake", "ready": False, "error": None,
            "final": "", "final_ready": False, "final_error": None,
        }  # fmt: skip
        gate.set()
        assert wait_health(client, lambda h: h["ready"])["error"] is None


def test_quit_aborts_the_session_and_ends_the_server():
    quit_called = threading.Event()
    with make_client() as client:
        client.app.state.on_quit = quit_called.set
        with client.websocket_connect("/ws/listen") as ws:
            assert start(ws) == Started()
            assert client.post("/quit", json={}).json() == {"ok": True}
            assert quit_called.is_set()
            with client.websocket_connect("/ws/listen") as other:
                assert start(other) == Started()  # the slot was freed


def test_refuses_other_hosts_and_other_origins():
    """A web page you visit can't open the mic or quit the service (app_kit.local_guard)."""
    quit_called = threading.Event()
    with make_client() as client:
        client.app.state.on_quit = quit_called.set
        # Another site's page: a cross-site WebSocket, or a POST to /quit.
        with pytest.raises(WebSocketDisconnect) as refused:
            with client.websocket_connect("/ws/listen", headers={"origin": "https://evil.example"}) as ws:
                ws.receive_text()
        assert refused.value.code == 1008
        assert client.post("/quit", json={}, headers={"origin": "https://evil.example"}).status_code == 403
        # DNS rebinding: a foreign Host.
        assert TestClient(client.app).get("/health").status_code == 403  # Host: testserver
        # A plain form (not JSON) can't quit it either.
        assert client.post("/quit", content=b"x", headers={"content-type": "text/plain"}).status_code == 415
        assert not quit_called.is_set()
        assert client.get("/health").status_code == 200  # its real clients: a local Host, no Origin


def test_main_refuses_a_non_local_host():
    from voice_service.__main__ import main

    assert main(["--host", "0.0.0.0"]) == 2


# --- /ws/listen: the main path ---


def test_start_partials_stop_final():
    with make_client(source=[CHUNK] * 6) as client, client.websocket_connect("/ws/listen") as ws:
        assert start(ws) == Started()
        partials = [recv(ws) for _ in range(3)]
        assert partials == [Partial(text="hello"), Partial(text="hello big"), Partial(text="hello big world")]
        stop(ws)
        final = recv(ws)
        assert isinstance(final, Final)
        assert (final.text, final.complete, final.ended_by) == ("hello big world", True, "stop")
        assert 0 <= final.latency_ms < 2000


def test_stop_with_nothing_listening_gets_an_empty_final():
    with make_client() as client, client.websocket_connect("/ws/listen") as ws:
        stop(ws)
        assert recv(ws) == Final(text="", latency_ms=0)


def test_start_while_the_model_loads_buffers_the_audio():
    gate = threading.Event()
    with make_client(FakeEngine("one two", load_gate=gate), source=[CHUNK] * 4) as client:
        with client.websocket_connect("/ws/listen") as ws:
            assert start(ws) == Started()
            time.sleep(0.1)
            gate.set()
            assert until(ws, Partial)[-1] == Partial(text="one")


def test_second_client_is_busy_and_the_first_carries_on():
    with make_client() as client, client.websocket_connect("/ws/listen") as a:
        assert start(a) == Started()
        with client.websocket_connect("/ws/listen") as b:
            error = start(b)
            assert isinstance(error, Error) and error.reason is ErrorCode.BUSY
        stop(a)
        assert isinstance(recv(a), Final)


def test_bad_messages_keep_the_session_running():
    with make_client() as client, client.websocket_connect("/ws/listen") as ws:
        assert start(ws) == Started()
        for raw in ("not json", '{"type": "shout"}'):
            ws.send_text(raw)
            error = recv(ws)
            assert isinstance(error, Error) and error.reason is ErrorCode.BAD_MESSAGE
        stop(ws)
        assert isinstance(recv(ws), Final)


def test_disconnect_mid_session_frees_the_slot():
    with make_client() as client:
        with client.websocket_connect("/ws/listen") as a:
            assert start(a) == Started()
        with client.websocket_connect("/ws/listen") as b:
            deadline = time.monotonic() + 5
            reply = start(b)
            while isinstance(reply, Error) and reply.reason is ErrorCode.BUSY and time.monotonic() < deadline:
                time.sleep(0.02)
                reply = start(b)
            assert reply == Started()


def test_long_silence_stops_the_session_itself():
    config = make_config(silence_stop_seconds=0.2)
    with make_client(source=[CHUNK] * 2, config=config) as client, client.websocket_connect("/ws/listen") as ws:
        assert start(ws) == Started()
        final = until(ws, Final)[-1]
        assert (final.text, final.ended_by, final.complete) == ("hello", "silence", True)
        stop(ws)
        assert recv(ws) == Final(text="", latency_ms=0)  # nothing listening any more


# --- /ws/listen: errors ---


def test_model_load_failure_is_engine_failed_and_shows_in_health():
    with make_client(FakeEngine(fail_on_load=True)) as client:
        health = wait_health(client, lambda h: h["error"] is not None)
        assert health["ready"] is False and "load failed" in health["error"]
        with client.websocket_connect("/ws/listen") as ws:
            error = start(ws)
            assert isinstance(error, Error) and error.reason is ErrorCode.ENGINE_FAILED


def test_engine_crash_ends_the_session_and_the_next_start_works():
    with make_client(FakeEngine(fail_on_accept=True), source=[CHUNK]) as client:
        with client.websocket_connect("/ws/listen") as ws:
            assert start(ws) == Started()
            error = recv(ws)
            assert isinstance(error, Error) and error.reason is ErrorCode.ENGINE_FAILED
            assert "accept failed" in error.detail
            assert start(ws) == Started()
            stop(ws)
            assert until(ws, Final)[-1].text == "hello"


def test_mic_that_cannot_open_is_mic_unavailable():
    with make_client(source=lambda: FakeSource(fail_on_open=True)) as client:
        with client.websocket_connect("/ws/listen") as ws:
            error = start(ws)
            assert isinstance(error, Error) and error.reason is ErrorCode.MIC_UNAVAILABLE
            assert "failed to open" in error.detail
        assert client.get("/health").json()["ready"] is True


def test_lost_mic_without_recovery_sends_an_incomplete_final_then_mic_lost():
    config = make_config(mic_recovery_seconds=0)
    with make_client(source=lambda: FakeSource([CHUNK] * 10, lose_after=4), config=config) as client:
        with client.websocket_connect("/ws/listen") as ws:
            assert start(ws) == Started()
            messages = until(ws, Error)
            assert not any(isinstance(m, MicDropped) for m in messages)  # today's behavior, unchanged
            final, error = messages[-2:]
            assert isinstance(final, Final) and final.complete is False and final.text == "hello big"
            assert error.reason is ErrorCode.MIC_LOST and "unplugged" in error.detail


def take(*sources):
    """A source factory handing these out in turn; the last one repeats."""
    pending = list(sources)
    return lambda: pending.pop(0) if len(pending) > 1 else pending[0]


@pytest.fixture
def fast_retry(monkeypatch):
    monkeypatch.setattr(ListenSession, "retry_seconds", 0.02)


def test_dropped_mic_comes_back_and_the_text_carries_on(fast_retry):
    factory = take(FakeSource([CHUNK] * 2, lose_after=2), FakeSource(fail_on_open=True), FakeSource([CHUNK] * 4))
    config = make_config(mic_recovery_seconds=5)
    with make_client(source=factory, config=config) as client, client.websocket_connect("/ws/listen") as ws:
        assert start(ws) == Started()
        messages = until(ws, MicBack)
        dropped = next(m for m in messages if isinstance(m, MicDropped))
        assert "unplugged" in dropped.detail and dropped.wait_seconds == 5
        assert Partial(text="hello") in messages
        while recv(ws) != Partial(text="hello big world"):  # the new mic's words carry on from "hello"
            pass
        stop(ws)
        final = recv(ws)
        assert isinstance(final, Final) and (final.text, final.complete) == ("hello big world", True)


def test_mic_that_doesnt_come_back_ends_with_mic_lost(fast_retry):
    factory = take(FakeSource([CHUNK] * 2, lose_after=2), FakeSource(fail_on_open=True))
    config = make_config(mic_recovery_seconds=0.2)
    with make_client(source=factory, config=config) as client, client.websocket_connect("/ws/listen") as ws:
        assert start(ws) == Started()
        messages = until(ws, Error)
        assert any(isinstance(m, MicDropped) for m in messages) and not any(isinstance(m, MicBack) for m in messages)
        final, error = messages[-2:]
        assert isinstance(final, Final) and (final.text, final.complete) == ("hello", False)
        assert error.reason is ErrorCode.MIC_LOST


def test_stop_while_dropped_ends_with_mic_lost(fast_retry):
    factory = take(FakeSource([CHUNK] * 2, lose_after=2), FakeSource(fail_on_open=True))
    config = make_config(mic_recovery_seconds=30)
    with make_client(source=factory, config=config) as client, client.websocket_connect("/ws/listen") as ws:
        assert start(ws) == Started()
        until(ws, MicDropped)
        stop(ws)
        final, error = until(ws, Error)[-2:]
        assert isinstance(final, Final) and final.complete is False and error.reason is ErrorCode.MIC_LOST


def test_the_silence_timer_pauses_while_the_mic_is_dropped(monkeypatch):
    monkeypatch.setattr(ListenSession, "retry_seconds", 0.5)  # the drop lasts longer than the silence limit
    factory = take(FakeSource([CHUNK] * 2, lose_after=2), FakeSource([CHUNK] * 2))
    config = make_config(mic_recovery_seconds=5, silence_stop_seconds=0.3)
    with make_client(source=factory, config=config) as client, client.websocket_connect("/ws/listen") as ws:
        assert start(ws) == Started()
        assert not any(isinstance(m, Final) for m in until(ws, MicBack))


def test_a_mic_that_goes_quiet_without_a_report_counts_as_dropped(fast_retry):
    """An unplug Windows doesn't report: the stream stays open but no chunks come (the stall watchdog)."""
    factory = take(FakeSource([CHUNK] * 2), FakeSource([CHUNK] * 2))  # both go quiet after their chunks
    config = make_config(mic_recovery_seconds=5, stall_seconds=0.2)
    with make_client(source=factory, config=config) as client, client.websocket_connect("/ws/listen") as ws:
        assert start(ws) == Started()
        messages = until(ws, MicBack)
        dropped = next(m for m in messages if isinstance(m, MicDropped))
        assert dropped.detail == "no audio from the mic for 0.2 s"
        stop(ws)
        assert isinstance(until(ws, Final)[-1], Final)


def test_a_stall_that_doesnt_recover_ends_with_mic_lost(fast_retry):
    factory = take(FakeSource([CHUNK] * 2), FakeSource(fail_on_open=True))
    config = make_config(mic_recovery_seconds=0.2, stall_seconds=0.2)
    with make_client(source=factory, config=config) as client, client.websocket_connect("/ws/listen") as ws:
        assert start(ws) == Started()
        final, error = until(ws, Error)[-2:]
        assert final.complete is False and error.reason is ErrorCode.MIC_LOST and "no audio" in error.detail


def test_a_steady_source_never_stalls():
    config = make_config(stall_seconds=0.2)
    source = FakeSource([CHUNK] * 30, interval=0.02)  # 0.6 s of steady chunks, longer than the stall limit
    with make_client(source=lambda: source, config=config) as client, client.websocket_connect("/ws/listen") as ws:
        assert start(ws) == Started()
        time.sleep(0.5)
        stop(ws)
        messages = until(ws, Final)
        assert not any(isinstance(m, MicDropped) for m in messages) and messages[-1].complete is True


# --- MicSource (with a stand-in sounddevice) and the check command ---


class _FakeSd:
    def __init__(self) -> None:
        self.calls: list[str] = []
        sd = self

        class RawInputStream:
            def __init__(self, **kwargs) -> None:
                sd.calls.append("open")

            def start(self) -> None: ...
            def stop(self) -> None: ...
            def close(self) -> None: ...

        self.RawInputStream = RawInputStream

    def _terminate(self) -> None:
        self.calls.append("terminate")

    def _initialize(self) -> None:
        self.calls.append("initialize")


def test_mic_source_reloads_the_device_list_after_a_lost_mic(monkeypatch):
    from voice_service.audio import MicSource

    fake = _FakeSd()
    monkeypatch.setitem(sys.modules, "sounddevice", fake)
    monkeypatch.setattr(MicSource, "stale_devices", False)
    source = MicSource()
    source.start(lambda pcm: None, lambda reason: None)
    assert fake.calls == ["open"]  # a normal open: no reload
    source._last_audio = time.monotonic() - 5  # went quiet, then the session closed it (the stall case)
    source.stop()
    assert MicSource.stale_devices is True
    MicSource().start(lambda pcm: None, lambda reason: None)
    assert fake.calls == ["open", "terminate", "initialize", "open"] and MicSource.stale_devices is False


def test_check_level_and_privacy():
    from array import array

    from voice_service.check import level, mic_privacy

    assert level(array("h")) == (0.0, 0, 1.0)
    rms, peak, zeros = level(array("h", [0, 0, 3, -4]))
    assert (round(rms, 2), peak, zeros) == (2.5, 4, 0.5)
    privacy = mic_privacy()  # reads only; whatever this machine says
    assert set(privacy) <= {"machine", "you", "desktop apps"}
    assert all(isinstance(v, str) for v in privacy.values())


# --- config ---


def test_config_file_matches_the_built_in_defaults():
    with DEFAULT_CONFIG.open("rb") as f:
        assert ServiceConfig.model_validate(tomllib.load(f)) == ServiceConfig()
    defaults = ServiceConfig()
    assert (defaults.server.port, defaults.engine.name, defaults.engine.zipformer.int8) == (8767, "zipformer", True)


def test_local_override_then_flags(tmp_path):
    base = tmp_path / "voice.toml"
    base.write_text('[server]\nport = 9000\n[engine]\nname = "fake"\n', encoding="utf-8")
    (tmp_path / "voice.local.toml").write_text('[server]\nhost = "0.0.0.0"\n[engine.zipformer]\nint8 = false\n', encoding="utf-8")
    config = load_service_config(base)
    assert (config.server.host, config.server.port, config.engine.name) == ("0.0.0.0", 9000, "fake")
    assert config.engine.zipformer.int8 is False
    config = load_service_config(base, host="127.0.0.2", port=9100)
    assert (config.server.host, config.server.port) == ("127.0.0.2", 9100)


def test_missing_config_file_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_service_config(tmp_path / "nope.toml")


def test_models_dir(monkeypatch, tmp_path):
    monkeypatch.delenv("VOICE_SERVICE_MODELS", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert models_dir(ServiceConfig()) == tmp_path / "AI_Assistant" / "voice_models"
    assert models_dir(ServiceConfig.model_validate({"engine": {"models_dir": "D:/m"}})).as_posix() == "D:/m"
    monkeypatch.setenv("VOICE_SERVICE_MODELS", str(tmp_path / "env"))
    assert models_dir(ServiceConfig.model_validate({"engine": {"models_dir": "D:/m"}})) == tmp_path / "env"


# --- engines ---


def test_load_engine_by_name(monkeypatch, tmp_path):
    monkeypatch.setenv("VOICE_SERVICE_MODELS", str(tmp_path))
    assert isinstance(load_engine("fake", ServiceConfig()), FakeEngine)
    zipformer = load_engine("zipformer", ServiceConfig())
    assert isinstance(zipformer, ZipformerEngine) and zipformer.model_dir.parent == tmp_path
    whisper = load_engine("whisper", ServiceConfig())
    assert isinstance(whisper, WhisperEngine) and whisper.model_dir == tmp_path / "faster-whisper-small.en"
    assert (whisper.live_partials, zipformer.live_partials) == (False, True)
    with pytest.raises(EngineError, match="unknown engine"):
        load_engine("vosk", ServiceConfig())


def test_zipformer_missing_model_names_the_download_command(tmp_path):
    engine = ZipformerEngine(tmp_path / "missing", ServiceConfig().engine.zipformer)
    with pytest.raises(EngineError, match="python -m voice_service download zipformer"):
        engine.load()


def test_zipformer_picks_int8_or_full_precision(tmp_path):
    for name in ("tokens.txt", "encoder-e.onnx", "encoder-e.int8.onnx", "decoder-d.onnx", "decoder-d.int8.onnx",
                 "joiner-j.onnx", "joiner-j.int8.onnx"):  # fmt: skip
        (tmp_path / name).write_text("x")
    int8 = ZipformerEngine(tmp_path, ServiceConfig().engine.zipformer).model_files()
    full = ZipformerEngine(tmp_path, ServiceConfig().engine.zipformer.model_copy(update={"int8": False})).model_files()
    assert int8["encoder"].name == "encoder-e.int8.onnx" and full["encoder"].name == "encoder-e.onnx"


def test_no_heavy_imports_without_the_real_engine_and_mic():
    assert "sherpa_onnx" not in sys.modules and "sounddevice" not in sys.modules


# --- download ---


def _tar(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:bz2") as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def test_download_extracts_the_model_without_the_network(monkeypatch, tmp_path):
    monkeypatch.setenv("VOICE_SERVICE_MODELS", str(tmp_path))
    config = ServiceConfig()
    model = config.engine.zipformer.model
    urls = []

    def fetch(url, dest):
        urls.append(url)
        dest.write_bytes(_tar({f"{model}/tokens.txt": b"a 0\n", f"{model}/test_wavs/0.wav": b"RIFF"}))

    target = download_model("zipformer", config, fetch=fetch)
    assert target == tmp_path / model and (target / "tokens.txt").read_bytes() == b"a 0\n"
    assert urls == [f"https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/{model}.tar.bz2"]
    assert download_model("zipformer", config, fetch=fetch) == target and len(urls) == 1  # already there
    assert sorted(p.name for p in tmp_path.iterdir()) == [model]  # the temporary archive is gone


def test_download_refuses_paths_outside_the_models_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("VOICE_SERVICE_MODELS", str(tmp_path / "models"))
    with pytest.raises(tarfile.FilterError):
        download_model("zipformer", ServiceConfig(), fetch=lambda url, dest: dest.write_bytes(_tar({"../evil.txt": b"x"})))
    assert not (tmp_path / "evil.txt").exists()
    with pytest.raises(ValueError):
        download_model("fake", ServiceConfig())


def test_whisper_download_goes_through_a_temp_folder(monkeypatch, tmp_path):
    monkeypatch.setenv("VOICE_SERVICE_MODELS", str(tmp_path))
    sizes = []

    def fetch(size, dest):
        sizes.append(size)
        dest.mkdir(parents=True)
        (dest / "model.bin").write_bytes(b"m")

    target = download_model("whisper", ServiceConfig(), fetch_whisper=fetch)
    assert target == tmp_path / "faster-whisper-small.en" and (target / "model.bin").is_file()
    assert download_model("whisper", ServiceConfig(), fetch_whisper=fetch) == target and sizes == ["small.en"]
    assert download_model("whisper", ServiceConfig(), model="base.en", fetch_whisper=fetch).name == "faster-whisper-base.en"
    with pytest.raises(RuntimeError, match="no model.bin"):
        download_model("whisper", ServiceConfig(), model="tiny.en", fetch_whisper=lambda size, dest: dest.mkdir())
    assert sorted(p.name for p in tmp_path.iterdir()) == ["faster-whisper-base.en", "faster-whisper-small.en"]


# --- whisper ---


def test_whisper_without_the_package_names_the_install(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    with pytest.raises(EngineError, match=r"voice_in's module\.toml"):
        WhisperEngine(tmp_path, ServiceConfig().engine.whisper).load()


def test_whisper_missing_model_names_the_download_command(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=object))
    with pytest.raises(EngineError, match="python -m voice_service download whisper"):
        WhisperEngine(tmp_path, ServiceConfig().engine.whisper).load()


def test_whisper_stream_buffers_and_decodes_at_the_finish():
    pytest.importorskip("numpy")
    calls = []

    class Model:
        def transcribe(self, samples, **options):
            calls.append((len(samples), options))
            return iter([types.SimpleNamespace(text=" Hello,"), types.SimpleNamespace(text=" world. ")]), None

    engine = WhisperEngine(".", ServiceConfig().engine.whisper)
    engine._model = Model()
    stream = engine.new_stream()
    assert stream.finish() == ""  # no audio: no decoding
    stream.accept(CHUNK)
    stream.accept(CHUNK)
    assert stream.partial() == "" and calls == []
    assert stream.finish() == "Hello, world."
    assert calls == [(1024, {"language": "en", "beam_size": 5, "vad_filter": True})]


# --- the file source and transcribe ---


def write_wav(path, frames: bytes, rate: int = 16000, channels: int = 1):
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(frames)
    return path


def test_file_source_chunks_and_length(tmp_path):
    source = FileSource(write_wav(tmp_path / "a.wav", CHUNK * 3 + bytes(100)))
    assert [len(c) for c in source.chunks] == [1024, 1024, 1024, 100]
    assert source.seconds == pytest.approx((3 * 1024 + 100) / 2 / 16000)


def test_file_source_refuses_other_formats(tmp_path):
    with pytest.raises(ValueError, match="16 kHz mono"):
        FileSource(write_wav(tmp_path / "cd.wav", bytes(4410), rate=44100))
    with pytest.raises(ValueError, match="16 kHz mono"):
        FileSource(write_wav(tmp_path / "stereo.wav", bytes(4000), channels=2))


def test_file_source_feeds_like_a_mic(tmp_path):
    path = write_wav(tmp_path / "a.wav", CHUNK * 10)
    for realtime, slowest, fastest in ((True, 0.25, 5.0), (False, 0.0, 0.25)):
        got, source = [], FileSource(path, realtime=realtime)
        began = time.monotonic()
        source.start(got.append, lambda reason: None)
        deadline = began + 5
        while len(got) < 10 and time.monotonic() < deadline:
            time.sleep(0.005)
        elapsed = time.monotonic() - began
        source.stop()
        assert len(got) == 10 and slowest <= elapsed < fastest


def test_transcribe_a_file_through_an_engine(tmp_path):
    source = FileSource(write_wav(tmp_path / "a.wav", CHUNK * 6))
    timings = {}
    assert transcribe(FakeEngine("hello big world"), source, timings=timings) == "hello big world"
    assert set(timings) == {"audio_seconds", "load_seconds", "accept_seconds", "finish_seconds"}
    assert timings["audio_seconds"] == pytest.approx(6 * 0.032)


def test_transcribe_imports_neither_the_server_nor_the_mic():
    code = (
        "import sys, voice_service.transcribe\n"
        "bad = [m for m in ('voice_service.server', 'fastapi', 'sounddevice', 'sherpa_onnx', 'faster_whisper')"
        " if m in sys.modules]\n"
        "print(bad)\nsys.exit(1 if bad else 0)\n"
    )
    env = launch_env("voice_service", {k: v for k, v in os.environ.items() if k != "PYTHONPATH"})  # its app/ folder
    done = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stdout + done.stderr


# --- text on send: the live-text flag ---

LOUD = array("h", [3000] * 512).tobytes()  # 32 ms of speech-loud audio


class OnSendEngine(FakeEngine):
    live_partials = False


def test_rms():
    assert (rms(CHUNK), rms(LOUD), rms(b"")) == (0.0, 3000.0, 0.0)


def test_an_engine_without_live_text_sends_only_the_final():
    with make_client(OnSendEngine("hello big world"), source=[LOUD] * 6) as client:
        with client.websocket_connect("/ws/listen") as ws:
            assert start(ws) == Started(partials=False)
            time.sleep(0.2)
            stop(ws)
            messages = until(ws, Final)
            assert len(messages) == 1 and messages[0].text == "hello big world"


def test_a_client_can_ask_a_live_engine_for_text_on_send():
    with make_client(source=[CHUNK] * 6) as client, client.websocket_connect("/ws/listen") as ws:
        ws.send_text('{"type": "start", "partials": false}')
        assert recv(ws) == Started(partials=False)
        time.sleep(0.2)
        stop(ws)
        messages = until(ws, Final)
        assert len(messages) == 1 and messages[0].text == "hello big world"


@pytest.mark.parametrize(("chunk", "at_least", "under"), [(LOUD, 0.6, 5.0), (CHUNK, 0.0, 0.6)])
def test_without_live_text_the_silence_stop_listens_to_the_level(chunk, at_least, under):
    config = make_config(silence_stop_seconds=0.3)
    source = lambda: FakeSource([chunk] * 20, interval=0.032)  # noqa: E731 - 0.64 s of audio
    with make_client(OnSendEngine(), source=source, config=config) as client:
        with client.websocket_connect("/ws/listen") as ws:
            began = time.monotonic()
            assert start(ws) == Started(partials=False)
            final = until(ws, Final)[-1]
            assert final.ended_by == "silence" and at_least <= time.monotonic() - began < under


# --- swapping the engine: a config change restarts the service ---


def _swap_client(path, quit_event):
    app = create_app(make_config(), FakeEngine("hello big world"), lambda: FakeSource([CHUNK] * 6),
                      config_path=path, watch_seconds=0.05)  # fmt: skip
    app.state.on_quit = quit_event.set
    return LocalClient(app)


def _write(path, text: str, bump: int) -> None:
    path.write_text(text, encoding="utf-8")
    stamp = time.time_ns() + bump * 10**9  # a clearly new modification time
    os.utime(path, ns=(stamp, stamp))


SAME_ENGINE = '[engine]\nname = "fake"\npartial_interval_ms = 0\n'


def test_an_engine_change_while_idle_quits_the_service(tmp_path):
    path, quit_event = tmp_path / "voice.toml", threading.Event()
    _write(path, SAME_ENGINE, 0)
    with _swap_client(path, quit_event):
        _write(path, SAME_ENGINE + "[audio]\nsilence_stop_seconds = 99\n", 1)  # not the engine: carries on
        assert not quit_event.wait(0.4)
        _write(tmp_path / "voice.local.toml", '[engine]\nname = "zipformer"\n', 2)  # the override counts too
        assert quit_event.wait(3)


def test_an_engine_change_mid_session_waits_for_the_final(tmp_path):
    path, quit_event = tmp_path / "voice.toml", threading.Event()
    _write(path, SAME_ENGINE, 0)
    with _swap_client(path, quit_event) as client, client.websocket_connect("/ws/listen") as ws:
        assert start(ws) == Started()
        _write(path, '[engine]\nname = "whisper"\n', 1)
        assert not quit_event.wait(0.4)  # you're talking: no restart yet
        stop(ws)
        assert until(ws, Final)[-1].text == "hello big world"
        assert quit_event.wait(3)
