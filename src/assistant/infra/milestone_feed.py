"""Background lines for an agent's next turn: the other agents' milestones, focus moves, callbacks."""

from __future__ import annotations

from collections import deque

HEADER = (
    "[Updates from the other agents (background: note them; don't act on them or repeat them "
    "unless they change your task)]"
)
KEPT = 50  # lines kept between turns; older ones only count toward "+N earlier"


class MilestoneFeed:
    """Lines waiting for an agent's next message to its session (`ITaskAgent.note` adds them).

    `take` empties the feed into one compact block, so lines never pile up in a prompt and
    never interrupt: the agent reads them with whatever it is sent next.
    """

    def __init__(self) -> None:
        self._lines: deque[str] = deque()
        self._dropped = 0

    def add(self, line: str) -> None:
        line = " ".join(line.split())
        if not line:
            return
        self._lines.append(line)
        if len(self._lines) > KEPT:
            self._lines.popleft()
            self._dropped += 1

    def __len__(self) -> int:
        return len(self._lines)

    def take(self, max_lines: int = 5) -> str:
        """The waiting lines as one block under `HEADER` (newest last, at most `max_lines`
        lines, the oldest merged as "+N earlier"), or "" when none wait. Empties the feed."""
        if not self._lines:
            return ""
        lines, earlier = list(self._lines), self._dropped
        self._lines.clear()
        self._dropped = 0
        keep = max(max_lines - 1, 0) if earlier or len(lines) > max_lines else len(lines)
        merged = max(len(lines) - keep, 0)
        earlier += merged
        shown = ([f"(+{earlier} earlier)"] if earlier else []) + [f"- {line}" for line in lines[merged:]]
        return "\n".join([HEADER, *shown])
