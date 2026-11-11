"""One big agent built from its config section: `AgentProfile` + `ClaudeSession` + `SessionTaskAgent`.

Every big agent (the Main Assistant, each `task_agents` profile, an agent bundled with its own
module such as the job agent) is put together the same way, so that wiring lives here once.
The module that owns it provides `agent` as `ITaskAgent` and calls `start` / `stop`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

from assistant.contracts import IAgentNames, IModuleDoor, ModuleContext, ModuleState, ModuleStateChanged
from assistant.infra.agent_profile import HELPER_BLOCK, AgentProfile, hook_env
from assistant.infra.claude_session import ClaudeSession
from assistant.infra.session_agent import SessionTaskAgent


class ProfileAgent:
    """A `claude` task agent from `config` (an agent's section: `AgentProfile.from_config`'s keys,
    plus `description`, `capabilities`, `permission_timeout`, `fresh_sessions`, `max_handoffs`,
    `context_reminder`, `edit_note`, `transcript`, `door`).

    The session's command is read at each session start, so it gets the permission mode of that
    moment, the module door's config under this agent's own name (`mcp_config(agent_id)`, or
    none when the door is off or not there), the profile as it is then (`set_access` replaces it
    when a grant changes), and a read rule for the launch's snips folder. `start_session`: start
    the `claude` process with the module (the Main Assistant); otherwise it starts on the first task.

    `subject`: the grant it holds (a task-agent module's agent: its own id, or its kind). Given,
    its start tells the permissions handler (`ctx.permissions.own_agent`), so it may ask for more
    access itself with `permissions.request`, and its prompt says how.
    """

    def __init__(
        self,
        ctx: ModuleContext,
        agent_id: str,
        config: dict[str, Any],
        prompt: str,
        role_block: str = HELPER_BLOCK,
        start_session: bool = False,
        subject: str | None = None,
        session_factory: Callable[..., ClaudeSession] = ClaudeSession,
    ) -> None:
        """`role_block`: its half of the shared prompt block (`AgentProfile.role_block`; the
        coordinator's module passes its own). `session_factory` builds its session
        (`ClaudeSession`'s arguments); pass a fake to test or swap it without patching (principle 22)."""
        self._ctx = ctx
        self.agent_id = agent_id
        self._config = config
        self._role_block = role_block
        self._start_session = start_session
        self.subject = subject
        self._claimed = False  # start claimed our id
        self._door_pending = False  # the session started before the door was up
        self._regrant: asyncio.Task | None = None  # the idle restart after a live grant
        self.workspace = Path(config.get("workspace", "workspace")).resolve()
        self.profile = self._profile(config)
        edit_note = bool(config.get("edit_note", True))
        task_file = self.workspace / ".claude" / "state" / f"{agent_id}-task.txt"
        transcript = config.get("transcript")
        self.session = session_factory(
            lambda: self.profile.command(prompt, self.agent.permission_mode, self.door(), self.snips()),
            cwd=self.workspace, log=ctx.log, transcript=ctx.logs.sink(transcript) if transcript else None,
            env=hook_env(agent_id, task_file, edit_note),
        )  # fmt: skip
        self.agent = SessionTaskAgent(
            self.session,
            ctx,
            agent_id=agent_id,
            description=str(config.get("description", f"The {agent_id} agent")),
            capabilities=tuple(config.get("capabilities", ())),
            permission_timeout=float(config.get("permission_timeout", 600.0)),
            fresh_sessions=bool(config.get("fresh_sessions", True)),
            max_handoffs=int(config.get("max_handoffs", 3)),
            manual_claude_mode=self.profile.claude_mode,
            context_reminder=int(config.get("context_reminder", 150_000)),
            edit_note=edit_note,
            task_file=task_file,
            write_folders=self.profile.write_folders(),
            compact_handoffs=lambda: self.profile.chrome,  # its tabs stay across a handoff
            close_tabs=lambda: self.profile.chrome,  # and are closed at the task's end
        )

    def _profile(self, config: dict[str, Any]) -> AgentProfile:
        """The profile from `config`, in the workspace it started with."""
        own = {**config, "workspace": str(self.workspace), "permission_requests": self.subject is not None}
        return AgentProfile.from_config(self.agent_id, own, self._role_block)

    def door(self) -> dict:
        """The module door's MCP config under this agent's name, read at each session start (the
        Hub may have been reloaded), or {} if the door is off or not there yet."""
        if not self._config.get("door", True):
            return {}
        door = self._ctx.get_one(IModuleDoor)
        return door.mcp_config(self.agent_id) if door is not None else {}

    def snips(self) -> str:
        """The launch's snips folder (snips and pasted images), read at each session start: the
        launch's log folder is named at the first message, after the app has started."""
        return str(self._ctx.logs.folder() / "snips")

    def set_access(self, config: dict[str, Any]) -> None:
        """A grant changed: rebuild the profile from the new granted config (folders, commands,
        Python, Chrome) and hand the agent its new write folders. An idle open session restarts
        once in the background to pick it up; a running task is never cut and takes it at its
        next session (its next task or a handoff). The workspace stays as it started."""
        self._config = config
        self.profile = self._profile(config)
        self.agent.write_folders = self.profile.write_folders()
        self._ctx.log.info("%s's access changed; it applies from its next session", self.agent_id)
        if self.session.running and not self.agent.has_task and (self._regrant is None or self._regrant.done()):
            self._regrant = asyncio.create_task(self._restart_for_grant(), name=f"{self.agent_id}:regrant")

    async def _restart_for_grant(self) -> None:
        try:
            restarted = await self.agent.restart_session()
        except Exception:
            self._ctx.log.exception("%s couldn't restart its session with its new access", self.agent_id)
            return
        if restarted:
            self._ctx.log.info("%s restarted its idle session with its new access", self.agent_id)
        else:  # a task got in first; its session already read the new profile
            self._ctx.log.info("%s is busy; its new access applies at its next session", self.agent_id)

    def busy(self) -> str | None:
        """Why a reload should wait: this agent has a task."""
        return f"{self.agent_id} is working on a task" if self.agent.has_task else None

    async def start(self) -> None:
        """Claim the agent's id (`IAgentNames`, when the Hub runs), then make the workspace.
        A refused id raises `RuntimeError` with the reason, so nothing runs under a taken name."""
        names = self._ctx.get_one(IAgentNames)
        if names is not None:
            claimed = await names.claim(self.agent_id, self._ctx.module_id)
            if not claimed.is_ok:
                raise RuntimeError(claimed.error)
            self._claimed = True
        if self.subject is not None:
            self._ctx.permissions.own_agent(self.agent_id, self.subject)
        self.workspace.mkdir(parents=True, exist_ok=True)
        if self._start_session:
            # At launch this agent starts before the Hub, whose door has no address until the
            # Hub's own start: wait for a module to turn on, then restart once with the door.
            self._door_pending = self._config.get("door", True) and not self.door()
            if self._door_pending:
                self._ctx.log.warning("%s starts without the module door; it restarts when the door is up", self.agent_id)
                self._ctx.subscribe(ModuleStateChanged, self._on_module_state)
            await self.session.start()

    async def _on_module_state(self, event: ModuleStateChanged) -> None:
        """The door is up: an idle session restarts once to pick it up; a busy one is left alone
        (its next session start reads the door anyway)."""
        if not self._door_pending or event.state is not ModuleState.ACTIVE or not self.door():
            return
        self._door_pending = False
        if self.agent.has_task:
            self._ctx.log.info("%s is busy; it picks up the module door at its next session", self.agent_id)
            return
        try:
            restarted = await self.agent.restart_session()
        except Exception:
            self._ctx.log.exception("%s couldn't restart its session with the module door", self.agent_id)
            return
        if not restarted:  # a task got in first
            self._ctx.log.info("%s is busy; it picks up the module door at its next session", self.agent_id)
            return
        self._ctx.log.info("%s restarted its session with the module door", self.agent_id)

    async def stop(self) -> None:
        if self._regrant is not None:
            self._regrant.cancel()
            await asyncio.gather(self._regrant, return_exceptions=True)
        await self.agent.close()
        await self.session.close()
        # Released through today's provider: the Hub may have been reloaded since the claim.
        names = self._ctx.get_one(IAgentNames) if self._claimed else None
        if names is not None:
            names.release(self.agent_id, self._ctx.module_id)
        self._claimed = False
