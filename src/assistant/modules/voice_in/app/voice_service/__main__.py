"""Run the voice service, download a model, transcribe a file, or check this machine's mic.

    python -m voice_service [--config F] [--host H] [--port P]
    python -m voice_service download zipformer|whisper [--model M] [--config F]
    python -m voice_service transcribe FILE.wav [--engine E] [--model M] [--config F]
    python -m voice_service check [--seconds S] [--no-model] [--config F]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from app_kit import require_loopback

from .config import DEFAULT_CONFIG, LoggingConfig, final_engine_name, load_service_config, whisper_folder


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="voice_service", description="Local speech to text over a WebSocket.")
    parser.add_argument("--config", help="config file (default: voice_service.toml beside the code)")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    if argv[:1] == ["download"]:
        parser.add_argument("command", choices=["download"])
        parser.add_argument("engine", help="the engine whose model to fetch: zipformer or whisper")
        parser.add_argument("--model", help="whisper only: the size, e.g. small.en (default: the config's)")
    elif argv[:1] == ["transcribe"]:
        parser.add_argument("command", choices=["transcribe"])
        parser.add_argument("file", help="a 16 kHz mono 16-bit WAV")
        parser.add_argument("--engine", help="zipformer, whisper or fake (default: the config's)")
        parser.add_argument("--model", help="whisper only: the size or folder, e.g. small.en (default: the config's)")
    elif argv[:1] == ["check"]:
        parser.add_argument("command", choices=["check"])
        parser.add_argument("--seconds", type=float, default=3.0, help="how long to listen (default 3)")
        parser.add_argument("--no-model", action="store_true", help="skip loading the model")
    return parser.parse_args(argv)


def _setup_logging(config: LoggingConfig) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if config.file:
        handlers.append(logging.FileHandler(config.file, encoding="utf-8"))
    logging.basicConfig(
        level=config.level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s", handlers=handlers
    )


def _transcribe(args: argparse.Namespace, config) -> int:
    from .engines import EngineError
    from .transcribe import transcribe_file

    if args.model:
        config.engine.whisper.model = whisper_folder(args.model)
    timings: dict = {}
    try:
        text = transcribe_file(args.file, args.engine, config, timings=timings)
    except (OSError, ValueError, EngineError) as exc:
        print(f"voice_service: transcribe failed: {exc}", file=sys.stderr)
        return 1
    print(text)
    print(
        f"audio {timings['audio_seconds']:.1f} s · load {timings['load_seconds']:.1f} s · "
        f"feed {timings['accept_seconds']:.2f} s · wait after the end {timings['finish_seconds']:.2f} s",
        file=sys.stderr,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse(sys.argv[1:] if argv is None else argv)
    try:
        config = load_service_config(args.config, host=args.host, port=args.port)
        require_loopback(config.server.host)
    except (OSError, ValueError) as exc:
        print(f"voice_service: bad config: {exc}", file=sys.stderr)
        return 2
    _setup_logging(config.logging)

    if getattr(args, "command", None) == "download":
        from .download import download_model

        try:
            print(download_model(args.engine, config, model=args.model))
        except (OSError, ValueError, RuntimeError) as exc:
            print(f"voice_service: download failed: {exc}", file=sys.stderr)
            return 1
        return 0

    if getattr(args, "command", None) == "transcribe":
        return _transcribe(args, config)

    if getattr(args, "command", None) == "check":
        from .check import run_check

        return 0 if run_check(config, args.seconds, model=not args.no_model) else 1

    import uvicorn

    from .audio import MicSource
    from .engines import EngineError, load_engine
    from .server import create_app

    try:
        engine = load_engine(config.engine.name, config)
        final_name = final_engine_name(config)
        final_engine = load_engine(final_name, config) if final_name else None
    except EngineError as exc:
        print(f"voice_service: {exc}", file=sys.stderr)
        return 2
    watched = Path(args.config) if args.config else (DEFAULT_CONFIG if DEFAULT_CONFIG.exists() else None)
    app = create_app(
        config, engine, lambda: MicSource(config.audio.device, config.audio.chunk_ms),
        final_engine=final_engine, config_path=watched,
    )  # fmt: skip
    server = uvicorn.Server(
        uvicorn.Config(app, host=config.server.host, port=config.server.port, log_level="warning", lifespan="on")
    )
    app.state.on_quit = lambda: setattr(server, "should_exit", True)
    logging.getLogger("voice_service").info(
        "voice service on http://%s:%d (engine %s%s)", config.server.host, config.server.port, engine.name,
        f", final {final_engine.name}" if final_engine is not None else "",
    )  # fmt: skip
    server.run()  # Ctrl+C ends it too; the lifespan aborts any session
    return 0


if __name__ == "__main__":
    sys.exit(main())
