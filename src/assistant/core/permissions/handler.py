"""The permissions handler (its first piece), part of the core: access lists, saved grants, the
card, the review, and the grant calls. Always on: no module or agent can turn it off or reload it.

It uses only the core's generic parts, handed in by the App: the router's `send`, the bus's
`publish`, and the container's `find` (for `IAgentNames` at revoke time). The review (D6) is a
listener's job: the handler sends `ReviewAccessList` and waits for `AddCardNotes`; the module
that handles it (the Agent Hub) runs the review task. The core never starts a task, and no
module is imported.

A module's start can't wait on a card (`ActivateModule` times out), so `request_set(wait=False)`
answers from the saved grant when the list is unchanged, and otherwise opens a card and raises
`AccessPending`; on Allow the handler saves the grant and turns the module on itself. With
`wait=True` (a helper launched inside an approved run) it awaits your answer.

An answered card is applied by its action's handler, looked up in a table (principle 20):
`access` saves the module's list; `grant` and `revoke` carry out an agent's call; `message`
(one item a module asks for an agent, `ask`: the Hub's message gate) is Allow once, Always
allow (saved under the module and the agent's kind) or Deny. Taking back only `message:`
items never turns the module off.

**Auto skips the card.** Before any card, `_in_auto(caller)` reads the calling agent's own
permission mode (each worker and Talker pair has its own; `talker:<id>` is `<id>`'s pair) from
the core's Callers port (`mode_of`). The main tab's plain `talker` has no pair here, so it always
gets the card. In Auto the card isn't shown: a grant, request or revoke is carried out at once, a
message is Allow once, and an access list is allowed for this launch, nothing saved. The caller
of an access list is whoever turned the module on (`ACTING_FOR`, set by `modules.on`). An unknown
caller, a failed lookup or Manual: the card shows. `git push` and the risky-step stop are never
cards, so this check doesn't touch them.

**Confirm cards: Auto never skips them.** `confirm` asks yes or no before a risky step (the core
menu's `modules.add`, `modules.remove`, `modules.reload`, `modules.off` with dependents; the
Talker's restart). An agent's `RELOAD:` / `ADD_MODULE:` line asks on the agent's own card
instead (`PermissionGate.ask(always=True)`), shown in Auto too. Only a caller that is you clicking
(`you`) runs at once; a step marked `risky` (lesser) also runs at once for a caller in Auto. On
Allow the handler runs the step itself (a command it sends, so its sender is the core).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable, Iterable, Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
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
    AddCardNotes,
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
    PermissionMode,
    PermissionRequested,
    Result,
    ReviewAccessList,
)
from assistant.core.permissions.rules import FIXED_RULES, REPO, protected_paths, refusals, rule_warnings
from assistant.core.permissions.store import OLD_GRANTS, Grant, GrantStore, copy_old_grants, fingerprint

GRANTS_FILE = REPO / "config" / "permissions.toml"
OLD_GRANTS_FILE = REPO / OLD_GRANTS  # copied once to the grants file at startup if that is missing
# Defaults for `from_config`, read at each call (tests make them short and turn the review off).
# Shared code names no module (principle 21): which agent reviews a list and which callers are
# you clicking come from `[core.permissions]` in config (`reviewer`, `you`); none by default.
REVIEWER = ""
YOU: tuple[str, ...] = ()
REVIEW_TIMEOUT = 90.0
ANSWER_TIMEOUT = 600.0
TALKER_PREFIX = "talker:"  # a helper tab's Talker, `talker:<agent id>`: its pair's mode is that agent's

# Who turned a module on, for its access list's Auto check. `modules.on` sets it around its
# `ActivateModule`; the module's start runs in a task copied from that context, so its
# `request_set` reads it (requires turned on with it too). Empty: nobody known, the card shows.
ACTING_FOR: ContextVar[str] = ContextVar("permissions_acting_for", default="")

MAX_REVIEW_LINES = 8
REVIEW_GRACE = 5.0  # seconds past the review's own timeout before the card shows without it


class CardAction(StrEnum):
    """What a card asks: a module's access list, or an agent's grant or revoke call. The values
    are `PermissionRequested.action`'s."""

    ACCESS = "access"
    GRANT = "grant"
    REVOKE = "revoke"
    MESSAGE = "message"
    CONFIRM = "confirm"


