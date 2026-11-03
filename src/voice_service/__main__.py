"""Run the voice service, or download a model.

    python -m voice_service [--config F] [--host H] [--port P]
    python -m voice_service download zipformer [--config F]
"""

from __future__ import annotations

import argparse
import logging
import sys

from .config import LoggingConfig, load_service_config


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="voice_service", description="Local speech to text over a WebSocket.")
    parser.add_argument("--config", help="config file (default: config/voice_service.toml)")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    if argv[:1] == ["download"]:
        parser.add_argument("command", choices=["download"])
        parser.add_argument("engine", help="the engine whose model to fetch: zipformer")
    return parser.parse_args(argv)


def _setup_logging(config: LoggingConfig) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if config.file:
        handlers.append(logging.FileHandler(config.file, encoding="utf-8"))
    logging.basicConfig(
        level=config.level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s", handlers=handlers
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse(sys.argv[1:] if argv is None else argv)
    try:
        config = load_service_config(args.config, host=args.host, port=args.port)
    except (OSError, ValueError) as exc:
        print(f"voice_service: bad config: {exc}", file=sys.stderr)
        return 2
    _setup_logging(config.logging)

    if getattr(args, "command", None) == "download":
        from .download import download_model

        try:
            print(download_model(args.engine, config))
        except (OSError, ValueError, RuntimeError) as exc:
            print(f"voice_service: download failed: {exc}", file=sys.stderr)
            return 1
        return 0

    import uvicorn

    from .audio import MicSource
    from .engines import EngineError, load_engine
    from .server import create_app

    try:
        engine = load_engine(config.engine.name, config)
    except EngineError as exc:
        print(f"voice_service: {exc}", file=sys.stderr)
        return 2
    app = create_app(config, engine, lambda: MicSource(config.audio.device, config.audio.chunk_ms))
    server = uvicorn.Server(
        uvicorn.Config(app, host=config.server.host, port=config.server.port, log_level="warning", lifespan="on")
    )
    app.state.on_quit = lambda: setattr(server, "should_exit", True)
    logging.getLogger("voice_service").info(
        "voice service on http://%s:%d (engine %s)", config.server.host, config.server.port, engine.name
    )
    server.run()  # Ctrl+C ends it too; the lifespan aborts any session
    return 0


if __name__ == "__main__":
    sys.exit(main())
