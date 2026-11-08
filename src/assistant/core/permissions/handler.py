"""The permissions handler (its first piece), part of the core: access lists, saved grants, the
card, the review, and the grant calls. Always on: no module or agent can turn it off or reload it.

It uses only the core's generic parts, handed in by the App: the router's `send`, the bus's
`publish`, and the container's `find` (for `IAgentNames` at revoke time). The Main Assistant's
review is a normal task through the Agent Hub's contracts (`StartTask`, `TaskUpdated`,
`CancelTask`); no module is imported.

A module's start can't wait on a card (`ActivateModule` times out), so `request_set(wait=False)`
answers from the saved grant when the list is unchanged, and otherwise opens a card and raises
`AccessPending`; on Allow the handler saves the grant and turns the module on itself. With
`wait=True` (a helper launched inside an approved run) it awaits your answer.

An answered card is applied by its action's handler, looked up in a table (principle 20):
`access` saves the module's list; `grant` and `revoke` carry out an agent's call.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from assistant.contracts import (
    AccessDenied,
    AccessItem,
    AccessKind,
    AccessNote,
    AccessPending,
    ActivateModule,
    AgentNotice,
    AnswerPermissionRequest,
    CancelTask,
    Command,
    DeactivateModule,
    Event,
    GetTaskStatus,
    IAgentNames,
    ListModules,
    ModuleState,
    PermissionChanged,
    PermissionRequested,
    Result,
    StartTask,
    TaskState,
    TaskUpdated,
)
from assistant.core.permissions.rules import FIXED_RULES, REPO, protected_paths, refusals, rule_warnings
from assistant.core.permissions.store import Grant, GrantStore, fingerprint

GRANTS_FILE = REPO / "data" / "permissions.toml"
# Defaults for `from_config`, read at each call (tests make them short and turn the review off).
# Shared code names no module (principle 21): which agent reviews a list and which callers are
# you clicking come from `[core.permissions]` in config (`reviewer`, `you`); none by default.
REVIEWER = ""
YOU: tuple[str, ...] = ()
REVIEW_TIMEOUT = 90.0
ANSWER_TIMEOUT = 600.0

REVIEW_PROMPT = """\
Review an access list before the user answers it on a card. Use no tools and ask no questions.
Reply with one short line per risk the warnings below don't already cover (what it could do, and \
with which items), or exactly `No further warnings.` Nothing else.

Who asks: {who}{reason}
The list:
{items}
Warnings already on the card:
{warnings}"""

NO_FURTHER = "no further warnings"
MAX_REVIEW_LINES = 8
FINALS_KEPT = 32


class CardAction(StrEnum):
    """What a card asks: a module's access list, or an agent's grant or revoke call. The values
    are `PermissionRequested.action`'s."""

    ACCESS = "access"
    GRANT = "grant"
    REVOKE = "revoke"


@dataclass(eq=False)
class Card:
    """One open card. `reply`: None for Deny, the kept keys for Allow. `outcome`: the granted
    items, or `AccessDenied`."""

    module_id: str
    subject: str
    action: CardAction
    items: tuple[AccessItem, ...]
    reason: str = ""
    caller: str = ""
    asked: tuple[str, ...] = ()  # access: every key asked for, before refusals
    fingerprint: str = ""
    everything: bool = False  # revoke: the whole grant of every subject named
    activate: bool = False  # access: turn the module on after Allow
    adds: bool = False  # grant: an agent's own request, whose items join the grant's added ones
    notes: tuple[AccessNote, ...] = ()
    reviewed: bool | None = None
    shown: bool = False
    task: asyncio.Task | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    reply: asyncio.Future = field(default_factory=lambda: asyncio.get_running_loop().create_future())
    outcome: asyncio.Future = field(default_factory=lambda: asyncio.get_running_loop().create_future())

    def __post_init__(self) -> None:
        self.outcome.add_done_callback(lambda f: f.cancelled() or f.exception())  # nobody may await it

    @property
    def who(self) -> str:
        return who(self.module_id, self.subject)


def who(module_id: str, subject: str) -> str:
    """How a card or a result names a module's list: `job_search`, or `task_agents → helper`."""
    return module_id if subject in ("", module_id) else f"{module_id} → {subject}"


