"""Token counting for one `claude` session, from its stream-json lines, and the one map of the
token kinds: how each is named by the API's `usage`, a result's per-model usage, and the
`SessionUsage` event. Plain Python, no app imports."""

from __future__ import annotations

from typing import Any, NamedTuple


class TokenKind(NamedTuple):
    """One kind of token under its three names."""

    usage: str  # in an API `usage` (assistant lines, results, a sub-agent's result)
    model: str  # in a result's `modelUsage` / `model_usage_since_last_result`, per model
    event: str  # the `SessionUsage` field (also `UsageLedger`'s)


# `used` keys → their names. The one owner of the token fields (principle 19).
TOKEN_KINDS: dict[str, TokenKind] = {
    "input": TokenKind("input_tokens", "inputTokens", "input_tokens"),
    "cache_write": TokenKind("cache_creation_input_tokens", "cacheCreationInputTokens", "cache_write_tokens"),
    "cache_read": TokenKind("cache_read_input_tokens", "cacheReadInputTokens", "cache_read_tokens"),
    "output": TokenKind("output_tokens", "outputTokens", "output_tokens"),
}
# `used` keys and the `usage` fields they come from.
USAGE_FIELDS = {key: kind.usage for key, kind in TOKEN_KINDS.items()}
# The `SessionUsage` token fields, in order.
EVENT_FIELDS = tuple(kind.event for kind in TOKEN_KINDS.values())


def _zero() -> dict[str, int]:
    return dict.fromkeys(TOKEN_KINDS, 0)


def event_fields(used: dict[str, int]) -> dict[str, int]:
    """`used` (by key) as `SessionUsage` keyword arguments."""
    return {kind.event: used[key] for key, kind in TOKEN_KINDS.items()}


