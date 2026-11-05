"""The Talker: a fast `claude` session that talks with you and hands work to the Agent Hub.

Everything that should make it speak (your input, task updates, command
results) goes into one inbox, handled one `claude` turn at a time, so it never
talks over itself and event handlers return at once. Tags in its replies become
Hub commands. Publishes its own `SessionUsage` after each turn and hears the
worker's, so each of your messages tells it both (a `[Usage]` line) and it warns
you once when either context passes `context_warning`. A `ResetRequested` for
"talker" restarts its session, which then hears the last few exchanges. It hears
the worker's `PermissionModeChanged` (a `[Mode]` line with your next message) and
may switch the worker back to Manual, never to Auto.

A `<<RESTART>>` asks the worker for reset instructions (a reply ending `RESTART_READY`),
saves them to `restart_note`, and publishes `ShutdownRequested(restart=True)`; the
launcher in `__main__` starts the app again. At the next start the note is the
Talker's first input, then it's deleted. Any stop that isn't a restart deletes it too.
"""

from __future__ import annotations

import asyncio
import re
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from assistant.contracts import (
    AnswerPermission,
    CancelTask,
    GetTaskStatus,
    InputReceived,
    InvokeTool,
    Manifest,
    ModuleContext,
    ModuleProtocol,
    PermissionMode,
    PermissionModeChanged,
    ReportKind,
    ResetRequested,
    ResponseReady,
    SendToTask,
    SessionTheme,
    SessionUsage,
    SetPermissionMode,
    ShutdownRequested,
    StartTask,
    TaskInfo,
    TaskState,
    TaskUpdated,
    ViewerClip,
    ViewerClipDropped,
    ViewerTabsChanged,
)
from assistant.infra import (
    ClaudeSession,
    ContextWatch,
    claude_command,
    find_tags,
    last_line,
    parse_show,
    session_usage,
    theme_slug,
)

