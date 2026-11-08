"""The Rezi connection: an MCP client of Rezi's server and the token it signs in with.

- `TokenStore`: the token file, kept outside the repo. Rezi's token lasts 30 days with no refresh
  token, so `days_left` says when you sign in again. It is also the `mcp` package's `TokenStorage`.
- `McpClient`: Streamable HTTP with OAuth (dynamic client registration, PKCE) through the `mcp`
  package. `list_tools` and `call` never open a browser: with no valid token they raise
  `NotSignedIn` before connecting. Only `sign_in` opens the browser, and `LoopbackCallback`
  catches Rezi's redirect on 127.0.0.1.

This lives in the cv module only (the decided exception to "modules never import MCP"). Nothing
connects on import or construction; the `mcp` package is imported on first use. Every value that
comes out is plain data (`ToolInfo.as_value`, `ToolOutput.as_value`, `status`).
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import site
import sys
import webbrowser
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

if TYPE_CHECKING:
    from mcp import Client
    from mcp.shared.auth import AuthorizationCodeResult, OAuthClientInformationFull, OAuthToken

def pywin32_paths(site_dirs: list[str] | None = None) -> list[str]:
    """Put pywin32's folders on `sys.path` as its `pywin32.pth` does when Python starts. `mcp` imports
    `pywintypes` on Windows, and an app started before `pip install mcp` brought pywin32 in never read
    that `.pth` (found in the first real run, 2026-11-07). Adds only folders that exist and are missing;
    in a fresh process it adds nothing. Returns what it added."""
    if sys.platform != "win32":
        return []
    added = []
    for site_dir in site_dirs if site_dirs is not None else site.getsitepackages():
        for sub in ("win32", os.path.join("win32", "lib"), "pythonwin"):
            path = os.path.join(site_dir, sub)
            if os.path.isdir(path) and path not in sys.path:
                sys.path.append(path)
                added.append(path)
    if added:
        dlls = [os.path.join(d, "pywin32_system32") for d in (site_dirs or site.getsitepackages())]
        for dll_dir in dlls:
            if os.path.isdir(dll_dir):
                os.add_dll_directory(dll_dir)
    return added


pywin32_paths()

REZI_URL = "https://api.rezi.ai/mcp"
TOKEN_DAYS = 30  # Rezi's token lasts 30 days, with no refresh token
CALLBACK_PORT = 33418
CLIENT_NAME = "AI Assistant cv module"

OpenBrowser = Callable[[str], Awaitable[Any] | Any]


class NotSignedIn(Exception):
    """No token, an expired one, or Rezi refused it: `sign_in` is needed (an item gives `not_available`)."""


class ReziError(Exception):
    """Rezi answered with an error: a tool's error or a protocol error (an item gives `failed`)."""


class ReziUnreachable(Exception):
    """No answer from Rezi: network, timeout, server down (an item gives `failed`, retryable)."""


def default_token_file() -> Path:
    """`%LOCALAPPDATA%\\assistant\\cv\\rezi_token.json` (the home folder if there's no LOCALAPPDATA)."""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "assistant" / "cv" / "rezi_token.json"


def _now() -> datetime:
    return datetime.now(UTC)


