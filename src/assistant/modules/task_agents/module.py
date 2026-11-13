"""Helper agents beside the Main Assistant, from kinds of helper in config.

A *kind* is one section under `[modules.task_agents.agents.<kind>]` (its prompt, access and
workspace); the keys at the module's top level (besides `agents`) are defaults for every kind.
Each helper is a `ProfileAgent` (an `AgentProfile` + `ClaudeSession` + `SessionTaskAgent`)
provided as `ITaskAgent`, so the Agent Hub lists it, starts its tasks, holds its questions
behind its tab's **!**, and feeds its `STATUS:` lines to the coordinator. Each helper's session
uses the module door under its own id, and claims that id from the Hub (`IAgentNames`).

Helpers are launched by name for one task: `agents.launch(name, task, kind)` from an agent with
an open task (the Main Assistant). It only *proposes*: the caller puts it to you with the
permission card (`ITaskAgent.request_approval`), and on Allow the helper is built in
`<kind workspace>/<name>` and its task starts as the caller's child (`StartTask`, so the
Hub's cap and folder-clash check apply). `agents.close` takes back an idle launched helper.
Launched helpers end with the module (a reload waits while one has a task).

You can open one yourself (the temp UI's **+**, caller `temp_ui`): your click is the yes, so no
approval card and no open task are needed, and the task is optional. The name and kind are
checked at once; the rest (the kind's access card, the build) runs in the background, so the
call returns before the card is answered. With no task the helper opens idle (your first
message to its tab starts one); with a task it starts as your own task, with no parent.
`agents.kinds` gives a free name per kind for the form.

A kind with `autostart = true` starts at launch: `instances = N` gives `<kind>`, `<kind>_2`, ...,
each writing its own sub-folder `<workspace>/<id>` and reading the rest.

Access is asked for per kind (`request_access`, subject = the kind), so every copy and every
launched helper of a kind shares one grant: autostart kinds when the module is turned on, a
launched helper's kind when it launches (the card waits inside the approved run).

A big agent that comes with code of its own (a menu, background workers) is bundled with its own
module instead, built on the same `ProfileAgent` (see the multi-agent note's decision).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from assistant.contracts import (
    AccessDenied,
    AccessItem,
    AccessPending,
    AgentStateChanged,
    GetTaskStatus,
    IAgentNames,
    ITaskAgent,
    Manifest,
    Menu,
    ModuleContext,
    ModuleProtocol,
    PermissionChanged,
    Result,
    StartTask,
)
from assistant.infra import (
    AGENT_LISTENS,
    AGENT_PUBLISHES,
    AGENT_SENDS,
    AGENT_USES,
    AgentKit,
    ProfileAgent,
    check_agent_id,
    free_agent_id,
    granted_config,
    request_access,
    watch_grant,
)

HELPER_PROMPT = """\
You are {agent_id}, a helper agent of a personal AI assistant. {role}

