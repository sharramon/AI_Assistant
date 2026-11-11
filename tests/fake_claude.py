"""A stand-in for `claude -p` in stream-json mode, for tests. Arguments are ignored.

Each user message gets one turn: an assistant text, then a `result` whose text
is the message itself, except:
- a `New task:` containing `ASKME`: the result ends with `NEED: Which style?`
- containing `SLOW`: no result until an interrupt arrives; then the turn ends
  with `error_during_execution`, as the real one does
- containing `CRASH`: the process exits
- containing `PERMIT`: asks permission with a `can_use_tool` control request, waits
  for the answer, and ends the turn with `allowed` or `denied: <message>` (a Write;
  with `PUSHPERMIT`, a PowerShell `git push origin main`)
- a `New task:` containing `HANDOFFONCE`, or anything containing `HANDOFFALWAYS`: the result
  ends with `HANDOFF: docs/next-steps/part.md`
- containing "asked to restart the app": the result is a reset note ending `RESTART_READY`
- containing "asked to reset your session": the result ends with `HANDOFF: docs/next-steps/reset.md`
- containing "[Context check]": the result ends with `HANDOFF: docs/next-steps/context.md`
- starting with `/compact`: the result is `Compacted.`; it fails (`error_during_execution`)
  if this process has had `COMPACTFAIL`, and waits half a second first if it has had `COMPACTWAIT`
- a `New task:` containing `RELOADME <id>`: the result ends with `RELOAD: <id>`
- containing `SUBAGENT`: one Agent call to a `general-purpose` sub-agent (`agentId` `a1b2`),
  its last call's tokens on the tool result's `tool_use_result.usage`, and the turn's every
  call (its own and the sub-agent's) on the result's `model_usage_since_last_result`
  (see `subagent_turn`)
- containing `CHROMEUSE`: a Chrome `navigate` call first; containing `CHROMECLOSE`: a Chrome
  `tabs_close_mcp` call first (either way the turn goes on as above)
- containing "Close each of your Chrome tabs" (the app's end-of-task check): a `tabs_close_mcp`
  call, and the result `Closed 1 tab.`

Each turn is one call (one message id, `msg_<n>`): its `usage` says 1000 input tokens per
message this process has had, so a fresh process starts small again, plus 10 output
tokens; its result says 25 output tokens for the turn (the streamed count is low, as for
real). A `[Usage] ...` line is left out of the echo (the model wouldn't repeat it)
unless the message contains `SHOWUSAGE`.
"""

import json
import sys
import time

TOKENS_PER_MESSAGE = 1000


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


messages = 0  # in this process
seen: set[str] = set()  # the compact flags this process has had


def result(text: str, error: bool = False, **extra) -> None:
    emit({
        "type": "result",
        "subtype": "error_during_execution" if error else "success",
        "is_error": error,
        "result": "" if error else text,
        "usage": {"output_tokens": 25},  # the turn's real output; the streamed lines say less, as for real
        **extra,
    })


SUB_USAGE = {"input_tokens": 2, "cache_creation_input_tokens": 2874, "cache_read_input_tokens": 0, "output_tokens": 4}
# The sub-agent's every call (more than its last one, as for real: 2026-11-07).
SUB_ALL = {"inputTokens": 6, "cacheCreationInputTokens": 2874, "cacheReadInputTokens": 5000, "outputTokens": 40}


def subagent_turn() -> None:
    """One Agent call, shaped like the real runs (2026-11-05, 2026-11-07): the sub-agent's prompt as a
    `user` line with `parent_tool_use_id`, a sub-agent `assistant` line with usage (the real one streams
    none; it must never count as the parent's), then its LAST call's usage on the tool_result's
    `tool_use_result`. The result's `usage` is the parent's own; its `model_usage_since_last_result`
    holds every call of the turn: the parent's two (input 2+2, cache read 1000n-2 and 100, output 25)
    and the sub-agent's (`SUB_ALL`)."""
    tool_id = f"toolu_{messages}"
    emit({"type": "assistant", "message": {"id": f"msg_{messages}_agent", "usage": {
        "input_tokens": 2, "cache_read_input_tokens": 100, "output_tokens": 5,
    }, "content": [{"type": "tool_use", "id": tool_id, "name": "Agent", "input": {"prompt": "reply with pong"}}]}})
    emit({"type": "system", "subtype": "task_started", "task_id": "t1", "tool_use_id": tool_id, "spawn_depth": 1})
    emit({"type": "user", "parent_tool_use_id": tool_id, "agent_id": "a1b2", "subagent_type": "general-purpose",
          "message": {"role": "user", "content": [{"type": "text", "text": "reply with pong"}]}})
    emit({"type": "assistant", "parent_tool_use_id": tool_id, "message": {"id": "msg_sub", "usage": {
        "input_tokens": 999, "cache_read_input_tokens": 99999, "output_tokens": 999,
    }, "content": [{"type": "text", "text": "pong"}]}})
    emit({"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tool_id, "content": [{"type": "text", "text": "pong"}]},
    ]}, "tool_use_result": {"agentId": "a1b2", "agentType": "general-purpose", "usage": SUB_USAGE,
                            "totalTokens": 2880, "totalToolUseCount": 0}})
    emit({"type": "system", "subtype": "task_notification", "task_id": "t1", "tool_use_id": tool_id,
          "usage": {"total_tokens": 2880}})
    own = {"inputTokens": 4, "cacheCreationInputTokens": 0, "cacheReadInputTokens": messages * TOKENS_PER_MESSAGE - 2 + 100,
           "outputTokens": 25}  # fmt: skip
    result("pong", model_usage_since_last_result={"claude-opus-5-5": {key: own[key] + SUB_ALL[key] for key in own}})