class TokenStore:
    """The token file: `{"token", "saved_at", "expires_at", "client"}`. A missing or broken file is
    an empty store. Writes go through a temporary file, so a crash never leaves half a token."""

    def __init__(self, path: str | Path, now: Callable[[], datetime] = _now) -> None:
        self.path = Path(path)
        self._now = now

    # --- the plain side ---------------------------------------------------------------------------------

    def load(self) -> dict[str, Any] | None:
        """The token's fields (`access_token`, `token_type`, ...), or None when there's none or it expired."""
        data = self._read()
        token, expires = data.get("token"), self.expires_at()
        if not token or expires is None or expires <= self._now():
            return None
        return dict(token)

    def save(self, token: dict[str, Any]) -> None:
        """Keeps a new token; it expires after its `expires_in`, else after 30 days."""
        if not token.get("access_token"):
            raise ValueError("a token needs an access_token")
        now = self._now()
        seconds = token.get("expires_in") or TOKEN_DAYS * 86400
        data = self._read()
        data.update(token=dict(token), saved_at=now.isoformat(), expires_at=(now + timedelta(seconds=seconds)).isoformat())
        self._write(data)

    def expires_at(self) -> datetime | None:
        value = self._read().get("expires_at")
        try:
            return datetime.fromisoformat(value) if value else None
        except (TypeError, ValueError):
            return None

    def days_left(self) -> float | None:
        """Days until the token runs out (0.0 once it has), one decimal; None with no token."""
        expires = self.expires_at() if self._read().get("token") else None
        if expires is None:
            return None
        return max(0.0, round((expires - self._now()).total_seconds() / 86400, 1))

    def clear_token(self) -> None:
        """Forgets the token, keeps the registered client."""
        data = self._read()
        if any(key in data for key in ("token", "saved_at", "expires_at")):
            for key in ("token", "saved_at", "expires_at"):
                data.pop(key, None)
            self._write(data)

    def client(self) -> dict[str, Any] | None:
        """The client Rezi registered for us (dynamic client registration), or None."""
        client = self._read().get("client")
        return dict(client) if client else None

    def save_client(self, client: dict[str, Any]) -> None:
        data = self._read()
        data["client"] = dict(client)
        self._write(data)

    def clear_client(self) -> None:
        data = self._read()
        if data.pop("client", None) is not None:
            self._write(data)

    # --- the mcp package's TokenStorage -----------------------------------------------------------------

    async def get_tokens(self) -> OAuthToken | None:
        from mcp.shared.auth import OAuthToken

        token, expires = self.load(), self.expires_at()
        if token is None or expires is None:
            return None
        token["expires_in"] = max(1, int((expires - self._now()).total_seconds()))  # what's left, not the start
        return OAuthToken.model_validate(token)

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self.save(tokens.model_dump(mode="json", exclude_none=True))

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        from mcp.shared.auth import OAuthClientInformationFull

        client = self.client()
        return OAuthClientInformationFull.model_validate(client) if client else None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self.save_client(client_info.model_dump(mode="json", exclude_none=True))

    # --- the file ---------------------------------------------------------------------------------------

    def _read(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        part = self.path.with_name(self.path.name + ".part")
        part.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(part, self.path)


@dataclass(frozen=True)
class ToolInfo:
    """One of Rezi's tools, as its server lists it."""

    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)

    def as_value(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}


@dataclass(frozen=True)
class ToolOutput:
    """A tool's answer: its text, and its data (the structured content, else the text read as JSON;
    None when it's neither)."""

    text: str
    data: Any = None

    def as_value(self) -> dict[str, Any]:
        return {"text": self.text, "data": self.data}


