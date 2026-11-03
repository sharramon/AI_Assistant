"""`python -m voice_service check`: is this machine ready to listen?

Checks, in order, and prints one line each: the voice extra, Windows' mic privacy switches,
the input devices, the model (loaded, timed), and a few seconds of the real mic through
`MicSource` (open time, first audio, level). With the model loaded, it also transcribes what
it heard, so speaking during the check shows the whole path. Reads only; changes nothing.
"""

from __future__ import annotations

import math
import sys
import time
from array import array

from .audio import SAMPLE_RATE, MicSource, MicUnavailable
from .config import ServiceConfig, models_dir

PRIVACY_KEY = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"
PRIVACY_FIX = (
    "Windows is blocking the mic. Open Settings > Privacy & security > Microphone and turn on "
    "'Microphone access' and 'Let desktop apps access your microphone'."
)


def mic_privacy() -> dict[str, str]:
    """Windows' mic consent values ("Allow" / "Deny") for all apps and for desktop apps; empty elsewhere."""
    if sys.platform != "win32":
        return {}
    import winreg

    found = {}
    for label, hive, sub in (
        ("machine", winreg.HKEY_LOCAL_MACHINE, PRIVACY_KEY),
        ("you", winreg.HKEY_CURRENT_USER, PRIVACY_KEY),
        ("desktop apps", winreg.HKEY_CURRENT_USER, PRIVACY_KEY + r"\NonPackaged"),
    ):
        try:
            with winreg.OpenKey(hive, sub) as key:
                found[label] = str(winreg.QueryValueEx(key, "Value")[0])
        except OSError:
            pass
    return found


def record(source: MicSource, seconds: float) -> dict:
    """Run `source` for `seconds`: open time, time to the first chunk, chunks, the samples, and a lost reason."""
    chunks: list[bytes] = []
    first: list[float] = []
    lost: list[str] = []

    def on_chunk(pcm: bytes) -> None:
        if not first:
            first.append(time.perf_counter())
        chunks.append(pcm)

    started = time.perf_counter()
    source.start(on_chunk, lost.append)
    opened = time.perf_counter()
    time.sleep(seconds)
    source.stop()
    samples = array("h", b"".join(chunks))
    return {
        "open_ms": (opened - started) * 1000,
        "first_ms": (first[0] - started) * 1000 if first else None,
        "chunks": len(chunks),
        "samples": samples,
        "lost": lost[0] if lost else None,
    }


def level(samples: array) -> tuple[float, int, float]:
    """RMS, peak, and the share of exact zeros (a blocked mic on Windows sends pure zeros)."""
    if not samples:
        return 0.0, 0, 1.0
    rms = math.sqrt(sum(s * s for s in samples) / len(samples))
    return rms, max(abs(s) for s in samples), samples.count(0) / len(samples)


def run_check(config: ServiceConfig, seconds: float = 3.0, model: bool = True, out=print) -> bool:
    """Print the checks; True if the mic delivered sound (and, with `model`, the model loaded)."""
    ok = True
    try:
        import sherpa_onnx  # noqa: F401
        import sounddevice as sd
    except (ImportError, OSError) as exc:
        out(f"[fail] voice extra: {exc}. Install it: pip install -e .[voice]")
        return False
    out(f"[ok]   voice extra: sounddevice {sd.__version__}, PortAudio {sd.get_portaudio_version()[1]}")

    privacy = mic_privacy()
    if privacy:
        blocked = [k for k, v in privacy.items() if v.lower() == "deny"]
        line = ", ".join(f"{k}: {v}" for k, v in privacy.items())
        out(f"[fail] mic privacy ({line}). {PRIVACY_FIX}" if blocked else f"[ok]   mic privacy: {line}")
        ok = ok and not blocked

    try:
        default = sd.query_devices(kind="input")
        hostapi = sd.query_hostapis(default["hostapi"])["name"]
        inputs = [d for d in sd.query_devices() if d["max_input_channels"] > 0 and d["hostapi"] == default["hostapi"]]
        out(f"[ok]   default mic: {default['name']} ({hostapi}); config device: {config.audio.device or 'the default'}")
        for d in inputs:
            out(f"         {d['index']:>3}  {d['name']}")
    except Exception as exc:
        out(f"[fail] no input device: {exc}")
        return False

    engine = None
    if model:
        from .engines import load_engine

        try:
            engine = load_engine(config.engine.name, config)
            started = time.perf_counter()
            engine.load()
            out(f"[ok]   model: {config.engine.name} from {models_dir(config)}, loaded in {time.perf_counter() - started:.1f} s")
        except Exception as exc:
            out(f"[fail] model: {exc}")
            engine, ok = None, False

    out(f"       listening for {seconds:g} s through MicSource{' (say something)' if engine else ''}…")
    try:
        got = record(MicSource(config.audio.device, config.audio.chunk_ms), seconds)
    except MicUnavailable as exc:
        out(f"[fail] mic: couldn't open it: {exc}")
        return False
    expected = int(seconds * 1000 / config.audio.chunk_ms)
    first = f"{got['first_ms']:.0f} ms" if got["first_ms"] is not None else "never"
    out(f"       opened in {got['open_ms']:.0f} ms, first audio after {first}, {got['chunks']} chunks (expected ~{expected})")
    rms, peak, zeros = level(got["samples"])
    if got["lost"]:
        out(f"[fail] mic: lost during the check: {got['lost']}")
        ok = False
    if got["chunks"] == 0:
        out("[fail] mic: opened, but no audio arrived")
        ok = False
    elif zeros > 0.99:
        out(f"[fail] mic: only silence (all zeros). {PRIVACY_FIX} Also check the laptop's mic mute key.")
        ok = False
    elif rms < 20:
        out(f"[warn] mic: audio arrives but is nearly silent (rms {rms:.0f}, peak {peak}). Run the check again while "
            "speaking. If it stays this low, check the laptop's mic mute key, and the input volume in Settings > "
            "System > Sound > Input")  # fmt: skip
    else:
        out(f"[ok]   mic: sound arrives (rms {rms:.0f}, peak {peak}, {zeros:.0%} exact zeros)")

    if engine is not None and got["samples"]:
        stream, pcm = engine.new_stream(), got["samples"].tobytes()
        size = SAMPLE_RATE * config.audio.chunk_ms // 1000 * 2
        started = time.perf_counter()
        for i in range(0, len(pcm), size):
            stream.accept(pcm[i : i + size])
        stream.partial()
        mid = time.perf_counter()
        text = stream.finish()
        audio_s = len(got["samples"]) / SAMPLE_RATE
        out(f"       heard: {text!r}")
        out(f"       decoding {audio_s:.1f} s of audio took {(mid - started) * 1000:.0f} ms "
            f"({(mid - started) / audio_s:.2f}x real time), finish {(time.perf_counter() - mid) * 1000:.0f} ms")  # fmt: skip
    return ok