class PermissionsHandler:
    """The core's permissions handler. `send`, `publish`, `find`: the router's, the bus's and the
    container's (`get_one`). Config (`[core.permissions]`, every key optional): `from_config`."""

    def __init__(self, send: Callable[[Command], Awaitable[Result]], publish: Callable[[Event], None],
                 find: Callable[[type], Any], grants_file: Path = GRANTS_FILE, reviewer: str = REVIEWER,
                 review_timeout: float = REVIEW_TIMEOUT, answer_timeout: float = ANSWER_TIMEOUT,
                 you: Iterable[str] = YOU, log: logging.Logger | None = None) -> None:  # fmt: skip
        self._send = send
        self._publish = publish
        self._find = find
        self._log = log or logging.getLogger(__name__)
        self.store = GrantStore(grants_file, self._log)
        self._protected = protected_paths(grants_file)
        self._reviewer = reviewer
        self._review_timeout = review_timeout
        self._answer_timeout = answer_timeout
        self._you = tuple(you)
        self._cards: dict[str, Card] = {}
        self._asking: dict[tuple[str, str], Card] = {}
        self._last: dict[tuple[str, str], str] = {}  # the fingerprint asked this launch
        self._reviews: dict[str, asyncio.Future] = {}
        self._finals: OrderedDict[str, tuple[TaskState, str]] = OrderedDict()
        self._work: set[asyncio.Task] = set()
        self._agents: dict[str, tuple[str, str]] = {}  # agent id -> (its module, the subject of its grant)
        # An answered card's handler, by its action (principle 20).
        self._appliers: dict[CardAction, Callable[[Card, tuple[str, ...] | None, str], Awaitable[None]]] = {
            CardAction.ACCESS: self._apply_access,
            CardAction.GRANT: self._apply_grant,
            CardAction.REVOKE: self._apply_revoke,
        }

    @classmethod
    def from_config(cls, config: dict[str, Any], send, publish, find) -> PermissionsHandler:
        """From `[core.permissions]`: `grants_file` (default `data/permissions.toml` in the repo, the
        protected zone; relative to the repo), `reviewer` (the agent that reviews a list before the
        card shows; empty for none), `review_timeout`, `answer_timeout`, and `you` (the callers that
        are you clicking in a UI; anyone else's grant or revoke shows you a card)."""
        grants_file = Path(config.get("grants_file") or GRANTS_FILE)
        if not grants_file.is_absolute():
            grants_file = REPO / grants_file
        return cls(send, publish, find, grants_file, reviewer=str(config.get("reviewer", REVIEWER)),
                   review_timeout=float(config.get("review_timeout", REVIEW_TIMEOUT)),
                   answer_timeout=float(config.get("answer_timeout", ANSWER_TIMEOUT)),
                   you=tuple(config.get("you", YOU)))  # fmt: skip

    # --- what ctx.permissions forwards ---

    async def request_set(self, module_id: str, subject: str, items: Sequence[AccessItem], reason: str = "",
                          wait: bool = False) -> tuple[AccessItem, ...]:  # fmt: skip
        """`module_id`'s access list for `subject` (its agent's kind). The saved grant when the
        list is unchanged; otherwise a card. `wait`: await your answer; else raise `AccessPending`
        and turn the module on once you allow. Raises `AccessDenied` on Deny."""
        subject = subject or module_id
        items = tuple(dict.fromkeys(items))
        fp = fingerprint(items)
        self._last[(module_id, subject)] = fp
        saved = self.store.get(module_id, subject)
        if saved is not None and saved.fingerprint == fp and not saved.denied:
            return saved.granted_items()
        card = self._asking.get((module_id, subject))
        if card is not None and card.fingerprint != fp:
            self._drop(card, f"{card.who}'s list changed; it asks again")
            card = None
        if card is None:
            card = Card(module_id, subject, CardAction.ACCESS, items, reason, asked=tuple(i.key for i in items),
                        fingerprint=fp)  # fmt: skip
            self._asking[(module_id, subject)] = card
            self._open(card)
        if not wait:
            card.activate = True
            raise AccessPending(f"{card.who} waits for your answer on its access card; it turns on when you allow")
        return await asyncio.shield(card.outcome)

    def own_agent(self, module_id: str, agent_id: str, subject: str) -> None:
        """`module_id`'s agent `agent_id` holds `subject`'s grant (`ctx.permissions.own_agent`)."""
        self._agents[agent_id] = (module_id, subject)

    def open_cards(self) -> int:
        return len(self._cards)

    # --- answers ---

    async def answer(self, cmd: AnswerPermissionRequest) -> Result:
        card = self._cards.get(cmd.request_id)
        if card is None or not card.shown or card.reply.done():
            return Result.invalid_arguments(f"No open permission card {cmd.request_id!r}")
        if not cmd.allow:
            card.reply.set_result(None)
            return Result.ok("denied")
        offered = [i.key for i in card.items]
        if cmd.keep is not None and (bad := [k for k in cmd.keep if k not in offered]):
            return Result.invalid_arguments(f"Not on card {card.id}: {', '.join(bad)}")
        card.reply.set_result(tuple(offered if cmd.keep is None else cmd.keep))
        return Result.ok("allowed")

    async def on_task_updated(self, event: TaskUpdated) -> None:
        if not event.state.is_final:
            return
        future = self._reviews.get(event.task_id)
        if future is not None and not future.done():
            future.set_result((event.state, event.text))
            return
        self._finals[event.task_id] = (event.state, event.text)
        while len(self._finals) > FINALS_KEPT:
            self._finals.popitem(last=False)

    # --- the grant calls ---

    def grants(self) -> list[dict[str, Any]]:
        """Every saved grant (and every list waiting on a card without one), for the menu."""
        rows: list[dict[str, Any]] = []
        for g in sorted(self.store.all(), key=lambda g: (g.module_id, g.subject)):
            last = self._last.get((g.module_id, g.subject))
            rows.append({
                "module_id": g.module_id, "subject": g.subject, "granted": list(g.granted),
                "labels": [i.label for i in g.granted_items()], "asked": list(g.asked), "denied": g.denied,
                "date": g.date, "matches": None if last is None else last == g.fingerprint,
                "waiting": (g.module_id, g.subject) in self._asking, "added": list(g.added),
            })  # fmt: skip
        for (m, s), card in self._asking.items():
            if self.store.get(m, s) is None:
                rows.append({"module_id": m, "subject": s, "granted": [], "labels": [], "asked": list(card.asked),
                             "denied": False, "date": "", "matches": None, "waiting": True, "added": []})  # fmt: skip
        return rows

    async def grant(self, module_id: str, keys: Sequence[str], subject: str = "", caller: str = "") -> Result:
        found = self._one_grant(module_id, subject)
        if isinstance(found, Result):
            return found
        keys = tuple(dict.fromkeys(keys))
        if not keys:
            return Result.invalid_arguments("Name the items to grant (their keys from permissions.grants)")
        if bad := [k for k in keys if k not in (*found.asked, *found.added)]:
            return Result.invalid_arguments(f"{', '.join(bad)}: not on {module_id}'s list; only asked items can be granted")
        items = tuple(AccessItem.from_key(k) for k in keys)
        if refused := refusals(items, self._protected):
            return Result.invalid_arguments(" ".join(refused.values()))
        if caller in self._you:
            return Result.ok(await self._do_grant(found, keys))
        card = Card(module_id, found.subject, CardAction.GRANT, items, f"{caller} asks to grant these to {module_id}",
                    caller, notes=tuple(rule_warnings(items)))  # fmt: skip
        self._open(card)
        return Result.ok(f"Asked the user on a card ({card.id}); the answer reaches you as a note")

    async def request(self, caller: str, items: Sequence[AccessItem], reason: str = "") -> Result:
        """An agent asks for more access for itself (`permissions.request`): new folders,
        commands, a Python or Chrome. Its module and subject come from `own_agent`, checked
        against the name's claim, so an agent can only ask for itself. Opens a card; on Allow
        the items join its grant (as added items) and reach the agent from its next session."""
        owner = self._agents.get(caller)
        if owner is None:
            return Result.not_available(f"{caller or 'The caller'} has no access list to add to; its access is set in config")
        module_id, subject = owner
        names = self._find(IAgentNames)
        if names is not None and names.taken().get(caller) != module_id:
            return Result.not_available(f"{caller} isn't running under {module_id} now")
        name = who(module_id, subject)
        saved = self.store.get(module_id, subject)
        if saved is None or saved.denied:
            return Result.not_available(f"{name} has no saved grant to add to; its module asks when turned on")
        items = tuple(dict.fromkeys(items))
        if any(i.kind is AccessKind.WORKSPACE for i in items):
            return Result.invalid_arguments("An agent can't ask for another working folder; ask for read or write")
        new = tuple(i for i in items if i.key not in saved.granted)
        if not new:
            return Result.ok("You already have all of these")
        refused = refusals(new, self._protected)
        new = tuple(i for i in new if i.key not in refused)
        if not new:
            return Result.invalid_arguments(" ".join(refused.values()))
        notes = [AccessNote(text=t, items=(k,), source="refused") for k, t in refused.items()]
        card = Card(module_id, subject, CardAction.GRANT, new,
                    f"{caller} asks for more access" + (f": {reason}" if reason else ""),
                    caller, notes=tuple(notes + rule_warnings(new)), adds=True)  # fmt: skip
        self._open(card)
        return Result.ok(f"Asked the user on a card ({card.id}); the answer reaches you as a note, and what they "
                         "allow applies from your next session (your next task or handoff)")  # fmt: skip

    async def revoke(self, module_id: str, subject: str = "", keys: Sequence[str] | None = None,
                     caller: str = "") -> Result:  # fmt: skip
        targets = [g for g in self.store.of(module_id) if not subject or g.subject == subject]
        if not targets:
            return Result.invalid_arguments(f"{module_id} has no saved grant{' for ' + subject if subject else ''}")
        keys = tuple(dict.fromkeys(keys)) if keys else None
        if keys is not None:
            held = {k for g in targets for k in g.granted}
            if bad := [k for k in keys if k not in held]:
                return Result.invalid_arguments(f"{', '.join(bad)}: not granted to {module_id}")
        if caller in self._you:
            return Result.ok(await self._do_revoke(module_id, subject, keys))
        items = tuple(AccessItem.from_key(k) for k in keys) if keys else ()
        what = "these items" if keys else "its whole grant"
        card = Card(module_id, subject, CardAction.REVOKE, items, f"{caller} asks to take back {what} from "
                    f"{module_id}; it turns off right away and its running task is stopped", caller,
                    everything=keys is None)  # fmt: skip
        self._open(card)
        return Result.ok(f"Asked the user on a card ({card.id}); the answer reaches you as a note")

    async def close(self) -> None:
        cards = list(self._cards.values())
        for task in list(self._work):
            task.cancel()
        await asyncio.gather(*self._work, return_exceptions=True)
        for card in cards:
            self._settle(card, AccessDenied("the app stopped before you answered"))
            if card.shown:
                self._changed(card.module_id, card.subject, f"{card.who}'s card closed: the app stopped", card.id)

    # --- inside ---

    def _changed(self, module_id: str, subject: str, text: str, request_id: str = "",
                 granted: tuple[AccessItem, ...] = ()) -> None:  # fmt: skip
        """Publish one `PermissionChanged`: every grant change and closed card goes through here."""
        self._publish(PermissionChanged(module_id=module_id, subject=subject, granted=granted,
                                        request_id=request_id, text=text))  # fmt: skip

    def _open(self, card: Card) -> None:
        self._cards[card.id] = card
        task = asyncio.create_task(self._run(card), name=f"permissions-card-{card.id}")
        self._work.add(task)
        task.add_done_callback(self._work.discard)
        card.task = task

    def _drop(self, card: Card, text: str) -> None:
        if card.task is not None:
            card.task.cancel()
        self._forget(card)
        self._settle(card, AccessDenied(text))
        if card.shown:
            self._changed(card.module_id, card.subject, text, card.id)

    def _forget(self, card: Card) -> None:
        if self._cards.get(card.id) is card:
            del self._cards[card.id]
        if self._asking.get((card.module_id, card.subject)) is card:
            del self._asking[(card.module_id, card.subject)]

    @staticmethod
    def _settle(card: Card, result: tuple[AccessItem, ...] | Exception) -> None:
        if card.outcome.done():
            return
        if isinstance(result, Exception):
            card.outcome.set_exception(result)
        else:
            card.outcome.set_result(result)

    async def _run(self, card: Card) -> None:
        try:
            rules: tuple[str, ...] = ()
            if card.action is CardAction.ACCESS:
                refused = refusals(card.items, self._protected)
                notes = [AccessNote(text=t, items=(k,), source="refused") for k, t in refused.items()]
                card.items = tuple(i for i in card.items if i.key not in refused)
                notes += rule_warnings(card.items)
                if self._reviewer:
                    review = await self._review(card, notes)
                    card.reviewed = review is not None
                    notes += review or []
                card.notes, rules = tuple(notes), FIXED_RULES
            card.shown = True
            self._publish(PermissionRequested(
                request_id=card.id, module_id=card.module_id, subject=card.subject, action=card.action.value,
                reason=card.reason, items=card.items, notes=card.notes, reviewed=card.reviewed, rules=rules,
                caller=card.caller,
            ))  # fmt: skip
            try:
                keep = await asyncio.wait_for(asyncio.shield(card.reply), self._answer_timeout)
                late = ""
            except TimeoutError:
                keep, late = None, " (no answer in time)"
            self._forget(card)
            await self._appliers[card.action](card, keep, late)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._log.exception("Permission card %s for %s failed", card.id, card.who)
            self._settle(card, AccessDenied(f"{card.who}'s card failed: {exc}"))
        finally:
            self._forget(card)
            self._settle(card, AccessDenied(f"{card.who}'s card closed"))

    async def _apply_grant(self, card: Card, keep: tuple[str, ...] | None, late: str) -> None:
        async def widen() -> str:
            saved = self.store.get(card.module_id, card.subject)
            if card.adds and saved is not None:
                saved = saved.with_added(keep)
            return await self._do_grant(saved, keep)

        await self._close_agent_card(card, keep, late, widen)

    async def _apply_revoke(self, card: Card, keep: tuple[str, ...] | None, late: str) -> None:
        async def take_back() -> str:
            return await self._do_revoke(card.module_id, card.subject, None if card.everything else keep)

        await self._close_agent_card(card, keep, late, take_back)

    async def _close_agent_card(self, card: Card, keep: tuple[str, ...] | None, late: str,
                                act: Callable[[], Awaitable[str]]) -> None:  # fmt: skip
        """An agent's grant or revoke card was answered: carry it out on Allow, then tell you and the agent."""
        if keep is None:
            text = f"The user denied {card.caller}'s {card.action.value} for {card.who}{late}; nothing changed."
        else:
            text = await act()
        self._changed(card.module_id, card.subject, text, card.id)
        if card.caller:
            self._publish(AgentNotice(agent_id=card.caller, text=text, source="permissions"))
        self._settle(card, ())

    async def _apply_access(self, card: Card, keep: tuple[str, ...] | None, late: str) -> None:
        # Items its agent asked for itself stay granted when its config list asks again.
        prev = self.store.get(card.module_id, card.subject)
        kept_added = tuple(k for k in prev.added if k in prev.granted and k not in card.asked) if prev else ()
        asked = Grant(card.module_id, card.subject, card.fingerprint, card.asked, added=kept_added)
        if keep is None:
            text = f"{card.who}'s access list was denied{late}; it stays off."
            self.store.put(asked.with_granted((), denied=True))
            self._changed(card.module_id, card.subject, text, card.id)
            self._settle(card, AccessDenied(text))
            return
        offered = {i.key for i in card.items}
        always = {i.key for i in card.items if not i.trimmable}
        grant = asked.with_granted(((set(keep) | always) & offered) | set(kept_added))
        self.store.put(grant)
        granted = grant.granted_items()
        text = f"{card.who} was allowed {len(granted)} of {len(card.asked)} items."
        self._changed(card.module_id, card.subject, text, card.id, granted)
        self._settle(card, granted)
        if card.activate and await self._state(card.module_id) is not ModuleState.ACTIVE:
            result = await self._send(ActivateModule(module_id=card.module_id))
            if not result.is_ok:
                self._log.warning("%s was allowed but didn't turn on: %s", card.module_id, result.error)

    async def _review(self, card: Card, notes: Sequence[AccessNote]) -> list[AccessNote] | None:
        """The reviewer's extra notes, or None when it's busy or didn't answer in time."""
        prompt = REVIEW_PROMPT.format(
            who=card.who, reason=f" ({card.reason})" if card.reason else "",
            items="\n".join(f"- {i.label}" for i in card.items) or "- (nothing)",
            warnings="\n".join(f"- {n.text}" for n in notes) or "- (none)",
        )  # fmt: skip
        started = await self._send(StartTask(text=prompt, agent_id=self._reviewer))
        if not started.is_ok:
            self._log.info("%s's list is not reviewed: %s", card.who, started.error)
            return None
        task_id = str(started.value)
        future = asyncio.get_running_loop().create_future()
        self._reviews[task_id] = future
        try:
            if task_id in self._finals:
                state, text = self._finals.pop(task_id)
            else:
                state, text = await asyncio.wait_for(future, self._review_timeout)
        except TimeoutError:
            await self._send(CancelTask(task_id=task_id))
            self._log.info("%s's list is not reviewed: no answer in %gs", card.who, self._review_timeout)
            return None
        finally:
            self._reviews.pop(task_id, None)
        if state is not TaskState.DONE:
            return None
        lines = [line.strip().lstrip("-* ").strip() for line in (text or "").splitlines()]
        lines = [line[:300] for line in lines if line and NO_FURTHER not in line.lower()]
        return [AccessNote(text=line, source="review") for line in lines[:MAX_REVIEW_LINES]]

    def _one_grant(self, module_id: str, subject: str) -> Grant | Result:
        grants = self.store.of(module_id)
        if not grants:
            return Result.invalid_arguments(f"{module_id} has no saved list yet; turn it on and it asks")
        if subject:
            found = self.store.get(module_id, subject)
            return found or Result.invalid_arguments(f"{module_id} has no saved list for {subject!r}")
        if len(grants) > 1:
            return Result.invalid_arguments(f"Name the subject: {', '.join(g.subject for g in grants)}")
        return grants[0]

    async def _do_grant(self, saved: Grant | None, keys: Iterable[str]) -> str:
        if saved is None:
            return "The list it was asked for is gone; nothing changed."
        always = {i.key for i in saved.asked_items() if not i.trimmable}
        grant = saved.with_granted(set(saved.granted) | set(keys) | always)
        self.store.put(grant)
        name = who(grant.module_id, grant.subject)
        self._changed(grant.module_id, grant.subject, f"{name}'s grant was widened.", granted=grant.granted_items())
        if await self._state(grant.module_id) is ModuleState.ACTIVE:
            return (f"{name} now holds {len(grant.granted)} items; it applies from its next session (at once when "
                    "idle), with no need to turn it off.")  # fmt: skip
        result = await self._send(ActivateModule(module_id=grant.module_id))
        if not result.is_ok:
            return f"{name} now holds {len(grant.granted)} items, but didn't turn on: {result.error}"
        return f"{name} now holds {len(grant.granted)} items and was turned on."

    async def _do_revoke(self, module_id: str, subject: str, keys: Iterable[str] | None) -> str:
        keys = set(keys) if keys is not None else None
        for g in [g for g in self.store.of(module_id) if not subject or g.subject == subject]:
            whole = keys is None or any(AccessItem.from_key(k).kind is AccessKind.WORKSPACE for k in keys & set(g.granted))
            if whole:
                self.store.remove(module_id, g.subject)
                granted: tuple[AccessItem, ...] = ()
            else:
                narrowed = g.with_granted(set(g.granted) - keys)
                self.store.put(narrowed)
                granted = narrowed.granted_items()
            self._changed(module_id, g.subject, f"{module_id} ({g.subject})'s grant was taken back.", granted=granted)
        return await self._turn_off(module_id)

    async def _turn_off(self, module_id: str) -> str:
        if await self._state(module_id) is not ModuleState.ACTIVE:
            return f"{module_id}'s grant was taken back; it was off, and it asks again when turned on."
        stopped = await self._stop_tasks(module_id)
        result = await self._send(DeactivateModule(module_id=module_id, with_dependents=True))
        if not result.is_ok:
            return f"{module_id}'s grant was taken back, but it didn't turn off: {result.error}"
        tail = "; its running task was stopped." if stopped == 1 else f"; {stopped} running tasks were stopped." if stopped else "."
        return f"{module_id} turned off{tail}"

    async def _stop_tasks(self, module_id: str) -> int:
        names = self._find(IAgentNames)
        owned = {agent for agent, owner in names.taken().items() if owner == module_id} if names else set()
        if not owned:
            return 0
        result = await self._send(GetTaskStatus())
        tasks = result.value if result.is_ok and result.value else []
        stopped = 0
        for task in tasks:
            if task.agent_id in owned and not task.state.is_final:
                stopped += (await self._send(CancelTask(task_id=task.id))).is_ok
        return stopped

    async def _state(self, module_id: str) -> ModuleState | None:
        result = await self._send(ListModules())
        infos = result.value if result.is_ok and result.value else []
        return next((i.state for i in infos if i.id == module_id), None)
