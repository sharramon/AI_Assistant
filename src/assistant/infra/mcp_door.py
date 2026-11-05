"""The one MCP door from Claude sessions to the module menus (module system, decision 2).

Two halves, both here so they share the tool names:

- **The relay** (`python -m assistant.infra.mcp_door`): a tiny stdio MCP server that `claude`
  starts itself from its `--mcp-config`. It offers three fixed tools and passes every call to
  the app over local HTTP. Standard library only. It never changes when modules are swapped,
  turned on or off: the menus are read through the core at call time.
- **`DoorServer`** (in the app, hosted by `agent_hub`): the local HTTP endpoint the relay calls.
  Each call becomes a core command (`ListModules`, `GetMenu`, `InvokeTool`), so the directory,
  permissions and hot swap all still apply. Guarded by a random token.

Modules are never MCP servers and never import this; MCP stays at the agents' edge.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import secrets
import sys
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Any

SERVER = "modules"  # the MCP server's name: claude calls its tools `mcp__modules__<tool>`
URL_ENV, TOKEN_ENV = "ASSISTANT_DOOR_URL", "ASSISTANT_DOOR_TOKEN"
TOKEN_HEADER = "x-door-token"

TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_modules",
        "description": "Every module in the assistant app, one line each (id, what it does, on or off), "
        "plus 'core' (module control). Start here, then show_menu for the one you need.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "show_menu",
        "description": "One module's menu: the items you can use, each with its description and inputs. "
        "Use 'core' for turning modules on, off, reloading or adding them.",
        "inputSchema": {
            "type": "object",
            "properties": {"module_id": {"type": "string", "description": "From list_modules"}},
            "required": ["module_id"],
        },
    },
    {
        "name": "use_item",
        "description": "Use one menu item by its name (from show_menu), with its inputs. "
        "Returns its status and value or error.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The item's name, e.g. viewer.open"},
                "args": {"type": "object", "description": "The item's inputs"},
            },
            "required": ["name"],
        },
    },
]
TOOL_NAMES = tuple(f"mcp__{SERVER}__{tool['name']}" for tool in TOOLS)
READ_ONLY = TOOL_NAMES[:2]  # list_modules and show_menu only read the directory


def plain(value: Any) -> Any:
    """Commands' results as plain JSON data: pydantic models, dataclasses, enums, tuples."""
    if hasattr(value, "model_dump"):
        return plain(value.model_dump(mode="json"))
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return plain(dataclasses.asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [plain(v) for v in value]
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


# --- the app side ---


class DoorServer:
    """The local HTTP endpoint behind the relay: `POST /tool` with `{"tool", "arguments"}`.

    `send` is a module's `ctx.send`; `commands` builds the core commands (passed in, so this
    file needs nothing from the contracts and the relay stays light).
    """

    def __init__(
        self,
        send: Callable[[Any], Awaitable[Any]],
        commands: dict[str, Callable[..., Any]],
        host: str = "127.0.0.1",
        port: int = 0,
        token: str | None = None,
        core_line: dict[str, Any] | None = None,
    ) -> None:
        self._send = send
        self._commands = commands  # "list" -> ListModules, "menu" -> GetMenu, "call" -> InvokeTool
        self._host, self._port = host, port
        self.token = token or secrets.token_hex(16)
        self._core_line = core_line
        self._server: asyncio.Server | None = None
        self.url = ""

    def mcp_config(self) -> dict[str, Any]:
        """The `--mcp-config` for a claude session: the relay, pointed at this endpoint."""
        if not self.url:
            return {}
        return {
            "mcpServers": {
                SERVER: {
                    "type": "stdio",
                    "command": sys.executable,
                    "args": ["-m", "assistant.infra.mcp_door"],
                    "env": {URL_ENV: self.url, TOKEN_ENV: self.token},
                }
            }
        }

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._serve, self._host, self._port)
        self.url = f"http://{self._host}:{self._server.sockets[0].getsockname()[1]}"

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        self.url = ""

    async def call(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """One tool call: `{"ok", "value"}` or `{"ok": False, "error"}`."""
        if tool == "list_modules":
            result = await self._send(self._commands["list"]())
            if not result.is_ok:
                return {"ok": False, "error": result.error}
            lines = [{"id": m["id"], "description": m.get("description", ""), "state": m.get("state")}
                     for m in plain(result.value)]  # fmt: skip
            return {"ok": True, "value": lines + ([self._core_line] if self._core_line else [])}
        if tool == "show_menu":
            result = await self._send(self._commands["menu"](module_id=str(arguments.get("module_id", ""))))
        elif tool == "use_item":
            args = arguments.get("args") or {}
            if not isinstance(args, dict):
                return {"ok": False, "error": "args must be an object"}
            result = await self._send(self._commands["call"](name=str(arguments.get("name", "")), args=args))
        else:
            return {"ok": False, "error": f"No tool called {tool!r}"}
        if result.is_ok:
            return {"ok": True, "value": plain(result.value)}
        return {"ok": False, "status": plain(result.status), "error": result.error}

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            method, path, _ = (await reader.readline()).decode("latin-1").split(" ", 2)
            headers = {}
            while (line := await reader.readline()) not in (b"\r\n", b"\n", b""):
                name, _, value = line.decode("latin-1").partition(":")
                headers[name.strip().lower()] = value.strip()
            body = await reader.readexactly(int(headers.get("content-length", 0)))
            if headers.get(TOKEN_HEADER) != self.token:
                status, answer = 403, {"ok": False, "error": "wrong door token"}
            elif method != "POST" or path != "/tool":
                status, answer = 404, {"ok": False, "error": "not found"}
            else:
                request = json.loads(body or b"{}")
                status, answer = 200, await self.call(str(request.get("tool", "")), request.get("arguments") or {})
            data = json.dumps(answer, ensure_ascii=False).encode()
            reason = {200: "OK", 403: "Forbidden", 404: "Not Found"}[status]
            writer.write(f"HTTP/1.1 {status} {reason}\r\nContent-Type: application/json\r\n"
                         f"Content-Length: {len(data)}\r\nConnection: close\r\n\r\n".encode() + data)  # fmt: skip
            await writer.drain()
        except (ConnectionError, ValueError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()


# --- the relay (runs in its own process, started by claude) ---


def _post(url: str, token: str, tool: str, arguments: dict[str, Any], timeout: float = 120) -> dict[str, Any]:
    data = json.dumps({"tool": tool, "arguments": arguments}).encode()
    request = urllib.request.Request(f"{url}/tool", data=data, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header(TOKEN_HEADER, token)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return json.loads(exc.read() or b"{}")


def answer(message: dict[str, Any], url: str, token: str) -> dict[str, Any] | None:
    """The relay's reply to one JSON-RPC message, or None for a notification."""
    method, msg_id = message.get("method"), message.get("id")
    if msg_id is None:
        return None  # notifications (initialized, cancelled): nothing to answer
    if method == "initialize":
        version = (message.get("params") or {}).get("protocolVersion", "2025-06-18")
        result: Any = {"protocolVersion": version, "capabilities": {"tools": {}},
                       "serverInfo": {"name": SERVER, "version": "1"}}  # fmt: skip
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = message.get("params") or {}
        try:
            reply = _post(url, token, str(params.get("name", "")), params.get("arguments") or {})
        except (OSError, ValueError) as exc:
            reply = {"ok": False, "error": f"the assistant app didn't answer ({exc}); it may be restarting"}
        result = {"content": [{"type": "text", "text": json.dumps(reply, ensure_ascii=False)}],
                  "isError": not reply.get("ok")}  # fmt: skip
    else:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"no method {method}"}}
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def relay() -> int:
    """Read JSON-RPC lines on stdin, answer on stdout, until stdin closes."""
    url, token = os.environ.get(URL_ENV, ""), os.environ.get(TOKEN_ENV, "")
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except ValueError:
            continue
        reply = answer(message, url, token)
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")  # ASCII: safe whatever the console's encoding
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(relay())
