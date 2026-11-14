# Infrastructure

Shared services for the main app's modules. All items: `from assistant.infra import ...`. Back to the [API index](README.md). Entries marked **Reusable** are listed in the [reusable parts index](reusable.md). What the independent apps share too is in [App kit](app_kit.md).

## `load_config`

**Reusable** · Used by: `__main__`, tests

`load_config(config_dir: str | Path | None = None) -> dict[str, Any]`

Load the app's config from `config/`, each layer deep-merged over the one before (tables key by key; other values, lists included, replaced), with [`app_kit.load_layered`](app_kit.md#load_layered) and [`merge`](app_kit.md#merge):

1. `default.toml`: the core's settings.
2. `modules.toml`, then `modules.local.toml`, into `[modules]`: which modules are on (`enabled`). Missing is fine.
3. For every module id with a file (`module_config_ids`): `<id>.toml`, then `<id>.local.toml`, into `[modules.<id>]`; top-level keys are the module's settings. Either may be missing.
4. `local.toml`, if it exists, over everything (as before).

A module's own `module.toml` defaults go under all of these; the core merges them in (`App._config_of`). `NOT_MODULE_FILES` (`default`, `local`, `modules`, `permissions`, `voice_service`) are never read as a module's file. Also exported from `assistant.infra.config`: `module_config_ids(directory) -> list[str]`; `config_folder(config_dir=None) -> Path` (the directory `load_config` reads: `config_dir`, else `ASSISTANT_CONFIG_DIR`, else `config`); `module_config_files(directory, module_id) -> list[Path]` (its `<id>.toml` and `<id>.local.toml`, existing or not; `[]` for an id in `NOT_MODULE_FILES`), used by the core's [`RemoveModule`](control.md#removemodule) purge.

**Parameters**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `config_dir` | `str \| Path \| None` | no | Directory holding the files. Defaults to `ASSISTANT_CONFIG_DIR`, then `./config` |

**Example:** `config/temp_ui.toml` holding `port = 9001` makes temp_ui's `ctx.config["port"]` 9001 over its `module.toml`'s 8765; `config/temp_ui.local.toml` overrides that, and `[modules.temp_ui]` in `config/local.toml` last.

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
| `id: str` | A new id per `ClaudeSession` object (kept across process restarts inside it), sent as `SessionUsage.session` |
| `subagents` | Each sub-agent's tokens, by `agentId`, with its type. Taken per turn from the `result`: its `model_usage_since_last_result` (or the cumulative `modelUsage`) less the session's own calls since the last result. Shared among the sub-agents that returned that turn, by last-call size; with none, under `unnamed`. Without per-turn numbers, each sub-agent's last-call numbers are used. Rows with no tokens yet are left out |
| `on_event` | Settable callback. Also gets `{"type": "exit", "returncode": n}` if the process ends on its own |

**Example**

    session = ClaudeSession(claude_command(model="sonnet"), on_event=print)
    await session.start()
    await session.send("Hello")

**Defined in:** `src/assistant/infra/claude_session.py`

## `claude_command`