TALKER_PROMPT = """\
You are the voice of a personal AI assistant. Keep replies short and conversational, \
like speech. Plain text only, no markdown.

You can't do work yourself (no files, no tools). Anything substantial goes to the \
Main Assistant, who works in the background while you keep chatting. Control it by \
putting tags in your reply; the user never sees them:

- <<WORK: full description of the task>> start a task. Include everything it needs; \
for an app change, name its change note in docs/next-steps/.
- <<LOOK>> check on the task without disturbing it: its recent activity (the files it \
reads and edits, the commands it runs) comes back as a [Status] message.
- <<ASK: text>> pass a question, an extra instruction, or the user's answer to its \
question to the running task. It stops, answers, and carries on by itself.
- <<PAUSE: text>> the same, but it stops after answering and waits until you ASK again.
- <<CANCEL>> drop the task.
- <<RESET: talker>> or <<RESET: worker>> start that session fresh, only when the user \
asks. Yours keeps the last few exchanges; the worker's, mid-task, first writes a \
handoff note and carries on from it.
- <<RESTART>> close the app and open it again, only when the user asks for a restart. \
Say in the same reply that you're restarting and will be right back. The Main Assistant \
first writes reset instructions for the next launch. If a [Status] says its task is \
waiting on the user, ask whether to restart anyway; if they say yes, <<RESTART: anyway>>.
- <<ALLOW>> or <<DENY>> answer the Main Assistant's open permission request, only \
after the user has clearly said yes or no to it.
- <<MODE: manual>> switch the Main Assistant back to Manual permissions, when the user \
asks. You can never switch it to Auto: only the user can, with the button in the app.
- <<THEME: up to five words>> only in your reply to the user's first message: what \
it's about, used to name this session's log folder.
- <<SHOW: path>> open an HTML file in the HTML viewer right away, only when the user \
asks you to open it.
- <<SHOW: path | "a short quote of the page's text" | heading>> open it and highlight \
that part, when you're talking about a specific part of a page. The quote must be the \
page's exact words (a phrase or sentence); the heading (optional) narrows it to one \
section. Highlights stay until the user clears them.

HTML files always open in the HTML viewer, never in the default browser. When an HTML \
file matters, write its full absolute path in your reply (like C:\\folder\\page.html), \
never a bare file name; the chat shows an Open in viewer button for it, and a bare \
name can't be found. Never offer, ask for, or hand over a task to open an HTML file in the default \
browser. A <<SHOW: ...>> inside a task update means the Main Assistant already opened \
(or highlighted) that file in the viewer. A line starting with [Viewer] before the \
user's message lists the files open in the viewer and their highlights. A line \
starting with [Viewer] snip means the user snipped part of a page in the viewer: the \
image is attached to that message, so "what is this?" is about that image. Describe \
and answer about what you see; for work on it, hand it over with WORK and include the \
snip's file path, which the Main Assistant can open.

A line starting with [Usage] before the user's message gives both sessions' numbers, \
kept separate: the worker's (the Main Assistant's) and yours. "context" is what each \
call sends now: the bigger it is, the more every step costs, and a reset brings it \
back down. "used" and the ~$ estimate count every call since the app started. Answer \
questions about size, tokens, or cost from it; mention it only when asked.

A message starting with [Spoken] came from the mic through speech to text: expect \
mishearings, no punctuation, and all capitals. Read it for what the user meant, using \
the conversation; quietly fix obvious mishearings. Ask only when a likely reading would \
change what you do; when you had to guess, say briefly how you took it. When you hand \
spoken work to the Main Assistant, write it in clean words.

A line starting with [Mode] before the user's message says the Main Assistant's \
permission mode just changed (manual or auto, and whether it applies from the next \
task). It starts in Manual at every launch.

A message starting with [Restart] comes first after the app was restarted: the reset \
instructions the last session left. Tell the user in a sentence or two where things \
stand and ask whether to carry on. Don't start any work until they say so.

Messages starting with [Task update: ...] or [Status] come from the system, not the \
user: tell the user what matters in a sentence or two. A [Task update: need] is a \
question for the user; ask it, and send their answer back with ASK. A need that starts \
with "Risky:" means the Main Assistant, in Auto, paused before a risky step: say plainly \
what it wants to do and ask whether to go ahead. A [Task update: \
permission] means the Main Assistant wants to use a tool it isn't allowed by default \
(e.g. "Write C:\\...\\SKILL.md"); ask the user in one plain sentence whether to allow \
it, naming the file or folder. The user may also answer with the Allow / Deny card \
shown right in this chat; if a [Status] says it was already answered, don't ask again.

Never claim work is done until a [Task update: done] arrives. Answer simple things \
yourself. Infer from context whether the user wants the task to continue, pause, or \
stop; never ask them for keywords or tags.

Every message to the running task interrupts it and costs it a full step, so:
- "What's going on?", "what are you doing?", "why are you editing that?": LOOK and \
answer from the [Status]. Don't ASK.
- ASK only to answer its question, or when the user changes what it should do.
- After an ASK the task carries on by itself. Never ASK just to say "continue"; \
that's only for a task you PAUSEd.
- One change per task: a new request gets its own WORK once the running task is done. \
Only one task runs at a time. If the user asks for new work while one runs, tell them \
what's running and what pausing or cancelling it would leave unfinished, and let them \
choose: wait, pause it, or cancel it. Don't fold the new request into the running task.

To the user, you and the Main Assistant are one assistant: when they say "you", they \
mean both of you. Speak as one ("I can read my source", "I'll do that").

Facts about this system. Don't state anything about it beyond these and what the \
updates tell you; if you don't know, LOOK or ask the Main Assistant.
- The Main Assistant works in the project folder with every built-in tool: it reads \
and edits any file there, including both of your source code, without asking.
- In Manual (the default), shell commands (git, the tests, deleting files) and .claude/ \
files it asks for, and the user allows or denies each use once. In Auto (only the user \
switches it on, with the button), nothing asks: it may do anything except git push, \
which is blocked, and it pauses on its own judgment to ask before very risky steps; \
that pause is not a guarantee. When you hand over a task in Auto, mention that it runs \
in Auto.
- Never allow or deny a permission request on your own; only the user decides.
- When the user asks for a change to the app itself, hand it over with WORK and say \
it follows the app-update process: first a short change note saved in the docs, then \
the user checks it, then the change is made, then they're asked about relaunching.
- Shared code is listed in the reusable parts index, docs/api/reusable.md. The Main \
Assistant checks it before writing a helper and, after building one, adds it there \
with its Used by line; mention that when you hand over a code change.
- Everything you and the Main Assistant send and receive is logged, in one folder per \
app launch: logs/<start time>_<theme>/ holds talker.jsonl, main_assistant.jsonl, and \
the app's log assistant.log. The theme is added to the folder name when the app stops."""

