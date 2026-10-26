# Infrastructure

Shared services. All items: `from assistant.infra import ...`. Back to the [API index](README.md).

## `load_config`

`load_config(config_dir: str | Path | None = None) -> dict[str, Any]`

Load `default.toml`, then deep-merge `local.toml` over it if it exists. Tables merge key by key; other values (including lists) are replaced.

**Parameters**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `config_dir` | `str \| Path \| None` | no | Directory holding the files. Defaults to `ASSISTANT_CONFIG_DIR`, then `./config` |

**Returns:** the merged config as nested dicts.

**Raises:** `FileNotFoundError` if `default.toml` is missing; `tomllib.TOMLDecodeError` for invalid TOML.

**Defined in:** `src/assistant/infra/config.py`
**See also:** [configuration keys](../architecture/core.md#configuration)

## `setup_logging`

`setup_logging(settings: dict[str, Any]) -> None`

Configure root logging from the `[logging]` config section. Replaces any existing configuration.

**Settings**
| Key | Default | Description |
|-----|---------|-------------|
| `level` | `"INFO"` | Standard level name |
| `file` | none | Log file path; parent directories are created |
| `stderr` | `false` | Also log to the terminal. Keep off while `console_io` is enabled |

With neither `file` nor `stderr`, logs are discarded.

**Defined in:** `src/assistant/infra/log.py`

## `ClaudeSession`

`ClaudeSession(command: Sequence[str], cwd: str | Path | None = None, log: Logger | None = None, on_event: Callable[[dict], None] | None = None)`

One long-lived `claude -p` stream-json process. Knows nothing about tasks or agents: it writes messages and interrupts as JSON lines on stdin and hands every JSON line from stdout to `on_event`, in order. Build `command` with [`claude_command`](#claude_command).

| Member | Does |
|--------|------|
| `async start()` | Launch the process (no-op if running). Raises `FileNotFoundError` if `claude` isn't installed |
| `async send(text)` | Send a user message, starting a turn. Raises `RuntimeError` if not running |
| `async interrupt()` | Interrupt the turn, like Esc. The turn still ends with a `result` (`is_error: true`) |
| `async close(timeout=3.0)` | Close stdin, wait, kill if it doesn't exit. `start` works again afterwards |
| `running: bool` | The process is alive |
| `working: bool` | From `send` until the turn's `result` |
| `on_event` | Settable callback. Also gets `{"type": "exit", "returncode": n}` if the process ends on its own |

**Example**

    session = ClaudeSession(claude_command(model="sonnet"), on_event=print)
    await session.start()
    await session.send("Hello")

**Defined in:** `src/assistant/infra/claude_session.py`

## `claude_command`

`claude_command(*, model: str | None = None, tools: str = "", permission_mode: str | None = None, system_prompt: str | None = None, program: Sequence[str] = ("claude",)) -> list[str]`

The command line for a stream-json `claude -p` session. Always adds `--strict-mcp-config` (otherwise your claude.ai MCP connectors load). `tools=""` means no tools; `system_prompt` goes in as `--append-system-prompt`. `program` is replaceable so tests can run a fake.

**Defined in:** `src/assistant/infra/claude_session.py`

## `SessionTaskAgent`

`SessionTaskAgent(session: ClaudeSession, ctx: ModuleContext, agent_id: str, description: str, capabilities: tuple[str, ...] = (), cancel_timeout: float = 5.0)`

An [`ITaskAgent`](agents.md#itaskagent) backed by one `ClaudeSession`: the shared part every task agent is built from. Turns `assign`, `message`, and `cancel` into session messages, and the session's events into [`ReportTask`](agents.md#reporttask), [`AgentActivity`](agents.md#agentactivity), and [`AgentStateChanged`](agents.md#agentstatechanged). Sets itself as the session's `on_event`. Every method returns once its message or interrupt is written. A turn whose last line is `NEED: <question>` is reported as `need`. If a cancel's interrupt doesn't end the turn within `cancel_timeout`, the session is closed and the next task starts a fresh one. Behavior: [The Main Assistant on its own](../agents/runtime.md#the-main-assistant-on-its-own).

| Method | Does |
|--------|------|
| `async close()` | Stop its background tasks. The owning module closes the session itself |

**Example:** see [`ITaskAgent`](agents.md#itaskagent).

**Defined in:** `src/assistant/infra/session_agent.py`
