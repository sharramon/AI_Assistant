"""The Main Assistant: the worker. A `claude` session with file tools, working in its own folder.

Provides `ITaskAgent` through a composed `SessionTaskAgent`; only the Agent Hub
calls it. Its process starts with the module and stops with it; each task gets
a fresh one (`fresh_sessions`). A `ResetRequested` for it resets the session.
Each session's command line and prompt are built for the agent's permission
mode at that moment (`build_command`): Manual at every launch, Auto only from
the UI button.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from assistant.contracts import (
    AgentActivity,
    AgentStateChanged,
    ITaskAgent,
    Manifest,
    ModuleContext,
    ModuleProtocol,
    PermissionMode,
    PermissionModeChanged,
    ReportTask,
    ResetRequested,
    SessionUsage,
)
from assistant.infra import ClaudeSession, SessionTaskAgent, claude_command
from assistant.infra.claude_session import path_rule

WORKER_PROMPT = """\
You are the Main Assistant of a personal AI assistant. Tasks are handed to you \
by another agent that talks with the user; you never talk with the user directly. \
To the user, you and that agent are one assistant.

- Your access is listed at the end of this prompt.
- Before each major step, write one short line saying what you're about to do.
- If you need a decision from the user, stop and end your turn with a last line \
`NEED: <question>`. You'll get the answer as the next message.
- When you're finished, end with a short summary of what you did.
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

MANUAL_ACCESS = """\
- If a task needs more than this, just use the tool: the user is asked to allow or deny \
that one use. If it's denied, don't try another way around it; say what was denied and \
continue without it, or end with NEED.
- Anything else, including other shell commands: the user is asked each time."""

AUTO_ACCESS = """\
- Auto mode: you have full permissions for every tool, and nothing asks the user, \
except `git push`, which is blocked.

Before a very risky step, stop and ask first: end your turn with \
`NEED: Risky: <what you want to do and why>`. Continue once the user answers. Very risky means:
- deleting data or files beyond what the task needs
- rewriting git history (`reset --hard`, `rebase`, force anything, deleting branches)
- changing secrets, credentials, or settings (`config/`, `.env`, `.claude/settings*`, \
system or account settings)
- installing, upgrading, or removing packages or programs
- spending money, or calling a paid service
- sending anything outside this machine (email, posts, uploads)
- anything else that's hard to undo

If you're unsure whether a step counts, ask. `git push` is blocked: if the task needs \
one, say so in your summary and the user pushes."""

# Auto's one hard block. Refused even under bypassPermissions, with no prompt (checked
# against the real claude, 2026-11-02). Both shells: claude may offer either.
AUTO_BLOCKED = tuple(f"{tool}(git push{args})" for tool in ("PowerShell", "Bash") for args in ("", " *"))
AUTO_CLAUDE_MODE = "bypassPermissions"


class MainAssistantModule(ModuleProtocol):
    manifest = Manifest(
        id="main_assistant",
        description="The worker: does the tasks the Talker hands over",
        provides=(ITaskAgent,),
        sends=(ReportTask,),
        publishes=(AgentActivity, AgentStateChanged, SessionUsage, PermissionModeChanged,),
        listens=(ResetRequested,),
    )

    async def init(self, ctx: ModuleContext) -> None:
        self._ctx = ctx
        self._workspace = Path(ctx.config.get("workspace", "workspace")).resolve()
        edit_note = bool(ctx.config.get("edit_note", True))
        task_file = self._workspace / ".claude" / "state" / f"{self.manifest.id}-task.txt"
        # Read on every session start, so a new session gets the mode of that moment.
        self._session = ClaudeSession(
            lambda: build_command(ctx.config, self._workspace, self._agent.permission_mode),
            cwd=self._workspace, log=ctx.log, transcript=ctx.config.get("transcript"),
            env=hook_env(self.manifest.id, task_file, edit_note),
        )
        self._agent = SessionTaskAgent(
            self._session,
            ctx,
            agent_id=self.manifest.id,
            description="The main assistant: reasons, plans, and does the work",
            capabilities=("general", "files"),
            permission_timeout=ctx.config.get("permission_timeout", 600.0),
            fresh_sessions=ctx.config.get("fresh_sessions", True),
            max_handoffs=ctx.config.get("max_handoffs", 3),
            manual_claude_mode=ctx.config.get("permission_mode", "acceptEdits"),
            context_reminder=ctx.config.get("context_reminder", 150_000),
            edit_note=edit_note,
            task_file=task_file,
        )
        ctx.provide(ITaskAgent, self._agent)
        ctx.subscribe(ResetRequested, self._on_reset)

    async def _on_reset(self, event: ResetRequested) -> None:
        if event.agent_id == self.manifest.id:
            result = await self._agent.reset()
            if not result.is_ok:
                self._ctx.log.warning("Couldn't reset: %s", result.error)

    def busy(self) -> str | None:
        """A reload waits while a task runs (no handover of the task yet)."""
        return "working on a task" if self._agent.info().busy else None

    async def start(self) -> None:
        self._workspace.mkdir(parents=True, exist_ok=True)
        await self._session.start()

    async def stop(self) -> None:
        await self._agent.close()
        await self._session.close()


