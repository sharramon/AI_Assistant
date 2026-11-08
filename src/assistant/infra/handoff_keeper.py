"""How often a task has been handed to a fresh session, and the words for it. `SessionTaskAgent`
composes one: a `HANDOFF: <note>` last line continues the task in a fresh session told to read
the note, up to `max_handoffs` times per task; then the user is asked."""

from __future__ import annotations

HANDED_OFF = (
    "Task, continued in a fresh session: {text}\n\n"
    "An earlier session worked on this and wrote a handoff in {note}. Read it first and "
    "carry on from there; don't redo the finished parts."
)
RESET_NOW = (
    "The user asked to reset your session. At a safe point, write what's done and what's "
    "next into this task's change note in docs/next-steps/ (or a short note "
    "docs/next-steps/handoff-{task_id}.md if it has none), then end with the line "
    "`HANDOFF: <that note's path>`."
)
CONTEXT_REMINDER = (
    "[Context check] Your context is at {tokens}, past {limit}: every step now resends that "
    "much. Find a good reset point: finish the step you're on or pause at a safe boundary "
    "(tests passing, no half-done edits). Then write what's done and what's next into this "
    "task's change note in docs/next-steps/ (or docs/next-steps/handoff-{task_id}.md), say in "
    "one line that you're at a reset point, and end with `HANDOFF: <that note's path>`."
)
TOO_MANY_HANDOFFS = "I've handed this task off {count} times (latest notes: {note}). Should I carry on?"


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

    def progress(self, note: str) -> str:
        """The progress report for the handoff just taken."""
        return f"Handed off to a fresh session ({self.count}): {note}"

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
