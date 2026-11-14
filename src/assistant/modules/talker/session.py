"""One Talker conversation: the session of one agent tab, talking for its agent (its partner).

The talker module keeps one `TalkerSession` per agent tab and routes each event to the right
one; the main tab's partner is the coordinator (the Main Assistant). Each session has its own
`claude` process, inbox and turn loop, history, open cards and transcript. Its tags act on its
partner: WORK starts a task on it, ASK / PAUSE / LOOK / CANCEL / MODE / PASS reach its task,
ALLOW / DENY answer its own cards. Only the main tab's session restarts the app.
"""

from __future__ import annotations

import asyncio
import re
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from assistant.contracts import (
    AnswerPermissionRequest,
    IModuleDoor,
    InvokeTool,
    PermissionMode,
    PermissionRequested,
    ResetRequested,
    ResponseReady,
    Result,
    TaskInfo,
)
from assistant.infra import (
    ClaudeSession,
    claude_command,
    find_tags,
    parse_show,
    session_usage,
    show_page,
    subagent_usage,
)
from assistant.infra.mcp_door import TOOL_NAMES as DOOR_TOOLS
from assistant.modules.talker.prompt import talker_prompt

if TYPE_CHECKING:
    from assistant.modules.talker.module import TalkerModule

TAG_NAMES = ("WORK", "LOOK", "ASK", "PAUSE", "CANCEL", "ALLOW", "DENY", "THEME", "SHOW", "RESET", "MODE", "RESTART",
             "AGENTS", "FOCUS", "PASS")  # fmt: skip
TALKER_ID = "talker"  # the main tab's session id in SessionUsage, ContextWatch and ResetRequested
ACCESS_CARD = "access:"  # how a permissions handler card is keyed among the open cards
MANY_CARDS = ("More than one permission request is open ({cards}). Ask the user which one they mean, "
              "then answer it with ALLOW or DENY and the agent's name.")  # fmt: skip
RESET_CONTEXT = "[Context] Your session was just reset to save space. The conversation so far, newest last:\n{history}"
SPOKEN = "[Spoken] "  # before input from voice_in (InputReceived source "voice")
ONLY_YOU_AUTO = "Only the user can switch {agent} to Auto, with the button in the app. Tell them so."
RESTART_HERE = "Restarting the app is the Main Assistant's: tell the user to ask in the Main Assistant's tab."
SORRY = "Sorry, something went wrong on my side."


def access_card_text(event: PermissionRequested) -> str:
    """One permissions handler card in words: who asks and why, the items, the notes, reviewed."""
    name = event.module_id if event.subject in ("", event.module_id) else f"{event.module_id} → {event.subject}"
    if event.action == "access":
        head = f"{name} asks for its access list"
    elif event.action == "confirm":  # a risky step: ALLOW runs it, DENY runs nothing
        return f"{event.caller or name} asks you to confirm: {event.reason}. ALLOW runs it; DENY runs nothing."
    elif event.action == "message":  # ALLOW sends it once; "Always allow" is the card's button
        head = f"{event.caller} wants to message {', '.join(i.target for i in event.items)} (ALLOW: this once)"
        return head + (f". {event.reason}" if event.reason else ".")
    else:
        head = f"{event.caller} asks to {event.action} access for {name}"
    parts = [head + (f" ({event.reason})" if event.reason else "") + "."]
    if event.items:
        parts.append("The list: " + "; ".join(i.label for i in event.items) + ".")
    parts += [f"{'Refused' if n.source == 'refused' else 'Warning'}: {n.text}" for n in event.notes]
    if event.reviewed is False:
        parts.append("Not reviewed (the Main Assistant was busy or didn't answer in time).")
    return " ".join(parts)


def split_tags(reply: str) -> tuple[str, list[tuple[str, str]]]:
    """Split a Talker reply into the text to show and its (tag, argument) pairs, in order."""
    found = find_tags(reply, TAG_NAMES)
    tags = [(tag.name, tag.argument) for tag in found]
    kept, last = [], 0
    for tag in found:
        kept.append(reply[last:tag.start])
        last = tag.end
    kept.append(reply[last:])
    text = re.sub(r"[ \t]+\n", "\n", "".join(kept)).strip()
    # A page opened for the user always comes with its path, so the chat shows its button.
    for tag, argument in tags:
        path = parse_show(argument).path if tag == "SHOW" else ""
        if path and path not in text:
            text = f"{text}\n{path}".strip()
    return text, tags


