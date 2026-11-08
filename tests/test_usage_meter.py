"""UsageMeter: one session's token counting, and the one token-field map."""

from assistant.infra.usage_ledger import TOKEN_FIELDS
from assistant.infra.usage_meter import EVENT_FIELDS, UsageMeter, event_fields


def _call(call_id, inp, out, cache_read=0):
    usage = {"input_tokens": inp, "output_tokens": out, "cache_read_input_tokens": cache_read}
    return {"type": "assistant", "message": {"id": call_id, "usage": usage}}


def test_meter_counts_calls_once_and_takes_output_from_the_result():
    meter = UsageMeter()
    meter.line(_call("a", 100, 5, cache_read=900))
    meter.line(_call("a", 100, 8, cache_read=900))  # the same call, streamed again
    assert meter.context_tokens == 1000
    meter.line({"type": "result", "usage": {"output_tokens": 50}})
    assert meter.used == {"input": 100, "cache_write": 0, "cache_read": 900, "output": 50}
    meter.line({"type": "assistant", "parent_tool_use_id": "x", "message": {"id": "s", "usage": {"input_tokens": 7}}})
    assert meter.used["input"] == 100  # a sub-agent's line never counts as the session's own
    meter.restarted()
    assert meter.context_tokens == 0 and meter.used["input"] == 100


def test_meter_shares_a_turns_extra_tokens_with_the_subagent_that_returned():
    meter = UsageMeter()
    meter.line(_call("a", 10, 1))
    meter.line({"type": "user", "tool_use_result": {"agentId": "s1", "agentType": "Explore", "usage": {"input_tokens": 3}}})
    meter.line({"type": "result", "usage": {"output_tokens": 1},
                "model_usage_since_last_result": {"m": {"inputTokens": 40, "outputTokens": 6}}})
    sub = meter.subagents["s1"]
    assert sub["type"] == "Explore" and sub["used"]["input"] == 30 and sub["used"]["output"] == 5


def test_one_map_for_the_event_fields():
    assert TOKEN_FIELDS == EVENT_FIELDS
    assert event_fields({"input": 1, "cache_write": 2, "cache_read": 3, "output": 4}) == {
        "input_tokens": 1, "cache_write_tokens": 2, "cache_read_tokens": 3, "output_tokens": 4,
    }
