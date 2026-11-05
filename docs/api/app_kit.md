# App kit

Helpers shared by the main app **and** the independent apps (the HTML viewer, the voice service). All items: `from app_kit import ...`. Standard library only; never imports `assistant`. Every item is reusable and listed in the [reusable parts index](reusable.md). Back to the [API index](README.md). Why it exists: [Reusable parts](../architecture/reusable-parts.md).

> **Status: built (2026-11-02).** Tested in `tests/test_app_kit.py`, which also checks that `app_kit` never imports `assistant`.

## `window`

**Reusable** · Used by: `temp_ui`, the HTML viewer app (`viewer.py`: open, close, raise; `snip.py`: `devtools_port`)

`from app_kit.window import open_app_window, close_app_windows, raise_window, devtools_port`

One copy of the Edge app-window code, merged from `assistant/infra/app_window.py` and `html_viewer/window.py` (both removed). Not re-exported from `assistant.infra`.

| Function | Does |
|----------|------|
| `open_app_window(url, profile, *, size="1400,850", devtools=False, log=...) -> subprocess.Popen \| None` | Open `url` in its own window: Edge app mode (`msedge --app=URL`, no tabs or address bar) on its own profile folder, so it's its own Edge process. With `devtools`, Edge also listens for DevTools on `127.0.0.1` (the viewer's snip). Without Edge it opens a browser tab and returns `None` |
| `close_app_windows(profile, log=...)` | Stop every Edge process running on `profile`: that app's window and nothing else. Windows only (no-op elsewhere). Blocking, up to 15 s; call with `asyncio.to_thread` from async code |
| `raise_window(pid, title) -> bool` | Bring the window to the front, restoring it if minimized: the Edge window owned by `pid`, else one whose title ends with `title`. Windows only; elsewhere it returns `True` (it can't tell) |
| `devtools_port(profile) -> int \| None` | The DevTools port Edge picked for that profile |

**Example**

    edge = open_app_window("http://127.0.0.1:8765/", Path(r"C:\Users\me\AppData\Local\AI_Assistant\temp_ui_window"))

**Defined in:** `src/app_kit/window.py`

## `load_layered`

**Reusable** · Used by: [`assistant.infra.load_config`](infra.md#load_config) (as a thin wrapper), `voice_service` (`config.py`: `config/voice_service.toml` and its `.local.toml`)

`load_layered(base: str | Path, local: str | Path | None = None) -> dict[str, Any]`

Load the TOML file `base`, then deep-merge `local` over it if it exists (default: `base` with `.local` before the suffix, e.g. `voice_service.local.toml`). Tables merge key by key; other values, lists included, are replaced.

**Raises:** `FileNotFoundError` if `base` is missing; `tomllib.TOMLDecodeError` for invalid TOML.

**Defined in:** `src/app_kit/config.py`

## `local_path`

**Reusable** · Used by: `load_layered` (its default `local`), `voice_service` (`server.py`: the engine watch reads both files)

`local_path(base: str | Path) -> Path`

The local override's path for `base`: `.local` before the suffix (`voice_service.toml` → `voice_service.local.toml`). Added 2026-11-03.

**Defined in:** `src/app_kit/config.py`

## `CompanionApp`

**Reusable** · Used by: `html_viewer` module (launch, calls, the relay of the viewer's event stream, handover or restart on reload); `voice_in` (launch on the first mic click, `/health` calls, quit at stop if it launched it, handover or restart on reload); any app that launches `voice_service`

`CompanionApp(module: str, host: str, port: int, *, ping: str, args: Sequence[str] = (), start_timeout: float = 20.0, quit: str = "/api/quit", name: str | None = None, log: Logger | None = None)`

Launches and talks to a local [companion app](../architecture/reusable-parts.md#companion-app-checklist). Relies on its convention: the ping answers `{"app": "<name>", ...}` (`name` defaults to `module`), and a JSON `POST` to `quit` quits it.

| Member | Does |
|--------|------|
| `async ping() -> bool` | Whether the app answers its ping with its own name (1 s timeout) |
| `async ensure_running() -> bool` | Ping; if nothing answers, launch `python -m <module> <args>` with no console and poll every 100 ms until `start_timeout`. Returns whether it launched it now. Raises `OSError` if the process exits early, `TimeoutError` if it never answers |
| `async call(method, path, body=None, *, timeout=10) -> dict` | A JSON request to its HTTP API; error responses are read as JSON too |
| `async events(path) -> AsyncIterator[dict]` | Read its event stream (server-sent events), one JSON event at a time, until it ends. Raises `OSError` if it can't connect |
| `async stop(adopted=False)` | If this object launched it: `POST` quit, wait 5 s, then kill. With `adopted=True`, also an app it found already running: `POST` quit, then wait up to 5 s for the ping to stop answering (a reload with new code) |
| `code_changed() -> bool` | Whether the app's own source (its package's `.py` files) changed since this object launched it or first found it running. A reloading module uses it to decide between handing the app over and quitting it (built 2026-11-05) |
| `launched: bool` | Whether this object started the process (and hasn't stopped it) |
| `process` | The process it launched, or `None` |

`source_stamp(module) -> (int, int) | None` (in `app_kit.companion`): the fingerprint `code_changed` compares, the newest `.py` mtime and the file count, found without importing the package.

**Reload with new code** (`voice_in`, `html_viewer`): in `export_state`, hand the `CompanionApp` over unless `code_changed()`; if it changed, return nothing and `stop(adopted=True)`, so the new copy launches the new code.

**Example**

    app = CompanionApp("voice_service", "127.0.0.1", 8767, ping="/health", log=ctx.log)
    await app.ensure_running()
    info = await app.call("GET", "/health")
    await app.stop()

**Defined in:** `src/app_kit/companion.py`
