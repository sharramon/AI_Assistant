"""The Main Assistant: the worker. A `claude` session with file tools, working in its own folder.

Provides `ITaskAgent` through a composed `SessionTaskAgent`; only the Agent Hub
calls it. Its process starts with the module and stops with it.
"""

from __future__ import annotations

from pathlib import Path

from assistant.contracts import ITaskAgent, Manifest, Module, ModuleContext
from assistant.infra import ClaudeSession, SessionTaskAgent, claude_command

WORKER_PROMPT = """\
You are the Main Assistant of a personal AI assistant. Tasks are handed to you \
by another agent that talks with the user; you never talk with the user directly.

- Work only inside your current folder.
- Before each major step, write one short line saying what you're about to do.
- If you need a decision from the user, stop and end your turn with a last line \
`NEED: <question>`. You'll get the answer as the next message.
- When you're finished, end with a short summary of what you did.
- If a message starts with "[The user interrupted your task", answer it briefly and \
stop; you'll be told when to continue."""


class MainAssistantModule(Module):
    manifest = Manifest(id="main_assistant", provides=(ITaskAgent,))

    async def init(self, ctx: ModuleContext) -> None:
        self._ctx = ctx
        self._workspace = Path(ctx.config.get("workspace", "workspace")).resolve()
        command = claude_command(
            model=ctx.config.get("model"),
            tools=ctx.config.get("tools", "Read,Write,Edit,Glob,Grep"),
            permission_mode=ctx.config.get("permission_mode", "acceptEdits"),
            system_prompt=WORKER_PROMPT,
            program=ctx.config.get("program", ["claude"]),
        )
        self._session = ClaudeSession(command, cwd=self._workspace, log=ctx.log)
        self._agent = SessionTaskAgent(
            self._session,
            ctx,
            agent_id=self.manifest.id,
            description="The main assistant: reasons, plans, and does the work",
            capabilities=("general", "files"),
        )
        ctx.provide(ITaskAgent, self._agent)

    async def start(self) -> None:
        self._workspace.mkdir(parents=True, exist_ok=True)
        await self._session.start()

    async def stop(self) -> None:
        await self._agent.close()
        await self._session.close()
