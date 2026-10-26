"""A stand-in for `claude -p` in stream-json mode, for tests. Arguments are ignored.

Each user message gets one turn: an assistant text, then a `result` whose text
is the message itself, except:
- a `New task:` containing `ASKME`: the result ends with `NEED: Which style?`
- containing `SLOW`: no result until an interrupt arrives; then the turn ends
  with `error_during_execution`, as the real one does
- containing `CRASH`: the process exits
"""

import json
import sys


def emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def result(text: str, error: bool = False) -> None:
    emit({
        "type": "result",
        "subtype": "error_during_execution" if error else "success",
        "is_error": error,
        "result": "" if error else text,
    })


def main() -> None:
    for raw in sys.stdin:
        message = json.loads(raw)
        if message["type"] == "control_request":  # interrupt with no turn running
            emit({"type": "control_response", "response": {"subtype": "success"}})
            continue
        text = message["message"]["content"][0]["text"]
        emit({"type": "system", "subtype": "init"})
        emit({"type": "assistant", "message": {"content": [{"type": "text", "text": f"working on: {text}"}]}})
        if "CRASH" in text:
            return
        if "SLOW" in text:
            emit({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Write", "input": {"file_path": "slow.txt"}},
            ]}})
            json.loads(sys.stdin.readline())  # wait for the interrupt
            emit({"type": "control_response", "response": {"subtype": "success"}})
            result("", error=True)
        elif text.startswith("New task:") and "ASKME" in text:
            result("Let me check.\nNEED: Which style?")
        else:
            result(text)


if __name__ == "__main__":
    main()