@dataclass
class Item:
    text: str
    input_id: str | None = None  # set when the item is your input; the reply is correlated to it
    conversation_id: str | None = None
    source: str | None = None  # the input's source; "voice" is marked [Spoken]
    reset: bool = False  # not a message: reset the session, in turn with the messages
    restart_note: bool = False  # the last session's reset instructions: deleted once sent


class TalkerSession:
    """The Talker of one agent tab. `talker` is the module (the router) it shares state with,
    reached only through its methods for the sessions (`name`, `description`, `task_of`,
    `task_started`, `usage_of`, `hub`, `notes_for`, `send_theme`, `check_size`, `restart`) and
    its `ctx`, `worker_id` and `turn_timeout`; it never changes the module's fields itself.
    Each tag is run by its handler in `_tags` (principle 20)."""

    def __init__(self, talker: TalkerModule, partner: str, history: list[str] | tuple[str, ...] = ()) -> None:
        self.talker = talker
        self.partner = partner
        self.main = partner == talker.worker_id
        self.id = TALKER_ID if self.main else f"{TALKER_ID}:{partner}"
        ctx = talker.ctx
        self.history: deque[str] = deque(history, maxlen=2 * ctx.config.get("context_exchanges", 6))
        self.cards: dict[str, tuple[str, str]] = {}  # open permission cards you've been told: task → (agent, text)
        self.answered: set[str] = set()  # tasks whose next "permission ..." update is our own answer
        self.viewer_seen = 0  # the viewer note told so far (the module's sequence number)
        self._carry_over = bool(self.history)  # handed a history (a reload or a reset): tell the new session
        self._inbox: asyncio.Queue[Item] = asyncio.Queue()
        self._turn: asyncio.Future[dict[str, Any]] | None = None
        self._loop_task: asyncio.Task | None = None
        # One handler per tag, each `(tag, argument, item)`; THEME is handled in `_handle`.
        self._tags: dict[str, Callable[[str, str, Item], Awaitable[None]]] = {
            "THEME": self._tag_theme, "SHOW": self._tag_show, "MODE": self._tag_mode, "WORK": self._tag_work,
            "LOOK": self._tag_look, "AGENTS": self._tag_agents, "FOCUS": self._tag_focus, "PASS": self._tag_pass,
            "RESET": self._tag_reset, "RESTART": self._tag_restart, "ALLOW": self._tag_answer,
            "DENY": self._tag_answer, "CANCEL": self._tag_cancel, "ASK": self._tag_send, "PAUSE": self._tag_send,
        }  # fmt: skip
        transcript = ctx.config.get("transcript")
        if transcript and not self.main:
            name = Path(transcript)
            transcript = f"{name.stem}-{partner}{name.suffix}"
        self.session = ClaudeSession(
            self.command,  # read at each session start: the module door may have come up since
            cwd=ctx.config.get("cwd"),
            log=ctx.log,
            on_event=self._on_event,
            transcript=ctx.logs.sink(transcript) if transcript else None,
        )

    # --- lifecycle ---

    def start(self) -> None:
        """Start the turn loop. The `claude` process starts on the first turn, unless `warm` ran."""
        self._loop_task = asyncio.create_task(self._run(), name=f"{self.id}:inbox")

    async def warm(self) -> None:
        """Start the `claude` process now (the main tab's, kept warm)."""
        await self.session.start()
        self.publish_usage()

    async def close(self) -> None:
        if self._loop_task:
            self._loop_task.cancel()
            await asyncio.gather(self._loop_task, return_exceptions=True)
        await self.session.close()

    def busy(self) -> bool:
        return self._turn is not None and not self._turn.done()

    def put(self, item: Item) -> None:
        self._inbox.put_nowait(item)

    def status(self, text: str) -> None:
        """A [Status] turn in this tab."""
        self.put(Item(f"[Status] {text}"))

    # --- turns ---

    def _on_event(self, event: dict[str, Any]) -> None:
        if self._turn is None or self._turn.done():
            return
        if event.get("type") == "result":
            self._turn.set_result(event)
        elif event.get("type") == "exit":
            self._turn.set_exception(RuntimeError(f"The Talker's claude process ({self.partner}'s tab) exited"))

    async def _run(self) -> None:
        while True:
            item = await self._inbox.get()
            try:
                if item.reset:
                    await self._reset()
                    continue
                await self._handle(item)
            except Exception:
                self.talker.ctx.log.exception("Talker turn failed (%s's tab)", self.partner)
                if item.input_id:
                    self._say(SORRY, item)
                    self.talker.send_theme([], item.text)

    async def _reset(self) -> None:
        await self.session.close()
        await self.session.start()
        self._carry_over = bool(self.history)
        self.publish_usage()

    async def _handle(self, item: Item) -> None:
        talker = self.talker
        said = SPOKEN + item.text if item.source == "voice" else item.text  # what the session and history see
        prompt, images = said, []
        if item.input_id:
            notes, images = talker.notes_for(self, item)
            prompt = "\n".join([f"{await self._usage_line()}", *notes, prompt])
        if self._carry_over:
            prompt = RESET_CONTEXT.format(history="\n".join(self.history)) + "\n\n" + prompt
            self._carry_over = False
        result = await self._take_turn(prompt, images)
        if item.restart_note:
            talker.restart.used()
        self.publish_usage()
        text, tags = split_tags(result.get("result") or "")
        if result.get("is_error") and not text:
            text = SORRY
        self.history.append(f"User: {said}" if item.input_id else said)
        if text:
            self.history.append(f"Assistant: {text}")
            self._say(text, item)
        if item.input_id:
            talker.send_theme(tags, item.text)
        for tag, argument in tags:
            await self._run_tag(tag, argument, item)

    async def _take_turn(self, text: str, images: list[str] | None = None) -> dict[str, Any]:
        if not self.session.running:
            await self.session.start()
        self._turn = asyncio.get_running_loop().create_future()
        try:
            await self.session.send(text, images or ())
        except OSError as exc:  # a snip's image is gone: send the text alone
            self.talker.ctx.log.warning("Couldn't attach the snip: %s", exc)
            await self.session.send(text)
        timeout = self.talker.turn_timeout
        try:
            return await asyncio.wait_for(asyncio.shield(self._turn), timeout)
        except TimeoutError:
            self.talker.ctx.log.warning("Talker turn (%s's tab) took over %ss; interrupting", self.partner, timeout)
            await self.session.interrupt()
            return await asyncio.wait_for(self._turn, 10)

    def command(self) -> list[str]:
        """This tab's command line, with the module door when the core offers it. All three door
        tools are allowed (the Talker has no Claude Code prompts); every `use_item` still passes
        the core's one gate in `dispatch_tool`: items marked `ask` show you a confirm card first
        (the Talker is never in Auto, so `ask="risky"` items card too)."""
        ctx, talker = self.talker.ctx, self.talker
        door = ctx.get_one(IModuleDoor) if ctx.config.get("door", True) else None
        mcp = door.mcp_config(talker.manifest.id) if door is not None else {}
        prompt = talker_prompt(self.partner, talker.worker_id, talker.description(self.partner), door=bool(mcp))
        return claude_command(
            model=ctx.config.get("model", "sonnet"),
            tools="",
            allowed=list(DOOR_TOOLS) if mcp else (),
            system_prompt=prompt,
            program=ctx.config.get("program", ["claude"]),
            mcp_config=mcp or None,
        )

    def _say(self, text: str, item: Item) -> None:
        self.talker.ctx.publish(ResponseReady(text=text, correlation_id=item.input_id,
                                              conversation_id=item.conversation_id, agent_id=self.partner))  # fmt: skip

    # --- usage ---

    def publish_usage(self) -> None:
        ctx = self.talker.ctx
        usage = session_usage(self.id, self.session)
        if not self.main:  # listed under its agent in the usage tally
            usage = usage.model_copy(update={"parent": self.partner})
        ctx.publish(usage)
        for sub in subagent_usage(self.id, self.session):  # none while it has no tools
            ctx.publish(sub)
        self.talker.check_size(self.id, usage.context_tokens, self)

    async def _usage_line(self) -> str:
        """This tab's agent's usage (with its sub-agents, from `usage.mine`, without this Talker),
        this Talker's own, and every agent's total (`usage.total`). Without the `usage` module:
        that agent's own."""
        ctx, partner = self.talker.ctx, self.partner
        label = "worker" if self.main else partner
        mine = await ctx.send(InvokeTool(name="usage.mine", args={"agent_id": partner}))
        if mine.is_ok and isinstance(mine.value, dict) and mine.value.get("total", {}).get("used_tokens"):
            row = mine.value
            used = row["total"]["used_tokens"]
            for child in row.get("children", ()):  # this Talker's own row is told apart
                if child.get("agent_id") == self.id:
                    used -= child["total"]["used_tokens"]
            agent = describe_usage(row["context_tokens"], used)
        elif (seen := self.talker.usage_of(partner)) is not None:
            agent = describe_usage(seen.context_tokens, seen.used_tokens)
        else:
            agent = "not started"
        own = session_usage(self.id, self.session)
        line = f"[Usage] {label}: {agent} · you: {describe_usage(own.context_tokens, own.used_tokens)}"
        total = await ctx.send(InvokeTool(name="usage.total")) if mine.is_ok else mine
        if total.is_ok and isinstance(total.value, dict):
            line += f" · all agents: used {tokens_text(total.value['used_tokens'])}"
        return line

    # --- tags: each acts on this tab's agent ---

    def _pick_card(self, argument: str) -> str | None:
        """The task whose permission card ALLOW / DENY answers; None (with a status) if it's unclear."""
        if argument:
            match = [task for task, (agent, _) in self.cards.items() if argument in (agent, task)]
            if not match:
                self.status(f"There's no open permission request from {argument}.")
            return match[0] if match else None
        if not self.cards:
            self.status("There's no open permission request.")
            return None
        if len(self.cards) > 1:  # a bare "yes" can't tell which
            cards = "; ".join(f"{self.talker.name(agent)}: {text}" for agent, text in self.cards.values())
            self.status(MANY_CARDS.format(cards=cards))
            return None
        return next(iter(self.cards))

    async def _run_tag(self, tag: str, argument: str, item: Item) -> None:
        if (handler := self._tags.get(tag)) is not None:
            await handler(tag, argument, item)

    async def _tag_theme(self, tag: str, argument: str, item: Item) -> None:
        return  # handled in _handle

    async def _tag_show(self, tag: str, argument: str, item: Item) -> None:
        # `path`, or `path | "quoted text" | heading` to highlight part of the page.
        show, result = outcome = await show_page(self.talker.ctx, argument)
        if not result.is_ok:
            self.status(f"Couldn't open {show.path} in the viewer: {result.error}")
        elif outcome.quote_missing:
            self.status(f'Opened {show.path}, but "{show.quote}" isn\'t on the page, so nothing is highlighted.')

    async def _tag_mode(self, tag: str, argument: str, item: Item) -> None:
        # Manual only: switching to Auto takes the user's own click.
        name = self.talker.name(self.partner)
        if argument.strip().lower() != PermissionMode.MANUAL:
            self.status(ONLY_YOU_AUTO.format(agent=name))
            return
        result = await self.talker.hub("hub.mode", agent_id=self.partner, mode=PermissionMode.MANUAL.value)
        if not result.is_ok:
            self.status(f"Couldn't switch {name} to Manual: {result.error}")

    async def _tag_work(self, tag: str, argument: str, item: Item) -> None:
        talker, partner = self.talker, self.partner
        result = await talker.hub("hub.start", text=argument, agent_id=partner, context="\n".join(self.history))
        if result.is_ok:
            talker.task_started(result.value, partner)
        else:
            self.status(f"{talker.name(partner)} couldn't take the task: {result.error}")

    async def _tag_look(self, tag: str, argument: str, item: Item) -> None:
        talker = self.talker
        result = await talker.hub("hub.status", task_id=talker.task_of(argument.strip() or self.partner))
        self.status(describe_tasks(result.value) if result.is_ok else f"Couldn't get the status: {result.error}")

    async def _tag_agents(self, tag: str, argument: str, item: Item) -> None:
        result = await self.talker.hub("hub.agents")
        self.status(describe_agents(result.value) if result.is_ok else f"Couldn't list the agents: {result.error}")

    async def _tag_focus(self, tag: str, argument: str, item: Item) -> None:
        result = await self.talker.hub("hub.focus", agent_id=argument.strip())
        if not result.is_ok:
            self.status(f"Couldn't switch to {argument.strip()}: {result.error}")

    async def _tag_pass(self, tag: str, argument: str, item: Item) -> None:
        if not item.input_id:
            return  # only the user's own message passes through
        # No task id: this tab's agent, word for word.
        result = await self.talker.hub("hub.send", text=item.text, agent_id=self.partner)
        if not result.is_ok:
            self.status(f"Couldn't pass that to {self.talker.name(self.partner)}: {result.error}")

    async def _tag_reset(self, tag: str, argument: str, item: Item) -> None:
        if argument.lower().startswith("talker"):  # this Talker's own session: its own code
            self.talker.reset_session(self.id)
            return
        result = await self.talker.ctx.send(ResetRequested(agent_id=self.partner))  # the Hub handles it
        if not result.is_ok:
            self.status(f"Couldn't reset {self.talker.name(self.partner)}: {result.error}")

    async def _tag_restart(self, tag: str, argument: str, item: Item) -> None:
        if not self.main:
            self.status(RESTART_HERE)
            return

        async def restart() -> Result:
            await self.talker.restart.ask()
            return Result.ok("the Main Assistant writes the reset note, then the app restarts")

        # Never without your yes on a confirm card, in Auto too; the card's answer runs it.
        result = await self.talker.ctx.permissions.confirm("restart the app", restart, caller=self.id)
        self.status(result.value if result.is_ok else f"Couldn't ask to restart: {result.error}")

    async def _tag_answer(self, tag: str, argument: str, item: Item) -> None:
        """ALLOW / DENY: answer one open permission card."""
        task_id = self._pick_card(argument.strip())
        if task_id is None:
            return
        ctx = self.talker.ctx
        self.answered.add(task_id)
        if task_id.startswith(ACCESS_CARD):  # the permissions handler's card: all of it, or nothing
            # remember=False: a message card allowed in words goes once (others ignore it)
            answer = AnswerPermissionRequest(request_id=task_id.removeprefix(ACCESS_CARD), allow=tag == "ALLOW",
                                             remember=False)  # fmt: skip
            result = await ctx.send(answer)
        else:
            result = await self.talker.hub("hub.answer", task_id=task_id, allow=tag == "ALLOW")
        if result.is_ok:
            self.cards.pop(task_id, None)
        else:
            self.answered.discard(task_id)
            self.status(f"Couldn't answer the permission request (maybe already answered): {result.error}")

    async def _tag_cancel(self, tag: str, argument: str, item: Item) -> None:
        talker = self.talker
        agent = argument.strip() or self.partner
        if (task_id := talker.task_of(agent)) is None:
            self.status(f"{talker.name(agent)} has no task to cancel.")
            return
        result = await talker.hub("hub.cancel", task_id=task_id)
        if not result.is_ok:
            self.status(f"Couldn't cancel the task: {result.error}")

    async def _tag_send(self, tag: str, argument: str, item: Item) -> None:
        """ASK / PAUSE: a message to this tab's agent's task (PAUSE also pauses it)."""
        if (task_id := self.talker.task_of(self.partner)) is None:
            self.status("There's no task to send that to.")
            return
        result = await self.talker.hub("hub.send", text=argument, task_id=task_id, pause=tag == "PAUSE")
        if not result.is_ok:
            self.status(f"Couldn't reach the task: {result.error}")