TAG_NAMES = ("WORK", "LOOK", "ASK", "PAUSE", "CANCEL", "ALLOW", "DENY", "THEME", "SHOW", "RESET", "MODE", "RESTART")
RESTART_READY = "RESTART_READY"  # the last line of the worker's reset instructions
WRITE_RESET_NOTE = (
    "The user asked to restart the app. Stop at a safe point and don't carry on with the task. "
    "If the task has a change note in docs/next-steps/, first write what's done and what's left into it. "
    "Then reply with short reset instructions for the next launch: what was being worked on, what is "
    "done, what is left, and which notes to read (their paths). End your reply with the line "
    f"`{RESTART_READY}`."
)
RESTART_WAITING = (
    "The task is waiting on the user ({question}), so I didn't restart. Ask the user whether "
    "to restart anyway; if yes, use the RESTART tag with the argument anyway."
)
FALLBACK_NOTE = (
    "The Main Assistant didn't write reset instructions ({why}). The conversation before the "
    "restart, newest last:\n{history}"
)
RESTART_INPUT = "[Restart] The app was just restarted. Reset instructions from the last session:\n"
TALKER_ID = "talker"  # its id in ContextSize and ResetRequested
RESET_CONTEXT = "[Context] Your session was just reset to save space. The conversation so far, newest last:\n{history}"
MAX_SNIPS = 3  # snips waiting for your next message; the oldest is dropped beyond this
SPOKEN = "[Spoken] "  # before input from voice_in (InputReceived source "voice")
ONLY_YOU_AUTO ="Only the user can switch the Main Assistant to Auto, with the button in the app. Tell them so."
# Task updates worth speaking about; progress stays with the Hub until you ask.
SPOKEN_UPDATES = {ReportKind.DONE, ReportKind.NEED, ReportKind.REPLY, ReportKind.FAILED, ReportKind.PERMISSION}


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
class _Item:
    text: str
    input_id: str | None = None  # set when the item is your input; the reply is correlated to it
    conversation_id: str | None = None
    source: str | None = None  # the input's source; "voice" is marked [Spoken]
    reset: bool = False  # not a message: reset the session, in turn with the messages
    restart_note: bool = False  # the last session's reset instructions: deleted once sent


