# Infrastructure

Shared services for the main app's modules. All items: `from assistant.infra import ...`. Back to the [API index](README.md). Entries marked **Reusable** are listed in the [reusable parts index](reusable.md). What the independent apps share too is in [App kit](app_kit.md).

## `load_config`

**Reusable** · Used by: `__main__`, tests

`load_config(config_dir: str | Path | None = None) -> dict[str, Any]`

Load `default.toml`, then deep-merge `local.toml` over it if it exists. Tables merge key by key; other values (including lists) are replaced. A thin wrapper over [`app_kit.load_layered`](app_kit.md#load_layered).

**Parameters**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `config_dir` | `str \| Path \| None` | no | Directory holding the files. Defaults to `ASSISTANT_CONFIG_DIR`, then `./config` |

**Returns:** the merged config as nested dicts.

**Raises:** `FileNotFoundError` if `default.toml` is missing; `tomllib.TOMLDecodeError` for invalid TOML.

**Defined in:** `src/assistant/infra/config.py`
**See also:** [configuration keys](../architecture/core.md#configuration)

## `setup_logging`

**Reusable** · Used by: `__main__`, tests

`setup_logging(settings: dict[str, Any], extra: Sequence[logging.Handler] = ()) -> None`

Configure root logging from the `[logging]` config section. Replaces any existing configuration. `extra` handlers (e.g. [`LogSession.handler`](#logsession)) are added with the same format.

**Settings**
| Key | Default | Description |
|-----|---------|-------------|
| `level` | `"INFO"` | Standard level name |
| `file` | none | Log file path; parent directories are created |
| `stderr` | `false` | Also log to the terminal. Keep off while `console_io` is enabled |

With no `file`, `stderr`, or `extra`, logs are discarded. In the app, `[logging]` also has `dir` (default `"logs"`), and `file` is a file name: `__main__` takes both for the [`LogSession`](#logsession) and removes `file`, so the app log goes through `LogSession.handler` instead.

**Defined in:** `src/assistant/infra/log.py`

## `LogSession`

**Reusable** · Used by: `__main__` (the app log and every transcript)

`LogSession(root: str | Path = "logs", now: datetime | None = None, app_log: str = "assistant.log")`

The log handler: owns *where* one app launch's logs go. Nothing reaches disk until the first message's theme: then it creates `root/<start time>_<theme>/` (e.g. `logs/2026-10-26_03-06-52_can-you-split-the-logs/`; `-2`, `-3`… added after the time if the name is taken) and writes what its sinks held. A launch without a theme leaves no folder. Design: [Logging](../architecture/core.md#logging).

| Member | Does |
|--------|------|
| `root: Path` | The logs folder |
| `path: Path \| None` | The session folder, `None` until `set_theme` |
| `handler: logging.Handler` | The app log (`app_log`): pass it to [`setup_logging`](#setup_logging) |
| `sink(name) -> LogSink` | The [`LogSink`](#logsink) for the file `name` in the session folder; one per name |
| `folder() -> Path` | `path` once it exists, else `root` (for the temp UI's Logs button) |
| `set_theme(text)` | Make the theme folder-safe with [`theme_slug`](#theme_slug), create the folder, write what's held. The first usable theme wins; an unusable one (`"?!"`) is ignored |
| `finish() -> Path \| None` | Close the files; returns `path`. Without a theme, drops what was held, unless the app log had a warning or error: then it's appended to `root/no-chat.log`. Never raises |

**Example**

    session = LogSession("logs")
    setup_logging({}, [session.handler])            # held in memory
    session.set_theme("Can you split the logs per session?")
    session.finish()   # logs/2026-10-26_03-06-52_can-you-split-the-logs

**Defined in:** `src/assistant/infra/log.py`

## `LogSink`

**Reusable** · Used by: `ClaudeSession` transcripts (Talker, Main Assistant)

One log file of a [`LogSession`](#logsession), from `LogSession.sink(name)`. Holds what's written in memory until the session folder exists, then writes it to the file, and everything after it directly. Thread-safe.

| Member | Does |
|--------|------|
| `write(text)` | Append `text` (include the newline) |
| `held() -> str` | What was written while the folder didn't exist |
| `close()` | Close the file; a later `write` opens it again |

**Example**

    transcript = session.sink("talker.jsonl")
    ClaudeSession(command, transcript=transcript)

**Defined in:** `src/assistant/infra/log.py`

## `theme_slug`

**Reusable** · Used by: `LogSession`, `talker`

`theme_slug(text: str, max_words: int = 5) -> str`

A folder-safe theme: lowercase ASCII letters and digits, words joined by hyphens, at most `max_words` words. `"Session log folders?!"` → `"session-log-folders"`. Returns `""` if nothing usable is left.

**Defined in:** `src/assistant/infra/log.py`

## `ClaudeSession`

**Reusable** · Used by: `talker`, `main_assistant` (a callable command, for the permission mode; `env` for the edit hook), `SessionTaskAgent` (`set_permission_mode`)

`ClaudeSession(command: Sequence[str] | Callable[[], Sequence[str]], cwd: str | Path | None = None, log: Logger | None = None, on_event: Callable[[dict], None] | None = None, transcript: str | Path | LogSink | None = None, env: Mapping[str, str] | None = None)`

`env` adds variables to the process's environment, on top of the app's. The Main Assistant uses it so the edit hook can tell its worker apart from your own Claude Code sessions ([batching note](../agents/runtime.md#fresh-sessions-and-handoffs)).

One long-lived `claude -p` stream-json process. Knows nothing about tasks or agents: it writes messages and interrupts as JSON lines on stdin and hands every JSON line from stdout to `on_event`, in order. Build `command` with [`claude_command`](#claude_command). **`command` may be a callable** returning the command line: it's called on every `start`, so each new process gets the settings of that moment (the Main Assistant's permission mode). With `transcript`, every line in and out (and stderr) is appended to that file as `{"t", "dir": "in" | "out" | "stderr", "msg"}` JSON lines, for debugging. `transcript` may be a file path or a [`LogSink`](#logsink). Modules pass their `transcript` setting, which `__main__` has replaced with the session's sink.

| Member | Does |
|--------|------|
| `async start()` | Launch the process (no-op if running), reading `command` if it's a callable. Raises `FileNotFoundError` if `claude` isn't installed |
| `async send(text, images=())` | Send a user message, starting a turn. `images` are PNG or JPEG files sent with it as image blocks, so the model sees them; the transcript records their paths, not their data. Raises `RuntimeError` if not running, `OSError` if an image can't be read |
| `async interrupt()` | Interrupt the turn, like Esc. The turn still ends with a `result` (`is_error: true`) |
| `async set_permission_mode(mode)` | Switch the running process's `--permission-mode` (e.g. `acceptEdits`) with a `set_permission_mode` control request, as the Agent SDK does. Applies from the next tool use; the prompt stays as it started. Checked against the real `claude` (2026-11-02). Raises `RuntimeError` if not running |
| `async answer_permission(request, allow, message=...)` | Answer a `can_use_tool` control request (the whole event); deny sends `message` |
| `async close(timeout=3.0)` | Close stdin, wait, kill if it doesn't exit. `start` works again afterwards. Lines still arriving while it closes are logged, not passed on |
| `running: bool` | The process is alive |
| `working: bool` | From `send` until the turn's `result` |
| `context_tokens: int` | The latest call's input size, cached or not (from each assistant line's `usage`): what every further call resends. 0 after `start` |
| `used: dict[str, int]` | Tokens by kind (`input`, `cache_write`, `cache_read`, `output`), every call since construction, across restarts. Input counts each call once (by message id). Output comes from each turn's `result`: the streamed lines undercount it (2.5k against 129k in one real session) and only stand in while a turn runs |
| `cost_usd: float` | `claude`'s estimate (`total_cost_usd`, which counts per process) added up across restarts |
| `on_event` | Settable callback. Also gets `{"type": "exit", "returncode": n}` if the process ends on its own |

**Example**

    session = ClaudeSession(claude_command(model="sonnet"), on_event=print)
    await session.start()
    await session.send("Hello")

**Defined in:** `src/assistant/infra/claude_session.py`

## `claude_command`

**Reusable** · Used by: `talker`, `main_assistant` (`disallowed` for Auto's `git push` block)

`claude_command(*, model: str | None = None, tools: str = "", permission_mode: str | None = None, allowed: Sequence[str] = (), disallowed: Sequence[str] = (), permission_prompts: bool = False, system_prompt: str | None = None, program: Sequence[str] = ("claude",)) -> list[str]`

The command line for a stream-json `claude -p` session. Always adds `--strict-mcp-config` (otherwise your claude.ai MCP connectors load). `tools=""` means no tools; `allowed` are permission rules passed as `--allowedTools` (build path rules with [`path_rule`](#path_rule)); `disallowed` rules (e.g. `PowerShell(git push *)`) go in as `--disallowedTools`, one argument each, and are refused outright, even under `bypassPermissions` (checked against the real `claude`, 2026-11-02); `permission_prompts` adds `--permission-prompt-tool stdio`, so anything the rules don't allow arrives as a `can_use_tool` control request instead of being refused; `system_prompt` goes in as `--append-system-prompt`. `program` is replaceable so tests can run a fake.

**Defined in:** `src/assistant/infra/claude_session.py`

## `path_rule`

**Reusable** · Used by: `main_assistant` (one user so far; any agent that gets folder rules)

`path_rule(tool: str, folder: str | Path) -> str`

A permission rule for everything under `folder`: `path_rule("Edit", "docs")` → `Edit(//c/Chang/.../docs/**)`. `claude` matches absolute paths in POSIX form with a leading `//`, so Windows `C:\x` becomes `//c/x`. `Read` rules cover Read, Glob, and Grep; `Edit` rules cover Edit and Write. Checked against a real session: reads and writes inside the rule's folder work without a prompt; writes elsewhere are refused.

**Defined in:** `src/assistant/infra/claude_session.py` (`from assistant.infra.claude_session import path_rule`)

## `SessionTaskAgent`

**Reusable** · Used by: `main_assistant`; every task agent later (the decided pattern)

`SessionTaskAgent(session: ClaudeSession, ctx: ModuleContext, agent_id: str, description: str, capabilities: tuple[str, ...] = (), cancel_timeout: float = 5.0, permission_timeout: float = 600.0, fresh_sessions: bool = True, max_handoffs: int = 3, manual_claude_mode: str = "acceptEdits", context_reminder: int = 0, edit_note: bool = False, task_file: str | Path | None = None)`

An [`ITaskAgent`](agents.md#itaskagent) backed by one `ClaudeSession`: the shared part every task agent is built from. Turns `assign`, `message`, and `cancel` into session messages, and the session's events into [`ReportTask`](agents.md#reporttask), [`AgentActivity`](agents.md#agentactivity), [`AgentStateChanged`](agents.md#agentstatechanged), and [`SessionUsage`](agents.md#sessionusage). Sets itself as the session's `on_event`. Every method returns once its message or interrupt is written. A turn whose last line is `NEED: <question>` is reported as `need`. If a cancel's interrupt doesn't end the turn within `cancel_timeout`, the session is closed and the next task starts a fresh one. A `can_use_tool` request is reported as `permission` and held until [`answer_permission`](agents.md#itaskagentanswer_permission); after `permission_timeout` seconds it's denied. Behavior: [The Main Assistant on its own](../agents/runtime.md#the-main-assistant-on-its-own).

**Fresh sessions and handoffs.** With `fresh_sessions`, each task starts in a new `claude` process, so its context holds only that task. A turn (or a reply) whose last line is `HANDOFF: <note path>` continues the same task in a fresh session told to read that note; it's reported as `progress` "Handed off to a fresh session (n): <note>". After `max_handoffs` in one task it asks you instead (`need`).

**Context reminder.** With `context_reminder` (tokens; 0, the default, is off), the first time the session's context passes it during a task, checked with [`ContextWatch`](#contextwatch) wherever usage is published, the task gets a `[Context check]` message the same way [`message`](agents.md#itaskagent) sends any (interrupt, then carry on): find a safe point, write what's done and next into the change note, and end with `HANDOFF:`. Once per crossing: a fresh session starts small and re-arms it. While the task waits on you (a `NEED` or a permission request) the reminder is held and sent once it works again, so an open request isn't dropped. Logged (`context 152k past 150k: reminded task … to find a reset point`) and published as `AgentActivity` (`context reminder sent (152k)`).

**Edit note.** With `edit_note`, the second edit to a file in a task (`Edit`, `Write`, `MultiEdit` or `NotebookEdit`, paths compared lowercase with `/`, counted across handoffs) is logged (`batching note for task … : <path> edited twice`) and published as `AgentActivity` (`batching note: a.md`), once per file. It only reports and never sends the agent anything: the note the agent reads comes from the edit hook, with the tool call. With `task_file`, the current task's id is written there at each `assign`, so the hook can count by task across sessions.

**Permission mode.** It holds the [`PermissionMode`](agents.md#permissionmode) in memory, Manual at every launch. The owning module builds each session's command for `permission_mode` (pass the session a callable). A session started in another mode is always replaced at the next task, even if unused. Mid-task, a switch to Manual sends `ClaudeSession.set_permission_mode(manual_claude_mode)` when the running session is in Auto. Every switch is logged, published as `AgentActivity`, and published as [`PermissionModeChanged`](agents.md#permissionmodechanged).

| Member | Does |
|--------|------|
| `permission_mode: PermissionMode` | (property) The mode the next session starts in |
| `async set_permission_mode(mode) -> Result` | Set it. No task: `now`. Mid-task: Manual applies at once (`now`; `next_task` if the control request fails), Auto from the next task or handoff session (`next_task`). Always `ok` |
| `async reset() -> Result` | Start fresh. Idle: close the session now; the next task starts a new one. With a task: ask it (as a message) to write a handoff note, which continues it in a fresh session. `not_available` while a cancelled turn is still stopping |
| `async close()` | Stop its background tasks. The owning module closes the session itself |

**Example:** see [`ITaskAgent`](agents.md#itaskagent).

**Defined in:** `src/assistant/infra/session_agent.py`

## `session_usage`

**Reusable** · Used by: `SessionTaskAgent`, `talker`

`session_usage(agent_id: str, session: ClaudeSession) -> SessionUsage`

`session`'s usage so far ([`ClaudeSession`](#claudesession) `context_tokens`, `used`, `cost_usd`) as a [`SessionUsage`](agents.md#sessionusage) event; context 0 when the session isn't running. Used by `SessionTaskAgent` and the Talker.

**Example**

    ctx.publish(session_usage("talker", self._session))

**Defined in:** `src/assistant/infra/session_agent.py`

## `ContextWatch`

**Reusable** · Used by: `talker` (`context_warning`), `SessionTaskAgent` (`context_reminder`, in `main_assistant`) · built 2026-11-03

`ContextWatch(limit: int)`

Says when a session's context first passes `limit` tokens, once per crossing. `crossed(key, tokens) -> bool` is `True` the first time `key`'s context is at or past the limit, `False` while it stays over, and re-arms once that context comes back under (a reset or a fresh session). Keys are independent (the Talker watches itself and the worker). A `limit` of 0 or less turns it off. `limit` is readable.

**Example**

    watch = ContextWatch(150_000)
    if watch.crossed("main_assistant", usage.context_tokens):
        ...  # warn or remind, once

**Defined in:** `src/assistant/infra/context_watch.py`

## `agent_tags`

**Reusable** · Used by: `talker` (`find_tags`, `parse_show`), `html_viewer` module (`find_tags`, `parse_show`), `SessionTaskAgent` (`last_line`), `talker` (`last_line` for `RESTART_READY`) · built 2026-11-02

`from assistant.infra import find_tags, last_line, parse_show, Tag, ShowTag`

Reads the tags agents write in their text, the same way everywhere. Replaced the two SHOW parsers (Talker, `html_viewer` module), which handled quotes differently, and `SessionTaskAgent`'s own last-line reader.

| Function | Does |
|----------|------|
| `find_tags(text, names) -> list[Tag]` | Every `<<NAME>>` or `<<NAME: argument>>` in `text` whose name is in `names`, in order. `Tag(name, argument, start, end)`: the argument stripped (empty if none), `start`/`end` to slice it out of a reply. Names are case-sensitive; an unclosed tag, or an argument without a colon, isn't a tag |
| `last_line(text, prefix) -> str \| None` | The rest of the last non-empty line if it starts with `prefix` (`"NEED:"`, `"HANDOFF:"`, any case; `*` and backticks around it ignored), else `None` |
| `parse_show(argument) -> ShowTag` | A SHOW argument, `path \| "quote" \| heading`, as `ShowTag(path, quote, heading)`; empty parts are `None` |

**Quotes:** every quote mark around the path goes (paths never contain them). Around the quote and the heading only **one matching pair** goes (`"…"`, `'…'`, `“…”`, `‘…’`), so the page's own apostrophes and quote marks stay: `"the users' files"` → `the users' files`. An unclosed double quote mark at one end is dropped; a lone apostrophe is kept.

**Example**

    for tag in find_tags(reply, ("SHOW",)):
        show = parse_show(tag.argument)   # ShowTag(path='C:\\d\\x.html', quote='Parts', heading=None)
    question = last_line(text, "NEED:")   # "Which folder?" or None

**Defined in:** `src/assistant/infra/agent_tags.py` · **Tests:** `tests/test_agent_tags.py`

The Edge window functions (`open_app_window`, `close_app_windows`) moved to [App kit](app_kit.md#window); they aren't re-exported here.