- Tasks reach you through the assistant; when the user turns to you, their words reach you \
unchanged. You never talk with the user in the main chat.
- Keep your conversation small: batch independent reads and edits into one step."""

TALKER = "talker"
NO_TASK = ("agents.launch needs the caller's open task to ask the user on; "
           "hand it to the Main Assistant, which asks them with a card")  # fmt: skip
# The callers that are you clicking. For now the same list as the permissions handler's `you`;
# later `ctx.permissions.is_you(caller)`, so the rule lives in one place (plus-agent-tab note).
YOU = ("temp_ui",)
# Callers this menu trusts more than an agent: no helper may take their names (it would get
# their rights here). The Hub's `IAgentNames` reserves more when it's on.
TRUSTED_CALLERS = frozenset({TALKER, *YOU})

menu = Menu()


class TaskAgentsModule(ModuleProtocol):
    manifest = Manifest(
        id="task_agents",
        description="Helper agents launched by name from kinds in config, each a task agent the Hub can start and focus",
        provides=(ITaskAgent,),
        uses=(*AGENT_USES, ITaskAgent,),  # the asking agent, found among every module's agents
        sends=(*AGENT_SENDS, StartTask, GetTaskStatus,),
        publishes=AGENT_PUBLISHES,  # AgentStateChanged with change "opened" / "closed" for a helper
        listens=(*AGENT_LISTENS, PermissionChanged,),
        permissions=("agent.access",),
    )
    menu = menu

    async def init(self, ctx: ModuleContext) -> None:
        self._ctx = ctx
        self._kinds = kind_configs(ctx.config)
        agent_configs(ctx.config)  # check the autostart ids now: a bad one fails the turn-on
        self._agents: dict[str, ProfileAgent] = {}  # autostarted at launch
        self._kind_of: dict[str, str] = {}  # autostarted id -> its kind
        self._launched: dict[str, tuple[str, ProfileAgent]] = {}  # name -> (kind, agent)
        self._opening: dict[str, asyncio.Task[Result]] = {}  # name -> your open, in the background
        if not self._kinds:
            ctx.log.info("No kinds of helper under [modules.task_agents.agents]")
        self._kit = AgentKit(ctx)  # provides, resets, takes back and stops every helper here
        watch_grant(ctx, self._on_grant)  # every kind: subject = the kind

    async def start(self) -> None:
        """Ask for each autostart kind's access list (grants are per kind: `helper_2` shares
        `helper`'s). Every card opens at once; while any waits, this start ends with
        `AccessPending` and your Allow turns the module on. Then build the helpers from what
        you allowed."""
        granted: dict[str, dict[str, Any]] = {}
        pending: list[str] = []
        for kind, config in self._kinds.items():
            if not config.get("autostart"):
                continue
            try:
                granted[kind] = await request_access(self._ctx, config, own_folder=False, subject=kind, reason=f"autostart {kind}")
            except AccessPending as exc:
                pending.append(str(exc))
        if pending:
            raise AccessPending("; ".join(pending))
        for kind, config in granted.items():
            for agent_id, own in instances(kind, config).items():
                agent = self._kit.add(self._build(agent_id, kind, own))
                self._agents[agent_id] = agent
                self._kind_of[agent_id] = kind
        for agent in self._agents.values():
            await agent.start()

    async def stop(self) -> None:
        for job in list(self._opening.values()):
            job.cancel()
        await asyncio.gather(*self._opening.values(), return_exceptions=True)
        await self._kit.stop()
        self._launched.clear()

    def busy(self) -> str | None:
        """A reload restarts every helper here, so it waits while any of them has a task."""
        agents = [*self._agents.values(), *(a for _, a in self._launched.values())]
        reasons = [f"opening {name}" for name in self._opening] + [r for a in agents if (r := a.busy())]
        return "; ".join(reasons) or None

    # --- the menu ---

    @menu.item("agents.kinds", "The kinds of helper you can launch (each with a free name), and the helpers running")
    async def kinds_item(self, caller: str = "") -> Result:
        names = self._ctx.get_one(IAgentNames)
        taken = {*(names.taken() if names else ()), *self._agents, *self._launched, *self._opening}
        kinds = [{"kind": k, "description": str(c.get("description", "")), "free_name": free_agent_id(k, taken)}
                 for k, c in self._kinds.items()]  # fmt: skip
        running = [{"agent_id": a, "kind": None, "launched": False} for a in self._agents]
        running += [{"agent_id": n, "kind": k, "launched": True} for n, (k, _) in self._launched.items()]
        return Result.ok({"kinds": kinds, "running": running})

    @menu.item("agents.launch", "Propose a new helper for one task: the user gets a card, and it starts as your "
               "child task only if they allow it. End your turn after; the outcome is your next message",
               {"name": {"type": "string", "minLength": 1}, "task": {"type": "string"},
                "kind": {"type": "string"}}, required=["name"])  # fmt: skip
    async def launch_item(self, name: str, task: str = "", kind: str = "helper", caller: str = "") -> Result:
        if kind not in self._kinds:
            return Result.invalid_arguments(f"No kind of helper {kind!r}; kinds: {', '.join(self._kinds) or 'none'}")
        if name in self._opening:
            return Result.invalid_arguments(f"`{name}` is already opening")
        names = self._ctx.get_one(IAgentNames)
        reason = (await names.check(name, self.manifest.id) if names
                  else check_agent_id(name, reserved=TRUSTED_CALLERS))  # fmt: skip
        if reason:
            return Result.invalid_arguments(reason)
        if caller in YOU:
            return self._open_for_you(name, kind, task.strip())
        if not task.strip():
            return Result.invalid_arguments("agents.launch needs the helper's task")
        parent = await self._open_task_of(caller) if caller and caller != TALKER else None
        asker = self._agent_of(caller) if parent else None
        if parent is None or asker is None:
            return Result.not_available(NO_TASK)

        async def run() -> Result:
            return await self._launch(name, kind, task, parent)

        action = f"Launch a new helper `{name}` ({kind}) for: {task}"
        asked = await asker.request_approval(action, run)
        if not asked.is_ok:
            return asked
        return Result.ok(f"Asked the user to allow {name}. End your turn now; the outcome is your next message.")

    @menu.item("agents.close", "Close a launched helper that has no task, and free its name",
               {"agent_id": {"type": "string", "minLength": 1}}, required=["agent_id"])  # fmt: skip
    async def close_item(self, agent_id: str, caller: str = "") -> Result:
        entry = self._launched.get(agent_id)
        if entry is None:
            return Result.invalid_arguments(f"{agent_id!r} isn't a launched helper")
        agent = entry[1]
        if reason := agent.busy():
            return Result.not_available(reason)
        del self._launched[agent_id]
        await self._take_back(agent)
        # Like a launch, say so: the Talker closes its tab's session, UIs drop its tab, usage marks it closed.
        self._ctx.publish(AgentStateChanged(agent_id=agent_id, change="closed"))
        self._ctx.log.info("Closed helper %s", agent_id)
        return Result.ok(f"{agent_id} closed")

    # --- launching ---

    def _open_for_you(self, name: str, kind: str, task: str) -> Result:
        """Your own open (the temp UI's +): no card for the launch, and it runs in the
        background, so this call returns while the kind's access card may still wait."""

        async def run() -> Result:
            try:
                outcome = await self._launch(name, kind, task or None, None)
            except Exception as exc:  # noqa: BLE001 - nobody awaits this job: say it in the log
                outcome = Result.failed(f"{name} couldn't open: {exc}")
            finally:
                self._opening.pop(name, None)
            log = self._ctx.log.info if outcome.is_ok else self._ctx.log.warning
            log("Your helper %s (%s): %s", name, kind, outcome.value if outcome.is_ok else outcome.error)
            return outcome

        self._opening[name] = asyncio.create_task(run())
        return Result.ok(f"Opening {name} ({kind}); its access card shows if the kind has no saved grant")

    async def _launch(self, name: str, kind: str, task: str | None, parent_task_id: str | None) -> Result:
        """Ask for `kind`'s access list (waits on your card unless its saved grant matches),
        build helper `name` from what you allowed, claim its name, and start `task` on it (as
        `parent_task_id`'s child, or your own task with none). With no task it stays idle."""
        if name in self._agents or name in self._launched:  # our own claim would repeat, and pass
            return Result.failed(f"{name} is already one of this module's helpers")
        try:
            base = await request_access(self._ctx, self._kinds[kind], own_folder=False, subject=kind, reason=f"launch {name}", wait=True)
        except AccessDenied as exc:
            return Result.failed(f"{name} wasn't launched: {exc}")
        agent = self._kit.add(self._build(name, kind, launched_config(name, base)))
        try:
            await agent.start()  # claims the name: refused if it was taken meanwhile
        except Exception as exc:
            await self._take_back(agent)
            return Result.failed(f"{name} couldn't start: {exc}")
        # Nothing else says a helper appeared (its own state events come with a task): UIs add its tab.
        self._ctx.publish(AgentStateChanged(agent_id=name, change="opened"))
        if task is None:
            self._launched[name] = (kind, agent)
            self._ctx.log.info("Opened helper %s (%s), idle", name, kind)
            return Result.ok(f"{name} opened, with no task yet")
        started = await self._ctx.send(StartTask(text=task, agent_id=name, parent_task_id=parent_task_id))
        if not started.is_ok:
            await self._take_back(agent)
            return Result.failed(f"{name} was built but its task didn't start: {started.error}")
        self._launched[name] = (kind, agent)
        self._ctx.log.info("Launched helper %s (%s) on task %s", name, kind, started.value)
        return Result.ok(f"{name} started on task {started.value}")

    async def _take_back(self, agent: ProfileAgent) -> None:
        await self._kit.take_back(agent)  # stops it (releasing its name) and withdraws it

    def _build(self, agent_id: str, kind: str, config: dict[str, Any]) -> ProfileAgent:
        role = str(config.get("prompt", "")).strip()
        prompt = HELPER_PROMPT.format(agent_id=agent_id, role=role).replace(" \n", "\n")
        config = {"description": f"A helper ({kind})", **config}
        return ProfileAgent(self._ctx, agent_id, config, prompt, subject=kind)

    async def _on_grant(self, kind: str, granted: tuple[AccessItem, ...]) -> None:
        """A kind's grant changed while the module runs: every helper of that kind, autostarted
        or launched, takes it live (`ProfileAgent.set_access`), built the same way as at start."""
        if kind not in self._kinds:
            return
        try:
            base = granted_config(self._kinds[kind], granted)
            autostart = instances(kind, base) if any(k == kind for k in self._kind_of.values()) else {}
        except (AccessDenied, ValueError) as exc:  # its workspace was taken back: the revoke turns it off
            self._ctx.log.info("The %s kind's new grant doesn't apply: %s", kind, exc)
            return
        for agent_id, agent in self._agents.items():
            if self._kind_of.get(agent_id) == kind and agent_id in autostart:
                agent.set_access(autostart[agent_id])
        for name, (own_kind, agent) in self._launched.items():
            if own_kind == kind:
                agent.set_access(launched_config(name, base))

    async def _open_task_of(self, agent_id: str) -> str | None:
        result = await self._ctx.send(GetTaskStatus())
        tasks = result.value if result.is_ok and result.value else []
        return next((t.id for t in tasks if t.agent_id == agent_id and not t.state.is_final), None)

    def _agent_of(self, agent_id: str) -> ITaskAgent | None:
        return next((a for a in self._ctx.get_all(ITaskAgent) if a.info().agent_id == agent_id), None)


def kind_configs(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Each kind of helper and its full config: the module's defaults, then its own section."""
    defaults = {k: v for k, v in config.items() if k != "agents"}
    return {kind: {**defaults, **section} for kind, section in (config.get("agents") or {}).items()}


def agent_configs(config: dict[str, Any]) -> dict[str, tuple[str, dict[str, Any]]]:
    """The helpers that start at launch (kinds with `autostart = true`): id -> (kind, config).

    `instances = N` gives `<kind>`, `<kind>_2`, ... Raises ValueError for an id that breaks
    the naming rules (taken and reserved ids are refused by the Hub's claim at start)."""
    result: dict[str, tuple[str, dict[str, Any]]] = {}
    for kind, merged in kind_configs(config).items():
        if merged.get("autostart"):
            result.update({agent_id: (kind, own) for agent_id, own in instances(kind, merged).items()})
    return result


def launched_config(name: str, base: dict[str, Any]) -> dict[str, Any]:
    """A launched helper's config from its kind's granted config: it writes only its own
    sub-folder `<workspace>/<name>`, reads the kind's workspace, and has its own transcript.
    Used at launch and again when the kind's grant changes, so both build the same config."""
    workspace = Path(base.get("workspace", "workspace")).resolve()
    return {**base, "workspace": str(workspace / name), "read_dirs": [*base.get("read_dirs", ()), str(workspace)],
            "write_dirs": [], "transcript": f"{name}.jsonl"}  # fmt: skip


def instances(kind: str, merged: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The helpers one kind starts at launch, from its (granted) config: id -> config.
    `instances = N` gives `<kind>`, `<kind>_2`, ...; peers each write only their own sub-folder
    and read the shared one. Raises ValueError for an id that breaks the naming rules."""
    merged = dict(merged)
    count = max(1, int(merged.pop("instances", 1)))
    merged.pop("autostart", None)
    result: dict[str, dict[str, Any]] = {}
    for n in range(1, count + 1):
        agent_id = kind if n == 1 else f"{kind}_{n}"
        if reason := check_agent_id(agent_id, reserved=TRUSTED_CALLERS):
            raise ValueError(reason)
        own = dict(merged)
        if count > 1:
            base = Path(merged.get("workspace", "workspace")).resolve()
            own["workspace"] = str(base / agent_id)
            own["read_dirs"] = [*merged.get("read_dirs", ()), str(base)]
            own["write_dirs"] = []
        result[agent_id] = own
    return result
