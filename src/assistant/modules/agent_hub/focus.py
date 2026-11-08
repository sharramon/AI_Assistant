"""The Agent Hub's focus: the agent you're talking to, and what it held while you weren't.

The focus starts on the coordinator. Moving it (`SetFocus`) releases what the agent held
(the task board's `release`) and publishes `FocusChanged` with it. An agent that is gone
(closed, turned off, failed) loses the focus at once, back to the coordinator, and that move
is announced too, so no UI stays on a dead tab. Each move is a line in the coordinator's feed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from assistant.contracts import FocusChanged, ITaskAgent, Result, SetFocus, TaskInfo


class Focus:
    """Who you're talking to. `agent(id)` finds a running agent, `release(id)` frees what it
    held, `feed(line)` is a background line for the coordinator."""

    def __init__(
        self,
        *,
        publish: Callable[[Any], None],
        log: logging.Logger,
        coordinator: str,
        initial: str | None,
        agent: Callable[[str], ITaskAgent | None],
        release: Callable[[str], list[TaskInfo]],
        feed: Callable[[str], None],
    ) -> None:
        self._publish, self._log = publish, log
        self._coordinator = coordinator
        self._focus = initial or coordinator
        self._agent, self._release, self._feed = agent, release, feed

    @property
    def stored(self) -> str:
        """The focus as stored, unchecked (for a reload's handover)."""
        return self._focus

    def focused(self) -> str:
        """The focused agent, or the coordinator when that agent is no longer running. Falling
        back is announced (`FocusChanged`), so no UI stays on a dead tab."""
        if self._focus != self._coordinator and self._agent(self._focus) is None:
            gone, self._focus = self._focus, self._coordinator
            self._log.info("Focus: %s (%s is gone)", self._coordinator, gone)
            self._publish(FocusChanged(agent_id=self._coordinator, previous=gone))
            self._feed(f"[focus] {gone} is gone; the user is now talking to {self._coordinator}")
        return self._focus

    async def check(self, _event: Any) -> None:
        """An agent may have gone: off its tab at once."""
        self.focused()

    async def set(self, command: SetFocus) -> Result:
        """Focus `agent_id` (empty: the coordinator) and release what it held: questions,
        replies and ends (finished tasks too)."""
        target = command.agent_id or self._coordinator
        if target != self._coordinator and self._agent(target) is None:
            return Result.invalid_arguments(f"No agent {target!r}")
        previous, self._focus = self._focus, target  # a gone agent counts as previous: the move is said
        released = self._release(target)
        if target != previous or released:
            self._log.info("Focus: %s (was %s), %d question(s) released", target, previous, len(released))
            self._publish(FocusChanged(agent_id=target, previous=previous, released=tuple(released)))
        if target != previous:
            self._feed(f"[focus] the user is now talking to {target}")
        return Result.ok(target)
