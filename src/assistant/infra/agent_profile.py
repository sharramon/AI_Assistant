"""What makes one `claude` task agent: its folders, access, command line and shared prompt block.

Every task agent (the Main Assistant today, the `task_agents` profiles next) differs only in
config, so the folder and access code lives here once. `AgentProfile.command` builds the
session's command for a permission mode; `prompt_block` is the part of every agent's prompt
that explains the two kinds of message (`STATUS:` for the coordinator, `NEED:` for you).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from assistant.contracts import PermissionMode
from assistant.infra.claude_session import claude_command, path_rule
from assistant.infra.mcp_door import READ_ONLY as DOOR_READ_TOOLS

DOOR_PROMPT = """

The app's modules: your `modules` tools reach every module's menu through the app's core. \
Call `list_modules` (one line each), then `show_menu` for the module you need, then \
`use_item` with an item's name and inputs (for example `modules.docs` with a module's id). \
Module control (on, off, reload, add) is the `core` menu. The SHOW, RELOAD and ADD_MODULE \
lines still work as before."""

# The Claude in Chrome tools' names, and the two that list and close the session's own tabs:
# allowed with no card for an agent with Chrome (docs/next-steps/chrome-tabs-close.md).
CHROME_TOOLS = "mcp__claude-in-chrome__"
CHROME_CLOSE_TAB = CHROME_TOOLS + "tabs_close_mcp"
CHROME_TAB_TOOLS = (CHROME_TOOLS + "tabs_context_mcp", CHROME_CLOSE_TAB)

# For an agent with an access list (a task-agent module's), when it has the door.
REQUEST_PROMPT = """
- More access: if a task needs a folder, a shell command, a Python or Chrome you don't have, \
ask with `permissions.request` on the `core` menu (`use_item`), with a short reason. The user \
answers on a card; the answer reaches you as a note, and what they allow applies from your \
next session (your next task or handoff). Don't ask to be restarted."""

# What every agent is told, whatever its job (once here, not in each module's prompt).
BASICS_BLOCK = """

- Your access is listed at the end of this prompt.
- Before each major step, write one short line saying what you're about to do.
- Chrome tabs belong to your session: a new one (a new task) can't see or reach them. A \
handoff keeps your session (its context is compacted) when you use Chrome, but if that fails \
you start fresh. So before a `HANDOFF:`, write each open tab's URL and state (filled or not, \
saved on the site or not) into the note, and save or finish unsaved form work first. In a \
fresh session, reopen the note's URLs in your own tab group; don't look for the old tabs.
- Close a Chrome tab (`tabs_close_mcp`) as soon as you're done with its page. Keep it while you \
still need it, while a question to the user is about it, and across a handoff. Before your \
final reply, close each tab of yours you don't need any more (`tabs_context_mcp` lists them), \
except one the user should act on (a filled form for them to submit): name that one in the reply.
- When you're finished, end with a short summary of what you did."""

# The two kinds of message (multi-agent, section 8), for a helper agent.
HELPER_BLOCK = """

Other agents work alongside you; the Main Assistant coordinates. You have two kinds of \
message, and they never mix:
- Status for the Main Assistant: when you reach a big milestone (a step finished, a result \
ready, a blocker), write a line on its own: `STATUS: <one short line>`. One line, no detail; \
the work itself stays in your own view. Not for routine progress.
- Questions for the user: end your turn with a last line `NEED: <question>`, or use a tool \
that asks for permission. These wait until the user turns to you, possibly much later, so \
each question must make sense on its own.
Never put a question in a STATUS line, and never a status in NEED."""

# The coordinator's half names other modules' menus, so it lives with the coordinator's module
# (`main_assistant.COORDINATOR_BLOCK`), passed in as its `role_block` (principle 21).

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
# The claude modes a session may start in from config: every session starts in Manual, so a
# config can't skip the prompts (agent-permissions, decision 8). Anything else falls back.
MANUAL_CLAUDE_MODES = ("default", "acceptEdits", "plan")
MANUAL_FALLBACK = "acceptEdits"

log = logging.getLogger(__name__)


def manual_claude_mode(value: Any) -> str:
    """The claude mode a session starts in from config's `permission_mode`: one of
    `MANUAL_CLAUDE_MODES`, else `acceptEdits` (with a warning), so no list starts it in Auto."""
    if value is None or value in MANUAL_CLAUDE_MODES:
        return value or MANUAL_FALLBACK
    log.warning("permission_mode %r isn't a Manual mode; the session starts in %s", value, MANUAL_FALLBACK)
    return MANUAL_FALLBACK


@dataclass(frozen=True)
class AgentProfile:
    """One task agent's settings: from its config section (`from_config`).

    `role_block`: its half of the shared prompt block, after the basics: a helper's
    (`HELPER_BLOCK`, the default), or the coordinator's, which its module passes in.
    """

    agent_id: str
    workspace: Path
    read_dirs: tuple[str, ...] = ()
    write_dirs: tuple[str, ...] = ()
    allowed_commands: tuple[str, ...] = ()
    tools: str = "Read,Write,Edit,Glob,Grep"
    model: str | None = None
    claude_mode: str = "acceptEdits"  # the claude permission mode in Manual
    permission_prompts: bool = True
    program: tuple[str, ...] = ("claude",)
    role_block: str = HELPER_BLOCK
    chrome: bool = False  # the Claude in Chrome tools (`--chrome`)
    python: str | None = None  # a Python it may run, with any arguments
    requests: bool = False  # it holds an access list and may ask for more (`permissions.request`)

    @classmethod
    def from_config(cls, agent_id: str, config: dict[str, Any], role_block: str = HELPER_BLOCK) -> AgentProfile:
        """From a config section: `workspace`, `read_dirs`, `write_dirs`, `allowed_commands`,
        `python`, `tools`, `model`, `permission_mode` (a Manual claude mode only:
        `manual_claude_mode`), `permission_prompts`, `program`, `chrome`, `permission_requests`
        (its prompt says how to ask for more access). A task-agent module passes the granted
        config (`agent_access.granted_config`)."""
        return cls(
            agent_id=agent_id,
            workspace=Path(config.get("workspace", "workspace")).resolve(),
            read_dirs=tuple(config.get("read_dirs", ())),
            write_dirs=tuple(config.get("write_dirs", ())),
            allowed_commands=tuple(config.get("allowed_commands", ())),
            python=str(config.get("python") or "").strip() or None,
            tools=config.get("tools", "Read,Write,Edit,Glob,Grep"),
            model=config.get("model"),
            claude_mode=manual_claude_mode(config.get("permission_mode")),
            permission_prompts=config.get("permission_prompts", True),
            program=tuple(config.get("program", ("claude",))),
            role_block=role_block,
            chrome=bool(config.get("chrome", False)),
            requests=bool(config.get("permission_requests", False)),
        )

    def write_folders(self) -> tuple[str, ...]:
        """Every folder it may write, resolved: its workspace and its `write_dirs`
        (`AgentInfo.write_folders`, for the Hub's folder-clash check)."""
        return (str(self.workspace), *(str(Path(d).resolve()) for d in self.write_dirs))

    def command(self, prompt: str, mode: PermissionMode, door: dict | None = None, snips: str | None = None) -> list[str]:
        """The session's command line and prompt for `mode`: `prompt`, the shared block, the
        access section, and the door's note when `door` (an `IModuleDoor.mcp_config`) is given.
        `snips`: the launch's snips folder (`ctx.logs.folder()/snips`), read with no card and
        not on any access list, since it holds only what the user snipped or pasted.

        Both modes keep the standing rules and the permission prompts, so a switch to Manual
        mid-task (a live `set_permission_mode`) asks through the cards again. Auto adds
        `bypassPermissions`, the `git push` block, and the risky-step rule in the prompt.
        With the door, its two read-only tools are allowed; `use_item` asks with a card in
        Manual, like any tool outside the rules.
        """
        allowed = [path_rule("Read", d) for d in self.read_dirs] + [path_rule("Edit", d) for d in self.write_dirs]
        if snips:
            allowed.append(path_rule("Read", snips))
        allowed += [rule for c in self.allowed_commands for rule in command_rules(c)]
        if self.python:
            allowed += command_rules(self.python)
        if door:
            allowed += list(DOOR_READ_TOOLS)
        if self.chrome:
            allowed += list(CHROME_TAB_TOOLS)  # listing and closing its own tabs asks no card
        auto =mode is PermissionMode.AUTO
        return claude_command(
            model=self.model,
            tools=self.tools,
            permission_mode=AUTO_CLAUDE_MODE if auto else self.claude_mode,
            allowed=allowed,
            disallowed=AUTO_BLOCKED if auto else (),
            permission_prompts=self.permission_prompts,
            system_prompt=prompt + prompt_block(self.role_block) + self.access(mode, snips)
            + (REQUEST_PROMPT if self.requests and door else "") + (DOOR_PROMPT if door else ""),
            program=list(self.program),
            mcp_config=door or None,
            chrome=self.chrome,
        )

    def access(self, mode: PermissionMode, snips: str | None = None) -> str:
        """The access section of the prompt, so the agent knows its permissions without probing."""
        lines = [f"\n\nYour access:\n- Read and write: {self.workspace} (your working folder)"]
        lines += [f"- Read: {Path(d).resolve()}" for d in self.read_dirs]
        if snips:
            lines.append(f"- Read: {snips} (the user's snips and pasted images)")
        lines += [f"- Write: {Path(d).resolve()}" for d in self.write_dirs]
        if self.allowed_commands:
            lines.append("- These shell commands, with any arguments, written exactly so and run one per call: "
                         + "; ".join(f"`{c}`" for c in self.allowed_commands))  # fmt: skip
        if self.python:
            lines.append(f"- Python: `{self.python}`, with any arguments, written exactly so and run one per call")
        if self.chrome:
            lines.append("- Chrome: the Claude in Chrome tools")
        lines.append(AUTO_ACCESS if mode is PermissionMode.AUTO else MANUAL_ACCESS)
        return "\n".join(lines)


def prompt_block(role_block: str = HELPER_BLOCK) -> str:
    """The shared part of every agent's prompt: the basics every agent is told, then its role's
    half (`HELPER_BLOCK`, or the coordinator's from its module)."""
    return BASICS_BLOCK + role_block


def command_rules(command: str) -> list[str]:
    """Permission rules allowing a shell command with any arguments, e.g.
    `PowerShell(ruff check)` and `PowerShell(ruff check *)`."""
    tool = "PowerShell" if os.name == "nt" else "Bash"
    return [f"{tool}({command})", f"{tool}({command} *)"]


def hook_env(agent_id: str, task_file: Path, edit_note: bool) -> dict[str, str]:
    """What an agent's process tells the edit hook (scripts/hooks/edit_tracker.py): that
    it's this app's agent, where its current task id is, and whether the note is on."""
    return {
        "ASSISTANT_AGENT": agent_id,
        "ASSISTANT_TASK_FILE": str(task_file),
        "ASSISTANT_EDIT_NOTE": "1" if edit_note else "0",
    }
