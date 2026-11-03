"""Snip: a screenshot of a box in the viewer's window, taken by Edge itself.

Uses the window's DevTools port (see `window.py`): `Page.captureScreenshot` with a clip, so the
image is exactly what you see, Mermaid diagrams included. The standard library has no
WebSocket client, so this has the few lines one request needs.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import struct
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from app_kit.window import devtools_port


class SnipError(Exception):
    """The snip couldn't be taken; the message says why."""


def capture(profile: Path, page_url: str, box: dict[str, float], timeout: float = 10) -> bytes:
    """A PNG of `box` (`x`, `y`, `width`, `height` in CSS pixels) of the viewer page in its window."""
    port = devtools_port(profile)
    if port is None:
        raise SnipError("Snip needs the viewer's own app window (window = \"app\"), which isn't open")
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=timeout) as response:
            targets = json.loads(response.read())
    except (OSError, ValueError) as exc:
        raise SnipError(f"The viewer window doesn't answer: {exc}") from None
    target = next((t for t in targets if t.get("type") == "page" and t.get("url", "").startswith(page_url)), None)
    if target is None:
        raise SnipError("The viewer page isn't showing in its window")
    clip = {key: float(box[key]) for key in ("x", "y", "width", "height")}
    if clip["width"] < 2 or clip["height"] < 2:
        raise SnipError("The box is too small")
    answer = _call(target["webSocketDebuggerUrl"], "Page.captureScreenshot",
                   {"format": "png", "clip": {**clip, "scale": 1}, "fromSurface": True}, timeout)
    try:
        return base64.b64decode(answer["data"])
    except (KeyError, ValueError) as exc:
        raise SnipError(f"Edge sent no image: {answer}") from exc


def _call(ws_url: str, method: str, params: dict[str, Any], timeout: float) -> dict[str, Any]:
    """One DevTools command over a WebSocket; its result."""
    url = urlsplit(ws_url)
    with socket.create_connection((url.hostname, url.port), timeout=timeout) as sock:
        key = base64.b64encode(os.urandom(16)).decode()
        sock.sendall(
            f"GET {url.path} HTTP/1.1\r\nHost: {url.netloc}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n".encode()
        )
        reader = sock.makefile("rb")
        status = reader.readline()
        if b" 101 " not in status:
            raise SnipError(f"Edge refused the connection: {status.decode(errors='replace').strip()}")
        while reader.readline() not in (b"\r\n", b""):
            pass
        _send(sock, json.dumps({"id": 1, "method": method, "params": params}).encode())
        while True:
            message = json.loads(_receive(reader))
            if message.get("id") == 1:
                if "error" in message:
                    raise SnipError(f"Edge: {message['error'].get('message')}")
                return message.get("result", {})


def _send(sock: socket.socket, payload: bytes) -> None:
    head = bytes([0x81])  # a final text frame
    size = len(payload)
    if size < 126:
        head += bytes([0x80 | size])
    elif size < 1 << 16:
        head += bytes([0x80 | 126]) + struct.pack("!H", size)
    else:
        head += bytes([0x80 | 127]) + struct.pack("!Q", size)
    mask = os.urandom(4)  # a client must mask what it sends
    sock.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))


def _receive(reader: Any) -> bytes:
    """One whole message (joining continuation frames)."""
    message = b""
    while True:
        first, second = _exact(reader, 2)
        size = second & 0x7F
        if size == 126:
            size = struct.unpack("!H", _exact(reader, 2))[0]
        elif size == 127:
            size = struct.unpack("!Q", _exact(reader, 8))[0]
        mask = _exact(reader, 4) if second & 0x80 else None
        data = _exact(reader, size)
        if mask:
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        if first & 0x0F == 0x8:
            raise SnipError("Edge closed the connection")
        if first & 0x0F in (0x0, 0x1, 0x2):
            message += data
            if first & 0x80:
                return message


def _exact(reader: Any, size: int) -> bytes:
    data = reader.read(size)
    if len(data) != size:
        raise SnipError("Edge closed the connection")
    return data
