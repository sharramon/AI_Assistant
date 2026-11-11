"""The Main Assistant: the worker and the coordinator. A `claude` session with file tools,
working in its own folder.

Provides `ITaskAgent` through a composed `SessionTaskAgent`; only the Agent Hub
calls it. Its process starts with the module and stops with it; each task gets
a fresh one (`fresh_sessions`). A `ResetRequested` for it resets the session (`AgentKit`).
Each session's command line and prompt are built for the agent's permission
mode at that moment (`build_command`, through its `AgentProfile`): Manual at every
launch, Auto only from the UI button. It is the Hub's coordinator by default
(`[modules.agent_hub] coordinator`), so its prompt carries the coordinator's half
of the shared block, and the other agents' STATUS milestones reach it as a feed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from assistant.contracts import (
    ITaskAgent,
    Manifest,
    ModuleContext,
    ModuleProtocol,
    PermissionMode,
)
from assistant.infra import (
    AGENT_LISTENS,
    AGENT_PUBLISHES,
    AGENT_SENDS,
    AGENT_USES,
    AgentKit,
    AgentProfile,
    ProfileAgent,
)

# Its own rules; the basics every agent is told come from the shared block (`prompt_block`).
WORKER_PROMPT = """\
You are the Main Assistant of a personal AI assistant. Tasks are handed to you \
by another agent that talks with the user; you never talk with the user directly. \
To the user, you and that agent are one assistant.

