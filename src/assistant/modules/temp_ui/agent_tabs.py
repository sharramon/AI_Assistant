"""The + and the × on the agent tabs (plus-agent-tab note): open a helper yourself, close an agent.

`POST /agent-tabs` `{"action": "kinds" | "turn_on" | "open" | "close", ...}`, all through menus
as `temp_ui`, which is you clicking: `agents.kinds` / `agents.launch` / `agents.close`
(`task_agents`) and `modules.on` / `modules.off` (the core's menu). The page asks before a close
("Close this agent?"); here a close cancels the agent's running task first, then closes a helper
that was launched (`agents.close`, which frees its name) or turns off the module the agent
belongs to (the job agent: `modules.off job_search`). The Main Assistant's tab has no ×, and a
helper `task_agents` started by itself (autostart) closes only with its module.
"""

from __future__ import annotations

import asyncio
from typing import Any

from assistant.contracts import (
    CancelTask,
    GetTaskStatus,
    IAgentNames,
    InvokeTool,
    ListAgents,
    ListModules,
    ModuleContext,
    ModuleState,
    Result,
)

HELPERS = "task_agents"
IDLE_WAIT = 10.0  # seconds a cancelled helper gets to go idle before agents.close


class AgentTabs:
    def __init__(self, ctx: ModuleContext, coordinator: str) -> None:
        self._ctx = ctx
        self._coordinator = coordinator
        self.to_focus: str | None = None  # the helper you opened: focused once its tab appears

    async def handle(self, body: dict[str, Any]) -> dict[str, Any]:
        action = body.get("action")
        if action == "kinds":
            result = await self._tool("agents.kinds")
            answer = _answer(result)
            if not result.is_ok:
                answer["off"] = await self._helpers_off()
            return answer
        if action == "turn_on":
            return _answer(await self._tool("modules.on", module_id=HELPERS))
        if action == "open":
            name = str(body.get("name", "")).strip()
            args = {"name": name, "kind": str(body.get("kind") or "helper"), "task": str(body.get("task") or "").strip()}
            result = await self._tool("agents.launch", **args)
            if result.is_ok:
                self.to_focus = name
            return _answer(result)
        if action == "close":
            return _answer(await self.close(str(body.get("agent_id", ""))))
        return {"ok": False, "value": None, "error": f"unknown action {action!r}"}

    async def close(self, agent_id: str) -> Result:
        """Cancel `agent_id`'s running task, then close it the way its owner allows."""
        if not agent_id or agent_id == self._coordinator:
            return Result.invalid_arguments("The Main Assistant's tab can't be closed")
        names = self._ctx.get_one(IAgentNames)
        owner = names.taken().get(agent_id) if names else None
        if owner is None:
            return Result.not_available(f"No module holds {agent_id}, so it can't be closed from here")
        if owner == HELPERS:
            kinds = await self._tool("agents.kinds")
            running = kinds.value.get("running", []) if kinds.is_ok else []
            if not any(r["agent_id"] == agent_id and r["launched"] for r in running):
                return Result.not_available(f"{agent_id} starts with the helpers; turn {HELPERS} off to close it")
        cancelled = await self._cancel_task(agent_id)
        if owner == HELPERS:
            await self._wait_idle(agent_id)
            result = await self._tool("agents.close", agent_id=agent_id)
        else:
            result = await self._tool("modules.off", module_id=owner)
            if result.is_ok:
                result = Result.ok(f"{agent_id} closed: its module {owner} is off")
        if result.is_ok and cancelled:
            result = Result.ok(f"{result.value} (its task {cancelled} was cancelled)")
        return result

    async def _cancel_task(self, agent_id: str) -> str | None:
        tasks = await self._ctx.send(GetTaskStatus())
        for task in (tasks.value or ()) if tasks.is_ok else ():
            if task.agent_id == agent_id and not task.state.is_final:
                await self._ctx.send(CancelTask(task_id=task.id))
                return task.id
        return None

    async def _wait_idle(self, agent_id: str) -> None:
        loop = asyncio.get_running_loop()
        end = loop.time() + IDLE_WAIT
        while loop.time() < end:
            listed = await self._ctx.send(ListAgents())
            if not any(a.agent_id == agent_id and a.active for a in (listed.value or ())):
                return
            await asyncio.sleep(0.1)

    async def _helpers_off(self) -> bool:
        listed = await self._ctx.send(ListModules())
        return listed.is_ok and any(m.id == HELPERS and m.state is not ModuleState.ACTIVE for m in listed.value)

    async def _tool(self, tool: str, **args: Any) -> Result:
        return await self._ctx.send(InvokeTool(name=tool, args=args))


def _answer(result: Result) -> dict[str, Any]:
    return {"ok": result.is_ok, "value": result.value, "error": result.error}