class LoopbackCallback:
    """Catches Rezi's redirect after you sign in in the browser: one small HTTP server on 127.0.0.1,
    answering `/callback?code=...&state=...`. Other paths (a favicon) get 404 and it keeps waiting."""

    def __init__(self, port: int = CALLBACK_PORT) -> None:
        self.port = port
        self._server: asyncio.Server | None = None
        self._answer: asyncio.Future[dict[str, str]] | None = None

    @property
    def redirect_uri(self) -> str:
        return f"http://127.0.0.1:{self.port}/callback"

    async def __aenter__(self) -> LoopbackCallback:
        self._answer = asyncio.get_running_loop().create_future()
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", self.port)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def wait(self, timeout: float) -> AuthorizationCodeResult:
        from mcp.shared.auth import AuthorizationCodeResult

        if self._answer is None:
            raise RuntimeError("LoopbackCallback.wait outside `async with`")
        try:
            query = await asyncio.wait_for(asyncio.shield(self._answer), timeout)
        except TimeoutError:
            raise NotSignedIn(f"no sign-in came back from the browser within {timeout:g} s") from None
        if "error" in query:
            raise NotSignedIn(f"Rezi refused the sign-in: {query['error']} {query.get('error_description', '')}".strip())
        return AuthorizationCodeResult(code=query["code"], state=query.get("state"), iss=query.get("iss"))

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request = (await reader.readline()).decode("latin-1").split()
            while (await reader.readline()) not in (b"\r\n", b"\n", b""):
                pass  # the headers: not needed
            url = urlparse(request[1]) if len(request) >= 2 else None
            query = {k: v[0] for k, v in parse_qs(url.query).items()} if url else {}
            ok = url is not None and url.path == "/callback" and ("code" in query or "error" in query)
            if ok and self._answer is not None and not self._answer.done():
                self._answer.set_result(query)
            body = ("Signed in to Rezi. You can close this tab." if ok and "code" in query
                    else "Rezi sign-in didn't work. You can close this tab." if ok else "Not found")  # fmt: skip
            status = "200 OK" if ok else "404 Not Found"
            data = body.encode()
            writer.write(f"HTTP/1.1 {status}\r\nContent-Type: text/plain; charset=utf-8\r\n"
                         f"Content-Length: {len(data)}\r\nConnection: close\r\n\r\n".encode() + data)  # fmt: skip
            await writer.drain()
        finally:
            writer.close()