Step = Command | Callable[[], Awaitable[Result]]  # what a confirm card runs on Allow


def messages_only(keys: Iterable[str]) -> bool:
    """Whether every key is a `message:` item (taking those back leaves the module on)."""
    keys = list(keys)
    return bool(keys) and all(AccessItem.from_key(k).kind is AccessKind.MESSAGE for k in keys)


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
    remember: bool = True  # message: Always allow (False: Allow once), from the answer
    notes: tuple[AccessNote, ...] = ()
    step: Step | None = None  # confirm: what runs on Allow
    result: Result | None = None  # confirm: the step's outcome (or the refusal)
    tell: bool = True  # confirm: tell the caller by a note (False: it awaits the result itself)
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

    #: The events it publishes (the card events), part of what the core offers (`App.PUBLISHES`).
    PUBLISHES = (PermissionRequested, PermissionChanged)

    def __init__(self, send: Callable[[Command], Awaitable[Result]], publish: Callable[[Event], None],
                 find: Callable[[type], Any], grants_file: Path = GRANTS_FILE, reviewer: str = REVIEWER,
                 review_timeout: float = REVIEW_TIMEOUT, answer_timeout: float = ANSWER_TIMEOUT,
                 you: Iterable[str] = YOU, log: logging.Logger | None = None,
                 mode_of: Callable[[str], PermissionMode] | None = None,
                 config_dir: Path | None = None) -> None:  # fmt: skip
        """`config_dir`: the app's config folder in use; it joins the protected zone (writes
        refused on every list, reads allowed), so an outside ASSISTANT_CONFIG_DIR is protected too."""
        self._send = send
        # Each agent's mode, from the core's Callers port (D2); none given: everyone is in Manual.
        self._mode_of = mode_of or (lambda _agent_id: PermissionMode.MANUAL)
        self._publish = publish
        self._find = find
        self._log = log or logging.getLogger(__name__)
        self.store = GrantStore(grants_file, self._log)
        self._protected = protected_paths(grants_file, config_dir)
        self._reviewer = reviewer
        self._review_timeout = review_timeout
        self._answer_timeout = answer_timeout
        self._you = tuple(you)
        self._cards: dict[str, Card] = {}
        self._asking: dict[tuple[str, str], Card] = {}
        self._last: dict[tuple[str, str], str] = {}  # the fingerprint asked this launch
        self._reviews: dict[str, asyncio.Future] = {}  # card id -> its review's (notes, reviewed)
        self._work: set[asyncio.Task] = set()
        self._agents: dict[str, tuple[str, str]] = {}  # agent id -> (its module, the subject of its grant)
        # An answered card's handler, by its action (principle 20).
        self._appliers: dict[CardAction, Callable[[Card, tuple[str, ...] | None, str], Awaitable[None]]] = {
            CardAction.ACCESS: self._apply_access,
            CardAction.GRANT: self._apply_grant,
            CardAction.REVOKE: self._apply_revoke,
            CardAction.MESSAGE: self._apply_message,
            CardAction.CONFIRM: self._apply_confirm,
        }

    @classmethod
    def from_config(cls, config: dict[str, Any], send, publish, find, mode_of=None,
                    config_dir: Path | None = None) -> PermissionsHandler:  # fmt: skip
        """`config_dir`: the app's config folder, protected like `config/` (passed on to the handler).
        From `[core.permissions]`: `grants_file` (default `config/permissions.toml` in the repo,
        the protected zone; relative to the repo), `reviewer` (the agent that reviews a list before the
        card shows, named in `ReviewAccessList`; empty for none), `review_timeout`, `answer_timeout`, and `you` (the callers that
        are you clicking in a UI; anyone else's grant or revoke shows you a card). At startup, a
        missing grants file is copied once from the old one (`copy_old_grants`), which stays."""
        grants_file = Path(config.get("grants_file") or GRANTS_FILE)
        if not grants_file.is_absolute():
            grants_file = REPO / grants_file
        copy_old_grants(grants_file, OLD_GRANTS_FILE)
        return cls(send, publish, find, grants_file, reviewer=str(config.get("reviewer", REVIEWER)),
                   review_timeout=float(config.get("review_timeout", REVIEW_TIMEOUT)),
                   answer_timeout=float(config.get("answer_timeout", ANSWER_TIMEOUT)),
                   you=tuple(config.get("you", YOU)), mode_of=mode_of, config_dir=config_dir)  # fmt: skip

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
        if await self._in_auto(caller := ACTING_FOR.get()):  # allowed for this launch, nothing saved
            refused = refusals(items, self._protected)
            allowed = tuple(i for i in items if i.key not in refused)
            self._log.info("%s's access list allowed in Auto (turned on by %s), not saved", who(module_id, subject), caller)
            return allowed
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

    def kind_of(self, agent_id: str) -> str:
        """The subject an agent's grants are saved under: its kind (from `own_agent`), else its id."""
        return self._agents.get(agent_id, ("", agent_id))[1] or agent_id

    def granted(self, module_id: str, agent_id: str, item: AccessItem) -> bool:
        saved = self.store.get(module_id, self.kind_of(agent_id))
        return saved is not None and not saved.denied and item.key in saved.granted

    async def ask(self, module_id: str, agent_id: str, item: AccessItem, reason: str = "") -> bool:
        """`module_id` asks whether `agent_id` may have `item`: a `message` card (Allow once,
        Always allow, Deny). Awaits your answer; True if allowed. Cancelling closes the card."""
        if self.granted(module_id, agent_id, item):
            return True
        if await self._in_auto(agent_id):  # Allow once: nothing saved
            self._log.info("%s may %s this once (Auto)", agent_id, item.label)
            return True
        card = Card(module_id, self.kind_of(agent_id), CardAction.MESSAGE, (item,), reason, agent_id)
        self._open(card)
        try:
            await asyncio.shield(card.outcome)
            return True
        except AccessDenied:
            return False
        except asyncio.CancelledError:
            self._drop(card, f"{agent_id}'s request to {item.label} was withdrawn")
            raise

    async def confirm(self, module_id: str, caller: str, what: str, step: Step, reason: str = "",
                      wait: bool = False, risky: bool = False) -> Result:  # fmt: skip
        """Ask you yes or no before `step` (`what`: "modules.add (package: x)"); see the module
        notes. `you` callers run at once; `risky` steps also for a caller in Auto. `wait=False`
        returns "Asked the user on a card" (the router's timeout would cut a waiting call); the
        outcome reaches `caller` as a notice. `wait=True` returns the step's `Result`."""
        if caller in self._you or (risky and await self._in_auto(caller)):
            return await self._run_step(step)
        text = what + (f": {reason}" if reason else "")
        card = Card(module_id, module_id, CardAction.CONFIRM, (), text, caller, step=step, tell=not wait)
        self._open(card)
        self._log.info("%s asks the user to confirm: %s (card %s)", caller or module_id, what, card.id)
        if not wait:
            return Result.ok(f"Asked the user on a card ({card.id}) to confirm {what}; the answer reaches you as a note")
        try:
            await asyncio.shield(card.outcome)
        except AccessDenied as exc:
            return Result.failed(str(exc))
        except asyncio.CancelledError:
            self._drop(card, f"{caller or module_id}'s request to {what} was withdrawn")
            raise
        return card.result or Result.failed(f"{what}: no outcome")

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
        card.remember = cmd.remember
        offered = [i.key for i in card.items]
        if cmd.keep is not None and (bad := [k for k in cmd.keep if k not in offered]):
            return Result.invalid_arguments(f"Not on card {card.id}: {', '.join(bad)}")
        card.reply.set_result(tuple(offered if cmd.keep is None else cmd.keep))
        return Result.ok("allowed")

    async def add_notes(self, cmd: AddCardNotes) -> Result:
        """`AddCardNotes`: a review's outcome for a card waiting on it (D6)."""
        future = self._reviews.get(cmd.request_id)
        if future is None or future.done():
            return Result.invalid_arguments(f"No card {cmd.request_id!r} waits for a review")
        future.set_result((cmd.notes, cmd.reviewed))
        return Result.ok("noted")

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
        if caller in self._you or await self._in_auto(caller):
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
        if await self._in_auto(caller):
            keys = tuple(i.key for i in new)
            return Result.ok(await self._do_grant(saved.with_added(keys), keys) + " It applies from your next session.")
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
        if caller in self._you or await self._in_auto(caller):
            return Result.ok(await self._do_revoke(module_id, subject, keys))
        items = tuple(AccessItem.from_key(k) for k in keys) if keys else ()
        what = "these items" if keys else "its whole grant"
        if messages_only(keys if keys is not None else (k for g in targets for k in g.granted)):
            effect = "the next message asks again"
        else:
            effect = "it turns off right away and its running task is stopped"
        card = Card(module_id, subject, CardAction.REVOKE, items, f"{caller} asks to take back {what} from "
                    f"{module_id}; {effect}", caller, everything=keys is None)  # fmt: skip
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

    async def _in_auto(self, caller: str) -> bool:
        """Whether `caller`'s worker and Talker pair is in Auto: the one place the handler reads a
        mode. `talker:<id>` is `<id>`'s pair; the main tab's plain `talker` has no pair here, so it
        always gets the card. You, nobody or an unknown agent: no. The mode is the
        core's Callers port's (only you set Auto there), never what an agent says of itself."""
        if not caller or caller in self._you:
            return False
        return self._mode_of(caller.removeprefix(TALKER_PREFIX)) is PermissionMode.AUTO

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

    async def _apply_message(self, card: Card, keep: tuple[str, ...] | None, late: str) -> None:
        """A `message` card: Deny (or no answer) refuses; Allow once saves nothing; Always adds
        the item to the module's grant for the agent's kind. The asking module tells the agent."""
        item, saved = card.items[0], self.store.get(card.module_id, card.subject)
        if keep is None:
            text = f"The user denied {card.caller}'s request to {item.label}{late}."
            self._changed(card.module_id, card.subject, text, card.id)
            self._settle(card, AccessDenied(text))
            return
        if card.remember:
            saved = saved or Grant(card.module_id, card.subject, "", ())
            asked = saved.asked if item.key in saved.asked else (*saved.asked, item.key)
            saved = replace(saved, asked=asked, fingerprint=fingerprint(AccessItem.from_key(k) for k in asked))
            saved = saved.with_granted({*saved.granted, item.key})
            self.store.put(saved)
            text = f"{card.caller} may {item.label} from now on (saved for {card.subject})."
        else:
            text = f"{card.caller} may {item.label} this once."
        self._changed(card.module_id, card.subject, text, card.id, saved.granted_items() if saved else ())
        self._settle(card, (item,))

    async def _apply_confirm(self, card: Card, keep: tuple[str, ...] | None, late: str) -> None:
        """A confirm card: Allow runs the step; Deny (or no answer) runs nothing. You and the
        caller (by a note, unless it awaits the result) are told the outcome."""
        if keep is None:
            card.result = Result.failed(f"The user said no to {card.reason}{late}; nothing ran.")
        else:
            card.result = await self._run_step(card.step)
        result = card.result
        text = (f"The user allowed {card.reason}: " + (str(result.value) if result.value else "done.")) if result.is_ok \
            else (result.error if keep is None else f"The user allowed {card.reason}, but it failed: {result.error}")
        self._changed(card.module_id, card.subject, text, card.id)
        if card.caller and card.tell:
            await self._notify(card.caller, text)
        self._settle(card, ())

    async def _run_step(self, step: Step | None) -> Result:
        if step is None:
            return Result.failed("nothing to run")
        try:
            return await (self._send(step) if isinstance(step, Command) else step())
        except Exception as exc:
            self._log.exception("A confirmed step failed")
            return Result.failed(f"it failed: {exc}")

    async def _close_agent_card(self, card: Card, keep: tuple[str, ...] | None, late: str,
                                act: Callable[[], Awaitable[str]]) -> None:  # fmt: skip
        """An agent's grant or revoke card was answered: carry it out on Allow, then tell you and the agent."""
        if keep is None:
            text = f"The user denied {card.caller}'s {card.action.value} for {card.who}{late}; nothing changed."
        else:
            text = await act()
        self._changed(card.module_id, card.subject, text, card.id)
        if card.caller:
            await self._notify(card.caller, text)
        self._settle(card, ())

    async def _notify(self, agent_id: str, text: str) -> None:
        """A note for `agent_id`'s next turn: `AgentNotice`, a command the Hub handles (D5). No
        Hub (a bare test app): logged only."""
        result = await self._send(AgentNotice(agent_id=agent_id, text=text, source="permissions"))
        if not result.is_ok:
            self._log.info("No note reached %s (%s): %s", agent_id, result.error, text)

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
        """The reviewer's extra notes, or None when there's no reviewer, it's busy, or it didn't
        answer in time. The core only asks (`ReviewAccessList`) and waits for `AddCardNotes`."""
        future = asyncio.get_running_loop().create_future()
        self._reviews[card.id] = future
        try:
            asked = await self._send(ReviewAccessList(
                request_id=card.id, reviewer=self._reviewer, who=card.who, reason=card.reason,
                items=tuple(i.label for i in card.items), warnings=tuple(n.text for n in notes),
                timeout=self._review_timeout,
            ))  # fmt: skip
            if not asked.is_ok and not future.done():
                self._log.info("%s's list is not reviewed: %s", card.who, asked.error)
                return None
            try:
                lines, reviewed = await asyncio.wait_for(future, self._review_timeout + REVIEW_GRACE)
            except TimeoutError:
                self._log.info("%s's list is not reviewed: no answer in %gs", card.who, self._review_timeout)
                return None
        finally:
            self._reviews.pop(card.id, None)
        if not reviewed:
            return None
        return [AccessNote(text=line[:300], source="review") for line in lines[:MAX_REVIEW_LINES] if line.strip()]

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
        targets = [g for g in self.store.of(module_id) if not subject or g.subject == subject]
        stays_on = messages_only(keys if keys is not None else (k for g in targets for k in g.granted))
        for g in targets:
            whole = keys is None or any(AccessItem.from_key(k).kind is AccessKind.WORKSPACE for k in keys & set(g.granted))
            if whole:
                self.store.remove(module_id, g.subject)
                granted: tuple[AccessItem, ...] = ()
            else:
                narrowed = g.with_granted(set(g.granted) - keys)
                self.store.put(narrowed)
                granted = narrowed.granted_items()
            self._changed(module_id, g.subject, f"{module_id} ({g.subject})'s grant was taken back.", granted=granted)
        if stays_on:
            return f"{module_id}'s message grant was taken back; it stays on, and the next message asks again."
        return await self._turn_off(module_id)

    async def _turn_off(self, module_id: str) -> str:
        if await self._state(module_id) is not ModuleState.ACTIVE:
            return f"{module_id}'s grant was taken back; it was off, and it asks again when turned on."
        stopped = await self._stop_tasks(module_id)
        result = await self._send(DeactivateModule(module_id=module_id))  # only it: its dependents stay on
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
