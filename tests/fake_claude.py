"""A stand-in for `claude -p` in stream-json mode, for tests. Arguments are ignored.

Each user message gets one turn: an assistant text, then a `result` whose text
is the message itself, except:
- a `New task:` containing `ASKME`: the result ends with `NEED: Which style?`
- containing `SLOW`: no result until an interrupt arrives; then the turn ends
  with `error_during_execution`, as the real one does
- containing `CRASH`: the process exits
- containing `PERMIT`: asks permission with a `can_use_tool` control request, waits
  for the answer, and ends the turn with `allowed` or `denied: <message>`
- a `New task:` containing `HANDOFFONCE`, or anything containing `HANDOFFALWAYS`: the result
  ends with `HANDOFF: docs/next-steps/part.md`
- containing "asked to reset your session": the result ends with `HANDOFF: docs/next-steps/reset.md`

Each turn is one call (one message id, `msg_<n>`): its `usage` says 1000 input tokens per
message this process has had, so a fresh process starts small again, plus 10 output
tokens; its result says 25 output tokens for the turn (the streamed count is low, as for
real) and `total_cost_usd` 0.01 per message, counted per process like the real one. A `[Usage] ...` line is left out of the echo (the model wouldn't repeat it)
unless the message contains `SHOWUSAGE`.
"""

import json
import sys

TOKENS_PER_MESSAGE = 1000


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


messages = 0  # in this process


def result(text: str, error: bool = False) -> None:
    emit({
        "type": "result",
        "subtype": "error_during_execution" if error else "success",
        "is_error": error,
        "result": "" if error else text,
        "total_cost_usd": round(messages * 0.01, 2),
        "usage": {"output_tokens": 25},  # the turn's real output; the streamed lines say less, as for real
    })


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
        if "asked to reset your session" in text:
            result("Saved where I was.\nHANDOFF: docs/next-steps/reset.md")
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
            emit({"type": "control_request", "request_id": "perm-1", "request": {
                "subtype": "can_use_tool", "tool_name": "Write",
                "input": {"file_path": ".claude/skills/x/SKILL.md", "content": "x"},
            }})
            answer = json.loads(sys.stdin.readline())["response"]
            decision = answer["response"]
            assert answer["request_id"] == "perm-1"
            result("allowed" if decision["behavior"] == "allow" else f"denied: {decision['message']}")
        elif text.startswith("New task:") and "ASKME" in text:
            result("Let me check.\nNEED: Which style?")
        else:
            result(text)


if __name__ == "__main__":
    main()