class McpClient:
    """Rezi's MCP server. Each `list_tools` / `call` opens one connection with the stored token and
    closes it again. `http_transport` swaps the network for a test server (an httpx2 transport)."""

    def __init__(
        self,
        store: TokenStore,
        url: str = REZI_URL,
        *,
        http_transport: Any = None,
        timeout: float = 60.0,
        callback_port: int = CALLBACK_PORT,
    ) -> None:
        self.store = store
        self.url = url
        self.timeout = timeout
        self.callback_port = callback_port
        self._transport = http_transport

    def status(self) -> dict[str, Any]:
        """Signed in or not, the token's days left, the server and the token file. Never connects."""
        return {
            "url": self.url,
            "signed_in": self.store.load() is not None,
            "days_left": self.store.days_left(),
            "token_file": str(self.store.path),
        }

    async def list_tools(self) -> list[ToolInfo]:
        """Every tool the server lists, page by page."""
        tools: list[ToolInfo] = []
        async with self._signed_in() as client:
            cursor: str | None = None
            for _ in range(100):  # a server whose pages never end can't hang us
                page = await client.list_tools(cursor=cursor)
                tools += [ToolInfo(t.name, t.description or "", dict(t.input_schema or {})) for t in page.tools]
                cursor = page.next_cursor
                if not cursor:
                    break
        return tools

    async def call(self, name: str, arguments: dict[str, Any] | None = None) -> ToolOutput:
        """Calls one tool. ReziError when the tool answers with an error."""
        async with self._signed_in() as client:
            result = await client.call_tool(name, arguments or {})
        text = "\n".join(part.text for part in result.content if getattr(part, "type", "") == "text")
        if result.is_error:
            raise ReziError(f"Rezi's {name}: {text or 'error, no message'}")
        data = result.structured_content
        if isinstance(data, dict) and list(data) == ["result"]:
            data = data["result"]  # a plain return value, wrapped by the server
        if (data is None or isinstance(data, str)) and text:
            try:
                data = json.loads(text)
            except ValueError:
                data = None
        return ToolOutput(text, data)

    async def sign_in(self, open_browser: OpenBrowser | None = None, *, force: bool = False,
                      timeout: float = 300.0) -> dict[str, Any]:  # fmt: skip
        """Signs in in the browser (OAuth with PKCE) and keeps the token. Already signed in and not
        `force`: nothing happens. Returns `status()`. NotSignedIn if the sign-in didn't finish."""
        if not force and self.store.load() is not None:
            return self.status()
        opener = open_browser or webbrowser.open
        async with LoopbackCallback(self.callback_port) as callback:
            client = self.store.client()
            if client and callback.redirect_uri not in client.get("redirect_uris", []):
                self.store.clear_client()  # registered for another port: register again
            self.store.clear_token()

            async def redirect(url: str) -> None:
                opened = opener(url)
                if inspect.isawaitable(opened):
                    await opened

            async def answer() -> AuthorizationCodeResult:
                return await callback.wait(timeout)

            async with self._connect(callback.redirect_uri, redirect, answer) as session:
                await session.list_tools()  # the first request runs the sign-in
        if self.store.load() is None:
            raise NotSignedIn("the sign-in finished without a token")
        return self.status()

    # --- the connection ---------------------------------------------------------------------------------

    @asynccontextmanager
    async def _signed_in(self) -> AsyncIterator[Client]:
        """A connection with the stored token; never a browser. A refused token is forgotten."""
        if self.store.load() is None:
            raise NotSignedIn("not signed in to Rezi, or the token ran out: use rezi.sign_in")

        async def no_browser(url: str) -> None:
            raise NotSignedIn("Rezi refused the stored token: use rezi.sign_in")

        async def no_answer() -> AuthorizationCodeResult:
            raise NotSignedIn("Rezi refused the stored token: use rezi.sign_in")

        try:
            async with self._connect(LoopbackCallback(self.callback_port).redirect_uri, no_browser, no_answer) as c:
                yield c
        except NotSignedIn:
            self.store.clear_token()
            raise

    @asynccontextmanager
    async def _connect(
        self,
        redirect_uri: str,
        redirect: Callable[[str], Awaitable[None]],
        answer: Callable[[], Awaitable[AuthorizationCodeResult]],
    ) -> AsyncIterator[Client]:
        import httpx2
        from mcp import Client
        from mcp.client.auth import OAuthClientProvider
        from mcp.client.streamable_http import streamable_http_client
        from mcp.shared.auth import OAuthClientMetadata

        metadata = OAuthClientMetadata(
            client_name=CLIENT_NAME,
            redirect_uris=[redirect_uri],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            token_endpoint_auth_method="none",
        )
        auth = OAuthClientProvider(self.url, metadata, self.store, redirect_handler=redirect, callback_handler=answer)
        try:
            async with (
                httpx2.AsyncClient(auth=auth, transport=self._transport, timeout=self.timeout) as http,
                Client(streamable_http_client(self.url, http_client=http), read_timeout_seconds=self.timeout) as client,
            ):
                yield client
        except BaseException as exc:
            plain = _plain(exc)
            if plain is exc:
                raise
            raise plain from exc


def _plain(exc: BaseException) -> BaseException:
    """One of NotSignedIn, ReziError, ReziUnreachable for anything the connection raised (the `mcp`
    package and anyio wrap errors in exception groups); cancellation and the like pass through."""
    leaves = _leaves(exc)
    for kind in (NotSignedIn, ReziError, ReziUnreachable):
        for leaf in leaves:
            if isinstance(leaf, kind):
                return leaf
    import httpx2
    from mcp import MCPError

    for leaf in leaves:
        if isinstance(leaf, MCPError):
            return ReziError(f"Rezi: {leaf}")
    for leaf in leaves:
        if isinstance(leaf, (httpx2.HTTPError, OSError, TimeoutError)):
            return ReziUnreachable(f"no answer from Rezi at its server: {type(leaf).__name__}: {leaf}")
    if not isinstance(exc, Exception):
        return exc  # cancelled, KeyboardInterrupt: not ours to change
    return ReziError(f"Rezi: {type(leaves[0]).__name__}: {leaves[0]}")


def _leaves(exc: BaseException) -> list[BaseException]:
    if isinstance(exc, BaseExceptionGroup):
        return [leaf for inner in exc.exceptions for leaf in _leaves(inner)]
    return [exc]