def describe_usage(context: int, used: int) -> str:
    """`context 145k (last call), used 2.3M (incl. resent cache)`."""
    return f"context {k_text(context)} (last call), used {tokens_text(used)} (incl. resent cache)"


def k_text(tokens: int) -> str:
    return f"{round(tokens / 1000)}k"


def tokens_text(tokens: int) -> str:
    return f"{tokens / 1_000_000:.1f}M" if tokens >= 1_000_000 else k_text(tokens)


def describe_agents(agents: list[dict]) -> str:
    """`hub.agents` as lines: names and marks only, never a held question's text."""
    if not agents:
        return "No agents are running."
    lines = []
    for agent in agents:
        marks = [m for m, on in (("talking to the user", agent.get("focused")), ("working", agent.get("state") == "active"),
                                 ("has something waiting (!)", agent.get("held"))) if on]  # fmt: skip
        lines.append(f"{agent['agent_id']}: {', '.join(marks) or 'idle'}")
    return "\n".join(lines)


def describe_tasks(tasks: list[TaskInfo]) -> str:
    if not tasks:
        return "No tasks."
    lines = []
    for task in tasks:
        lines.append(f"Task {task.id} is {task.state}: {task.text}")
        if task.question:
            lines.append(f"  Waiting for the answer to: {task.question_line}")
        lines += [f"  {report}" for report in task.recent[-3:]]
        if task.activity and not task.state.is_final:
            lines.append("  Recent activity, newest last:")
            lines += [f"    {line[:200]}" for line in task.activity]
        if task.result and task.state.is_final:
            lines.append(f"  Result: {task.result}")
    return "\n".join(lines)