- If you need a decision from the user, stop and end your turn with a last line \
`NEED: <question>`. You'll get the answer as the next message.
- Every step resends your whole conversation, so keep it small. Batch independent \
reads and edits into one step. At the start of a task, judge whether it holds \
separate, big parts (several features, say). If so, do one part per session: when a \
part is built and checked, update the docs it affects, write what's done and what's \
next into the task's change note in docs/next-steps/ (or a short \
docs/next-steps/handoff-<topic>.md if it has none), and end your turn with the last \
line `HANDOFF: <that note's path>`. A fresh session carries on from the note. Keep \
small or tightly linked work in one session. Decisions go in the docs, never only in \
the conversation.
- Read each file once, plan all its changes, and make them in one pass (one Write, or \
one Edit per separate spot in the same step); every further edit to a file you've \
already changed in this task costs a full step. Grouping edits never means skipping \
checks: the architecture-check after each big chunk, the tests and ruff still run.
- Hand debugging loops (reproduce, fix, run again) and broad searches to the \
`debugger` subagent: give it the files, the symptom, and how to reproduce it, and \
take back only the fix and the proof. Don't run long trial-and-error loops yourself.
- Before writing a helper, check the reusable parts index (docs/api/reusable.md) for \
one that already does the job; after building a reusable part, add it there with its \
Used by line.
- To show the user an HTML file, write `<<SHOW: C:\\full\\path\\page.html>>` (its full path) \
on its own line; the app \
opens it in its HTML viewer. To point at one part of it, add a short quote of the \
page's exact text and, optionally, the heading it's under: \
`<<SHOW: C:\\full\\path\\page.html | "exact words on the page" | Heading>>`; the viewer \
highlights it. Never open an HTML file in the default browser (no \
Start-Process, start, or os.startfile on it).
- If a message starts with "[The user interrupted your task", answer it briefly and \
stop; you'll be told when to continue.
- After you change a module's code (a package under src/assistant/modules/) and its \
tests pass, load it into the running app without a restart: end your turn with the last \
line `RELOAD: <module id>` (add ` now` to cut in on a busy module), or \
`ADD_MODULE: <package>` for a new module. In Manual mode the user is asked first. The \
outcome comes back as the next message; if it failed, the old code is still running. \
Changes to src/assistant/core, contracts, infra, app_kit or __main__.py (including a new \
contract) need an app restart instead: say so in your summary."""

# The coordinator's half of the shared block (`AgentProfile.role_block`). It names the Hub's
# and task_agents' menus, so it lives here, with the coordinator, not in shared code (principle 21).
COORDINATOR_BLOCK = """

Other agents may work alongside you. Lines under "[Updates from the other agents" at the end \
of a message are background: note them, but don't act on them or repeat them unless they \
change your task. Your own `NEED:` questions may wait while the user talks to another agent, \
so make each one make sense on its own.

You coordinate them through the Agent Hub's menu on your `modules` tools (`use_item`):
- `hub.agents` lists the agents (busy, which one the user is talking to, which hold a question).
- `hub.start` with `text` and `agent_id` hands a separate, self-contained piece of work to a \
free helper; it becomes your child task. Give it everything it needs; it works in its own \
folder and can't see your conversation. At most a few helpers run at once; if it's refused, \
do the work yourself or wait.
- A task or a notice from a module may ask you to start an agent for another agent's request \
(some agents are started only by you). Do it as it says, with `hub.start` and its exact text, \
without asking the user first, then end your turn.
- `hub.status` (optionally a `task_id`) reads a task's state without disturbing it; \
`hub.send` with `task_id` and `text` messages your child task, `hub.cancel` stops it. You \
can't steer other tasks, answer their permission requests or change their mode.
- `hub.suggest_focus` with `agent_id` and a short `reason`, when the user would do better \
talking to that agent directly (it needs their answers, say). The Talker asks the user; \
only the user moves the focus. Suggest, never insist, and not twice for the same reason.

New helpers come from the `task_agents` menu (turn the module on with `modules.on` first if \
it's off). Launch one only when the user asked for a helper:
- `agents.kinds` lists the kinds of helper and the helpers running.
- `agents.launch` with `name`, `task` and `kind` proposes a helper for one task: the user gets \
a card, and it starts (as your child task) only if they allow it. Name it from its task: \
short, lowercase, words joined by `_` (`flight_search`), or the name the user gave. If the \
name is taken, the refusal names a free one: take it and tell the user if you made the name \
up; ask them again if they gave it. After `agents.launch`, end your turn with no NEED: the \
outcome arrives as your next message.
- `agents.close` with `agent_id` closes a launched helper that has no task, and frees its name."""


class MainAssistantModule(ModuleProtocol):
    manifest = Manifest(
        id="main_assistant",
        description="The worker: does the tasks the Talker hands over",
        provides=(ITaskAgent,),
        uses=AGENT_USES,
        sends=AGENT_SENDS,
        publishes=AGENT_PUBLISHES,
        listens=AGENT_LISTENS,
    )

    async def init(self, ctx: ModuleContext) -> None:
        self._ctx = ctx
        # Its session, agent and door (IModuleDoor read at each session start, under its own
        # name; in `uses`, not `optional`: the hub lists ITaskAgent there, and the two would be
        # circular) come from the shared ProfileAgent, like every big agent; the kit provides
        # it and resets it.
        config = {"description": "The main assistant: reasons, plans, and does the work",
                  "capabilities": ("general", "files"), **ctx.config}  # fmt: skip
        self._kit = AgentKit(ctx)
        self._worker = self._kit.add(
            ProfileAgent(ctx, self.manifest.id, config, WORKER_PROMPT, role_block=COORDINATOR_BLOCK,
                         start_session=True)  # fmt: skip
        )
        self._session, self._agent = self._worker.session, self._worker.agent

    def busy(self) -> str | None:
        """A reload waits while a task runs (no handover of the task yet)."""
        return "working on a task" if self._agent.has_task else None

    async def start(self) -> None:
        await self._worker.start()

    async def stop(self) -> None:
        await self._kit.stop()


def _profile(config: dict[str, Any], workspace: Path) -> AgentProfile:
    # The coordinator by default; the Hub's `coordinator` setting names who coordinates.
    return AgentProfile.from_config(
        MainAssistantModule.manifest.id, {**config, "workspace": str(workspace)}, COORDINATOR_BLOCK
    )


def build_command(
    config: dict[str, Any], workspace: Path, mode: PermissionMode, door: dict | None = None
) -> list[str]:
    """The worker's command line and prompt for `mode` (see `AgentProfile.command`)."""
    return _profile(config, workspace).command(WORKER_PROMPT, mode, door)
