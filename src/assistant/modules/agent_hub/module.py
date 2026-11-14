"""The Agent Hub: who is doing what. Holds the authoritative task state; not an AI, launches nothing.

A small coordinator over five parts: the task board (`tasks.py`: every task and its state
machine), the focus (`focus.py`: who you're talking to, and what waits behind each tab's !),
message delivery (`delivery.py`), the message gate (`gate.py`) and the access-list reviewer
(`review.py`).
It wires them to the commands, the events and its menu, finds agents through `ITaskAgent` and
never imports an agent module. The agent names and modes are the core's (its Callers port,
`IAgentNames`); `SetPermissionMode` is the core's too, and the Hub only closes a card that a
switch to Auto answered (`PermissionModeChanged.answered`). The agents' module door is the
core's as well (`IModuleDoor`, decision D1). The access-list review is the Hub's (`review.py`,
D6): the core sends `ReviewAccessList`, the Hub runs it on the reviewer agent and answers with
`AddCardNotes`.

Several agents may run at once, one task each: the coordinator plus at most `max_extra_agents`
others (3 by default, from config), and never two whose agents write the same folder. The
coordinator hears about the others through `ITaskAgent.note`: their `STATUS:` milestones,
their ends, focus moves, and `AgentNotice` callbacks. Never an interrupt, never a wake.

Its menu (`hub.*`, on the module door) is how the agents and the Talker reach it; each item
knows its caller. An agent may message any other agent with `hub.send` and `agent_id`: its own
child task straight in, as before; anyone else through the message gate (`gate.py`), which asks
you once per direction on a permission card and never interrupts a turn. The Talker's mode switch (`hub.mode`, Manual only) and card answers
(`hub.answer`) go through it too, so they get the menu's caller check.
"""

from __future__ import annotations

from assistant.contracts import (
    AddCardNotes,
    AgentActivity,
    AgentNotice,
    AgentStateChanged,
    AnswerPermission,
    CancelTask,
    DeliverMessage,
    FocusChanged,
    FocusSuggested,
    GetTaskStatus,
    IAgentNames,
    ITaskAgent,
    ListAgents,
    Manifest,
    Menu,
    ModuleContext,
    ModuleProtocol,
    ModuleStateChanged,
    PermissionMode,
    PermissionModeChanged,
    ReportTask,
    ResetRequested,
    Result,
    ReviewAccessList,
    SendToTask,
    SetFocus,
    SetPermissionMode,
    StartTask,
    Status,
    TaskUpdated,
)

from .delivery import Delivery
from .focus import Focus
from .gate import MessageGate
from .review import Reviewer
from .tasks import TaskBoard

__all__ = ["AgentHubModule"]

TALKER = "talker"  # the caller that speaks for you on the menu


menu = Menu()


