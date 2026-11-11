"""The Agent Hub's message gate: an agent messages another agent that isn't its own child task.

The first message from A to B asks you on a permission card (Allow once · Always allow · Deny),
through `ctx.permissions.ask` with the item `message:<B>`; "Always" is saved by the core's
permissions handler under `agent_hub` and A's kind, so B → A is asked on its own. While the card
is open the message waits here (later ones from A to B wait behind the same card); on Allow they
go through the Hub's delivery (`Delivery.deliver`: never into a running turn). On Deny nothing is
sent and A gets a note saying so.

Held messages are not handed over on a reload: `held()` makes the Hub's reload wait instead.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from assistant.contracts import AccessItem, AccessKind, DeliverMessage, ModulePermissions, Result

PREVIEW = 200  # how much of the first message the card shows


def message_item(receiver: str) -> AccessItem:
    return AccessItem(kind=AccessKind.MESSAGE, target=receiver)


class MessageGate:
    """`send(sender, receiver, text)`: deliver now if `sender`'s kind may message `receiver`,
    else hold it behind one card per pair. `deliver`: the Hub's delivery; `note(agent, text)`:
    a background line for an agent (the Deny note)."""

    def __init__(self, permissions: ModulePermissions, deliver: Callable[[DeliverMessage], Awaitable[Result]],
                 note: Callable[[str, str], None], log: logging.Logger) -> None:  # fmt: skip
        self._permissions, self._deliver, self._note, self._log = permissions, deliver, note, log
        self._held: dict[tuple[str, str], list[str]] = {}
        self._asking: set[asyncio.Task] = set()

    async def send(self, sender: str, receiver: str, text: str) -> Result:
        pair = (sender, receiver)
        if pair in self._held:
            self._held[pair].append(text)
            return Result.ok({"agent_id": receiver, "how": "waiting on the user's card"})
        if self._permissions.granted(message_item(receiver), sender):
            return self._sent(receiver, await self._deliver(DeliverMessage(agent_id=receiver, text=text, sender=sender)))
        self._held[pair] = [text]
        task = asyncio.create_task(self._ask(sender, receiver), name=f"hub-message-card-{sender}-{receiver}")
        self._asking.add(task)
        task.add_done_callback(self._asking.discard)
        return Result.ok({"agent_id": receiver, "how": "waiting on the user's card"})

    def held(self) -> int:
        return sum(len(texts) for texts in self._held.values())

    async def close(self) -> None:
        for task in list(self._asking):
            task.cancel()
        await asyncio.gather(*self._asking, return_exceptions=True)
        if self._held:
            self._log.info("Dropped %d message(s) still waiting on a card", self.held())
            self._held.clear()

    async def _ask(self, sender: str, receiver: str) -> None:
        pair = (sender, receiver)
        first = self._held[pair][0]
        preview = first if len(first) <= PREVIEW else first[:PREVIEW] + "…"
        try:
            allowed = await self._permissions.ask(message_item(receiver), sender,
                                                  f"{sender} wants to message {receiver}: {preview}")  # fmt: skip
        except asyncio.CancelledError:
            raise
        except Exception:
            self._log.exception("The message card from %s to %s failed", sender, receiver)
            allowed = False
        texts = self._held.pop(pair, [])
        if not allowed:
            self._note(sender, f"[messages] The user didn't allow your message to {receiver}; "
                               f"{len(texts)} message(s) not sent.")  # fmt: skip
            return
        for text in texts:
            sent = await self._deliver(DeliverMessage(agent_id=receiver, text=text, sender=sender))
            if not sent.is_ok:
                self._note(sender, f"[messages] Your message to {receiver} couldn't be delivered: {sent.error}")

    @staticmethod
    def _sent(receiver: str, result: Result) -> Result:
        return Result.ok({"agent_id": receiver, "how": result.value}) if result.is_ok else result
