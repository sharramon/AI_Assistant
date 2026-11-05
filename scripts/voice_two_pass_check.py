r"""Real check for the two-pass voice flow (docs/next-steps/voice-two-pass.md, step 3).

Runs the voice service app in this process with the real models, feeds the Zipformer's test
recordings at the speed of speech, and measures what the note's section 9 lists: CPU while
talking, each piece's whisper time, how many pieces wait, how late the live partials come
compared with the live engine alone, the wait after stop, and the joined text against whisper on
the whole recording. Config overrides stay in memory: no config file is read for them or changed.

    .venv\Scripts\python scripts\voice_two_pass_check.py
"""

from __future__ import annotations

import difflib
import logging
import re
import statistics
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from starlette.testclient import TestClient  # noqa: E402

from voice_service.audio import FakeSource, FileSource  # noqa: E402
from voice_service.config import ServiceConfig, load_service_config, models_dir  # noqa: E402
from voice_service.engines import load_engine  # noqa: E402
from voice_service.protocol import Cleaned, Final, Partial, Refining, parse_service_message  # noqa: E402
from voice_service.server import create_app  # noqa: E402

CHUNK_MS = 32
CHUNK_BYTES = 16000 * CHUNK_MS // 1000 * 2


class Catch(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


def recordings(config: ServiceConfig) -> dict[str, list[bytes]]:
    folder = models_dir(config) / config.engine.zipformer.model / "test_wavs"
    a, b = FileSource(folder / "0.wav").chunks, FileSource(folder / "1.wav").chunks
    gap = [bytes(CHUNK_BYTES)] * round(1000 / CHUNK_MS)  # 1 s of quiet between them
    return {"0.wav": a, "1.wav": b, "joined": a + gap + b + gap + a + gap + b}


def make_config(base: ServiceConfig, *, final: str, whisper: str = "", prompt: bool = True) -> ServiceConfig:
    data = base.model_dump()
    data["audio"].update(stall_seconds=0, silence_stop_seconds=0, mic_recovery_seconds=0)
    data["engine"]["final"] = final
    if whisper:
        data["engine"]["whisper"]["model"] = whisper
    data["pieces"]["prompt_previous"] = prompt
    return ServiceConfig.model_validate(data)


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def run(config: ServiceConfig, chunks: list[bytes]) -> dict:
    catch = Catch()
    root = logging.getLogger("voice_service")
    root.addHandler(catch)
    root.setLevel(logging.INFO)
    live = load_engine(config.engine.name, config)
    final = load_engine(config.engine.final, config) if config.engine.final else None
    app = create_app(config, live, lambda: FakeSource(chunks, interval=CHUNK_MS / 1000), final_engine=final)
    out: dict = {"partials": {}, "cleaned": [], "cpu": []}
    try:
        with TestClient(app) as client:
            deadline = time.monotonic() + 60
            while True:
                health = client.get("/health").json()
                if health["ready"] and (final is None or health["final_ready"]):
                    break
                assert time.monotonic() < deadline and not health.get("error") and not health.get("final_error"), health
                time.sleep(0.1)
            with client.websocket_connect("/ws/listen") as ws:
                messages: list[tuple[float, object]] = []
                done = threading.Event()

                def read() -> None:
                    while True:
                        message = parse_service_message(ws.receive_text())
                        messages.append((time.monotonic(), message))
                        if isinstance(message, Final):
                            done.set()
                            return

                talking = threading.Event()

                def sample() -> None:  # the whole process's CPU, in cores, every 0.25 s while talking
                    last_cpu, last_wall = time.process_time(), time.monotonic()
                    while talking.wait(0.25) is False:
                        cpu, wall = time.process_time(), time.monotonic()
                        out["cpu"].append((cpu - last_cpu) / (wall - last_wall))
                        last_cpu, last_wall = cpu, wall

                reader = threading.Thread(target=read, daemon=True)
                sampler = threading.Thread(target=sample, daemon=True)
                t0 = time.monotonic()
                cpu0 = time.process_time()
                ws.send_text('{"type": "start", "partials": true}')
                reader.start()
                sampler.start()
                time.sleep(len(chunks) * CHUNK_MS / 1000 + 0.2)  # talk, then press stop
                talking.set()
                out["cpu_avg"] = (time.process_time() - cpu0) / (time.monotonic() - t0)
                t_stop = time.monotonic()
                ws.send_text('{"type": "stop"}')
                done.wait(40)
        for t, m in messages:
            if isinstance(m, Partial):
                out["partials"].setdefault(m.text, t - t0)
            elif isinstance(m, Cleaned):
                out["cleaned"].append(m)
            elif isinstance(m, Refining):
                out["refining"] = m
            elif isinstance(m, Final):
                out["final"], out["wait"] = m, t - t_stop
    finally:
        root.removeHandler(catch)
    out["piece_times"] = [(float(a), float(b)) for a, b in re.findall(r"cleaned in ([\d.]+) s \(([\d.]+) s of audio", "\n".join(catch.lines))]
    out["waiting"] = [int(n) for n in re.findall(r"live words \d+ to \d+, (\d+) waiting", "\n".join(catch.lines))]
    out["fallbacks"] = [c.fallback for c in out["cleaned"] if c.fallback]
    out["final_engine"] = final
    return out


def doubled(result: dict) -> int:
    """Cuts where the live word after a span is the cleaned piece's last word: shown twice on the line."""
    live = words(result["refining"].text) if "refining" in result else []
    count = 0
    for c in result["cleaned"]:
        cleaned = words(c.text)
        if cleaned and c.end < len(live) and live[c.end] == cleaned[-1]:
            count += 1
    return count


def whole(engine, chunks: list[bytes]) -> tuple[str, float]:
    stream = engine.new_stream()
    stream.accept(b"".join(chunks))
    began = time.monotonic()
    return stream.finish(), time.monotonic() - began


def report(name: str, result: dict, base: dict | None, reference: str | None) -> None:
    final: Final = result["final"]
    print(f"\n### {name}")
    print(f"  CPU while talking: average {result['cpu_avg']:.2f} cores, peak {max(result['cpu'] or [0]):.2f} cores (0.25 s windows)")
    if base is not None:
        lags = [result["partials"][t] - base["partials"][t] for t in result["partials"] if t in base["partials"]]
        if lags:
            lags.sort()
            p95 = lags[min(len(lags) - 1, int(len(lags) * 0.95))]
            print(f"  partial lag vs the live engine alone: median {1000 * statistics.median(lags):.0f} ms, "
                  f"p95 {1000 * p95:.0f} ms, max {1000 * lags[-1]:.0f} ms over {len(lags)} partials")  # fmt: skip
    if result["piece_times"]:
        times = ", ".join(f"{t:.2f} s for {a:.1f} s" for t, a in result["piece_times"])
        print(f"  pieces: {len(result['piece_times'])} ({times})")
        print(f"  most waiting at a cut (incl. the new piece): {max(result['waiting'] or [0])}; fallbacks: {result['fallbacks'] or 'none'}")
        print(f"  possible doubled words at cuts: {doubled(result)}")
    print(f"  wait after stop: {result['wait']:.2f} s (service latency_ms {final.latency_ms})")
    print(f"  sent text: {final.text!r}")
    if reference is not None:
        ratio = difflib.SequenceMatcher(None, words(final.text), words(reference)).ratio()
        print(f"  whisper on the whole recording: {reference!r}")
        print(f"  word match with it: {ratio:.3f}")


def main() -> None:
    base_config = load_service_config()
    recs = recordings(base_config)
    print("recordings:", {k: f"{len(v) * CHUNK_MS / 1000:.1f} s" for k, v in recs.items()})
    baseline = {}
    for name, chunks in recs.items():
        baseline[name] = run(make_config(base_config, final=""), chunks)
        report(f"live engine alone, {name}", baseline[name], None, None)
    for model, prompt in (("faster-whisper-small.en", True), ("faster-whisper-small.en", False), ("faster-whisper-base.en", True)):
        config = make_config(base_config, final="whisper", whisper=model, prompt=prompt)
        reference_engine = load_engine("whisper", config)
        reference_engine.load()
        for name, chunks in recs.items():
            reference, took = whole(reference_engine, chunks)
            print(f"\n(whole-recording {model} on {name}: {took:.2f} s)")
            result = run(config, chunks)
            report(f"two passes, {model}, prompt {'on' if prompt else 'off'}, {name}", result, baseline[name], reference)


if __name__ == "__main__":
    main()
