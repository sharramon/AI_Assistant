"""The voice service app (src/voice_service) with the fake engine and fake sources: no mic, no model, no network."""

import io
import sys
import tarfile
import threading
import time
import tomllib

import pytest
from fastapi.testclient import TestClient

from voice_service.audio import FakeSource
from voice_service.config import DEFAULT_CONFIG, ServiceConfig, load_service_config, models_dir
from voice_service.download import download_model
from voice_service.engines import EngineError, load_engine
from voice_service.engines.fake import FakeEngine
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
from voice_service.session import ListenSession

CHUNK = bytes(1024)  # 32 ms of silence: 512 frames of PCM16


def make_config(**audio) -> ServiceConfig:
    return ServiceConfig.model_validate({"engine": {"name": "fake", "partial_interval_ms": 0}, "audio": audio})


def make_client(engine=None, source=None, config=None) -> TestClient:
    engine = engine or FakeEngine("hello big world")
    factory = source if callable(source) else (lambda: FakeSource(source or []))
    return TestClient(create_app(config or make_config(), engine, factory))


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
        assert client.get("/health").json() == {"app": "voice_service", "engine": "fake", "ready": False, "error": None}
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
    with pytest.raises(EngineError, match="unknown engine"):
        load_engine("whisper", ServiceConfig())


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