**Reusable** · Used by: `talker`, `main_assistant` (`disallowed` for Auto's `git push` block)

`claude_command(*, model: str | None = None, tools: str = "", permission_mode: str | None = None, allowed: Sequence[str] = (), disallowed: Sequence[str] = (), permission_prompts: bool = False, system_prompt: str | None = None, program: Sequence[str] = ("claude",), mcp_config: dict | None = None, chrome: bool = False, settings: dict | None = None) -> list[str]`

The command line for a stream-json `claude -p` session. `chrome` adds `--chrome`, the Claude in Chrome tools on your logged-in browser (the job agent; whether it loads under `--strict-mcp-config` is to be checked in the real app). Always adds `--strict-mcp-config` (otherwise your claude.ai MCP connectors load). `tools=""` means no tools; `allowed` are permission rules passed as `--allowedTools` (build path rules with [`path_rule`](#path_rule)); `disallowed` rules (e.g. `PowerShell(git push *)`) go in as `--disallowedTools`, one argument each, and are refused outright, even under `bypassPermissions` (checked against the real `claude`, 2026-11-02); `permission_prompts` adds `--permission-prompt-tool stdio`, so anything the rules don't allow arrives as a `can_use_tool` control request instead of being refused; `system_prompt` goes in as `--append-system-prompt`. `settings` (Claude Code settings for this session only) goes in as `--settings <json>`: a module's own agent passes `{"claudeMdExcludes": [...]}` to skip the repo's CLAUDE.md ([`AgentProfile`](#agentprofile), module layout step 1, 2026-11-13; tried in a live session with claude 2.1.325, forward-slash and backslash paths both work). `program` is replaceable so tests can run a fake.

**Defined in:** `src/assistant/infra/claude_session.py`

## `path_rule`

**Reusable** · Used by: `main_assistant` (one user so far; any agent that gets folder rules)

`path_rule(tool: str, folder: str | Path) -> str`

A permission rule for everything under `folder`: `path_rule("Edit", "docs")` → `Edit(//c/Projects/AI_Assistant/docs/**)`. `claude` matches absolute paths in POSIX form with a leading `//`, so Windows `C:\x` becomes `//c/x`. `Read` rules cover Read, Glob, and Grep; `Edit` rules cover Edit and Write. Checked against a real session: reads and writes inside the rule's folder work without a prompt; writes elsewhere are refused.

**Defined in:** `src/assistant/infra/claude_session.py` (`from assistant.infra.claude_session import path_rule`)

## `SessionTaskAgent`

**Reusable** · Used by: `main_assistant`, `task_agents`, `job_search` (through [`ProfileAgent`](#profileagent))

`SessionTaskAgent(session: ClaudeSession, ctx: ModuleContext, agent_id: str, description: str, capabilities: tuple[str, ...] = (), cancel_timeout: float = 5.0, permission_timeout: float = 600.0, fresh_sessions: bool = True, max_handoffs: int = 3, manual_claude_mode: str = "acceptEdits", context_reminder: int = 0, edit_note: bool = False, task_file: str | Path | None = None, write_folders: Iterable[str] = (), compact_handoffs: Callable[[], bool] = lambda: False, close_tabs: Callable[[], bool] = lambda: False)`

**Working with other agents** (built 2026-11-05). `write_folders` goes into `info()` for the Hub's folder-clash check (pass [`AgentProfile.write_folders()`](#agentprofile)). Each `STATUS: <line>` in the agent's text ([`status_lines`](#agent_tags)) is reported as a `milestone`. [`note(text)`](agents.md#itaskagentnote) adds the line to a [`MilestoneFeed`](#milestonefeed), whose block goes at the end of the next message the agent writes to its session: a new task, a message (either kind), and every message it sends itself (handoffs, continues, reminders). Never an interrupt, never a turn of its own.

An [`ITaskAgent`](agents.md#itaskagent) backed by one `ClaudeSession`: the shared part every task agent is built from. Turns `assign`, `message`, and `cancel` into session messages, and the session's events into [`ReportTask`](agents.md#reporttask), [`AgentActivity`](agents.md#agentactivity), [`AgentStateChanged`](agents.md#agentstatechanged), and [`SessionUsage`](agents.md#sessionusage). Sets itself as the session's `on_event`. Every method returns once its message or interrupt is written. A turn whose last line is `NEED: <question>` is reported as `need`. If a cancel's interrupt doesn't end the turn within `cancel_timeout`, the session is closed and the next task starts a fresh one. A `can_use_tool` request is reported as `permission` and held until [`answer_permission`](agents.md#itaskagentanswer_permission); after `permission_timeout` seconds it's denied. Behavior: [The Main Assistant on its own](../agents/runtime.md#the-main-assistant-on-its-own).

**Fresh sessions and handoffs.** With `fresh_sessions`, each task starts in a new `claude` process, so its context holds only that task. A turn (or a reply) whose last line is `HANDOFF: <note path>` continues the same task in a fresh session told to read that note; it's reported as `progress` "Handed off to a fresh session (n): <note>". After `max_handoffs` in one task it asks you instead (`need`), a question like any other: its key is the note, and your answer starts a fresh session pointed at the note, as the first of a fresh allowance, so it asks again only after `max_handoffs` more. A finished task ends with a plain report, not `HANDOFF:` (which would continue it).

**Handoffs in place, for Chrome agents** (built 2026-11-10). Chrome ties an agent's tab group to its `claude` session id, so a fresh session can't reach the old tabs. When `compact_handoffs()` is true ([`ProfileAgent`](#profileagent) passes `lambda: profile.chrome`) and the session is live in the current mode, a `HANDOFF:` keeps the session: it sends `/compact` (asking the summary to keep the note's path and each tab's id), reports `progress` "Handed off in place, context compacted (n): <note>", and on the compact's result sends "Task, continued after your context was compacted …" with the note. Messages that come during the compact are held and added to that message. A failed compact falls back to a fresh session. It counts against `max_handoffs` like any handoff. A new task still starts fresh.

**Closing Chrome tabs at a task's end** (built 2026-11-10). When `close_tabs()` is true (`ProfileAgent` passes `lambda: profile.chrome`), the task used a Claude in Chrome tool (`mcp__claude-in-chrome__*`), and the turn with its final reply called no `tabs_close_mcp`, the agent holds the `done` report and sends one more turn (`CLOSE_TABS`): close the tabs you no longer need, keep any the user should act on, reply in one line. On that turn's result it reports `done` with the real final text, even if the turn failed. A message during that turn waits for it, then goes in like any message (`INTERRUPTED`), and the task carries on. A question, a handoff, a cancel or a failure closes nothing. `AgentProfile.command` allows `tabs_context_mcp` and `tabs_close_mcp` with no card for an agent with Chrome, and every agent's prompt has the rule: close a tab once its page is done, and the rest before the final reply.

**Questions are messages** (built 2026-11-10). Outside, the agent is `active` or `idle` ([`AgentState`](agents.md#agentstate), `info().state`). A turn ending `NEED: <question>` reports `need` with the question's key ([`ReportTask.key`](agents.md#reporttask)), drops the task and is idle as soon as the Hub has the report: it takes new work, whatever it asked. The answer comes back as the same task (`Task.question_key` set): into the live session if that still has the question (nothing ran since), else a fresh session whose first message adds "[App] This is a fresh session …" and the module's notes for the key. A `message` to a task it has just asked in gets `not_available` until the report is with the Hub.

**Context reminder.** With `context_reminder` (tokens; 0, the default, is off), the first time the session's context passes it during a task, checked with [`ContextWatch`](#contextwatch) wherever usage is published, the task gets a `[Context check]` message the same way [`message`](agents.md#itaskagent) sends any (interrupt, then carry on): find a safe point, write what's done and next into the change note, and end with `HANDOFF:`. Once per crossing: a fresh session starts small and re-arms it. While the task waits on you (a permission request) the reminder is held and sent once it works again, so an open request isn't dropped. Logged (`context 152k past 150k: reminded task … to find a reset point`) and published as `AgentActivity` (`context reminder sent (152k)`).

**Edit note.** With `edit_note`, the second edit to a file in a task (`Edit`, `Write`, `MultiEdit` or `NotebookEdit`, paths compared lowercase with `/`, counted across handoffs) is logged (`batching note for task … : <path> edited twice`) and published as `AgentActivity` (`batching note: a.md`), once per file. It only reports and never sends the agent anything: the note the agent reads comes from the edit hook, with the tool call. With `task_file`, the current task's id is written there at each `assign`, so the hook can count by task across sessions.

**SHOW tags.** Every `<<SHOW: path>>` or `<<SHOW: path | "quote" | heading>>` in the agent's text (read with [`agent_tags`](#agent_tags)) is opened through the page-opener slot ([`IPageOpener`](modules.md#ipageopener)) by [`show_page`](#show_page), in the background; the core turns the module that provides it on first if it's off ([`StartProvider`](control.md#startprovider)). A failure is logged and published as `AgentActivity` (`couldn't show <path>: <error>`). Built 2026-11-05; it was the `html_viewer` module's job before.

**Permission mode.** It holds the [`PermissionMode`](agents.md#permissionmode) in memory, Manual at every launch. The owning module builds each session's command for `permission_mode` (pass the session a callable). A session started in another mode is always replaced at the next task, even if unused. Every switch applies at once. Mid-task, a switch to Manual sends `ClaudeSession.set_permission_mode(manual_claude_mode)` when the running process is in Auto. A switch to Auto mid-task leaves the process in its Manual mode (the `git push` block is a launch flag) and the agent answers each `can_use_tool` itself: allowed, logged as `allowed in Auto: …`, or, for a PowerShell or Bash command containing `git push`, refused (`refused in Auto: …`). An open tool request is answered the same way at the switch. The session gets the new mode's rules (`AUTO_ACCESS` / `MANUAL_ACCESS`) at the end of its next message; to Auto mid-turn it's interrupted for them (the usual message path), then carries on. Every switch is logged, published as `AgentActivity`, and published as [`PermissionModeChanged`](agents.md#permissionmodechanged).

| Member | Does |
|--------|------|
| `permission_mode: PermissionMode` | (property) The mode the next session starts in |
| `state: AgentState` | (property) `active` (in a turn, or held in one) or `idle` (no task, or stopped on one) |
| `has_task: bool` | (property) It holds a task, in a turn or stopped on one: a reload or a restart would cut it. Used by `ProfileAgent.busy` and `main_assistant` |
| `set_context(key, notes)` | **♻ Reusable.** The owning module's hook for questions. `key(task_id) -> str`: a question's context key (`""` for none: the task's last handoff note is used). `notes(key) -> str`: what a fresh session needs to pick the work up again when the answer comes (`""` for nothing). Defaults: no key, and `default_context`. Used by: `cv` (`JobStartAgent.question_key`, `job_notes`) · built 2026-11-10 |
| `async set_permission_mode(mode) -> Result` | Set it; applies at once (`now`; `next_task` only if a live switch to Manual fails). `ok`; the value is `True` when it answered an open permission request (published as `PermissionModeChanged.answered`, so the Hub closes that card). **Auto only through the core** (G12, 2026-11-13): `not_available` unless the core's Callers port (`IAgentNames.mode`) already holds Auto for this agent; with no `IAgentNames` (a bare test context) it doesn't check |
| `async reset() -> Result` | [`ITaskAgent.reset`](agents.md#itaskagentreset), called by the Hub for `ResetRequested`. Start fresh. Idle: close the session now; the next task starts a new one. With a task: ask it (as a message) to write a handoff note, which continues it in a fresh session. `not_available` while a cancelled turn is still stopping |
| `async restart_session() -> bool` | Close the session and start a new one at once, so it re-reads its command (a changed grant). Only when idle: `False` if a task has it. Holds the session lock that every session start takes, so a task assigned meanwhile waits for the new session instead of racing it. Used by `ProfileAgent.set_access` (built 2026-11-05) |
| `async request_approval(action, run) -> Result` | [`ITaskAgent.request_approval`](agents.md#itaskagentrequest_approval): ask you on the current task in Manual; in Auto it runs at once (the one check is `PermissionGate.ask`). `not_available` with no task or with a question already open |
| `async close()` | Stop its background tasks. The owning module closes the session itself |

**Approvals** (built 2026-11-05). One path asks you to allow an app action on the task: `request_approval` (a helper launch from `task_agents`) and a turn whose last line is `RELOAD: <module id> [now]` or `ADD_MODULE: <package>`. It puts a `permission` report on the task, so you get the same card and answer with [`AnswerPermission`](agents.md#answerpermission). **A `RELOAD:` / `ADD_MODULE:` line asks in Auto too** (2026-11-13: `PermissionGate.ask(..., always=True)`; Auto never skips a reload or an add of code), then sends `ReloadModule` / `AddModule` (in [`AGENT_SENDS`](#agentkit); the [control-command check](modules.md#modulecontextsend) lets a task agent's module send them). A helper launch still runs at once in Auto. On Allow, `run()` runs and its outcome becomes the task's next message: `[App] <action>: <outcome> Continue the task...`. While the approval is open, a turn that ends doesn't finish the task; if you answer mid-turn, the outcome is sent when the turn ends. A tool's permission request that comes while an approval is open is refused (one question to you at a time).

**Its parts** (split 2026-11-08, principle 18). `SessionTaskAgent` keeps the task state machine and wires these together: a [`PermissionGate`](#permissiongate) (the one open question: tool requests, approvals, the timer, the Auto policy and the `git push` block), a [`HandoffKeeper`](#handoffkeeper) (handoff count, reminders, reset requests), and a [`LastLineTags`](#lastlinetags) table for the turn's last line (`NEED`, `RELOAD`, `ADD_MODULE`, `HANDOFF`). Its usage comes from the session's [`UsageMeter`](#usagemeter).

| Function | Does |
|----------|------|
| `default_context(key) -> str` | **♻ Reusable.** The notes for a question's key when its module has none of its own: "Your last handoff note for this work is <key>; read it first." (`""` for an empty key). `set_context`'s default notes; `cv`'s `job_notes` falls back to it for a key that isn't a job folder. `from assistant.infra.session_agent import default_context` · built 2026-11-10 |

**Example:** see [`ITaskAgent`](agents.md#itaskagent).

**Defined in:** `src/assistant/infra/session_agent.py` · parts in `permission_gate.py`, `handoff_keeper.py`, `agent_tags.py`

## `AgentProfile`

**Reusable** · Used by: `main_assistant` (its command line, prompt and `write_folders`), `task_agents`, `job_search` (through `ProfileAgent`) · built 2026-11-05

`AgentProfile(agent_id, workspace, read_dirs=(), write_dirs=(), allowed_commands=(), tools="Read,Write,Edit,Glob,Grep", model=None, claude_mode="acceptEdits", permission_prompts=True, program=("claude",), role_block=HELPER_BLOCK, chrome=False, python=None, requests=False, repo_claude_md=True, module_folder=None)` (frozen dataclass) · `from assistant.infra import AgentProfile, prompt_block, repo_claude_md_files`

What makes one `claude` task agent: everything but its own prompt comes from config, so the folder, access and command code lives here once (it moved out of `main_assistant`).

| Member | Does |
|--------|------|
| `from_config(agent_id, config, role_block=HELPER_BLOCK)` | From a config section: `workspace`, `read_dirs`, `write_dirs`, `allowed_commands`, `python` (a Python it may run, with any arguments: a rule and a line in its access section), `tools`, `model`, `permission_mode` (a Manual claude mode only, through `manual_claude_mode`), `permission_prompts`, `program`, `chrome` (passed to `claude_command`), `permission_requests`, `repo_claude_md` (true or false, else `ValueError`) and `module_folder` (`ProfileAgent` fills it from its module's id). A task-agent module passes the granted config ([`granted_config`](#agent_access)) |
| `write_folders() -> tuple[str, ...]` | Its workspace and `write_dirs`, resolved, for [`AgentInfo.write_folders`](agents.md#agentinfo) |
| `command(prompt, mode, door=None) -> list[str]` | The session's command line for a [`PermissionMode`](agents.md#permissionmode): `prompt`, then the shared block, the access section and, with a door config, the door's note. Auto adds `bypassPermissions`, the `git push` block (`AUTO_BLOCKED`) and the risky-step rule; with the door, its two read-only tools are allowed. With `repo_claude_md = false` (a module's own agent: cv's, the job agent) it adds `--settings` with `claudeMdExcludes` (`repo_claude_md_files()`) and ends the prompt with the developer rules (`developer_rules`) |
| `access(mode) -> str` | The access section of the prompt |

| Function or constant | Does |
|----------------------|------|
| `prompt_block(role_block=HELPER_BLOCK) -> str` | **The shared prompt block.** It starts with `BASICS_BLOCK` (what every agent is told: its access is listed at the end, a line before each step, a summary at the end), then the role's half. A helper's half (`HELPER_BLOCK`): `STATUS: <one line>` for big milestones, for the coordinator; `NEED:` (or a tool that asks) for questions for you, which may wait until you turn to it, so each must stand on its own; never mix the two. The coordinator's half (`COORDINATOR_BLOCK`) names the Hub's and `task_agents`' menus, so it lives in `main_assistant` and is passed in as `role_block` (principle 21: shared code names no module) |
| `repo_claude_md_files(repo=REPO_FOLDER) -> list[str]`, `developer_rules(module_folder) -> str`, `DEVELOPER_RULES` | **♻ Reusable.** The repo's own `CLAUDE.md`, `CLAUDE.local.md` and `.claude/CLAUDE.md` (absolute, forward slashes) for `claudeMdExcludes`; a workspace's own CLAUDE.md (the job project's) isn't among them, so it still loads. The short developer rules a module's own agent gets in their place: `src/assistant/infra/developer_rules.md`, with its module's folder, its `docs/README.md`, the reusable parts index and the repo's Python filled in. Used by: `AgentProfile.command` · built 2026-11-13 (module layout step 1) |
| `command_rules(command)`, `hook_env(agent_id, task_file, edit_note)` | Permission rules for a shell command with any arguments; the edit hook's environment |
| `DOOR_PROMPT`, `MANUAL_ACCESS`, `AUTO_ACCESS`, `AUTO_BLOCKED`, `AUTO_CLAUDE_MODE` | The prompt's door note and access texts; Auto's hard block and claude mode |
| `manual_claude_mode(value) -> str`, `MANUAL_CLAUDE_MODES` | **♻ Reusable.** The claude mode a session starts in from config's `permission_mode`: one of `MANUAL_CLAUDE_MODES` (`default`, `acceptEdits`, `plan`), else `acceptEdits` with a warning, so no config starts a session in Auto. Used by: `AgentProfile.from_config` (every task agent). `from assistant.infra.agent_profile import manual_claude_mode` |

**Example**

    profile = AgentProfile.from_config("main_assistant", ctx.config, role_block=COORDINATOR_BLOCK)
    session = ClaudeSession(lambda: profile.command(WORKER_PROMPT, agent.permission_mode, door()), ...)
    agent = SessionTaskAgent(session, ctx, ..., write_folders=profile.write_folders())

**Defined in:** `src/assistant/infra/agent_profile.py` · **Tests:** `tests/test_multi_agent.py`, `tests/test_agents.py`, `tests/test_mcp_door.py`, `tests/test_module_layout.py`

## `ProfileAgent`

**Reusable** · Used by: `main_assistant`, `task_agents` (the autostarted and the launched helpers), `job_search` (the job agent, bundled with its menu) · built 2026-11-05

`ProfileAgent(ctx, agent_id, config, prompt, role_block=HELPER_BLOCK, start_session=False, subject=None, session_factory=ClaudeSession)` · `from assistant.infra import ProfileAgent`

`session_factory` builds its session (with `ClaudeSession`'s arguments): pass a fake to test or swap it without patching (principle 22). A module that owns ProfileAgents declares what they use from [`AGENT_USES` and the rest](#agentkit).

One big agent put together from its config section, the same way for every agent: an [`AgentProfile`](#agentprofile), a [`ClaudeSession`](#claudesession) whose command is read at each session start (the mode of that moment, and the module door under the agent's own name), and a [`SessionTaskAgent`](#sessiontaskagent) with the profile's `write_folders` and the section's `named_only` (true: a free pick skips it, [`AgentInfo.named_only`](agents.md#agentinfo); not true or false: `ValueError`). The owning module provides `agent` as `ITaskAgent`. It claims its id from the core's Callers port ([`IAgentNames`](agents.md#iagentnames)) on `start` and releases it on `stop`, so every agent built this way gets the duplicate check with no code of its own; the claim is also what lets its module get the door config under the agent's id ([`IModuleDoor`](tools.md#imoduledoor)).

| Member | Does |
|--------|------|
| `agent`, `session`, `profile`, `workspace` | The parts, for the module to provide and use. The profile gets its module's own folder (`module_folder(ctx.module_id)`) as `module_folder`, named in the developer rules |
| `door() -> dict` | `IModuleDoor.mcp_config(agent_id)` (the core's door, only for an id this module claimed), read at each session start, or `{}` when `door = false` or the door is off |
| `snips() -> str` | This launch's snips folder (`ctx.logs.folder()/snips`), read at each session start; the command gets a `Read` rule and an access line for it, with no card |
| `set_access(config)` | A grant changed: rebuild `profile` from the new granted config and hand `agent` its new `write_folders` (a setter on `SessionTaskAgent`). An idle open session restarts once in the background; a busy one takes it at its next session. The workspace stays as it started. `stop` cancels a pending restart |
| `subject` | The grant it holds (its own id, or its kind). Given, `start` calls `ctx.permissions.own_agent`, and its prompt tells it to ask for more access with `permissions.request` (config `permission_requests`) |
| `busy() -> str \| None` | Why a reload should wait (it has a task: `agent.has_task`; a question waiting on you doesn't count) |
| `start()`, `stop()` | `start` claims the agent's id with `IAgentNames.claim(agent_id, ctx.module_id)` when the core's `IAgentNames` is there (a refusal raises `RuntimeError` with the reason, so at launch its module fails to start and the log says why), then makes the workspace (and, with `start_session`, starts `claude`). The core opens the door before any module starts, so the first session has it (the old wait-and-restart for a door that wasn't up yet is gone, 2026-11-13). `stop` closes the agent and session, then releases the id |

Config keys besides `AgentProfile.from_config`'s: `description`, `capabilities`, `permission_timeout`, `fresh_sessions`, `max_handoffs`, `context_reminder`, `edit_note`, `transcript`, `door`.

**Defined in:** `src/assistant/infra/profile_agent.py` · **Tests:** `task_agents/tests/test_task_agents.py`, `tests/test_agents.py`, `tests/test_agent_names.py`

## `agent_access`

**Reusable** · Used by: `job_search` (the job agent, subject `job_search_agent`), `cv` (`cv_agent`, through `AgentKit.open`), `task_agents` (each autostart kind on start, a launched helper's kind with `wait=True`; `own_folder=False`); `module_folder_of`: `agent_hub` (the folder check); `in_module_folder`, `data_folder`, `copy_data_once`: `cv`, `job_search` · built 2026-11-05; the own module folder 2026-11-13; `in_module_folder` 2026-11-13 (item 18); the data folder 2026-11-13 (module layout step 1)

`from assistant.infra import access_items, granted_config, request_access, watch_grant, module_roots, module_folder, module_folder_of, in_module_folder, data_folder, copy_data_once, MODULES_FOLDER, REPO_FOLDER`

A task agent's access list, from its config section, asked for in one request. A module that uses it declares `agent.access` in its manifest. Design: [access lists](../architecture/permissions.md#access-lists-built). Every module can edit itself: a module's own agent's list has a write on its own module folder by default.

| Function | Does |
|----------|------|
| `access_items(config, module_id="") -> tuple[AccessItem, ...]` | The [`AccessItem`](messaging.md#accessitem)s of a config section: `workspace` (resolved, always first), `read_dirs`, `write_dirs` (resolved), with `module_id` a write on that module's own folder (`module_folder`, when it exists), then `python`, `allowed_commands`, `chrome` |
| `granted_config(config, granted) -> dict` | The config cut down to the `granted` items: trimmed folders, Python, commands and Chrome dropped; paths resolved. Granted items beyond the config's list (its own module folder, or added by the agent's own `permissions.request`) are added. Raises [`AccessDenied`](messaging.md#accessdenied-accesspending) when the workspace wasn't granted, since an agent can't run without it |
| `async request_access(ctx, config, subject="", reason="", wait=False, own_folder=True) -> dict` | Both: asks with [`ctx.permissions.request_set`](modules.md#modulecontextpermissions) and returns the granted config. `own_folder`: the list includes a write on `ctx.module_id`'s own folder (`task_agents` passes False: its helpers aren't that module's own agent). Raises `AccessPending` (with `wait=False`, while its card is open) or `AccessDenied`, as `request_set` does |
| `module_roots() -> list[Path]` | Every folder holding module folders: `MODULES_FOLDER` (the repo's `src/assistant/modules`) first, then the outside ones `[core] module_folders` names. Read from the `assistant.modules` package's path, which the core's loader extends at startup ([`add_module_folders`](core.md#loader)), so the two never disagree. Used by `module_folder`, `module_folder_of`, `main_assistant` (its prompt names the folders), the docs build, the folder tests. Built 2026-11-13 (module layout step 2) |
| `module_folder(module_id) -> Path \| None` | The module's own folder: `<root> / module_id` in the first of `module_roots` that has it (`src/assistant/modules/<id>`, or an outside folder's `<id>`), or None when there's no such folder |
| `in_module_folder(module_id, path) -> Path` | A configured folder of a module: `~` expanded, a relative one from that module's own folder (`workspace` → `src/assistant/modules/<id>/workspace`, resolved), an absolute one as given. So no shipped default names a personal path. Used by `cv` (its `[agent] workspace`, `output_dir`) and `job_search` (`workspace`, `documents`) |
| `module_folder_of(path) -> Path \| None` | The module folder `path` is in (or is), in any of `module_roots`, or None outside every module's folder (a modules folder itself included). The Hub's folder check uses it |
| `data_folder(module_id, config) -> Path \| None` | **Your data leaves the repo** (module layout step 1). The module's `data_folder` key (yours, in `config/<id>.toml`), `~` expanded and resolved, or None when unset or empty: then its agent works in its module's own `workspace/`, as before. Set, it's the agent's workspace, so everything kept under the workspace follows it. `ValueError` if it isn't a string, isn't absolute, or is inside the repo (`REPO_FOLDER`). Used by `cv` (`settings`) and `job_search` (`job_config`) |
| `copy_data_once(source, target) -> bool` | A data folder's first use: when `target` is missing or empty and `source` (the old workspace) is a folder, copy it in (`__pycache__` skipped). Never moves or deletes: the old workspace stays, and a `target` holding any file is used as it is. True when it copied. Called in `cv`'s and `job_search`'s `init` (job_search then writes the copy's relative `job_paths.json` paths absolute) |
| `watch_grant(ctx, on_grant, subject=None)` | Call `async on_grant(subject, granted)` whenever one of this module's grants is saved with items (`PermissionChanged`); `subject=None`: every subject (a kind each in `task_agents`). A denied or removed grant is skipped (a revoke turns the module off). Subscribe in `init`; list `PermissionChanged` in `listens` |

A trimmed folder or command never becomes a rule, so `claude` asks for it with a normal card. The config keys it reads, including `python` (a Python it may run, with any arguments), are [`AgentProfile.from_config`](#agentprofile)'s.

**Example**

    config = await request_access(ctx, ctx.config, subject="job_search_agent", reason="the job agent's folders")
    agent = ProfileAgent(ctx, "job_search_agent", config, PROMPT, subject="job_search_agent")
    # in init: watch_grant(ctx, on_grant, subject="job_search_agent"); on_grant calls
    # agent.set_access(granted_config(ctx.config, granted))

**Defined in:** `src/assistant/infra/agent_access.py` · **Tests:** `tests/test_permissions_handler.py`, `tests/test_access_cards.py`

## `agent_names`

**Reusable** · Used by: the core's [`Callers`](core.md#callers) (its [`IAgentNames`](agents.md#iagentnames)), `task_agents` (the autostarted ids, and the launch check when no core names run) · built 2026-11-05

`from assistant.infra import check_agent_id, free_agent_id`

The rules for agent ids, in one place. The core's Callers port applies them when an agent claims its id; anything naming an agent can check a name early with the same rules. The shared rules reserve no id (principle 21): the caller passes the ones it reserves. The core reserves `core`, `hub`, `talker` (`RESERVED_AGENT_IDS` in `core/callers.py`; the coordinator needs no entry, since every module's id is refused anyway); `task_agents` passes the callers its menu trusts. Design: [agent names](../architecture/agents.md#agent-names).

| Item | Does |
|------|------|
| `check_agent_id(agent_id, owner="", module_ids=(), reserved=()) -> str \| None` | Why an agent of module `owner` can't use `agent_id`, or None. The form: lowercase letters, digits and `_`, starting with a letter, at most 32 characters (`^[a-z][a-z0-9_]{0,31}$`). `reserved` ids and module ids are refused, except when `agent_id == owner` (a module's own agent may carry its module's id) |
| `free_agent_id(base, taken) -> str` | `base` if it's not in `taken`, else the first free of `base_2`, `base_3`, ... |

**Example**

    check_agent_id("Flight-Search")                       # "`Flight-Search` isn't a valid agent id: ..."
    check_agent_id("voice_in", "task_agents", ["voice_in"])  # "`voice_in` is a module's id"
    check_agent_id("main_assistant", "main_assistant")    # None: its module's own id
    free_agent_id("helper", {"helper", "helper_2"})        # "helper_3"

**Defined in:** `src/assistant/infra/agent_names.py` · **Tests:** `tests/test_agent_names.py`

## `MilestoneFeed`

**Reusable** · Used by: `SessionTaskAgent` (`note`) · built 2026-11-05

`MilestoneFeed()` · `from assistant.infra import MilestoneFeed`

Lines waiting for an agent's next message to its session. `add(line)` keeps it (the last 50; older ones only count). `take(max_lines=5) -> str` empties the feed into one block under `HEADER` ("[Updates from the other agents (background: …)]"), one `- line` each, newest last, the oldest merged as `(+N earlier)`; `""` when nothing waits. So lines never pile up in a prompt and never interrupt.

**Defined in:** `src/assistant/infra/milestone_feed.py` · **Tests:** `tests/test_multi_agent.py`

## `session_usage`

**Reusable** · Used by: `SessionTaskAgent`, `talker`

`session_usage(agent_id: str, session: ClaudeSession) -> SessionUsage`

`session`'s usage so far ([`ClaudeSession`](#claudesession) `context_tokens`, `used`, `id` as `session`) as a [`SessionUsage`](agents.md#sessionusage) event; context 0 when the session isn't running. Used by `SessionTaskAgent` and the Talker.

**Example**

    ctx.publish(session_usage("talker", self._session))

`subagent_usage(agent_id, session) -> list[SessionUsage]`: one per sub-agent the session ran (from [`ClaudeSession.subagents`](#claudesession): each turn's sub-agent tokens, by `agentId`), with `parent = agent_id`, `kind = "subagent"`, its tokens and the parent session's `session` id. `SessionTaskAgent` publishes each one when its tally grows.

**Defined in:** `src/assistant/infra/session_agent.py`

## `UsageLedger`

**Reusable** · Used by: `usage`

`UsageLedger()`

Every agent's usage since the app started, from their running totals. Plain Python, no app imports.

| Method | Description |
|--------|-------------|
| `add(usage)` | Take one `SessionUsage` (or anything with its fields). Replaces that agent's numbers (they are totals); when its `session` id changes (or, with no id, when they go down), what it had is kept and the new numbers add to it |
| `total() -> dict` | Every agent together: the four token counts, `used_tokens`, and `agents` (top-level rows). Tokens only |
| `by_agent() -> list[dict]` | One row per top-level agent, in the order they first reported; sub-agents and tools in `children`; each row has its own numbers and a `total` with its children |
| `mine(agent_id) -> dict` | One agent's row with its children; zeros if it hasn't reported |

A row with a `parent` is listed under it and rolled into the parent's `total`. A sub-agent's tokens aren't in its parent's own numbers, so nothing is counted twice.

**Defined in:** `src/assistant/infra/usage_ledger.py` · **Tests:** `tests/test_usage.py`

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

**Reusable** · Used by: `talker` (`find_tags`, `parse_show`), `html_viewer` module (`find_tags`, `parse_show`), `SessionTaskAgent` (`last_line`, `status_lines`), `talker` (`last_line` for `RESTART_READY`) · built 2026-11-02

`from assistant.infra import find_tags, last_line, parse_show, status_lines, Tag, ShowTag`

Reads the tags agents write in their text, the same way everywhere. Replaced the two SHOW parsers (Talker, `html_viewer` module), which handled quotes differently, and `SessionTaskAgent`'s own last-line reader.

| Function | Does |
|----------|------|
| `find_tags(text, names) -> list[Tag]` | Every `<<NAME>>` or `<<NAME: argument>>` in `text` whose name is in `names`, in order. `Tag(name, argument, start, end)`: the argument stripped (empty if none), `start`/`end` to slice it out of a reply. Names are case-sensitive; an unclosed tag, or an argument without a colon, isn't a tag |
| `last_line(text, prefix) -> str \| None` | The rest of the last non-empty line if it starts with `prefix` (`"NEED:"`, `"HANDOFF:"`, any case; `*` and backticks around it ignored), else `None` |
| `parse_show(argument) -> ShowTag` | A SHOW argument, `path \| "quote" \| heading`, as `ShowTag(path, quote, heading)`; empty parts are `None` |
| `status_lines(text, max_len=160) -> list[str]` | What follows `STATUS:` on every line that starts with it (any case; `*` and backticks ignored), in order: an agent's milestones. A longer line is cut and ends with `…`. Built 2026-11-05 |

**Quotes:** every quote mark around the path goes (paths never contain them). Around the quote and the heading only **one matching pair** goes (`"…"`, `'…'`, `“…”`, `‘…’`), so the page's own apostrophes and quote marks stay: `"the users' files"` → `the users' files`. An unclosed double quote mark at one end is dropped; a lone apostrophe is kept.

**Example**

    for tag in find_tags(reply, ("SHOW",)):
        show = parse_show(tag.argument)   # ShowTag(path='C:\\d\\x.html', quote='Parts', heading=None)
    question = last_line(text, "NEED:")   # "Which folder?" or None

**Defined in:** `src/assistant/infra/agent_tags.py` · **Tests:** `tests/test_agent_tags.py`

## `show_page`

**Reusable** · Used by: `SessionTaskAgent` (`_show`), `talker` (its `SHOW` tag), `temp_ui` (`open_page`: the Open in viewer button)

`async show_page(ctx: ModuleContext, argument: str) -> ShowOutcome` · `async open_page(ctx, path, quote=None, heading=None, front=False) -> Result` · `from assistant.infra import show_page, open_page, ShowOutcome, NO_PAGE_VIEWER`

The one place that opens a page for the core group, through the page-opener slot ([`IPageOpener`](modules.md#ipageopener)), never a viewer's id or tools. `open_page` looks the provider up; with none on it sends [`StartProvider`](control.md#startprovider) so the core turns on the module that provides it and starts on use, then looks again; still none: `not_available` with `NO_PAGE_VIEWER` ("No page viewer is on"); a start that failed gives its error. `show_page` turns a SHOW tag's argument (`path`, or `path | "quote" | heading`) into that call. Each caller words its own messages from the outcome, and declares `IPageOpener` in `manifest.uses` and `StartProvider` in `manifest.sends` (the agent modules through [`AGENT_USES` / `AGENT_SENDS`](#agentkit)).

| Name | Does |
|------|------|
| `show_page(ctx, argument)` | Parse the argument ([`parse_show`](#agent_tags)) and open it with `open_page`; returns `ShowOutcome(show, result)` |
| `open_page(ctx, path, quote, heading, front)` | Open a page through `IPageOpener`, starting its provider on use; the `Result` of `IPageOpener.open` |
| `ShowOutcome.quote_missing` | The page opened but the quote isn't on it (`result.value["found"] is False`) |
| `NO_PAGE_VIEWER` | The error when no module provides `IPageOpener` |

**Example**

    outcome = await show_page(ctx, 'C:\\docs\\page.html | "exact words"')
    if not outcome.result.is_ok: ...
    elif outcome.quote_missing: ...

**Defined in:** `src/assistant/infra/show_pages.py` · **Tests:** `tests/test_show_pages.py`

## `PermissionGate`

**Reusable** · Used by: `SessionTaskAgent` · built 2026-11-08

`from assistant.infra import PermissionGate` · `src/assistant/infra/permission_gate.py`

A task agent's one open question to you: a tool's permission request or an app action's approval (`request_approval`, `RELOAD`, `ADD_MODULE`). `ask(action, run, always=False)` opens an approval; in Auto it runs `run` at once, unless `always` (added 2026-11-13: a reload or an add of code, which Auto never skips). Also: the answer timer (`permission_timeout`), the Auto policy (allow and log; refuse a shell command with `git push`), and an approval's outcome delivered after the turn ends. A task that ends waiting on its approval (rule 2, built 2026-11-13) leaves it here: `park(task_id)` keeps an open approval (or one whose action still runs) tied to that task and out of the next task's way; `answer_parked(task_id, allow)` answers it; its outcome goes to the `parked(task_id, text)` callback (the agent sends it to the Hub as that task's `progress`), unless `unpark(task_id)` gave the task back first; `parked` is that task's id. Helpers `describe_request`, `is_git_push`, `summarize`; the texts `CODE_LOADED`, `APPROVAL_PENDING`, `GIT_PUSH_BLOCKED`, `NO_TASK`, `TIMED_OUT`. **Tests:** `tests/test_worker_parts.py`

## `HandoffKeeper`

**Reusable** · Used by: `SessionTaskAgent` · built 2026-11-08

`from assistant.infra import HandoffKeeper` · `src/assistant/infra/handoff_keeper.py`

A task's handoffs: counts them against `max_handoffs` (`take`, `too_many`; `renew` and `answered` when you answer the question: a fresh allowance, your answer for the fresh session), the progress line, the message that starts the fresh session, the reset request and the context reminder. Texts `HANDED_OFF`, `RESET_NOW`, `CONTEXT_REMINDER`, `TOO_MANY_HANDOFFS`. **Tests:** `tests/test_worker_parts.py`

## `LastLineTags`

**Reusable** · Used by: `SessionTaskAgent` (`NEED`, `RELOAD`, `ADD_MODULE`, `HANDOFF`) · built 2026-11-08

`from assistant.infra import LastLineTags` · `src/assistant/infra/agent_tags.py`

A table of last-line prefixes to handlers (principle 20): `add(prefix, handler)`, then one lookup per turn instead of an if-chain. Adding a tag is adding an entry. **Tests:** `tests/test_worker_parts.py`

## `UsageMeter`

**Reusable** · Used by: `ClaudeSession` (`meter`), `UsageLedger` (`EVENT_FIELDS`), `session_usage` / `subagent_usage` (`event_fields`) · built 2026-11-08

`from assistant.infra.usage_meter import UsageMeter, TOKEN_KINDS, USAGE_FIELDS, EVENT_FIELDS, event_fields`

All the token counting of one session, out of `ClaudeSession`: `line(event)` takes each stream-json line, `restarted()` keeps the totals across a new process; `context_tokens`, `used` and `subagents` read it. `TokenKind` / `TOKEN_KINDS` is the one token-field map (the API usage field, the per-model field, the event field), so the three copies became one. **Tests:** `tests/test_usage_meter.py`, `tests/test_usage.py`

## `AgentKit`

**Reusable** · Used by: `main_assistant`, `job_search`, `cv`, `task_agents` · built 2026-11-08

`AgentKit(ctx)` · `from assistant.infra import AgentKit, AGENT_USES, AGENT_SENDS, AGENT_PUBLISHES, AGENT_LISTENS` · `src/assistant/infra/agent_kit.py`

What every agent module used to repeat: it provides each [`ProfileAgent`](#profileagent) as `ITaskAgent` (the Hub resets one through [`ITaskAgent.reset`](agents.md#itaskagentreset) on a `ResetRequested`, a command since 2026-11-13; the kit no longer listens for it), and hands a changed grant to the agent that holds it. Build it in the module's `init`.

| Member | Does |
|--------|------|
| `add(agent) -> ProfileAgent` | Provide it as `ITaskAgent` and keep it |
| `get(agent_id)`, `agents()` | The agents it holds |
| `async open(agent_id, config, prompt, *, subject, reason, wait=False, **kwargs)` | The start sequence: `request_access` → `ProfileAgent` → provide → start; a failed start is taken back and raised again |
| `async take_back(agent)` | Stop it (releasing its name) and withdraw it |
| `follow_grant(agent_id, config)` | The agent takes its grant live when it changes (`granted_config` → `set_access`) |
| `busy()`, `async stop()` | For the module's `busy` and `stop` |

**The declarations, named once** (principle 17): `AGENT_USES` (`IModuleDoor`, `IAgentNames`, `IPageOpener` for SHOW tags, in [`Manifest.uses`](modules.md#manifest): looked up at each call, no start order), `AGENT_SENDS` (`ReportTask`, `StartProvider`: a SHOW with no page opener on; `ReloadModule`, `AddModule`: a `RELOAD:` / `ADD_MODULE:` line once you allow its card, added 2026-11-13), `AGENT_PUBLISHES` (`AgentActivity`, `AgentStateChanged`, `SessionUsage`, `PermissionModeChanged`), `AGENT_LISTENS` (`ModuleStateChanged`; `ResetRequested` left it 2026-11-13). A module adds `PermissionChanged` when it follows grants, and `AgentNotice` to its `sends` when it sends notes (a command since 2026-11-13). `sends` and `publishes` are strict: an undeclared send is refused, an undeclared publish dropped.

    manifest = Manifest(id="job_search", provides=(ITaskAgent,), uses=AGENT_USES, sends=(*AGENT_SENDS, AgentNotice),
                        publishes=AGENT_PUBLISHES, listens=(*AGENT_LISTENS, PermissionChanged))

**Tests:** `tests/test_agent_kit.py`, `tests/test_honest_manifests.py`

## `mcp_door`

**Reusable** · Used by: the core (hosts the `DoorServer` in its [`CoreDoor`](core.md#coredoor-moduledoor)), `main_assistant`, `talker` and every `ProfileAgent` (their sessions run the relay) · built 2026-11-05

The agents' one MCP door to the module menus ([design](../architecture/modules.md#how-the-agents-reach-the-menus-one-door)). `from assistant.infra.mcp_door import ...`

| Item | Does |
|------|------|
| relay: `python -m assistant.infra.mcp_door` | A stdio MCP server `claude` starts from its `--mcp-config` (standard library only). Three fixed tools, `list_modules`, `show_menu(module_id)`, `use_item(name, args)`; each call is passed to the app over local HTTP with its caller and that caller's token (env `ASSISTANT_DOOR_URL`, `ASSISTANT_DOOR_TOKEN`, `ASSISTANT_DOOR_CALLER`; headers `x-door-token`, `x-door-caller`). If the app doesn't answer (a restart), the call returns an error and the next one tries again |
| `DoorServer(send, commands, host="127.0.0.1", port=0, token=None, core_line=None)` | The app-side endpoint, `POST /tool` with `{"tool", "arguments"}`. 403 unless `x-door-token` is `token_for(x-door-caller)` (compared in constant time), so one caller's token can't speak as another. `commands` maps `list` / `menu` / `call` to `ListModules` / `GetMenu` / `InvokeTool` (with `caller`), sent with `send` (the core router's `send`, so they are the core's own sends). `async start()` / `stop()`, `url`, `token` (the secret, for the app's run), `token_for(caller)` (an HMAC-SHA256 of the secret and the name), `mcp_config(caller)` (the relay's config, `{}` while down), `async call(tool, arguments, caller="")` |
| `TOOLS`, `TOOL_NAMES`, `READ_ONLY` | The tools' MCP specs; their names as claude sees them (`mcp__modules__list_modules`, …); the two that only read |
| `plain(value)` | A result as plain JSON data (pydantic models, dataclasses, enums) |

**Defined in:** `src/assistant/infra/mcp_door.py` · **Tests:** `tests/test_mcp_door.py` (the relay as a real process; one real-`claude` test under the `claude` marker)

The Edge window functions (`open_app_window`, `close_app_windows`) moved to [App kit](app_kit.md#window); they aren't re-exported here.
