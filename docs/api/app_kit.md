# App kit

Helpers shared by the main app **and** the independent apps (the HTML viewer, the voice service). All items: `from app_kit import ...`. Standard library only; never imports `assistant`. Every item is reusable and listed in the [reusable parts index](reusable.md). Back to the [API index](README.md). Why it exists: [Reusable parts](../architecture/reusable-parts.md).

> **Status: built (2026-11-02).** Tested in `tests/test_app_kit.py`, which also checks that `app_kit` never imports `assistant`.

## `window`

**Reusable** · Used by: `temp_ui` (open, close, `flash_window`), the HTML viewer app (`viewer.py`: open, close, raise; `snip.py`: `devtools_port`), the CV Tool app (`cv_tool/server.py`: open, raise, close; `window_profile("cv_tool")`)

`from app_kit.window import open_app_window, close_app_windows, raise_window, flash_window, devtools_port`

One copy of the Edge app-window code, merged from `assistant/infra/app_window.py` and `html_viewer/window.py` (both removed). Not re-exported from `assistant.infra`.

| Function | Does |
|----------|------|
| `open_app_window(url, profile, *, size="1400,850", devtools=False, log=...) -> subprocess.Popen \| None` | Open `url` in its own window: Edge app mode (`msedge --app=URL`, no tabs or address bar) on its own profile folder, so it's its own Edge process. With `devtools`, Edge also listens for DevTools on `127.0.0.1` (the viewer's snip). Without Edge it opens a browser tab and returns `None` |
| `close_app_windows(profile, log=...)` | Stop every Edge process running on `profile`: that app's window and nothing else. Windows only (no-op elsewhere). Blocking, up to 15 s; call with `asyncio.to_thread` from async code |
| `raise_window(pid, title) -> bool` | Bring the window to the front, restoring it if minimized: the Edge window owned by `pid`, else one whose title ends with `title`. Windows only; elsewhere it returns `True` (it can't tell) |
| `flash_window(pid, title) -> bool` | Flash the window's taskbar button (and caption) until you bring it to the front (`FlashWindowEx`, `FLASHW_ALL \| FLASHW_TIMERNOFG`), finding it as `raise_window` does. Does nothing while it's already in front. Returns whether it flashed; `False` elsewhere than Windows or with no window. Blocking but short; `temp_ui` calls it with `asyncio.to_thread` (built 2026-11-10) |
| `devtools_port(profile) -> int \| None` | The DevTools port Edge picked for that profile |
| `window_profile(name) -> Path` | **♻** The window's own profile folder, `%LOCALAPPDATA%\AI_Assistant\<name>_window`, built once (it was built four times). Used by: `temp_ui`, `voice_notes`, the `html_viewer` module and app (built 2026-11-08) |

**Example**

    edge = open_app_window("http://127.0.0.1:8765/", Path(r"C:\Users\me\AppData\Local\AI_Assistant\temp_ui_window"))

**Defined in:** `src/app_kit/window.py`

## `load_layered`

**Reusable** · Used by: [`assistant.infra.load_config`](infra.md#load_config) (as a thin wrapper), `voice_service` (`config.py`: `voice_service.toml` beside its code and its `.local.toml`)

`load_layered(base: str | Path, local: str | Path | None = None) -> dict[str, Any]`

Load the TOML file `base`, then deep-merge `local` over it if it exists (default: `base` with `.local` before the suffix, e.g. `voice_service.local.toml`). Tables merge key by key; other values, lists included, are replaced.

**Raises:** `FileNotFoundError` if `base` is missing; `tomllib.TOMLDecodeError` for invalid TOML.

**Defined in:** `src/app_kit/config.py`

## `local_path`

**Reusable** · Used by: `load_layered` (its default `local`), `voice_service` (`server.py`: the engine watch reads both files)

`local_path(base: str | Path) -> Path`

The local override's path for `base`: `.local` before the suffix (`voice_service.toml` → `voice_service.local.toml`). Added 2026-11-03.

**Defined in:** `src/app_kit/config.py`

## `merge`

**Reusable** · Used by: `load_layered` (the `.local` override), the core's `App` (a module's `module.toml` defaults under its `[modules.<id>]` section)

`merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]`

`override` deep-merged over `base`, as a new dict: tables merge key by key; other values, lists included, are replaced. Neither input is changed. Added 2026-11-06.

**Defined in:** `src/app_kit/config.py`

## `module_docs`

**Reusable** · Used by: the core's `App` (`modules.docs`), `scripts/build_docs.py` (publishes each module's own docs)