class UsageMeter:
    """Counts one session's tokens from the lines its process writes.

    `context_tokens` is the input size of the latest call (cached or not), read from each
    assistant line's `usage`: what every further call resends; 0 after `restarted`. `used`
    (tokens by kind) adds up every call since construction, across restarts, so cached
    context counts again on every call. `used` is this session's own calls; the sub-agents it
    starts are tallied apart in `subagents`. Lines with a `parent_tool_use_id` (a sub-agent's)
    never change `context_tokens` or `used`.

    Call `line(event)` for every JSON line before anyone else sees it, and `restarted()` when
    a new process starts.
    """

    def __init__(self) -> None:
        self.context_tokens = 0
        # Input: every call counts once; a call's lines share its message id, so the latest
        # line's usage stands for the call until the next id arrives. Output: the streamed
        # lines undercount it (2.5k against 129k in one real session), so it comes from each
        # turn's `result`, with the lines' count standing in only while a turn runs.
        self._used_before = _zero()
        self._call_id: str | None = None
        self._call_used = _zero()
        self._output_before = 0
        self._turn_output = 0  # streamed estimate for the turn in progress
        # Sub-agents (the Agent tool): their lines don't stream with `usage`, and an Agent call's
        # `tool_use_result.usage` is only the sub-agent's LAST call (checked on a real log,
        # 2026-11-07: 41 tool uses, one call's worth). So each turn's sub-agent tokens are the
        # result's `model_usage_since_last_result` (every call, sub-agents included) less this
        # session's own calls since the last result, shared among the sub-agents that returned
        # in the turn by their last-call sizes. Without that field, the last-call numbers are used.
        self._subagents: dict[str, dict[str, Any]] = {}
        self._pending: dict[str, dict[str, int]] = {}  # agentId -> its last call, returned this turn
        self._own_at_result = _zero()  # `used` at the last result
        self._model_before = _zero()  # this process's `modelUsage` so far

    @property
    def used(self) -> dict[str, int]:
        """Tokens by kind (`input`, `cache_write`, `cache_read`, `output`), every call so far."""
        used = {key: self._used_before[key] + self._call_used[key] for key in TOKEN_KINDS}
        used["output"] = self._output_before + self._turn_output
        return used

    @property
    def subagents(self) -> dict[str, dict[str, Any]]:
        """Each sub-agent's tokens since construction, by its `agentId`: `{"type": agentType,
        "used": {input, cache_write, cache_read, output}}`. Tokens a turn spent outside this
        session's own calls with no sub-agent returning (one cut off) go under `unnamed`."""
        return {key: {"type": sub["type"], "used": dict(sub["used"])}
                for key, sub in self._subagents.items() if any(sub["used"].values())}  # none until the turn's share

    def line(self, event: dict[str, Any]) -> None:
        """Count one line the process wrote."""
        kind = event.get("type")
        if kind == "result":
            self._count_turn(event)
        elif kind == "assistant" and not event.get("parent_tool_use_id"):
            self._count_call(event.get("message", {}))  # a sub-agent's line never counts as the parent's
        elif kind == "user":
            self._count_subagent(event)

    def restarted(self) -> None:
        """A new process: context from 0; a cut-off turn's output kept; its results count from 0
        again; a cut-off turn's sub-agents are dropped."""
        self.context_tokens = 0
        self._commit_call()
        self._output_before, self._turn_output = self._output_before + self._turn_output, 0
        self._own_at_result, self._model_before, self._pending = self.used, _zero(), {}

    # --- inside ---

    def _sub_row(self, key: str, kind: str) -> dict[str, Any]:
        return self._subagents.setdefault(key, {"type": kind, "used": _zero()})

    def _count_subagent(self, event: dict[str, Any]) -> None:
        """An Agent call's result line: note the sub-agent; its tokens come with the turn's result."""
        result = event.get("tool_use_result")
        if not isinstance(result, dict) or not result.get("agentId") or not isinstance(result.get("usage"), dict):
            return
        key = str(result["agentId"])
        self._sub_row(key, str(result.get("agentType") or "subagent"))
        self._pending[key] = {k: int(result["usage"].get(kind.usage) or 0) for k, kind in TOKEN_KINDS.items()}

    def _turn_models(self, result: dict[str, Any]) -> dict[str, int] | None:
        """Every call's tokens in this turn (sub-agents included), from the result; None if it doesn't say."""
        def summed(models: Any) -> dict[str, int]:
            out = _zero()
            for model in models.values() if isinstance(models, dict) else ():
                for key, kind in TOKEN_KINDS.items():
                    out[key] += int(model.get(kind.model) or 0) if isinstance(model, dict) else 0
            return out

        cumulative = summed(result["modelUsage"]) if isinstance(result.get("modelUsage"), dict) else None
        turn = None
        if isinstance(result.get("model_usage_since_last_result"), dict):
            turn = summed(result["model_usage_since_last_result"])
        elif cumulative is not None:
            turn = {key: max(0, cumulative[key] - self._model_before[key]) for key in TOKEN_KINDS}
        if cumulative is not None:
            self._model_before = cumulative
        return turn

    def _count_subagent_turn(self, result: dict[str, Any]) -> None:
        """Share the turn's tokens beyond this session's own calls among the sub-agents that returned."""
        own_now = self.used
        own = {key: own_now[key] - self._own_at_result[key] for key in TOKEN_KINDS}
        self._own_at_result = own_now
        pending, self._pending = self._pending, {}
        turn = self._turn_models(result)
        if turn is None:  # no per-turn numbers: the last-call numbers are all there is
            for key, last in pending.items():
                for field in TOKEN_KINDS:
                    self._subagents[key]["used"][field] += last[field]
            return
        extra = {key: max(0, turn[key] - own[key]) for key in TOKEN_KINDS}
        if not any(extra.values()):
            return
        if not pending:
            pending = {"unnamed": {}}
            self._sub_row("unnamed", "sub-agents and tools")
        weights = {key: sum(last.values()) or 1 for key, last in pending.items()}
        whole, keys = sum(weights.values()), list(pending)
        for field, amount in extra.items():
            given = 0
            for key in keys[:-1]:
                share = amount * weights[key] // whole
                self._subagents[key]["used"][field] += share
                given += share
            self._subagents[keys[-1]]["used"][field] += amount - given

    def _count_call(self, message: dict[str, Any]) -> None:
        usage = message.get("usage")
        if not usage:
            return
        call_id = message.get("id")
        if call_id is None or call_id != self._call_id:
            self._commit_call()
            self._call_id = call_id
        else:
            self._turn_output -= self._call_used["output"]
        self._call_used = {key: int(usage.get(kind.usage) or 0) for key, kind in TOKEN_KINDS.items()}
        self._turn_output += self._call_used["output"]
        self.context_tokens = self._call_used["input"] + self._call_used["cache_write"] + self._call_used["cache_read"]

    def _count_turn(self, result: dict[str, Any]) -> None:
        """A turn ended: its real output count replaces the streamed estimate; sub-agents get their share."""
        usage = result.get("usage") or {}
        self._output_before += int(usage["output_tokens"]) if "output_tokens" in usage else self._turn_output
        self._turn_output = 0
        self._count_subagent_turn(result)

    def _commit_call(self) -> None:
        for key in TOKEN_KINDS:
            self._used_before[key] += self._call_used[key]
        self._call_id, self._call_used = None, _zero()
