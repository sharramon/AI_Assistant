"""Spike step 2: does interrupt -> reply -> continue work on one session?

Plays the Hub's part against one worker `claude -p` session:

  A. message:  give it a multi-step file task, interrupt after its first file,
               ask a quick question, then tell it to continue. Pass: it stops,
               answers, and finishes all the files.
  B. cancel:   give it a new long task, interrupt it (like Esc), then ask what
               it did earlier. Pass: the process survives and remembers.

It also checks that `result` marks the end of every turn (what `working` relies
on): any event between a `result` and our next message is flagged.

Every raw line in and out is saved to spikes/logs/02_interrupt.jsonl. The worker
writes its files to spikes/workspace/02/ (emptied at the start).

Run: .\\.venv\\Scripts\\python spikes\\02_interrupt.py
"""

import asyncio
import json
import shutil
import time
from pathlib import Path
from uuid import uuid4

HERE = Path(__file__).parent
LOG = HERE / "logs" / "02_interrupt.jsonl"
WORKSPACE = HERE / "workspace" / "02"

CMD = [
    "claude", "-p",
    "--input-format", "stream-json",
    "--output-format", "stream-json",
    "--verbose",
    "--model", "sonnet",
    "--tools", "Write,Read,Glob",
    "--permission-mode", "acceptEdits",  # writes inside its cwd (the workspace) need no approval
    "--strict-mcp-config",  # --tools alone still loads claude.ai MCP connectors
]

TURN_TIMEOUT = 300  # seconds

TASK = (
    "Create 8 files named poem1.txt to poem8.txt in the current folder. Each is a "
    "4-line poem about a different animal. Write them one at a time, one tool call "
    "per file. When all 8 exist, reply with just DONE."
)
# How SessionTaskAgent would wrap a mid-task message.
QUESTION = (
    "[The user interrupted your task with a message. Answer it briefly; you'll be "
    "told when to continue.] Which animals have you written about so far? One line."
)
CONTINUE = "Continue the task from where you left off."
LONG_TASK = "Write a 1500-word short story about a lighthouse keeper. Reply with the story only."
MEMORY_CHECK = (
    "That task is cancelled; forget the story. What was the first task I gave you in "
    "this session, and how many poem files exist now? Check with your tools. One line."
)


class Session:
    def __init__(self, proc, log):
        self.proc = proc
        self.log = log
        self.events: asyncio.Queue = asyncio.Queue()
        self.in_turn = False  # what AgentInfo.working would report
        self.stray: list[str] = []  # events seen while not in a turn

    def _write_log(self, direction: str, obj) -> None:
        self.log.write(json.dumps({"dir": direction, "t": round(time.perf_counter(), 3), "msg": obj}) + "\n")
        self.log.flush()

    async def reader(self) -> None:
        while raw := await self.proc.stdout.readline():
            event = json.loads(raw)
            self._write_log("out", event)
            if not self.in_turn and event.get("type") != "control_response":
                self.stray.append(label(event))
            if event.get("type") == "result":
                self.in_turn = False
            await self.events.put(event)
        await self.events.put(None)

    async def _send(self, obj) -> None:
        self._write_log("in", obj)
        self.proc.stdin.write((json.dumps(obj) + "\n").encode())
        await self.proc.stdin.drain()

    async def say(self, text: str) -> None:
        print(f"\n> {text}")
        self.in_turn = True
        await self._send({"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": text}]}})

    async def interrupt(self) -> None:
        print("  !! sending interrupt")
        await self._send({"type": "control_request", "request_id": f"req_{uuid4().hex[:8]}",
                          "request": {"subtype": "interrupt"}})

    async def next_event(self) -> dict:
        event = await asyncio.wait_for(self.events.get(), TURN_TIMEOUT)
        if event is None:
            raise RuntimeError(f"process ended (exit {self.proc.returncode})")
        print(f"  {label(event)}")
        return event

    async def until_result(self) -> dict:
        while (event := await self.next_event()).get("type") != "result":
            pass
        self.in_turn = False
        return event

    async def until_tool_use(self) -> None:
        while True:
            event = await self.next_event()
            if event.get("type") == "result":
                self.in_turn = False
                raise RuntimeError("turn ended before any tool use; nothing to interrupt")
            if event.get("type") == "assistant" and any(
                    c.get("type") == "tool_use" for c in event["message"]["content"]):
                return


def label(event: dict) -> str:
    kind = event.get("type", "?")
    if event.get("subtype"):
        kind += "/" + event["subtype"]
    if kind == "assistant":
        parts = []
        for c in event["message"]["content"]:
            if c.get("type") == "tool_use":
                parts.append(f"tool_use {c['name']} {json.dumps(c.get('input', {}))[:60]}")
            elif c.get("type") == "text":
                parts.append(f"text {c['text'][:60]!r}")
        kind += ": " + "; ".join(parts)
    elif kind == "control_response":
        kind += ": " + json.dumps(event.get("response", {}))[:100]
    elif kind.startswith("result"):
        kind += f": stop_reason={event.get('stop_reason')} is_error={event.get('is_error')}"
    return kind


def poems() -> int:
    return len(list(WORKSPACE.glob("poem*.txt")))


async def main() -> None:
    shutil.rmtree(WORKSPACE, ignore_errors=True)
    WORKSPACE.mkdir(parents=True)
    LOG.parent.mkdir(exist_ok=True)
    proc = await asyncio.create_subprocess_exec(
        *CMD, cwd=WORKSPACE, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        limit=16 * 1024 * 1024,
    )
    pid = proc.pid
    print(f"started pid {pid}")
    findings: dict[str, object] = {}

    with LOG.open("w", encoding="utf-8") as log:
        s = Session(proc, log)
        reader = asyncio.create_task(s.reader())
        try:
            print("\n=== A. message: interrupt -> reply -> continue ===")
            await s.say(TASK)
            await s.until_tool_use()
            await s.interrupt()
            t0 = time.perf_counter()
            result = await s.until_result()
            findings["A interrupt stop time (s)"] = round(time.perf_counter() - t0, 1)
            findings["A interrupted result"] = f"subtype={result.get('subtype')} stop_reason={result.get('stop_reason')}"
            findings["A poems when stopped"] = poems()

            await s.say(QUESTION)
            result = await s.until_result()
            findings["A reply"] = result.get("result")

            await s.say(CONTINUE)
            result = await s.until_result()
            findings["A after continue"] = result.get("result")
            findings["A poems at end (want 8)"] = poems()

            print("\n=== B. cancel: interrupt -> memory survives ===")
            await s.say(LONG_TASK)
            await s.next_event()  # wait until it's actually working
            await s.interrupt()
            t0 = time.perf_counter()
            await s.until_result()
            findings["B cancel stop time (s)"] = round(time.perf_counter() - t0, 1)

            await s.say(MEMORY_CHECK)
            result = await s.until_result()
            findings["B memory check"] = result.get("result")
        except Exception as exc:
            findings["ERROR"] = f"{type(exc).__name__}: {exc}"
        finally:
            findings["same pid, alive"] = f"{proc.pid == pid}, {proc.returncode is None}"
            findings["events outside a turn"] = s.stray or "none"
            proc.stdin.close()
            try:
                await asyncio.wait_for(proc.wait(), 30)
            except TimeoutError:
                proc.kill()
            reader.cancel()

    print("\n=== findings ===")
    for key, value in findings.items():
        print(f"{key}: {value}")
    print(f"\nraw events in {LOG}")


if __name__ == "__main__":
    asyncio.run(main())