A module's (or an app's) own docs folder, `<its folder>/docs/`: the three standard pages (`README.md` overview, `architecture.md`, `tools.md` generated from its menu), optional Markdown and HTML pages, images, and an optional `docs.toml`. Every page shows in the docs' standard layout; an HTML page opens inside `frame.html`. Standard library only. Added 2026-11-06. `from app_kit.module_docs import ...`

| Name | Description |
|------|-------------|
| `docs_settings(docs) -> dict` | The folder's `docs.toml`, `{}` if it has none. Raises `tomllib.TOMLDecodeError` for invalid TOML |
| `doc_pages(docs) -> list[Path]` | Its pages (`.md`, `.html`, top level): the standard pages first in their order, then those `docs.toml` lists under `pages`, then the rest by name. `[]` if there's no folder |
| `page_title(page) -> str` | A Markdown page's first `# ` heading, an HTML page's `<title>`, else the file name |
| `tools_page(title, specs, notes="", intro="") -> str` | The tools page's text from the menu's specs (`ToolSpec.model_dump()` dicts): one section per item with its arguments table; `specs=None` for a module with no code. `intro` and `notes` are kept before and after the generated part |
| `tools_intro(text)`, `tools_notes(text) -> str` | The hand-written text before the `tools:start` marker and after `tools:end` |
| `STANDARD_PAGES` | `{"README.md": "Overview", "architecture.md": "Architecture", "tools.md": "Tools"}`: the required pages and their sidebar names |
| `DOCS_DIR`, `SETTINGS_FILE`, `SETTINGS_KEYS`, `TOOLS_FILE`, `TOOLS_START`, `TOOLS_END` | `"docs"`, `"docs.toml"`, its keys, `"tools.md"`, and the tools page's markers |

`docs.toml` keys (the docs build requires `group` for a module; the rest are optional):