def build_command(config: dict[str, Any], workspace: Path, mode: PermissionMode) -> list[str]:
    """The worker's command line and prompt for `mode`.

    Both modes keep the standing rules and the permission prompts, so a switch to Manual
    mid-task (a live `set_permission_mode`) asks through the cards again. Auto adds
    `bypassPermissions`, the `git push` block, and the risky-step rule in the prompt.
    """
    read_dirs = config.get("read_dirs", [])
    write_dirs = config.get("write_dirs", [])
    commands = config.get("allowed_commands", [])
    allowed = [path_rule("Read", d) for d in read_dirs] + [path_rule("Edit", d) for d in write_dirs]
    allowed += [rule for c in commands for rule in command_rules(c)]
    auto = mode is PermissionMode.AUTO
    return claude_command(
        model=config.get("model"),
        tools=config.get("tools", "Read,Write,Edit,Glob,Grep"),
        permission_mode=AUTO_CLAUDE_MODE if auto else config.get("permission_mode", "acceptEdits"),
        allowed=allowed,
        disallowed=AUTO_BLOCKED if auto else (),
        permission_prompts=config.get("permission_prompts", True),
        system_prompt=WORKER_PROMPT + _access(workspace, read_dirs, write_dirs, commands, mode),
        program=config.get("program", ["claude"]),
    )


def hook_env(agent_id: str, task_file: Path, edit_note: bool) -> dict[str, str]:
    """What the worker's process tells the edit hook (scripts/hooks/edit_tracker.py): that
    it's this app's worker, where its current task id is, and whether the note is on."""
    return {
        "ASSISTANT_AGENT": agent_id,
        "ASSISTANT_TASK_FILE": str(task_file),
        "ASSISTANT_EDIT_NOTE": "1" if edit_note else "0",
    }


def command_rules(command: str) -> list[str]:
    """Permission rules allowing a shell command with any arguments, e.g.
    `PowerShell(ruff check)` and `PowerShell(ruff check *)`."""
    tool = "PowerShell" if os.name == "nt" else "Bash"
    return [f"{tool}({command})", f"{tool}({command} *)"]


def _access(
    workspace: Path, read_dirs: list[str], write_dirs: list[str], commands: list[str], mode: PermissionMode
) -> str:
    """The access section of the prompt, so it knows its permissions without probing."""
    lines = [f"\n\nYour access:\n- Read and write: {workspace} (your working folder)"]
    lines += [f"- Read: {Path(d).resolve()}" for d in read_dirs]
    lines += [f"- Write: {Path(d).resolve()}" for d in write_dirs]
    if commands:
        lines.append("- These shell commands, with any arguments, written exactly so and run one per call: "
                     + "; ".join(f"`{c}`" for c in commands))
    lines.append(AUTO_ACCESS if mode is PermissionMode.AUTO else MANUAL_ACCESS)
    return "\n".join(lines)