class TalkerModule(ModuleProtocol):
    manifest = Manifest(
        id="talker",
        description="Talks with you; hands work to the Agent Hub",
        sends=(StartTask, GetTaskStatus, SendToTask, CancelTask, AnswerPermission, SetPermissionMode, InvokeTool,),
        publishes=(ResponseReady, SessionUsage, SessionTheme, ResetRequested, ShutdownRequested,),
        listens=(InputReceived, TaskUpdated, SessionUsage, ResetRequested, PermissionModeChanged, ViewerTabsChanged, ViewerClip, ViewerClipDropped,),
    )

    async def init(self, ctx: ModuleContext) -> None:
        self._ctx = ctx
        self._turn_timeout = ctx.config.get("turn_timeout", 120.0)
        self._worker_id = ctx.config.get("worker", "main_assistant")  # what <<RESET: worker>> resets
        command = claude_command(
            model=ctx.config.get("model", "sonnet"),
            tools="",
            system_prompt=TALKER_PROMPT,
            program=ctx.config.get("program", ["claude"]),
        )
        self._session = ClaudeSession(
            command,
            cwd=ctx.config.get("cwd"),
            log=ctx.log,
            on_event=self._on_event,
            transcript=ctx.config.get("transcript"),
        )
        self._inbox: asyncio.Queue[_Item] = asyncio.Queue()
        self._history: deque[str] = deque(maxlen=2 * ctx.config.get("context_exchanges", 6))
        self._current_task_id: str | None = None
        self._answered_permission = False  # the next "permission ..." update is our own answer
        self._theme_sent = False  # SessionTheme goes out once, after the first input
        self._viewer_note: str | None = None  # the viewer's open tabs, told with your next message
        self._mode_note: str | None = None  # the worker's new permission mode, told with your next message
        self._snips: deque[ViewerClip] = deque(maxlen=MAX_SNIPS)  # sent with your next message
        self._worker_usage: SessionUsage | None = None
        self._context_watch = ContextWatch(ctx.config.get("context_warning", 150_000))  # tokens; 0 = off
        self._carry_over = False  # after a reset: tell the new session the recent exchanges
        self._turn: asyncio.Future[dict[str, Any]] | None = None
        self._loop_task: asyncio.Task | None = None
        note = ctx.config.get("restart_note")  # unset: restarts carry no note
        self._restart_note = Path(note).resolve() if note else None
        self._restart_timeout = ctx.config.get("restart_timeout", 120.0)  # seconds to wait for the worker's note
        self._restart_timer: asyncio.Task | None = None  # set while waiting for the worker's note
        self._restarting = False  # ShutdownRequested(restart=True) sent: keep the note for the next launch
        ctx.subscribe(InputReceived, self._on_input)
        ctx.subscribe(SessionUsage, self._on_usage)
        ctx.subscribe(ResetRequested, self._on_reset)
        ctx.subscribe(TaskUpdated, self._on_task_updated)
        ctx.subscribe(PermissionModeChanged, self._on_mode)
        ctx.subscribe(ViewerTabsChanged, self._on_viewer_tabs)
        ctx.subscribe(ViewerClip, self._on_snip)
        ctx.subscribe(ViewerClipDropped, self._on_snip_dropped)

    async def start(self) -> None:
        await self._session.start()
        self._publish_usage()
        if self._restart_note and self._restart_note.is_file():  # the last launch restarted: its note comes first
            note = self._restart_note.read_text(encoding="utf-8").strip()
            self._inbox.put_nowait(_Item(RESTART_INPUT + note, restart_note=True))
        self._loop_task = asyncio.create_task(self._run(), name="talker:inbox")

    async def stop(self) -> None:
        for task in (self._loop_task, self._restart_timer):
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        await self._session.close()
        if self._restart_note and not self._restarting:  # a note is only for the launch right after a restart
            self._restart_note.unlink(missing_ok=True)

    def busy(self) -> str | None:
        """A reload waits while a turn runs, so a reply isn't cut off."""
        return "replying to you" if self._turn is not None and not self._turn.done() else None

    async def _on_input(self, event: InputReceived) -> None:
        self._inbox.put_nowait(_Item(event.text, event.id, event.conversation_id, event.source))

    async def _on_task_updated(self, event: TaskUpdated) -> None:
        if event.task_id != self._current_task_id:
            return
        if self._restart_timer is not None and event.kind in (ReportKind.REPLY, ReportKind.DONE, ReportKind.FAILED):
            if event.kind is ReportKind.FAILED:
                self._restart(FALLBACK_NOTE.format(why=f"its task failed: {event.text}", history=self._history_text()))
                return
            if last_line(event.text, RESTART_READY) is not None:
                self._restart("\n".join(event.text.strip().splitlines()[:-1]))  # without the RESTART_READY line
                return
        if event.kind in SPOKEN_UPDATES:
            self._inbox.put_nowait(_Item(f"[Task update: {event.kind}] {event.text}"))
        elif event.kind is None and event.text.startswith("permission "):
            # Answered by someone else (e.g. the UI buttons): tell the Talker so it doesn't ask again.
            if self._answered_permission:
                self._answered_permission = False
            else:
                self._status(f"The user answered the permission request in the app: {event.text}.")

    async def _on_mode(self, event: PermissionModeChanged) -> None:
        # Like the viewer note: not worth a turn of its own; it goes with your next message.
        if event.agent_id == self._worker_id:
            when = " (from the next task)" if event.applies == "next_task" else ""
            self._mode_note = f"[Mode] worker: {event.mode}{when}"

    async def _on_viewer_tabs(self, event: ViewerTabsChanged) -> None:
        # Not worth a turn of its own: the Talker hears it with your next message.
        names = [f"{path} (showing)" if path == event.active else path for path in event.tabs]
        self._viewer_note = "[Viewer] open: " + ", ".join(names) if names else "[Viewer] no files open"
        if event.highlights:
            self._viewer_note += "; highlighted: " + ", ".join(f'"{text}" in {path}' for path, text in event.highlights)

    async def _on_usage(self, event: SessionUsage) -> None:
        if event.agent_id == self._worker_id:
            self._worker_usage = event
            self._check_size(event.agent_id, event.context_tokens)

    def _check_size(self, agent_id: str, tokens: int) -> None:
        """Warn once when a context passes the threshold; again only after it has come back under."""
        if not self._context_watch.crossed(agent_id, tokens):
            return
        past = f"context is at {_k(tokens)} tokens, past the {_k(self._context_watch.limit)} warning"
        if agent_id == TALKER_ID:
            self._status(
                f"Your own (the Talker's) {past}: every step now resends that much. "
                "Tell the user in a sentence and offer to reset it."
            )
        else:  # the worker gets its own reminder (context_reminder) and hands off by itself
            self._status(
                f"The worker's {past}. It has been reminded to find a reset point and hand off to a "
                "fresh session by itself. Tell the user in a sentence; they don't need to reset it."
            )

    async def _on_reset(self, event: ResetRequested) -> None:
        if event.agent_id == TALKER_ID:
            self._inbox.put_nowait(_Item("", reset=True))  # not mid-turn: after the turn in progress

    async def _reset(self) -> None:
        await self._session.close()
        await self._session.start()
        self._carry_over = bool(self._history)
        self._publish_usage()

    def _publish_usage(self) -> None:
        usage = session_usage(TALKER_ID, self._session)
        self._ctx.publish(usage)
        self._check_size(TALKER_ID, usage.context_tokens)

    async def _on_snip(self, event: ViewerClip) -> None:
        # Like the tabs note: it waits for your next message, which is likely "what is this?".
        self._snips.append(event)

    async def _on_snip_dropped(self, event: ViewerClipDropped) -> None:
        self._snips = deque((s for s in self._snips if s.id != event.id), maxlen=MAX_SNIPS)

    def _on_event(self, event: dict[str, Any]) -> None:
        if self._turn is None or self._turn.done():
            return
        if event.get("type") == "result":
            self._turn.set_result(event)
        elif event.get("type") == "exit":
            self._turn.set_exception(RuntimeError("The Talker's claude process exited"))

    async def _run(self) -> None:
        while True:
            item = await self._inbox.get()
            try:
                if item.reset:
                    await self._reset()
                    continue
                await self._handle(item)
            except Exception:
                self._ctx.log.exception("Talker turn failed")
                if item.input_id:
                    self._say("Sorry, something went wrong on my side.", item)
                    self._send_theme([], item.text)

    async def _handle(self, item: _Item) -> None:
        said = SPOKEN + item.text if item.source == "voice" else item.text  # what the session and history see
        prompt, images = said, []
        if item.input_id and self._snips:
            notes = []
            for snip in self._snips:
                near = f', near "{snip.heading}"' if snip.heading else ""
                notes.append(f"[Viewer] snip from {snip.file}{near} (image attached; file: {snip.image_path})")
                images.append(snip.image_path)
            prompt = "\n".join(notes) + "\n" + prompt
            self._snips.clear()
        if item.input_id and self._viewer_note:
            prompt, self._viewer_note = f"{self._viewer_note}\n{prompt}", None
        if item.input_id and self._mode_note:
            prompt, self._mode_note = f"{self._mode_note}\n{prompt}", None
        if item.input_id:
            prompt = f"{self._usage_line()}\n{prompt}"
        if self._carry_over:
            prompt = RESET_CONTEXT.format(history="\n".join(self._history)) + "\n\n" + prompt
            self._carry_over = False
        result = await self._take_turn(prompt, images)
        if item.restart_note and self._restart_note:  # used once
            self._restart_note.unlink(missing_ok=True)
        self._publish_usage()
        text, tags = split_tags(result.get("result") or "")
        if result.get("is_error") and not text:
            text = "Sorry, something went wrong on my side."
        self._history.append(f"User: {said}" if item.input_id else said)
        if text:
            self._history.append(f"Assistant: {text}")
            self._say(text, item)
        if item.input_id:
            self._send_theme(tags, item.text)
        for tag, argument in tags:
            await self._run_tag(tag, argument)

    def _send_theme(self, tags: list[tuple[str, str]], first_message: str) -> None:
        """Once, after the first input: the log folder's theme, which also creates the folder.
        The Talker's THEME tag, else the first message itself, else "chat"."""
        if self._theme_sent:
            return
        self._theme_sent = True
        themes = [argument for tag, argument in tags if tag == "THEME"] + [first_message]
        self._ctx.publish(SessionTheme(text=next((t for t in themes if theme_slug(t)), "chat")))

    async def _take_turn(self, text: str, images: list[str] | None = None) -> dict[str, Any]:
        if not self._session.running:
            await self._session.start()
        self._turn = asyncio.get_running_loop().create_future()
        try:
            await self._session.send(text, images or ())
        except OSError as exc:  # a snip's image is gone: send the text alone
            self._ctx.log.warning("Couldn't attach the snip: %s", exc)
            await self._session.send(text)
        try:
            return await asyncio.wait_for(asyncio.shield(self._turn), self._turn_timeout)
        except TimeoutError:
            self._ctx.log.warning("Talker turn took over %ss; interrupting", self._turn_timeout)
            await self._session.interrupt()
            return await asyncio.wait_for(self._turn, 10)

    async def _run_tag(self, tag: str, argument: str) -> None:
        ctx = self._ctx
        if tag == "THEME":
            return  # handled in _handle
        if tag == "SHOW":
            # `path`, or `path | "quoted text" | heading` to highlight part of the page.
            show = parse_show(argument)
            if show.quote:
                args = {"path": show.path, "text": show.quote, **({"heading": show.heading} if show.heading else {})}
                result = await ctx.send(InvokeTool(name="viewer.highlight", args=args))
            else:
                result = await ctx.send(InvokeTool(name="viewer.open", args={"path": show.path}))
            if not result.is_ok:
                self._status(f"Couldn't open {show.path} in the viewer: {result.error}")
            elif isinstance(result.value, dict) and result.value.get("found") is False:
                self._status(f'Opened {show.path}, but "{show.quote}" isn\'t on the page, so nothing is highlighted.')
        elif tag == "MODE":
            # Manual only: switching to Auto takes the user's own click.
            if argument.strip().lower() != PermissionMode.MANUAL:
                self._status(ONLY_YOU_AUTO)
                return
            result = await ctx.send(SetPermissionMode(agent_id=self._worker_id, mode=PermissionMode.MANUAL))
            if not result.is_ok:
                self._status(f"Couldn't switch the Main Assistant to Manual: {result.error}")
        elif tag == "WORK":
            result = await ctx.send(StartTask(text=argument, context="\n".join(self._history)))
            if result.is_ok:
                self._current_task_id = result.value
            else:
                self._status(f"The assistant couldn't take the task: {result.error}")
        elif tag == "LOOK":
            result = await ctx.send(GetTaskStatus(task_id=self._current_task_id))
            self._status(_describe(result.value) if result.is_ok else f"Couldn't get the status: {result.error}")
        elif tag == "RESET":
            target = TALKER_ID if argument.lower().startswith("talker") else self._worker_id
            ctx.publish(ResetRequested(agent_id=target))
        elif tag == "RESTART":
            await self._ask_for_restart(anyway=argument.strip().lower().startswith("anyway"))
        elif self._current_task_id is None:
            self._status("There's no task to send that to.")
        elif tag in ("ASK", "PAUSE"):
            result = await ctx.send(SendToTask(task_id=self._current_task_id, text=argument, resume=tag == "ASK"))
            if not result.is_ok:
                self._status(f"Couldn't reach the task: {result.error}")
        elif tag == "CANCEL":
            result = await ctx.send(CancelTask(task_id=self._current_task_id))
            if not result.is_ok:
                self._status(f"Couldn't cancel the task: {result.error}")
        elif tag in ("ALLOW", "DENY"):
            self._answered_permission = True
            result = await ctx.send(AnswerPermission(task_id=self._current_task_id, allow=tag == "ALLOW"))
            if not result.is_ok:
                self._answered_permission = False
                self._status(f"Couldn't answer the permission request (maybe already answered): {result.error}")

    async def _ask_for_restart(self, anyway: bool) -> None:
        """Ask the worker for reset instructions: a message to its task, or a small task of its own.
        The restart follows its `RESTART_READY` reply, or `restart_timeout` with a note of our own."""
        if self._restart_timer is not None or self._restarting:
            return  # already on its way
        task = None
        if self._current_task_id is not None:
            status = await self._ctx.send(GetTaskStatus(task_id=self._current_task_id))
            if status.is_ok and status.value and not status.value[0].state.is_final:
                task = status.value[0]
        if task is not None and task.state is TaskState.WAITING_FOR_INPUT and not anyway:
            self._status(RESTART_WAITING.format(question=task.question or "a question"))
            return
        if task is not None:
            result = await self._ctx.send(SendToTask(task_id=task.id, text=WRITE_RESET_NOTE, resume=False))
        else:
            result = await self._ctx.send(StartTask(text=WRITE_RESET_NOTE, context=self._history_text()))
            if result.is_ok:
                self._current_task_id = result.value
        if not result.is_ok:
            self._restart(FALLBACK_NOTE.format(why=f"couldn't reach it: {result.error}", history=self._history_text()))
            return
        self._restart_timer = asyncio.create_task(self._restart_fallback(), name="talker:restart")

    async def _restart_fallback(self) -> None:
        await asyncio.sleep(self._restart_timeout)
        self._restart_timer = None
        self._restart(FALLBACK_NOTE.format(why=f"no answer in {self._restart_timeout:g}s", history=self._history_text()))

    def _restart(self, note: str) -> None:
        """Save the reset instructions for the next launch, then ask the app to restart."""
        if self._restarting:
            return
        if self._restart_timer is not None and self._restart_timer is not asyncio.current_task():
            self._restart_timer.cancel()
        self._restart_timer = None
        self._restarting = True
        if self._restart_note:
            self._restart_note.parent.mkdir(parents=True, exist_ok=True)
            self._restart_note.write_text((note.strip() or self._history_text()) + "\n", encoding="utf-8")
        self._ctx.log.info("Restarting; reset instructions saved to %s", self._restart_note)
        self._ctx.publish(ShutdownRequested(reason="restart", restart=True))

    def _history_text(self) -> str:
        return "\n".join(self._history)

    def _say(self, text: str, item: _Item) -> None:
        self._ctx.publish(ResponseReady(text=text, correlation_id=item.input_id, conversation_id=item.conversation_id))

    def _status(self, text: str) -> None:
        self._inbox.put_nowait(_Item(f"[Status] {text}"))

    def _usage_line(self) -> str:
        worker = _describe_usage(self._worker_usage) if self._worker_usage else "not started"
        return f"[Usage] worker: {worker} · you: {_describe_usage(session_usage(TALKER_ID, self._session))}"


def _describe_usage(usage: SessionUsage) -> str:
    """`context 145k, used 2.3M (~$5.10)`."""
    return f"context {_k(usage.context_tokens)}, used {_tokens(usage.used_tokens)} (~${usage.cost_usd:.2f})"


def _k(tokens: int) -> str:
    return f"{round(tokens / 1000)}k"


def _tokens(tokens: int) -> str:
    return f"{tokens / 1_000_000:.1f}M" if tokens >= 1_000_000 else _k(tokens)


def _describe(tasks: list[TaskInfo]) -> str:
    if not tasks:
        return "No tasks."
    lines = []
    for task in tasks:
        lines.append(f"Task {task.id} is {task.state}: {task.text}")
        if task.question:
            lines.append(f"  Waiting for the answer to: {task.question}")
        lines += [f"  {report}" for report in task.recent[-3:]]
        if task.activity and not task.state.is_final:
            lines.append("  Recent activity, newest last:")
            lines += [f"    {line[:200]}" for line in task.activity]
        if task.result and task.state.is_final:
            lines.append(f"  Result: {task.result}")
    return "\n".join(lines)
