"""The Agent Hub: who is doing what. Holds the authoritative task state; not an AI, launches nothing.

A small coordinator over three parts: the task board (`tasks.py`: every task and its state
machine), the focus (`focus.py`: who you're talking to, and what waits behind each tab's !),
and the agent names (`names.py`: `IAgentNames`). It wires them to the commands, the events
and its menu, finds agents through `ITaskAgent` and never imports an agent module. It also
routes `SetPermissionMode` to the agent, until the permissions handler takes that over.

Several agents may run at once, one task each: the coordinator plus at most `max_extra_agents`
others (3 by default, from config), and never two whose agents write the same folder. The
coordinator hears about the others through `ITaskAgent.note`: their `STATUS:` milestones,
their ends, focus moves, and `AgentNotice` callbacks. Never an interrupt, never a wake.

Its menu (`hub.*`, on the module door) is how the agents and the Talker reach it; each item
knows its caller. The Talker's mode switch (`hub.mode`, Manual only) and card answers
(`hub.answer`) go through it too, so they get the menu's caller check.
"""

from __future__ import annotations

from assistant.contracts import (
    AgentActivity,
    AgentNotice,
    AgentStateChanged,
    AnswerPermission,
    CancelTask,
    FocusChanged,
    FocusSuggested,
    GetMenu,
    GetTaskStatus,
    IAgentNames,
    IModuleDoor,
    InvokeTool,
    ITaskAgent,
    ListAgents,
    ListModules,
    Manifest,
    Menu,
    ModuleContext,
    ModuleProtocol,
    ModuleStateChanged,
    PermissionMode,
    ReportTask,
    Result,
    SendToTask,
    SetFocus,
    SetPermissionMode,
    StartTask,
    TaskUpdated,
)
from assistant.infra.mcp_door import DoorServer

from .focus import Focus
from .names import RESERVED_AGENT_IDS, AgentNames
from .tasks import TaskBoard

__all__ = ["RESERVED_AGENT_IDS", "AgentHubModule"]

TALKER = "talker"  # the caller that speaks for you on the menu
CORE_LINE = {"id": "core", "description": "Module control: list, menu, on, off, reload, add", "state": "active"}


class _Door(IModuleDoor):
    """The hub's `IModuleDoor` part: the MCP config for the relay in front of its `DoorServer`."""

    def __init__(self, server: DoorServer) -> None:
        self._server = server

    def mcp_config(self, caller: str) -> dict:
        return self._server.mcp_config(caller)


menu = Menu()