class AgentHubModule(ModuleProtocol):
    manifest = Manifest(
        id="agent_hub",
        description="Task state and routing between the agents, and who you're talking to",
        optional=(ITaskAgent,),
        uses=(IAgentNames,),
        handles=(ListAgents, StartTask, GetTaskStatus, SendToTask, CancelTask, ReportTask, AnswerPermission,
                 SetFocus, DeliverMessage, AgentNotice, ResetRequested, ReviewAccessList,),  # fmt: skip
        sends=(SetPermissionMode, AddCardNotes,),
        publishes=(TaskUpdated, FocusChanged, FocusSuggested,),
        listens=(AgentActivity, AgentStateChanged, ModuleStateChanged, PermissionModeChanged,),
    )
    menu = menu

    async def init(self, ctx: ModuleContext) -> None:
        self._ctx = ctx
        self._coordinator = str(ctx.config.get("coordinator", "main_assistant"))
        handover = ctx.handover if isinstance(ctx.handover, dict) else {}
        self._clashes_logged: set[str] = set()
        self._start_only_by = start_only_by(ctx.config.get("start_only_by", {}))
        named = agent_ids(ctx.config.get("named_only", []), "named_only")
        self._tasks = TaskBoard(
            publish=self._publish_task, log=ctx.log, agents=self._agents, agent=self._agent,
            focused=lambda: self._focus.focused(), feed=self._feed, coordinator=self._coordinator,
            # Big agents besides the coordinator that may have an open task at once.
            max_extra=int(ctx.config.get("max_extra_agents", 3)),
            # A free-agent pick never lands on these, nor on an agent whose info() says named_only.
            restricted=frozenset(self._start_only_by) | named,
            # A finished child task's end, as a message to its parent's agent (delivery is made below).
            tell_parent=lambda agent_id, text, task_id="": self._delivery.tell(agent_id, text, task_id),
        )  # fmt: skip
        self._tasks.restore(list(handover.get("questions") or []))  # questions outlive a Hub reload
        self._delivery = Delivery(self._tasks, self._agent, ctx.log, list(handover.get("waiting") or []))
        self._gate = MessageGate(ctx.permissions, self._delivery.deliver, self._note, ctx.log)
        self._focus = Focus(
            publish=ctx.publish, log=ctx.log, coordinator=self._coordinator,
            initial=str(handover.get("focus") or "") or None, agent=self._agent,
            release=self._tasks.release, feed=self._feed,
        )  # fmt: skip
        tasks = self._tasks
        # The access-list review (D6): the core asks, the Hub runs it as a task and sends the notes back.
        self._reviewer = Reviewer(tasks.start, tasks.cancel, ctx.send, ctx.log)
        ctx.handle(ReviewAccessList, self._reviewer.review)
        ctx.handle(ListAgents, self._list_agents)
        ctx.handle(StartTask, tasks.start)
        ctx.handle(GetTaskStatus, tasks.status)
        ctx.handle(SendToTask, self._send)
        ctx.handle(CancelTask, tasks.cancel)
        ctx.handle(ReportTask, self._report)
        ctx.handle(AnswerPermission, tasks.answer)
        ctx.handle(SetFocus, self._focus.set)
        ctx.handle(DeliverMessage, self._delivery.deliver)
        ctx.handle(AgentNotice, self._on_notice)
        ctx.handle(ResetRequested, self._on_reset)
        ctx.subscribe(AgentActivity, tasks.on_activity)
        ctx.subscribe(AgentStateChanged, self._on_state)
        ctx.subscribe(ModuleStateChanged, self._on_state)
        ctx.subscribe(PermissionModeChanged, tasks.on_mode_changed)

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        await self._gate.close()
        await self._reviewer.close()

    def export_state(self) -> dict | None:
        """For a reload: the focus, the messages still waiting and the questions waiting on you.
        The claimed agent ids and the module door are the core's, so they outlive a reload anyway."""
        return {"focus": self._focus.stored, "waiting": self._delivery.export(),
                "questions": self._tasks.export_questions()}  # fmt: skip

    def busy(self) -> str | None:
        """A reload waits while agents hold tasks (their records would be lost: no handover) and
        while messages wait on a card. Questions waiting on you are handed over, so they don't count."""
        open_tasks, held = len(self._tasks.held_records()), self._gate.held()
        reasons = [f"{open_tasks} task(s) open"] * bool(open_tasks) + [f"{held} message(s) on a card"] * bool(held)
        return "; ".join(reasons) or None

    # --- the menu (on the module door; every item knows its caller) ---

    @menu.item("hub.agents", "The big agents: state (active or idle; an idle one takes work, whatever it "
               "asked), focused (the one the user talks to), holding a question (!), and their open task")  # fmt: skip
    async def agents_item(self, caller: str = "") -> Result:
        focused = self._focus.focused()
        lines = []
        for agent in self._agents():
            info = agent.info()
            record = self._tasks.open_task_of(info.agent_id)
            lines.append({
                "agent_id": info.agent_id, "description": info.description, "state": str(info.state),
                "permission_mode": str(info.permission_mode),
                "focused": info.agent_id == focused, "held": self._tasks.holds(info.agent_id),
                "task_id": record.id if record else None,
            })  # fmt: skip
        return Result.ok(lines)

    @menu.item("hub.status", "Task status without disturbing the agent: one task, or the open and recent ones",
               {"task_id": {"type": "string"}})  # fmt: skip
    async def status_item(self, task_id: str | None = None, caller: str = "") -> Result:
        return await self._tasks.status(GetTaskStatus(task_id=task_id))

    @menu.item("hub.start", "Start a task on a free agent (or the one named); your open task becomes its parent. "
               "When it ends (done or failed), its end comes to you as a message (the coordinator: a background "
               "note); don't wait for it",
               {"text": {"type": "string", "minLength": 1}, "agent_id": {"type": "string"},
                "context": {"type": "string"}},
               required=["text"])  # fmt: skip
    async def start_item(self, text: str, agent_id: str | None = None, context: str = "", caller: str = "") -> Result:
        only = self._start_only_by.get(agent_id or "")
        if only is not None and caller != TALKER and caller not in only:
            return Result.not_available(f"hub.start for {agent_id} is only for: {', '.join(only)}")
        parent = self._tasks.open_task_of(caller)
        command = StartTask(text=text, context=context, agent_id=agent_id or None,
                            parent_task_id=parent.id if parent else None)  # fmt: skip
        return await self._tasks.start(command)

    @menu.item("hub.send", "Pass words to a task or an agent. task_id: your own child task (the Talker: any), "
               "straight in. agent_id: message that agent; its open task if it's your child, else it arrives "
               "when its turn ends (into its open task or as a new task), and the first message to it asks the "
               "user once on a card (Allow once / Always / Deny; the reply says 'waiting on the user's card'). "
               "The Talker with neither: the focused agent",
               {"text": {"type": "string", "minLength": 1}, "task_id": {"type": "string"},
                "agent_id": {"type": "string"}, "pause": {"type": "boolean"}}, required=["text"])  # fmt: skip
    async def send_item(self, text: str, task_id: str | None = None, agent_id: str | None = None,
                        pause: bool = False, caller: str = "") -> Result:  # fmt: skip
        tasks = self._tasks
        if task_id is None and caller != TALKER:
            if not agent_id:
                return Result.not_available("Name agent_id (the agent to message), or task_id for your own child task")
            if agent_id == caller:
                return Result.invalid_arguments("That's you; name another agent")
            names = self._ctx.get_one(IAgentNames)
            if self._agent(agent_id) is None and agent_id not in (names.taken() if names else {}):
                return Result.invalid_arguments(f"No agent {agent_id!r}")
            record = tasks.open_task_of(agent_id)
            if record is None or tasks.may_steer(record.id, caller) is not None:
                return await self._gate.send(caller, agent_id, text)
            task_id = record.id  # its own child task: straight in, as before
        if task_id is None:
            target = agent_id or self._focus.focused()
            record = tasks.open_task_of(target)
            if record is None:
                started = await tasks.start(StartTask(text=text, agent_id=target))
                return Result.ok({"agent_id": target, "task_id": started.value}) if started.is_ok else started
            task_id = record.id
        if (refused := tasks.may_steer(task_id, caller, anyone=caller == TALKER)) is not None:
            return refused
        result = await self._send(SendToTask(task_id=task_id, text=text, resume=not pause))
        if not result.is_ok:
            return result
        value = {"agent_id": tasks.get(task_id).agent_id, "task_id": task_id}
        return Result.ok(value | {"delivered": "when its agent is free"} if result.value == "pending" else value)

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
        return await self._ctx.send(SetPermissionMode(agent_id=agent_id, mode=PermissionMode.MANUAL))

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

    def _publish_task(self, event: TaskUpdated) -> None:
        """The board's `TaskUpdated`, seen by the reviewer first (a review's end), then published."""
        self._reviewer.on_task_updated(event)
        self._ctx.publish(event)

    async def _send(self, command: SendToTask) -> Result:
        """`SendToTask`: an answer to a question whose agent is in a turn (or not running) waits
        and goes in when it's free (`ok "pending"`); everything else as the board says."""
        result = await self._tasks.send(command)
        record = self._tasks.get(command.task_id)
        if result.status is Status.NOT_AVAILABLE and record is not None and record.asked:
            return await self._delivery.later(record.agent_id, record.id, command.text)
        return result

    async def _report(self, command: ReportTask) -> Result:
        """`ReportTask`, then a waiting message may go: an end frees the agent's slot on the board
        (the agent's idle state can come before its end report does)."""
        result = await self._tasks.report(command)
        await self._delivery.flush()
        return result

    async def _on_state(self, event: AgentStateChanged | ModuleStateChanged) -> None:
        """An agent may have gone (agents.close, modules.off, a module failing): off its tab at
        once. One may have ended its turn or started: a waiting message may go now."""
        await self._focus.check(event)
        await self._delivery.flush()

    async def _on_notice(self, command: AgentNotice) -> Result:
        """`AgentNotice` (a command, D5): one line for the agent's next turn, labelled with the
        stamped sender, so no module speaks as another; the core's own keep their `source`."""
        agent = self._agent(command.agent_id)
        if agent is None:
            self._ctx.log.info("Dropped a notice for %s (not running): %s", command.agent_id, command.text)
            return Result.not_available(f"No agent {command.agent_id!r} is running")
        label = (command.source or "core") if command.sent_by in ("", "core") else command.sent_by
        agent.note(f"[{label}] {command.text}")
        return Result.ok("noted")

    async def _on_reset(self, command: ResetRequested) -> Result:
        """`ResetRequested` (a command, D5): the agent's own `reset` (at once when idle, a handoff
        with a task)."""
        agent = self._agent(command.agent_id)
        if agent is None:
            return Result.not_available(f"No agent {command.agent_id!r} is running")
        result = await agent.reset()
        if not result.is_ok:
            self._ctx.log.warning("Couldn't reset %s: %s", command.agent_id, result.error)
        return result

    async def _list_agents(self, command: ListAgents) -> Result:
        return Result.ok([agent.info() for agent in self._agents()])

    # --- the running agents, shared by the parts ---

    def _note(self, agent_id: str, line: str) -> None:
        """A background line for one agent's next turn (the gate's Deny note)."""
        agent = self._agent(agent_id)
        if agent is not None:
            agent.note(line)

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


def agent_ids(value: object, key: str) -> frozenset[str]:
    """`[modules.agent_hub] <key>`: a list of agent ids. ValueError if it isn't one.
    `named_only`: a fallback list of agents a free-agent pick (`hub.start` with no agent_id) never
    lands on; the usual place is the agent's own config (`AgentInfo.named_only`)."""
    if not (isinstance(value, list) and all(isinstance(v, str) and v for v in value)):
        raise ValueError(f"agent_hub: {key} must be a list of agent ids, not {value!r}")
    return frozenset(value)


def start_only_by(value: object) -> dict[str, tuple[str, ...]]:
    """`[modules.agent_hub] start_only_by`: agent id -> the only callers whose `hub.start` may
    start it (the Talker always may). ValueError if it isn't that shape."""
    if not isinstance(value, dict):
        raise ValueError(f"agent_hub: start_only_by must be a table of agent id -> callers, not {value!r}")
    checked = {}
    for agent_id, callers in value.items():
        if not (isinstance(callers, list) and all(isinstance(c, str) and c for c in callers)):
            raise ValueError(f"agent_hub: start_only_by.{agent_id} must be a list of agent ids, not {callers!r}")
        checked[str(agent_id)] = tuple(callers)
    return checked