def main() -> None:
    global messages
    for raw in sys.stdin:
        message = json.loads(raw)
        if message["type"] == "control_request":  # interrupt with no turn running
            emit({"type": "control_response", "response": {"subtype": "success"}})
            continue
        messages += 1
        content = message["message"]["content"]
        text = next(block["text"] for block in content if block["type"] == "text")
        images = [block for block in content if block["type"] == "image" and block["source"]["data"]]
        if "SHOWUSAGE" not in text:
            text = "\n".join(line for line in text.splitlines() if not line.startswith("[Usage]"))
        if images:  # say what it was shown, so tests can see images arrive
            text = f"[{len(images)} image(s)] {text}"
        emit({"type": "system", "subtype": "init"})
        call = {"id": f"msg_{messages}", "usage": {
            "input_tokens": 2, "cache_read_input_tokens": messages * TOKENS_PER_MESSAGE - 2, "output_tokens": 10,
        }}
        emit({"type": "assistant", "message": {**call, "content": [{"type": "text", "text": f"working on: {text}"}]}})
        if "CRASH" in text:
            return
        seen.update(flag for flag in ("COMPACTFAIL", "COMPACTWAIT", "CLOSEWAIT") if flag in text)
        closing = "Close each of your Chrome tabs" in text
        for flag, tool in (("CHROMEUSE", "navigate"), ("CHROMECLOSE", "tabs_close_mcp")):
            if flag in text or (closing and tool == "tabs_close_mcp"):
                emit({"type": "assistant", "message": {**call, "content": [  # same call: counted once
                    {"type": "tool_use", "name": f"mcp__claude-in-chrome__{tool}", "input": {"tabId": 1}},
                ]}})
        if closing:
            if "CLOSEWAIT" in seen:
                time.sleep(0.5)
            result("Closed 1 tab.")
        elif text.startswith("/compact"):
            if "COMPACTWAIT" in seen:
                time.sleep(0.5)
            result("Compacted.", error="COMPACTFAIL" in seen)
        elif "asked to restart the app" in text:
            result("Was building the poems; part one done.\nRESTART_READY")
        elif "asked to reset your session" in text:
            result("Saved where I was.\nHANDOFF: docs/next-steps/reset.md")
        elif "[Context check]" in text:
            result("At a reset point.\nHANDOFF: docs/next-steps/context.md")
        elif "HANDOFFALWAYS" in text or (text.startswith("New task:") and "HANDOFFONCE" in text):
            result("Part one is built.\nHANDOFF: `docs/next-steps/part.md`")
        elif "SLOW" in text:
            emit({"type": "assistant", "message": {**call, "content": [  # same call: counted once
                {"type": "tool_use", "name": "Write", "input": {"file_path": "slow.txt"}},
            ]}})
            json.loads(sys.stdin.readline())  # wait for the interrupt
            emit({"type": "control_response", "response": {"subtype": "success"}})
            result("", error=True)
        elif "PERMIT" in text:
            tool = ({"tool_name": "PowerShell", "input": {"command": "git push origin main"}} if "PUSHPERMIT" in text
                    else {"tool_name": "Write", "input": {"file_path": ".claude/skills/x/SKILL.md", "content": "x"}})
            emit({"type": "control_request", "request_id": "perm-1", "request": {"subtype": "can_use_tool", **tool}})
            answer = json.loads(sys.stdin.readline())["response"]
            decision = answer["response"]
            assert answer["request_id"] == "perm-1"
            result("allowed" if decision["behavior"] == "allow" else f"denied: {decision['message']}")
        elif "SUBAGENT" in text:
            subagent_turn()
        elif text.startswith("New task:") and "RELOADME " in text:
            result(f"Built it.\nRELOAD: {text.split('RELOADME ', 1)[1].split()[0]}")
        elif text.startswith("New task:") and "ASKME" in text:
            result("Let me check.\nNEED: Which style?")
        else:
            result(text)


if __name__ == "__main__":
    main()
