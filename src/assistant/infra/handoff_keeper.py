"""How often a task has been handed to a fresh session, and the words for it. `SessionTaskAgent`
composes one: a `HANDOFF: <note>` last line continues the task in a fresh session told to read
the note, up to `max_handoffs` times per task; then the user is asked. Any answer is a go-ahead:
the handoff goes ahead with a fresh allowance (`renew`), and the answer goes with it."""

from __future__ import annotations

# Chrome tabs belong to one `claude` session; a fresh session can't reach them
# (docs/next-steps/chrome-tab-after-reset.md).
CHROME_HANDOFF = (
    " If you have Chrome tabs open, save or finish any unsaved form work first, and put each "
    "tab's URL and state in the note, in case the next session can't reach your tabs."
)
# An agent with Chrome keeps its session on a handoff: `/compact` keeps the session id, and so
# its tab group; a new process loses it (the spike, 2026-11-10).
COMPACT = (
    "/compact Keep the task, the path of its handoff note ({note}), and each open Chrome tab's "
    "id and what's on it."
)
HANDED_OFF_COMPACTED = (
    "Task, continued after your context was compacted: {text}\n\n"
    "You wrote a handoff in {note}. Read it first and carry on from there; don't redo the "
    "finished parts. This is the same session, so your Chrome tabs are still yours: check them "
    "with tabs_context_mcp, and don't open new tabs for pages you already have."
)
WHILE_COMPACTING = "\n\nA message came while your context was being compacted: {text}"
CHROME_FRESH = (
    " Chrome tabs from earlier sessions are in a group you can't reach: reopen the note's URLs "
    "in your own tab group, and don't look for the old tabs."
)
HANDED_OFF = (
    "Task, continued in a fresh session: {text}\n\n"
    "An earlier session worked on this and wrote a handoff in {note}. Read it first and "
    "carry on from there; don't redo the finished parts." + CHROME_FRESH
)
RESET_NOW = (
    "The user asked to reset your session. At a safe point, write what's done and what's "
    "next into this task's change note in docs/next-steps/ (or a short note "
    "docs/next-steps/handoff-{task_id}.md if it has none), then end with the line "
    "`HANDOFF: <that note's path>`." + CHROME_HANDOFF
)
CONTEXT_REMINDER = (
    "[Context check] Your context is at {tokens}, past {limit}: every step now resends that "
    "much. Find a good reset point: finish the step you're on or pause at a safe boundary "
    "(tests passing, no half-done edits). Then write what's done and what's next into this "
    "task's change note in docs/next-steps/ (or docs/next-steps/handoff-{task_id}.md), say in "
    "one line that you're at a reset point, and end with `HANDOFF: <that note's path>`."
    + CHROME_HANDOFF
)
TOO_MANY_HANDOFFS = "I've handed this task off {count} times (latest notes: {note}). Should I carry on?"
ANSWERED = "\n\nAsked whether to carry on after {count} handoffs, the user answered: {answer}"


class HandoffKeeper:
    """Counts one task's handoffs against `max_handoffs` and words what each one says."""

    def __init__(self, max_handoffs: int = 3) -> None:
        self.max_handoffs = max_handoffs
        self.count = 0

    def reset(self) -> None:
        """A new task: no handoffs yet."""
        self.count = 0

    def take(self) -> bool:
        """Count one more handoff; False (and nothing counted) when the task has had its maximum."""
        if self.count >= self.max_handoffs:
            return False
        self.count += 1
        return True

    def renew(self) -> int:
        """The user answered the too-many question: a fresh allowance, with the handoff they
        answered for as its first. Returns the count they were asked about."""
        asked, self.count = self.count, 1
        return asked

    @staticmethod
    def answered(count: int, answer: str) -> str:
        """The user's answer to the too-many question, for the fresh session's first message."""
        return ANSWERED.format(count=count, answer=answer)

    def progress(self, note: str, compacted: bool = False) -> str:
        """The progress report for the handoff just taken: to a fresh session, or in this one
        with its context compacted (an agent with Chrome)."""
        where = "in place, context compacted" if compacted else "to a fresh session"
        return f"Handed off {where} ({self.count}): {note}"

    def too_many(self, note: str) -> str:
        """The question to the user once the maximum is reached."""
        return TOO_MANY_HANDOFFS.format(count=self.count, note=note)

    @staticmethod
    def reset_request(task_id: str) -> str:
        """The message asking a task to hand off now (the user reset its session)."""
        return RESET_NOW.format(task_id=task_id)

    @staticmethod
    def reminder(tokens: str, limit: str, task_id: str) -> str:
        """The context reminder asking a task to find a reset point."""
        return CONTEXT_REMINDER.format(tokens=tokens, limit=limit, task_id=task_id)