| Key | Meaning |
|-----|---------|
| `group` | `"core"` or `"add-on"`: where the module sits in the docs (its tab among the core modules' or the add-ons', its table in the module library), never where its files live |
| `tab` | The docs tab it goes in (default: the module's id); one tab's modules share a group |
| `pages` | The order of its optional pages, after the standard three |
| `[related]` | Name = a page of the app's docs (`api/tools.md#anchor`), shown as links in its tab |

**Defined in:** `src/app_kit/module_docs.py`

## `CompanionApp`

**Reusable** · Used by: `html_viewer` module (launch, calls, the relay of the viewer's event stream, handover or restart on reload); `voice_in` (launch on the first mic click, `/health` calls, quit at stop if it launched it, handover or restart on reload); any app that launches `voice_service`; the `cv` module (`tool.py`, through `CompanionHandover`: the CV Tool on port 8771, ping `/api/ping`, quit `/api/quit`, handover or restart on reload); `job_search` (`ui.py`, through `CompanionHandover`: the job project's job UI on port 8781 by its command line, `plain_ping` on `/tracker`, `quit=None`; built 2026-11-10)

`CompanionApp(module: str, host: str, port: int, *, ping: str, args: Sequence[str] = (), start_timeout: float = 20.0, quit: str | None = "/api/quit", name: str | None = None, log: Logger | None = None, command: Sequence[str] | None = None, plain_ping: bool = False)`

Launches and talks to a local [companion app](../architecture/reusable-parts.md#companion-app-checklist). Relies on its convention: the ping answers `{"app": "<name>", ...}` (`name` defaults to `module`), and a JSON `POST` to `quit` quits it.

**An app outside the convention** (built 2026-11-10 for the job UI, a script of another project): `command` is its whole command line in place of `python -m <module>` (`args` follow it; `code_changed()` is then always False, so a reload hands it over); `plain_ping=True` takes any 200 answer from the ping path as alive, with no name check (`last_answer` is `{"status": 200}`); `quit=None` means it has no quit call: `stop` ends the process it launched at once and leaves one it found running. `CompanionHandover` passes these on, and its handover key includes `command`.

| Member | Does |
|--------|------|
| `async ping() -> bool` | Whether the app answers its ping with its own name (1 s timeout); with `plain_ping`, any 200 |
| `async ensure_running() -> bool` | Ping; if nothing answers, launch `python -m <module> <args>` (with `launch_env`: its package's folder first on `PYTHONPATH`) (or `<command> <args>`) with no console and poll every 100 ms until `start_timeout`. Returns whether it launched it now. Raises `OSError` if the process exits early, `TimeoutError` if it never answers |
| `async call(method, path, body=None, *, timeout=10) -> dict` | A JSON request to its HTTP API; error responses are read as JSON too |
| `async events(path) -> AsyncIterator[dict]` | Read its event stream (server-sent events), one JSON event at a time, until it ends. Raises `OSError` if it can't connect |
| `async stop(adopted=False)` | If this object launched it: `POST` quit, wait 5 s, then kill. With `adopted=True`, also an app it found already running: `POST` quit, then wait up to 5 s for the ping to stop answering (a reload with new code) |
| `code_changed() -> bool` | Whether the app's own source (its package's `.py` files) changed since this object launched it or first found it running. A reloading module uses it to decide between handing the app over and quitting it (built 2026-11-05) |
| `launched: bool` | Whether this object started the process (and hasn't stopped it) |
| `last_answer: dict` | The last ping's answer (`{}` if none), so a caller needn't ping again (`voice_in` reads the service's state from it; built 2026-11-08) |
| `process` | The process it launched, or `None` |

`source_stamp(module) -> (int, int) | None` (in `app_kit.companion`): the fingerprint `code_changed` compares, the newest `.py` mtime and the file count, found without importing the package.

**The app's folder on the child's path** (♻ Used by: `ensure_running` for every `python -m <module>` launch, so the CV Tool from `cv/app/` and the HTML viewer from `html_viewer/app/`; `tests/test_module_folders.py`; built 2026-11-13). `package_root(module) -> Path | None`: the folder the package is found in on this process's import path (`src/`, or a module's `app/` folder that the core put there with [`add_app_folders`](core.md#loader)), without importing it. `launch_env(module, base=None) -> dict`: `base` (default `os.environ`) with that folder first on `PYTHONPATH`, the rest kept. Both in `app_kit.companion`. A `command` launch gets no change.

**Reload with new code: `CompanionHandover`** (♻ Used by: `voice_in`, `html_viewer`; built 2026-11-08). `CompanionHandover(handover, module, host, port, *, args=(), label="", log=..., **app_kwargs)` takes the `CompanionApp` the module's last copy handed over (`ctx.handover`), or makes a new one. `app` is that `CompanionApp`; `export()` (the module's `export_state`) hands it over unless `code_changed()`, and if it changed returns nothing and marks it to quit; `stop()` (the module's `stop`) quits it unless it was handed over. It's its own class, not methods on `CompanionApp`, because the handed-over and restart flags belong to each module copy while the `CompanionApp` object moves between copies.

**Example**

    app = CompanionApp("voice_service", "127.0.0.1", 8767, ping="/health", log=ctx.log)
    await app.ensure_running()
    info = await app.call("GET", "/health")
    await app.stop()

**Defined in:** `src/app_kit/companion.py`

## `local_guard`

**Reusable** · Used by: `voice_service` (`server.py`: the `LocalOnly` guard on every request and WebSocket; `__main__.py`: refuses a non-local `--host`), HTML viewer app (`viewer.py`: every request; `ViewerServer` refuses a non-local host), the CV Tool app (`cv_tool/server.py`: every request, refuses a non-local host), the `cv` module (`LOOPBACK_HOSTS` for `tool.host`) · built 2026-11-08

`from app_kit import LOOPBACK_HOSTS, require_loopback, local_request`

Refuse other hosts and other origins: the check every local [companion app](../architecture/reusable-parts.md#companion-app-checklist) uses. A web page you visit can reach a local app by DNS rebinding (its own name pointing at `127.0.0.1`, so the `Host` header names another site) or as a cross-site request or WebSocket (the browser sends its `Origin`); these refuse both. Programs that aren't browsers send no `Origin`, so they pass with a local `Host`.

| Name | Does |
|------|------|
| `LOOPBACK_HOSTS` | `{"127.0.0.1", "localhost", "::1"}` |
| `require_loopback(host) -> str` | `host` if it's this machine's own address; `ValueError` for any other. Call it before listening |
| `local_request(host, origin) -> bool` | Whether to serve a request: its `Host` header names this machine and, if it has an `Origin`, that origin is the same app's own host and port (`http` or `https`). A missing or foreign `Host`, an `Origin` of `null` or another site: `False` |

Pair it with JSON-only POSTs (a web page can't send JSON cross-site without the browser asking first): the voice service's `POST /quit` answers 415 to anything else.

**Example**

    if not local_request(headers.get("host"), headers.get("origin")):
        return 403  # or close the WebSocket with 1008

**Defined in:** `src/app_kit/local_guard.py` · **Tests:** `tests/test_app_kit.py`, voice_in's `tests/test_voice_service.py`, html_viewer's `tests/test_html_viewer.py`
