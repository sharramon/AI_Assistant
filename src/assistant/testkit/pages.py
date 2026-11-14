"""Talking to a module's local page (temp_ui, voice_notes) over raw HTTP, and a voice_in stand-in:
`request`, `post`, `next_item` on an open `/events` stream, `ui_port` (a started page's port),
`read_events` (the first items after `hello`), and `FakeVoiceIn`, which answers the mic
commands and `IVoice` with the events voice_in publishes (no voice service). Also the snips a page
sends, as their publishers send them (`clip_event`, `dropped_event`), for the Talker's and temp_ui's tests."""

from __future__ import annotations

import asyncio
import json

from assistant.contracts import (
    InputReceived,
    IVoice,
    ListeningState,
    Manifest,
    ModuleContext,
    ModuleEvent,
    ModuleProtocol,
    Result,
    StartListening,
    Status,
    StopListening,
    VoiceDestination,
    VoiceState,
    VoiceTranscript,
)


async def request(port: int, raw: bytes) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Send `raw` to 127.0.0.1:`port`; the open reader and writer. A request without a `Host` header
    gets `Host: 127.0.0.1:<port>`, as a browser sends it (the pages refuse a request without one)."""
    head, _, rest = raw.partition(b"\r\n")
    if b"\r\nhost:" not in b"\r\n" + rest.lower().split(b"\r\n\r\n", 1)[0]:
        raw = head + b"\r\nHost: 127.0.0.1:%d\r\n" % port + rest
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(raw)
    await writer.drain()
    return reader, writer


async def post(port: int, path: str, body: dict) -> dict:
    """POST `body` as JSON to `path`; the JSON answer."""
    data = json.dumps(body).encode()
    reader, writer = await request(port, b"POST %s HTTP/1.1\r\nContent-Length: %d\r\n\r\n%s" % (path.encode(), len(data), data))
    raw = await reader.read()
    writer.close()
    return json.loads(raw.split(b"\r\n\r\n", 1)[1])


async def next_item(reader: asyncio.StreamReader, match) -> dict:
    """The next item on an open /events stream for which `match(item)` is true."""
    async with asyncio.timeout(2):
        while True:
            line = await reader.readline()
            if line.startswith(b"data: ") and match(item := json.loads(line[6:])):
                return item


def ui_port(app, module_id: str = "temp_ui") -> int:
    """The port a started app's page module (temp_ui by default) listens on, from its `url`."""
    return int(app._lifecycle._active[module_id][0].url.rsplit(":", 1)[1].strip("/"))


async def read_events(port: int, count: int) -> list[dict]:
    """The first `count` items on a page's /events stream, after its leading `hello` (checked, and
    returned first)."""
    reader, writer = await request(port, b"GET /events HTTP/1.1\r\n\r\n")
    items = []
    async with asyncio.timeout(2):
        while len(items) < count + 1:
            line = await reader.readline()
            if line.startswith(b"data: "):
                items.append(json.loads(line[6:]))
    writer.close()
    assert items[0]["kind"] == "hello" and items[0]["launch"]
    return items


class _FakeVoice(IVoice):
    """The fake's IVoice: the same sessions as its commands; finish ends only its own id."""

    def __init__(self, fake: FakeVoiceIn) -> None:
        self.fake = fake

    async def listen(self, session_id, destination=VoiceDestination.CALLER):
        return await self.fake.listen(StartListening(id=session_id, send_as_input=destination == VoiceDestination.TALKER))

    async def finish(self, session_id, discard=False):
        if self.fake.session != session_id:
            return Result.ok({"text": "", "ended": True})
        return await self.fake.stop_listening(StopListening(discard=discard))


class FakeVoiceIn(ModuleProtocol):
    """Stands in for voice_in: answers the two commands and IVoice with the events voice_in publishes."""

    manifest = Manifest(id="voice_in", provides=(IVoice,), handles=(StartListening, StopListening),
                        publishes=(VoiceState, VoiceTranscript, InputReceived))

    async def init(self, ctx: ModuleContext) -> None:
        self.ctx, self.session, self.commands = ctx, None, []
        self.fail: tuple[str, str] | None = None  # (reason, detail): the next start fails so
        ctx.handle(StartListening, self.listen)
        ctx.handle(StopListening, self.stop_listening)
        ctx.provide(IVoice, _FakeVoice(self))

    async def listen(self, command: StartListening) -> Result:
        self.commands.append(command)
        self.session = command.id
        self.ctx.publish(VoiceState(state=ListeningState.STARTING, correlation_id=command.id))
        if self.fail:
            reason, detail = self.fail
            self.ctx.publish(VoiceState(state=ListeningState.FAILED, reason=reason, detail=detail, correlation_id=command.id))
            self.session = None
            return Result(status=Status.NOT_AVAILABLE, error=detail, retryable=True)
        self.ctx.publish(VoiceState(state=ListeningState.LISTENING, correlation_id=command.id))
        return Result.ok({"session_id": command.id})

    async def stop_listening(self, command: StopListening) -> Result:
        self.commands.append(command)
        sid = self.session
        if sid is None:
            return Result.ok(None)
        if command.discard:
            self.ctx.publish(VoiceTranscript(session_id=sid, text="", final=True, correlation_id=sid))
            self.ctx.publish(VoiceState(state=ListeningState.IDLE, reason="cleared", detail="cleared", correlation_id=sid))
            return Result.ok({"text": "", "discarded": True})
        self.ctx.publish(VoiceTranscript(session_id=sid, text="hello there", final=True, correlation_id=sid))
        self.ctx.publish(InputReceived(text="hello there", source="voice"))
        self.ctx.publish(VoiceState(state=ListeningState.IDLE, correlation_id=sid))
        return Result.ok({"text": "hello there", "latency_ms": 50})

def clip_event(snip_id: str, image, file: str, heading: str | None = None, source: str = "html_viewer") -> ModuleEvent:
    """A snip as its publisher sends it: html_viewer's `html_viewer.clip`, or the temp UI's `temp_ui.clip`
    (a pasted image). `image` is the snip's image file."""
    data = {"id": snip_id, "image_path": str(image), "file": file, "heading": heading}
    return ModuleEvent(name=f"{source}.clip", source=source, data=data)


def dropped_event(snip_id: str) -> ModuleEvent:
    """The temp UI's `temp_ui.clip_dropped`: you dropped snip `snip_id` with its x."""
    return ModuleEvent(name="temp_ui.clip_dropped", source="temp_ui", data={"id": snip_id})
