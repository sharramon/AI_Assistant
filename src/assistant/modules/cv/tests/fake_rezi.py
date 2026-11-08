"""A fake Rezi MCP server for the tests: the `mcp` package's own server with an in-memory OAuth
provider (dynamic client registration, PKCE checked by the server), reached through
`httpx2.ASGITransport`, so no test ever touches the network or the real Rezi."""

from __future__ import annotations

import json
import secrets
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx2
from mcp.server.auth.provider import AccessToken, AuthorizationCode, AuthorizationParams, construct_redirect_uri
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

FAKE_URL = "https://rezi.test/mcp"
DAYS_30 = 30 * 86400


class FakeAuth:
    """Clients, codes and tokens in memory. `revoke_all` makes the next call get a 401."""

    def __init__(self) -> None:
        self.clients: dict[str, OAuthClientInformationFull] = {}
        self.codes: dict[str, AuthorizationCode] = {}
        self.tokens: dict[str, AccessToken] = {}
        self.authorized = 0
        self.store: Any = None  # the FakeResumes, set by fake_rezi

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self.clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        self.clients[client_info.client_id] = client_info

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        self.authorized += 1
        code = secrets.token_hex(8)
        self.codes[code] = AuthorizationCode(
            code=code, scopes=params.scopes or [], expires_at=time.time() + 300, client_id=client.client_id,
            code_challenge=params.code_challenge, redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly, resource=params.resource,
        )  # fmt: skip
        return construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state)

    async def load_authorization_code(self, client: OAuthClientInformationFull, authorization_code: str):
        return self.codes.get(authorization_code)

    async def exchange_authorization_code(self, client: OAuthClientInformationFull, authorization_code) -> OAuthToken:
        self.codes.pop(authorization_code.code, None)
        token = secrets.token_hex(16)
        self.tokens[token] = AccessToken(
            token=token, client_id=client.client_id, scopes=authorization_code.scopes,
            expires_at=int(time.time()) + DAYS_30, resource=authorization_code.resource,
        )  # fmt: skip
        return OAuthToken(access_token=token, token_type="Bearer", expires_in=DAYS_30)

    async def load_access_token(self, token: str) -> AccessToken | None:
        return self.tokens.get(token)

    async def load_refresh_token(self, client, refresh_token: str):
        return None  # like Rezi: no refresh token

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        raise NotImplementedError

    async def revoke_token(self, token) -> None:
        self.tokens.pop(getattr(token, "token", ""), None)

    def revoke_all(self) -> None:
        self.tokens.clear()


class FakeResumes:
    """Resumes in memory, like Rezi's: a write with no id makes one, with an id changes only the
    fields sent. `answer_with_id = False` makes the write answer without the new id."""

    def __init__(self) -> None:
        self.resumes: dict[str, dict[str, Any]] = {
            "r1": {"id": "r1", "name": "CV_Test_Umbrella", "sections": {"summary": ["Engineer"]}},
            "r2": {"id": "r2", "name": "CV_Test_Initech", "sections": {"summary": ["Engineer"]}},
        }
        self.writes: list[dict[str, Any]] = []
        self.answer_with_id = True
        self._next = 3

    def write(self, resume_id: str | None, fields: dict[str, Any]) -> dict[str, Any]:
        self.writes.append({"resume_id": resume_id, **fields})
        if resume_id is None:
            resume_id, self._next = f"r{self._next}", self._next + 1
            self.resumes[resume_id] = {"id": resume_id, "name": "Untitled", "sections": {}}
        elif resume_id not in self.resumes:
            raise ToolError("resume not found")
        resume = self.resumes[resume_id]
        resume.update({k: v for k, v in fields.items() if k not in ("sections", "data")})
        resume["sections"] = {**resume["sections"], **fields.get("sections", {})}
        if "data" in fields:  # Rezi's format: a section sent replaces its entries' fields by uuid
            data = resume.setdefault("data", {})
            for name, value in fields["data"].items():
                if isinstance(value, dict) and isinstance(data.get(name), dict) and name not in ("contact", "summary"):
                    data[name] = {k: {**data[name].get(k, {}), **v} for k, v in {**data[name], **value}.items()}
                else:
                    data[name] = value
        return {"id": resume_id, "saved": True} if self.answer_with_id else {"saved": True}


def make_server(auth: FakeAuth, store: FakeResumes | None = None) -> MCPServer:
    store = store or FakeResumes()
    server = MCPServer(
        "fake-rezi",
        auth_server_provider=auth,
        auth=AuthSettings(
            issuer_url="https://rezi.test",
            resource_server_url=FAKE_URL,
            client_registration_options=ClientRegistrationOptions(enabled=True),
            validate_token_resource=True,
        ),
    )

    @server.tool(description="Lists your resumes")
    def list_resumes(limit: int = 10) -> dict[str, Any]:  # Rezi's default is 10, like here
        return {"resumes": [{"id": r["id"], "name": r["name"]} for r in store.resumes.values()][:limit]}

    @server.tool(description="Reads one resume")
    def read_resume(resume_id: str) -> str:
        if resume_id not in store.resumes:
            raise ToolError("resume not found")
        return json.dumps(store.resumes[resume_id])  # an answer as JSON text

    @server.tool(description="The resume format")
    def get_resume_format() -> dict[str, Any]:
        return {"sections": ["contact", "summary", "experience", "education", "skills"]}

    @server.tool(description="Creates a resume, or updates one")
    def write_resume(resume: dict[str, Any], resume_id: str | None = None) -> dict:  # Rezi's live schema
        return store.write(resume_id, resume)

    @server.tool(description="Searches jobs")
    def search_jobs(role: str, location: str = "") -> dict[str, Any]:
        return {"jobs": [{"job_id": "j1", "title": role, "location": location or "Remote"}]}

    @server.tool(description="One job's details")
    def get_job_details(job_id: str) -> dict[str, Any]:
        return {"job_id": job_id, "description": "Build things"}

    @server.tool(description="Keywords for a job")
    def generate_keywords(resume_id: str) -> dict[str, Any]:  # Rezi's live schema: the JD saved on the resume
        jd = store.resumes.get(resume_id, {}).get("jobDescription", "")
        return {"keywords": sorted({w.strip(".,").lower() for w in jd.split() if len(w) > 4})}

    @server.tool(description="Always fails")
    def broken() -> str:
        raise ToolError("resume not found")

    return server


@asynccontextmanager
async def fake_rezi(store: FakeResumes | None = None):
    """`(auth, transport)`: the running fake and the httpx2 transport that reaches it; the resumes
    are `auth.store`."""
    auth = FakeAuth()
    auth.store = store or FakeResumes()
    server = make_server(auth, auth.store)
    app = server.streamable_http_app(
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    async with server.session_manager.run():
        yield auth, httpx2.ASGITransport(app=app)


def browser_for(transport: httpx2.ASGITransport, opened: list[str]):
    """A stand-in for the browser: opens Rezi's sign-in page on the fake (you "agree" at once) and
    follows its redirect to the loopback callback on 127.0.0.1, as the real browser would."""

    async def open_browser(url: str) -> None:
        opened.append(url)
        async with httpx2.AsyncClient(transport=transport) as fake:
            page = await fake.get(url)
        assert page.status_code in (302, 307), page.text
        async with httpx2.AsyncClient(trust_env=False) as loopback:
            done = await loopback.get(page.headers["location"])
        assert done.status_code == 200, done.text

    return open_browser
