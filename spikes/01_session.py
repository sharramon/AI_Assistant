"""Spike step 1: does one stream-json `claude -p` session stay alive across turns?

Starts one session, sends two messages (the second refers to the first), and
saves every raw JSON line to spikes/logs/01_session.jsonl.

Run: .\\.venv\\Scripts\\python spikes\\01_session.py
"""

import asyncio
import json
import time
from pathlib import Path

LOG = Path(__file__).parent / "logs" / "01_session.jsonl"

CMD = [
    "claude", "-p",
    "--input-format", "stream-json",
    "--output-format", "stream-json",
    "--verbose",
    "--model", "sonnet",
    "--tools", "",
    "--strict-mcp-config",  # --tools "" alone still loads claude.ai MCP connectors
]

MESSAGES = [
    "Remember this number: 4817. Reply with just 'ok'.",
    "What number did I ask you to remember? Reply with just the number.",
]


def user_line(text: str) -> bytes:
    msg = {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": text}]}}
    return (json.dumps(msg) + "\n").encode()


async def read_turn(proc, log) -> dict:
    """Read events until this turn's `result` event; return it."""
    while True:
        raw = await proc.stdout.readline()
        if not raw:
            raise RuntimeError(f"process ended (exit {proc.returncode})")
        log.write(raw.decode(errors="replace"))
        log.flush()
        event = json.loads(raw)
        kind = event.get("type"), event.get("subtype")
        print(f"  event: {kind[0]}{'/' + kind[1] if kind[1] else ''}")
        if event.get("type") == "result":
            return event


async def main() -> None:
    LOG.parent.mkdir(exist_ok=True)
    proc = await asyncio.create_subprocess_exec(
        *CMD, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        limit=16 * 1024 * 1024,
    )
    print(f"started pid {proc.pid}")
    with LOG.open("w", encoding="utf-8") as log:
        for text in MESSAGES:
            print(f"\n> {text}")
            sent = time.perf_counter()
            proc.stdin.write(user_line(text))
            await proc.stdin.drain()
            result = await read_turn(proc, log)
            print(f"< {result.get('result')!r}")
            print(f"  pid {proc.pid}, alive {proc.returncode is None}, "
                  f"session {result.get('session_id')}, {time.perf_counter() - sent:.1f}s")
        proc.stdin.close()
    await proc.wait()
    print(f"\nexit {proc.returncode}; raw events in {LOG}")


if __name__ == "__main__":
    asyncio.run(main())
