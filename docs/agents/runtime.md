# Agent runtime

How the two agents are spawned, how each behaves on its own, and how they talk to each other, down to the classes. Back to [Agents](README.md). The contracts are on the [architecture page](../architecture/agents.md#task-agents) and the [Agents API page](../api/agents.md).

> **Status: built (2026-10-25).** Run it with `.\.venv\Scripts\python -m assistant`. Code: `src/assistant/modules/{talker,main_assistant,agent_hub,assistant_view}/` and `src/assistant/infra/{claude_session,session_agent}.py`.

## What runs

Four OS processes. The app is the only one that knows about the others; the two `claude` processes never talk to each other directly.

```mermaid
flowchart LR
    You(["<b>You</b>"])
    subgraph App["python -m assistant (terminal 1)"]
        direction TB
        Console["console_io"]
        Talker["talker"]
        Hub["agent_hub"]
        Main["main_assistant"]
        View["assistant_view"]
    end
    TC["<b>claude -p</b><br/>Talker session<br/>sonnet, no tools"]
    MC["<b>claude -p</b><br/>Main Assistant session<br/>file tools, workspace/"]
    VW["<b>Terminal 2</b><br/>viewer script<br/>(new console window)"]

    You -- types --> Console
    Console -- prints --> You
    Talker <-- "stdin / stdout<br/>JSON lines" --> TC
    Main <-- "stdin / stdout<br/>JSON lines" --> MC
    View -- "stdin pipe<br/>text lines" --> VW
    VW -- shows --> You
```

| Process | Started by | Command |
|---------|------------|---------|
| The app | You | `python -m assistant` |
| Talker session | `talker` module, in `start` | `claude -p --input-format stream-json --output-format stream-json --verbose --strict-mcp-config --model sonnet --tools "" --append-system-prompt <talker prompt>` |
| Main Assistant session | `main_assistant` module, in `start` | `claude -p … --strict-mcp-config --tools Read,Write,Edit,Glob,Grep --permission-mode acceptEdits --append-system-prompt <worker prompt>`, working directory `workspace/`. `acceptEdits` approves writes inside the working directory only; others are refused, since nobody can approve them |
| Terminal 2 | `assistant_view` module, in `start` | `python -m assistant.modules.assistant_view.viewer` in a new console window, its stdin a pipe from the app. It writes to its own window (`CONOUT$`), because its inherited stdout is terminal 1. Windows only for now |

Each command line is built by [`claude_command`](../api/infra.md#claude_command); the model, tools, permission mode, and workspace come from `[modules.talker]` and `[modules.main_assistant]` in `config/default.toml`.

## Launched from the main app

Everything below runs in one Python process, on one `asyncio` event loop (plus `console_io`'s stdin thread). The agents' `claude` processes are children of it.

```mermaid
flowchart TB
    Run(["python -m assistant"]) --> Main["<b>__main__.main()</b><br/>load_config · setup_logging"]
    Main --> AppNew["<b>App(MODULES, config)</b><br/>builds CommandRouter, EventBus, Container<br/>resolve_modules → start order<br/>LifecycleManager"]
    AppNew --> AppRun["<b>asyncio.run(app.run())</b>"]
    AppRun --> AppStart["<b>App.start()</b><br/>registers the core's own handlers<br/>(ListModules, ActivateModule, …)"]
    AppStart --> LStart["<b>LifecycleManager.start()</b>"]
    LStart --> Ctx["for each module in start order:<br/><b>_make_context</b> → a ScopedContext<br/><b>module.init(ctx)</b>"]
    Ctx --> Start["then for each: <b>module.start()</b>"]
    Start --> CS["talker, main_assistant:<br/><b>ClaudeSession.start()</b>"]
    Start --> VS["assistant_view:<br/>launch the viewer in a new console"]
    CS --> Spawn["<b>asyncio.create_subprocess_exec</b>('claude', '-p', …)<br/>stdin + stdout pipes<br/>+ a reader task on stdout"]
    Start --> Wait["App waits for ShutdownRequested<br/>(you type exit, or Ctrl+C)"]
    Wait --> Stop["<b>App.stop()</b>: cancel in-flight commands,<br/>module.stop() in reverse → ClaudeSession.close(),<br/>close the viewer, close the bus"]

    classDef new fill:#efeaf7,stroke:#6b4fa0,color:#1d1d1b
    class CS,VS,Spawn new
```

Purple: added for the agents. Outside the new modules, the only edits were two lists (`MODULES` in `__main__.py` gained the four module classes, and `modules.enabled` in `config/default.toml` switches them on and the echo module off) and `console_io` now also prints uncorrelated replies, so the Talker can speak first.

## Messaging to and from the main app

Modules never hold references to each other. Each gets a `ScopedContext`, and everything goes through the core's three parts. Only the pipes leave the process.

```mermaid
flowchart LR
    subgraph App["Main app process"]
        direction TB
        subgraph Core["Core"]
            Router["<b>CommandRouter</b><br/>one handler per command"]
            Bus["<b>EventBus</b><br/>a queue per subscriber"]
            Cont["<b>Container</b><br/>contract → providers"]
        end
        Console["console_io"]
        Talker["talker<br/>+ ClaudeSession"]
        Hub["agent_hub"]
        Main["main_assistant<br/>SessionTaskAgent + ClaudeSession"]
        View["assistant_view"]
    end
    TC["claude (Talker)"]
    MC["claude (Main Assistant)"]
    VW["Terminal 2 viewer"]

    Talker -- "send: StartTask, SendToTask, …" --> Router
    Main -- "send: ReportTask" --> Router
    Router -- "runs handler" --> Hub
    Console -- "publish: InputReceived" --> Bus
    Talker -- "publish: ResponseReady" --> Bus
    Hub -- "publish: TaskUpdated" --> Bus
    Main -- "publish: AgentActivity, AgentStateChanged" --> Bus
    Bus -- "deliver" --> Console
    Bus -- "deliver" --> Talker
    Bus -- "deliver" --> View
    Main -- "provide ITaskAgent" --> Cont
    Hub -- "get_all(ITaskAgent),<br/>then calls it directly" --> Cont
    Talker <-- "JSON lines" --> TC
    Main <-- "JSON lines" --> MC
    View -- "text lines" --> VW
```

| Path | How it works | Waits? | Can be lost? | Used for |
|------|--------------|--------|--------------|----------|
| **Command** | `ctx.send(cmd)` → `CommandRouter.send` runs the one handler as its own task and returns its `Result`. Timeout from config (default 30 s) | The sender waits for the `Result` | No: always a `Result` (`ok`, `timed_out`, …) | Talker → Hub, agent → Hub (`ReportTask`) |
| **Event** | `ctx.publish(ev)` → `EventBus` puts it on each subscriber's queue; each subscriber has a worker running its handler, in order, 10 s limit | No, returns at once | Yes, if a subscriber's queue (100) is full | You → Talker, Talker → you, Hub → Talker, agent → terminal 2 |
| **Contract call** | `ctx.get_all(ITaskAgent)` → `Container` → a plain Python method call on the provider (`SessionTaskAgent`) | The Hub awaits the method, which returns at once | No | Hub → agent |
| **Session pipe** | `ClaudeSession` writes one JSON line to the child's stdin; its reader task reads stdout lines and calls `on_event` for each | Writing doesn't wait for a reply | Only if the process dies | Module ↔ its `claude` |
| **Viewer pipe** | `assistant_view` writes text lines to the viewer's stdin | No | If the window was closed | Terminal 2 |

Since each command handler runs as its own task, the Hub can handle a `ReportTask` while it's still inside a `SendToTask`. That's why the agent may report while the Hub is calling it.

### A message there and back, through the core

You ask for work; the Main Assistant finishes; the Talker tells you. Every hop shown:

```mermaid
sequenceDiagram
    participant C as console_io
    participant B as EventBus
    participant T as talker
    participant TC as claude (Talker)
    participant R as CommandRouter
    participant H as agent_hub
    participant K as Container
    participant A as SessionTaskAgent
    participant MC as claude (Main)

    C->>B: publish InputReceived
    B->>T: deliver → put in inbox, return
    T->>TC: stdin: user message
    TC-->>T: stdout: assistant text … result
    T->>B: publish ResponseReady ("On it")
    B->>C: deliver → print
    T->>R: send StartTask
    R->>H: run handler
    H->>K: get_all(ITaskAgent)
    K-->>H: [SessionTaskAgent]
    H->>A: assign(task)
    A->>MC: stdin: "New task: …"
    A-->>H: ok
    H-->>R: ok(task_id)
    R-->>T: Result ok(task_id)
    Note over MC: works: tool calls, notes
    MC-->>A: stdout: … result
    A->>R: send ReportTask(done)
    R->>H: run handler: state → done
    H->>B: publish TaskUpdated(done)
    H-->>R: ok
    R-->>A: Result ok
    B->>T: deliver → put in inbox, return
    T->>TC: stdin: "[Task update: done] …"
    TC-->>T: stdout: … result
    T->>B: publish ResponseReady ("Done!")
    B->>C: deliver → print
```

## Spawning

The core's lifecycle manager starts the modules in dependency order. Nothing else launches anything: each module starts its own process in `start` and ends it in `stop`.

```mermaid
sequenceDiagram
    participant L as Lifecycle (core)
    participant C as console_io
    participant M as main_assistant
    participant H as agent_hub
    participant T as talker
    participant V as assistant_view

    Note over L: init, in dependency order
    L->>C: init: subscribe ResponseReady
    L->>M: init: build ClaudeSession + SessionTaskAgent, provide ITaskAgent
    L->>H: init: handle StartTask, SendToTask, CancelTask, GetTaskStatus, ReportTask, ListAgents
    L->>T: init: build ClaudeSession, subscribe InputReceived + TaskUpdated
    L->>V: init: subscribe AgentActivity, AgentStateChanged, TaskUpdated

    Note over L: start, same order
    L->>C: start: read terminal 1
    L->>M: start: launch its claude (instant, ~6 s until it can first reply)
    L->>H: start: nothing to launch
    L->>T: start: launch its claude (kept warm), start its inbox loop
    L->>V: start: open terminal 2
```

- **Order:** `main_assistant` provides `ITaskAgent` and the Hub lists it as optional, so the agent starts before the Hub. `talker` and `assistant_view` depend on nothing; they only send commands and listen to events. The diagram shows one valid order; the actual one is `console_io, main_assistant, talker, assistant_view, agent_hub`.
- **Stop** runs in reverse, so the Hub stops first: reports an agent sends while shutting down are refused (logged as warnings, harmless). Each session closes its `claude` process: stdin closed, then killed if it hasn't exited within the stop timeout. Terminal 2 is closed.
- **Runtime control:** deactivating `main_assistant` ends its process; the Hub sees no agents and `StartTask` returns `not_available`. Activating it again starts a fresh session (no memory of before).

## Classes

```mermaid
classDiagram
    direction LR
    class ClaudeSession {
        <<infra>>
        +start()
        +send(text)
        +interrupt()
        +close()
        +running bool
        +working bool
        +on_event(dict)
    }
    class ITaskAgent {
        <<contract>>
        +info() AgentInfo
        +assign(task) Result
        +message(task_id, text, resume) Result
        +cancel(task_id) Result
    }
    class SessionTaskAgent {
        <<infra>>
        task, mode
    }
    class MainAssistantModule { <<module>> }
    class TalkerModule {
        <<module>>
        inbox: Queue
        current_task_id
    }
    class AgentHubModule {
        <<module>>
        tasks: dict
    }
    class AssistantViewModule { <<module>> }

    SessionTaskAgent --|> ITaskAgent
    SessionTaskAgent --> ClaudeSession : uses
    MainAssistantModule --> SessionTaskAgent : provides as ITaskAgent
    MainAssistantModule --> ClaudeSession : creates, closes
    TalkerModule --> ClaudeSession : creates, closes
    AgentHubModule ..> ITaskAgent : get_all()
```

The core's lifecycle manager starts all of these modules, and none of them launches another. In the diagram, the arrow with a hollow head means "implements", a plain arrow means "holds and uses", and the dotted arrow means "looks up through the Container".

`ClaudeSession` runs one `claude` process. It knows nothing about tasks or the Talker: it writes messages and interrupts, calls `on_event` for every JSON line, and sets `working` from "message sent" until `result`. `SessionTaskAgent` lives in `infra` too, not in the `main_assistant` module, so a later subagent module can reuse it without importing another module's internals ([principle 3](../architecture/principles.md)).

The Talker and the Main Assistant are both LLM agents. Each has its own `ClaudeSession`, so each runs its own `claude` process with its own model, prompt, and tools. What differs is their role, and the diagram shows it by which one implements `ITaskAgent`:

- `MainAssistantModule` is the worker. In `init` it builds a `ClaudeSession` and a `SessionTaskAgent`, and registers the agent with the Container as an `ITaskAgent`. `SessionTaskAgent` turns the Hub's calls (`assign`, `message`, `cancel`) into messages for its session, and the session's results into reports.
- `TalkerModule` talks with you and takes no tasks, so it doesn't implement `ITaskAgent`. When something needs doing, it hands the task to the Hub with a command (`StartTask`, `SendToTask`, …) and hears back through `TaskUpdated` events. Commands and events travel through the core, so they aren't drawn here; they're in [Messaging to and from the main app](#messaging-to-and-from-the-main-app).
- `AgentHubModule` holds no reference to any agent module. It asks the Container for every `ITaskAgent` and calls the ones it gets back. A future subagent is one more module that provides `ITaskAgent`, and the Hub finds it without any change.
- `AssistantViewModule` only listens to events, so it has no arrows.

## The Talker on its own

The Talker is a conversation loop with one **inbox**. Everything that should make it speak goes into the inbox, and it handles one item at a time, one `claude` turn each. So it never talks over itself, and the event handlers return at once (no 10 s handler timeout).

| Inbox item | Comes from | Sent to its session as |
|------------|------------|------------------------|
| You said something | `InputReceived` | your text, as is |
| Task update: `done`, `need`, `reply`, `failed` | `TaskUpdated` | `[Task update: done] <text>` |
| Command result worth telling | its own tags (e.g. `StartTask` refused, `GetTaskStatus`) | `[Status] <text>` |

`progress` updates don't go to the inbox: they'd make it chatter. The Hub keeps them and they come back when you ask "how's it going?".

```mermaid
flowchart TB
    Wait["Wait for the next inbox item"] --> Send["Send it to the Talker session"]
    Send --> Reply["Turn ends (result)"]
    Reply --> Split["Split the reply: text and tags"]
    Split --> Print["Publish the text as ResponseReady<br/>(correlated if it answers your input)"]
    Split --> Tags["Run each tag as a Hub command"]
    Tags -- "result to tell (LOOK, refused)" --> Queue["Put [Status] item in the inbox"]
    Print --> Wait
    Queue --> Wait
```

**Tags** (v1: one task at a time, so no task ids; the Talker module remembers the current task):

| Tag | Hub command |
|-----|-------------|
| `<<WORK: task>>` | `StartTask(task, context)`, context = the last few exchanges |
| `<<LOOK>>` | `GetTaskStatus()`; the result comes back as a `[Status]` item |
| `<<ASK: text>>` | `SendToTask(text, resume=true)`: a question, extra instruction, or your answer to a NEED |
| `<<PAUSE: text>>` | `SendToTask(text, resume=false)` |
| `<<CANCEL>>` | `CancelTask()` |

**Talker prompt, in short:** you're the voice of a personal assistant; keep replies short and conversational; you can't do work yourself, so hand anything substantial over with `WORK`; never claim work is done until a `[Task update: done]` arrives; infer from context whether the user means continue, pause, or cancel, and never ask them for keywords.

## The Main Assistant on its own

`SessionTaskAgent` turns `ITaskAgent` calls into session messages and session events into reports. It keeps an internal **mode**; the Hub's `TaskState` is the outside view of the same thing.

```mermaid
stateDiagram-v2
    [*] --> idle
    idle --> working: assign → send task
    working --> idle: result, no NEED → report done
    working --> idle: result is an error we didn't cause → report failed
    working --> waiting: result ends with NEED → report need
    working --> interrupting: message() or cancel()
    interrupting --> replying: interrupted result (message) → send wrapped message
    interrupting --> idle: interrupted result (cancel)
    replying --> working: result → report reply, then send "continue" (resume)
    replying --> paused: result → report reply (no resume)
    waiting --> working: message() → send your answer
    paused --> working: message(resume) → send it
    waiting --> idle: cancel()
    paused --> idle: cancel()
```

- **Interrupt isn't failure:** in `interrupting` the agent knows it caused the `error_during_execution` result ([spike finding](spike.md#findings)) and doesn't report `failed`.
- **`message` and `cancel` return as soon as the interrupt is sent**; the rest happens as events arrive. So the Hub never waits on the agent while the agent is reporting to the Hub.
- **Cancel fallback:** if no `result` arrives within a few seconds of the interrupt, close the process; the next task starts a fresh session.
- **Reports and events while working:**
  - every `assistant` text or tool call → `AgentActivity` (terminal 2)
  - a text note mid-turn → `ReportTask(progress)`
  - `working` / `busy` changes → `AgentStateChanged`

**Worker prompt, in short:** you're the Main Assistant doing tasks handed to you; work only in your folder; before each major step write one short progress line; if you need a decision from the user, stop and end your turn with a last line `NEED: <question>`; when finished, end with a short summary of what you did.

**Messages it sends to its session:**

| When | Text |
|------|------|
| New task | `New task: <text>` plus `Context: <context>` |
| Mid-task message | `[The user interrupted your task with a message. Answer it briefly; you'll be told when to continue.] <text>` |
| Continue | `Continue the task from where you left off.` |
| Answer to NEED, or resume from pause | the text as is |

## Talking to each other: a whole conversation

```mermaid
sequenceDiagram
    actor You
    participant C as console_io
    participant T as talker
    participant H as agent_hub
    participant M as main_assistant
    participant V as Terminal 2

    You->>C: "Write three poems about Seoul into poems.txt"
    C->>T: InputReceived
    Note over T: turn: reply + WORK tag
    T->>C: ResponseReady "On it, I'll have the assistant do that."
    T->>H: StartTask
    H->>M: assign(task)
    M-->>H: ok (returns at once)
    H-->>T: ok(task_id)
    M-->>V: AgentStateChanged(busy, working)
    loop while it works
        M-->>V: AgentActivity (text, tool calls)
        M->>H: ReportTask(progress)
    end
    You->>C: "Tell me a joke meanwhile"
    C->>T: InputReceived
    T->>C: ResponseReady (joke)
    M->>H: ReportTask(need, "Modern or traditional style?")
    H-->>T: TaskUpdated(need)
    Note over T: inbox: [Task update: need] → turn
    T->>C: ResponseReady "Quick question: modern or traditional?"
    You->>C: "Modern"
    C->>T: InputReceived
    Note over T: turn: ASK tag "modern"
    T->>H: SendToTask("modern", resume)
    H->>M: message → send answer (it was waiting, no interrupt)
    M->>H: ReportTask(done, "Wrote 3 poems to poems.txt")
    H-->>T: TaskUpdated(done)
    T->>C: ResponseReady "Done: three poems are in poems.txt."
    M-->>V: AgentStateChanged(idle)
```

The mid-task question flow (interrupt → reply → continue) is on the [architecture page](../architecture/agents.md#messages-and-cancel).

## Rules that keep it from locking up

- **Nobody waits on a `claude` turn inside a handler.** Event handlers queue; `assign`, `message` and `cancel` return once their message or interrupt is written.
- **The Hub is the only one that changes task state**, and only from commands (`StartTask`, `SendToTask`, `CancelTask`, `ReportTask`), so dropped events never corrupt it.
- **One turn at a time per session.** The Talker's inbox and the agent's mode guarantee nothing is written to a session mid-turn except an interrupt.
- **The Talker waits on nobody:** while the Main Assistant works, waits for you, or is paused, the Talker keeps chatting.