class AgentHubModule(ModuleProtocol):
    manifest = Manifest(
        id="agent_hub",
        description="Task state and routing between the agents, and who you're talking to; "
        "hosts the agents' door to the module menus",
        provides=(IModuleDoor, IAgentNames,),
        optional=(ITaskAgent,),
        handles=(ListAgents, StartTask, GetTaskStatus, SendToTask, CancelTask, ReportTask, AnswerPermission,
                 SetPermissionMode, SetFocus,),  # fmt: skip
        sends=(ListModules, GetMenu, InvokeTool,),
        publishes=(TaskUpdated, FocusChanged, FocusSuggested,),
        listens=(AgentActivity, AgentNotice, AgentStateChanged, ModuleStateChanged,),
    )
    menu = menu

    async def init(self, ctx: ModuleContext) -> None:
        self._ctx = ctx
        self._coordinator = str(ctx.config.get("coordinator", "main_assistant"))
        # The door's port and token survive a reload, so a running session's relay keeps working.
        handover = ctx.handover if isinstance(ctx.handover, dict) else {}
        self._door = DoorServer(
            ctx.send,
            {"list": ListModules, "menu": GetMenu, "call": InvokeTool},
            host=ctx.config.get("door_host", "127.0.0.1"),
            port=int(handover.get("door_port", ctx.config.get("door_port", 0))),
            token=handover.get("door_token"),
            core_line=CORE_LINE,
        )
        ctx.provide(IModuleDoor, _Door(self._door))
        self._names = AgentNames(ctx, dict(handover.get("claims") or {}), RESERVED_AGENT_IDS | {self._coordinator})
        ctx.provide(IAgentNames, self._names)
        self._clashes_logged: set[str] = set()
        self._tasks = TaskBoard(
            publish=ctx.publish, log=ctx.log, agents=self._agents, agent=self._agent,
            focused=lambda: self._focus.focused(), feed=self._feed, coordinator=self._coordinator,
            # Big agents besides the coordinator that may have an open task at once.
            max_extra=int(ctx.config.get("max_extra_agents", 3)),
        )  # fmt: skip
        self._focus = Focus(
            publish=ctx.publish, log=ctx.log, coordinator=self._coordinator,
            initial=str(handover.get("focus") or "") or None, agent=self._agent,
            release=self._tasks.release, feed=self._feed,
        )  # fmt: skip
        tasks = self._tasks
        ctx.handle(ListAgents, self._list_agents)
        ctx.handle(StartTask, tasks.start)
        ctx.handle(GetTaskStatus, tasks.status)
        ctx.handle(SendToTask, tasks.send)
        ctx.handle(CancelTask, tasks.cancel)
        ctx.handle(ReportTask, tasks.report)
        ctx.handle(AnswerPermission, tasks.answer)
        ctx.handle(SetPermissionMode, tasks.set_mode)
        ctx.handle(SetFocus, self._focus.set)
        ctx.subscribe(AgentActivity, tasks.on_activity)
        ctx.subscribe(AgentNotice, self._on_notice)
        # An agent may have gone (agents.close, modules.off, a module failing): off its tab at once.
        ctx.subscribe(AgentStateChanged, self._focus.check)
        ctx.subscribe(ModuleStateChanged, self._focus.check)

    async def start(self) -> None:
        if self._ctx.config.get("door", True):
            try:
                await self._door.start()
                self._ctx.log.info("The agents' module door is at %s", self._door.url)
            except OSError as exc:  # its port is taken: the agents just go without the door
                self._ctx.log.warning("Couldn't open the agents' module door: %s", exc)

    async def stop(self) -> None:
        await self._door.stop()

    def export_state(self) -> dict | None:
        """For a reload: the focus, the claimed agent ids, and the door's port and token, so the
        new copy opens the same door."""
        state: dict = {"focus": self._focus.stored, "claims": self._names.taken()}
        if self._door.url:
            state |= {"door_port": int(self._door.url.rsplit(":", 1)[1]), "door_token": self._door.token}
        return state

    def busy(self) -> str | None:
        """A reload waits while tasks are open: their records would be lost (no handover yet)."""
        open_tasks = len(self._tasks.open_records())
        return f"{open_tasks} task(s) open" if open_tasks else None

    # --- the menu (on the module door; every item knows its caller) ---

    @menu.item("hub.agents", "The big agents: busy, working, focused (the one the user talks to), "
               "holding a question (!), and their open task")  # fmt: skip
    async def agents_item(self, caller: str = "") -> Result:
        focused = self._focus.focused()
        lines = []
        for agent in self._agents():
            info = agent.info()
            record = self._tasks.open_task_of(info.agent_id)
            lines.append({
                "agent_id": info.agent_id, "description": info.description, "busy": info.busy,
                "working": info.working, "permission_mode": str(info.permission_mode),
                "focused": info.agent_id == focused, "held": self._tasks.holds(info.agent_id),
                "task_id": record.id if record else None,
            })  # fmt: skip
        return Result.ok(lines)

    @menu.item("hub.status", "Task status without disturbing the agent: one task, or the open and recent ones",
               {"task_id": {"type": "string"}})  # fmt: skip
    async def status_item(self, task_id: str | None = None, caller: str = "") -> Result:
        return await self._tasks.status(GetTaskStatus(task_id=task_id))

    @menu.item("hub.start", "Start a task on a free agent (or the one named); your open task becomes its parent",
               {"text": {"type": "string", "minLength": 1}, "agent_id": {"type": "string"},
                "context": {"type": "string"}}, required=["text"])  # fmt: skip
    async def start_item(self, text: str, agent_id: str | None = None, context: str = "", caller: str = "") -> Result:
        parent = self._tasks.open_task_of(caller)
        command = StartTask(text=text, context=context, agent_id=agent_id or None,
                            parent_task_id=parent.id if parent else None)  # fmt: skip
        return await self._tasks.start(command)

    @menu.item("hub.send", "Pass words to a task. No task_id (the Talker only): to agent_id (its tab's agent; "
               "default the focused one), its task or a new one. Others may send only to their child tasks",
               {"text": {"type": "string", "minLength": 1}, "task_id": {"type": "string"},
                "agent_id": {"type": "string"}, "pause": {"type": "boolean"}}, required=["text"])  # fmt: skip
    async def send_item(self, text: str, task_id: str | None = None, agent_id: str | None = None,
                        pause: bool = False, caller: str = "") -> Result:  # fmt: skip
        tasks = self._tasks
        if task_id is None:
            if caller != TALKER:
                return Result.not_available("hub.send without a task_id is only for the Talker")
            target = agent_id or self._focus.focused()
            record = tasks.open_task_of(target)
            if record is None:
                started = await tasks.start(StartTask(text=text, agent_id=target))
                return Result.ok({"agent_id": target, "task_id": started.value}) if started.is_ok else started
            task_id = record.id
        if (refused := tasks.may_steer(task_id, caller, anyone=caller == TALKER)) is not None:
            return refused
        result = await tasks.send(SendToTask(task_id=task_id, text=text, resume=not pause))
        return Result.ok({"agent_id": tasks.get(task_id).agent_id, "task_id": task_id}) if result.is_ok else result

    @menu.item("hub.cancel", "Stop a task, like Esc (the Talker: any task; others: their child tasks)",
               {"task_id": {"type": "string", "minLength": 1}}, required=["task_id"])  # fmt: skip
    async def cancel_item(self, task_id: str, caller: str = "") -> Result:
        if (refused := self._tasks.may_steer(task_id, caller, anyone=caller == TALKER)) is not None:
            return refused
        return await self._tasks.cancel(CancelTask(task_id=task_id))

    @menu.item("hub.answer", "Allow or deny a task's open permission request, once (the Talker, after the user "
               "answered)", {"task_id": {"type": "string", "minLength": 1}, "allow": {"type": "boolean"}},
               required=["task_id", "allow"], callers=(TALKER,))  # fmt: skip
    async def answer_item(self, task_id: str, allow: bool) -> Result:
        return await self._tasks.answer(AnswerPermission(task_id=task_id, allow=allow))

    @menu.item("hub.mode", "Switch an agent to Manual (only the user switches to Auto, with the app's button)",
               {"agent_id": {"type": "string", "minLength": 1},
                "mode": {"type": "string", "enum": [m.value for m in PermissionMode]}},
               required=["agent_id", "mode"], callers=(TALKER,))  # fmt: skip
    async def mode_item(self, agent_id: str, mode: str) -> Result:
        if mode != PermissionMode.MANUAL:
            return Result.not_available("Only the user switches an agent to Auto, with the app's button")
        return await self._tasks.set_mode(SetPermissionMode(agent_id=agent_id, mode=PermissionMode.MANUAL))

    @menu.item("hub.focus", "Move the focus to an agent, after the user said so (empty: back to the main one)",
               {"agent_id": {"type": "string"}}, required=["agent_id"], callers=(TALKER,))  # fmt: skip
    async def focus_item(self, agent_id: str) -> Result:
        return await self._focus.set(SetFocus(agent_id=agent_id))

    @menu.item("hub.suggest_focus", "Suggest the user talks to an agent directly (the coordinator only); "
               "the Talker asks them",
               {"agent_id": {"type": "string", "minLength": 1}, "reason": {"type": "string"}},
               required=["agent_id"])  # fmt: skip
    async def suggest_focus_item(self, agent_id: str, reason: str = "", caller: str = "") -> Result:
        if caller != self._coordinator:
            return Result.not_available(f"hub.suggest_focus is only for {self._coordinator}")
        if self._agent(agent_id) is None:
            return Result.invalid_arguments(f"No agent {agent_id!r}")
        self._ctx.publish(FocusSuggested(agent_id=agent_id, reason=reason, by=caller))
        return Result.ok()

    # --- events and commands of its own ---

    async def _on_notice(self, event: AgentNotice) -> None:
        agent = self._agent(event.agent_id)
        if agent is None:
            self._ctx.log.info("Dropped a notice for %s (not running): %s", event.agent_id, event.text)
            return
        agent.note(f"[{event.source or 'notice'}] {event.text}")

    async def _list_agents(self, command: ListAgents) -> Result:
        return Result.ok([agent.info() for agent in self._agents()])

    # --- the running agents, shared by the parts ---

    def _feed(self, line: str) -> None:
        """A background line for the coordinator's next turn; never wakes it."""
        coordinator = self._agent(self._coordinator)
        if coordinator is not None:
            coordinator.note(line)

    def _agents(self) -> list[ITaskAgent]:
        """Every running agent, one per id: a second agent with a taken id (one that skipped
        `IAgentNames.claim`) is left out, and the clash is logged once."""
        seen: dict[str, ITaskAgent] = {}
        for agent in self._ctx.get_all(ITaskAgent):
            agent_id = agent.info().agent_id
            if agent_id not in seen:
                seen[agent_id] = agent
            elif agent_id not in self._clashes_logged:
                self._clashes_logged.add(agent_id)
                self._ctx.log.error("Two agents share the id %r; only the first is used", agent_id)
        return list(seen.values())

    def _agent(self, agent_id: str) -> ITaskAgent | None:
        return next((a for a in self._agents() if a.info().agent_id == agent_id), None)
