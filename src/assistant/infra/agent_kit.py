"""The pieces every agent module repeats, built once: `AgentKit`.

An agent module (the Main Assistant, `task_agents`, `job_search`, `cv`) owns one or more
`ProfileAgent`s. Each used to write its own reset handler, grant handler and start sequence;
the kit holds them: it provides each agent as `ITaskAgent`, resets the one a `ResetRequested`
names, hands a changed grant to the agent that holds it, and opens an agent from its access
list (ask, build, provide, start). The module keeps only what is its own.

The module still declares what the kit and its agents use (principle 17), from the names below:
`provides=(ITaskAgent,)`, `uses=AGENT_USES`, `sends=AGENT_SENDS`, `publishes=AGENT_PUBLISHES`,
`listens=AGENT_LISTENS`, plus `PermissionChanged` with `follow_grant` or `watch_grant`.
"""

from __future__ import annotations

from typing import Any

from assistant.contracts import (
    AccessDenied,
    AccessItem,
    AgentActivity,
    AgentStateChanged,
    IAgentNames,
    IModuleDoor,
    IPageOpener,
    ITaskAgent,
    ModuleContext,
    ModuleStateChanged,
    PermissionModeChanged,
    ReportTask,
    ResetRequested,
    SessionUsage,
    StartProvider,
)
from assistant.infra.agent_access import granted_config, request_access, watch_grant
from assistant.infra.profile_agent import ProfileAgent

# What every agent module's manifest declares for its ProfileAgents and this kit, named once.
#: Looked up at each call, no start order (the Hub provides both and uses the agents):
#: the door at each session start, the names at start and stop; and the page opener, at each SHOW.
AGENT_USES = (IModuleDoor, IAgentNames, IPageOpener)
#: Reports to the Hub; SHOW asks the core to start the page opener's module if none is on.
AGENT_SENDS = (ReportTask, StartProvider)
AGENT_PUBLISHES = (AgentActivity, AgentStateChanged, SessionUsage, PermissionModeChanged)
#: The kit's resets; a ProfileAgent that starts before the door waits for a module to turn on.
AGENT_LISTENS = (ResetRequested, ModuleStateChanged)


class AgentKit:
    """The agents one module owns, by id. Build it in the module's `init`."""

    def __init__(self, ctx: ModuleContext) -> None:
        self._ctx = ctx
        self._agents: dict[str, ProfileAgent] = {}
        ctx.subscribe(ResetRequested, self._on_reset)

    def add(self, agent: ProfileAgent) -> ProfileAgent:
        """Provide `agent` as `ITaskAgent` and keep it (for resets, grants, `busy` and `stop`)."""
        self._ctx.provide(ITaskAgent, agent.agent)
        self._agents[agent.agent_id] = agent
        return agent

    def get(self, agent_id: str) -> ProfileAgent | None:
        return self._agents.get(agent_id)

    def agents(self) -> list[ProfileAgent]:
        return list(self._agents.values())

    async def open(
        self, agent_id: str, config: dict[str, Any], prompt: str, *, subject: str, reason: str,
        wait: bool = False, **kwargs: Any,
    ) -> ProfileAgent:  # fmt: skip
        """The start sequence: ask for `config`'s access list under `subject` (`request_access`:
        `AccessPending` / `AccessDenied` pass through), build the agent from what you allowed,
        provide it and start it. A failed start takes it back and raises again."""
        granted = await request_access(self._ctx, config, subject=subject, reason=reason, wait=wait)
        agent = self.add(ProfileAgent(self._ctx, agent_id, granted, prompt, subject=subject, **kwargs))
        try:
            await agent.start()
        except BaseException:
            await self.take_back(agent)
            raise
        return agent

    async def take_back(self, agent: ProfileAgent) -> None:
        """Stop `agent` (it releases its name) and withdraw it."""
        self._agents.pop(agent.agent_id, None)
        await agent.stop()
        self._ctx.withdraw(ITaskAgent, agent.agent)

    def follow_grant(self, agent_id: str, config: dict[str, Any]) -> None:
        """Agent `agent_id` (its grant's subject too) takes its grant live when it changes
        (`ProfileAgent.set_access`), cut from `config`; nothing while it isn't open."""

        async def on_grant(subject: str, granted: tuple[AccessItem, ...]) -> None:
            agent = self._agents.get(agent_id)
            if agent is None:
                return
            try:
                agent.set_access(granted_config(config, granted))
            except AccessDenied as exc:  # its workspace was taken back: the revoke turns it off
                self._ctx.log.info("%s's new grant doesn't apply: %s", agent_id, exc)

        watch_grant(self._ctx, on_grant, subject=agent_id)

    def busy(self) -> str | None:
        """Why a reload should wait: the agents that have a task."""
        return "; ".join(r for a in self._agents.values() if (r := a.busy())) or None

    async def stop(self) -> None:
        """Stop every agent (the module's stop; its context withdraws them)."""
        agents, self._agents = list(self._agents.values()), {}
        for agent in agents:
            await agent.stop()

    async def _on_reset(self, event: ResetRequested) -> None:
        agent = self._agents.get(event.agent_id or "")
        if agent is not None and not (result := await agent.agent.reset()).is_ok:
            self._ctx.log.warning("Couldn't reset %s: %s", agent.agent_id, result.error)
