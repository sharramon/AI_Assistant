"""Chunk 4: the Rezi connection (`mcp.py`) against a fake Rezi in-process. No test reaches the network
or the real Rezi: the fake is reached through `httpx2.ASGITransport`, and only the sign-in's loopback
callback listens, on 127.0.0.1."""

from __future__ import annotations

import json
import tomllib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx2
import pytest

from assistant.contracts import ListModules, ModuleState
from assistant.core import App
from assistant.modules.cv import CvModule
from assistant.modules.cv.mcp import (
    REZI_URL,
    LoopbackCallback,
    McpClient,
    NotSignedIn,
    ReziError,
    ReziUnreachable,
    TokenStore,
    default_token_file,
)
from assistant.modules.cv.module import rezi_client, settings
from assistant.modules.cv.tests.fake_rezi import FAKE_URL, browser_for, fake_rezi

REPO = Path(__file__).resolve().parents[5]
DEFAULTS = tomllib.loads((Path(__file__).parents[1] / "module.toml").read_text(encoding="utf-8"))


class Clock:
    def __init__(self) -> None:
        self.at = datetime(2026, 11, 6, 12, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.at


# --- TokenStore ---------------------------------------------------------------------------------------------

def test_a_token_lasts_its_expires_in_or_30_days(tmp_path):
    clock = Clock()
    store = TokenStore(tmp_path / "t" / "rezi_token.json", now=clock)
    assert store.load() is None and store.days_left() is None
    store.save({"access_token": "abc", "token_type": "Bearer"})
    assert store.load() == {"access_token": "abc", "token_type": "Bearer"}
    assert store.days_left() == 30.0
    clock.at += timedelta(days=29, hours=12)
    assert store.days_left() == 0.5
    clock.at += timedelta(days=1)
    assert store.load() is None and store.days_left() == 0.0
    store.save({"access_token": "def", "expires_in": 3600})
    assert store.days_left() == 0.0 and store.load()["access_token"] == "def"
    clock.at += timedelta(hours=2)
    assert store.load() is None
    with pytest.raises(ValueError):
        store.save({"token_type": "Bearer"})


def test_the_client_survives_a_cleared_token_and_a_broken_file_is_empty(tmp_path):
    store = TokenStore(tmp_path / "rezi_token.json")
    store.save_client({"client_id": "c1", "redirect_uris": ["http://127.0.0.1:1/callback"]})
    store.save({"access_token": "abc"})
    store.clear_token()
    assert store.load() is None and store.client()["client_id"] == "c1"
    assert not (tmp_path / "rezi_token.json.part").exists()
    store.clear_client()
    assert store.client() is None
    store.path.write_text("{not json", encoding="utf-8")
    assert store.load() is None and store.client() is None and store.days_left() is None


async def test_the_store_is_the_mcp_token_storage_with_the_time_left(tmp_path):
    from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

    clock = Clock()
    store = TokenStore(tmp_path / "rezi_token.json", now=clock)
    assert await store.get_tokens() is None and await store.get_client_info() is None
    await store.set_tokens(OAuthToken(access_token="abc", token_type="Bearer", expires_in=86400))
    clock.at += timedelta(hours=6)
    token = await store.get_tokens()
    assert token.access_token == "abc" and token.expires_in == 18 * 3600
    await store.set_client_info(OAuthClientInformationFull(client_id="c1", redirect_uris=["http://127.0.0.1:5/callback"]))
    assert (await store.get_client_info()).client_id == "c1"
    saved = json.loads(store.path.read_text(encoding="utf-8"))
    assert set(saved) == {"token", "saved_at", "expires_at", "client"}


def test_the_default_token_file_is_outside_the_repo():
    assert not default_token_file().resolve().is_relative_to(REPO)


# --- the loopback callback --------------------------------------------------------------------------------

async def test_the_callback_takes_the_code_and_ignores_other_paths():
    async with LoopbackCallback(0) as callback, httpx2.AsyncClient(trust_env=False) as http:
        assert callback.redirect_uri.startswith("http://127.0.0.1:") and callback.port != 0
        assert (await http.get(f"http://127.0.0.1:{callback.port}/favicon.ico")).status_code == 404
        assert (await http.get(callback.redirect_uri, params={"code": "c0de", "state": "s1"})).status_code == 200
        answer = await callback.wait(5)
    assert (answer.code, answer.state) == ("c0de", "s1")


async def test_the_callback_reports_a_refusal_and_a_timeout():
    async with LoopbackCallback(0) as callback, httpx2.AsyncClient(trust_env=False) as http:
        await http.get(callback.redirect_uri, params={"error": "access_denied"})
        with pytest.raises(NotSignedIn, match="access_denied"):
            await callback.wait(5)
    async with LoopbackCallback(0) as callback:
        with pytest.raises(NotSignedIn, match="within"):
            await callback.wait(0.05)


# --- McpClient against the fake Rezi --------------------------------------------------------------------

def never_called(request: httpx2.Request) -> httpx2.Response:
    raise AssertionError(f"no request expected, got {request.method} {request.url}")


async def test_not_signed_in_means_no_request_at_all(tmp_path):
    client = McpClient(TokenStore(tmp_path / "t.json"), FAKE_URL, http_transport=httpx2.MockTransport(never_called))
    assert client.status() == {"url": FAKE_URL, "signed_in": False, "days_left": None,
                               "token_file": str(tmp_path / "t.json")}  # fmt: skip
    with pytest.raises(NotSignedIn, match="rezi.sign_in"):
        await client.list_tools()
    with pytest.raises(NotSignedIn):
        await client.call("list_resumes")


async def test_sign_in_with_pkce_then_list_and_call(tmp_path):
    store = TokenStore(tmp_path / "rezi_token.json")
    opened: list[str] = []
    async with fake_rezi() as (auth, transport):
        client = McpClient(store, FAKE_URL, http_transport=transport, callback_port=0)
        status = await client.sign_in(browser_for(transport, opened), timeout=10)
        assert status["signed_in"] and status["days_left"] == 30.0
        assert len(opened) == 1 and "code_challenge=" in opened[0] and "code_challenge_method=S256" in opened[0]
        assert len(auth.clients) == 1 and len(auth.tokens) == 1

        tools = await client.list_tools()
        assert [t.name for t in tools][:2] == ["list_resumes", "read_resume"] and tools[-1].name == "broken"
        assert tools[1].as_value()["input_schema"]["required"] == ["resume_id"]

        resumes = await client.call("list_resumes")
        assert resumes.data["resumes"][0] == {"id": "r1", "name": "CV_Test_Umbrella"}
        resume = await client.call("read_resume", {"resume_id": "r2"})
        assert resume.as_value()["data"] == {"id": "r2", "name": "CV_Test_Initech",
                                             "sections": {"summary": ["Engineer"]}}  # fmt: skip
        with pytest.raises(ReziError, match="resume not found"):
            await client.call("broken")

        again = await client.sign_in(browser_for(transport, opened))  # signed in: no browser
        assert again["signed_in"] and len(opened) == 1 and auth.authorized == 1


async def test_a_refused_token_is_forgotten_and_never_opens_a_browser(tmp_path):
    store = TokenStore(tmp_path / "rezi_token.json")
    opened: list[str] = []
    async with fake_rezi() as (auth, transport):
        client = McpClient(store, FAKE_URL, http_transport=transport, callback_port=0)
        await client.sign_in(browser_for(transport, opened), timeout=10)
        auth.revoke_all()
        with pytest.raises(NotSignedIn, match="refused"):
            await client.call("list_resumes")
        assert store.load() is None and store.client() is not None
        assert len(opened) == 1 and auth.authorized == 1
        await client.sign_in(browser_for(transport, opened), timeout=10)  # signing in again works
        assert (await client.call("list_resumes")).data["resumes"]
        assert len(opened) == 2


async def test_no_answer_is_unreachable(tmp_path):
    def down(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("connection refused", request=request)

    store = TokenStore(tmp_path / "rezi_token.json")
    store.save({"access_token": "abc", "token_type": "Bearer"})
    client = McpClient(store, FAKE_URL, http_transport=httpx2.MockTransport(down))
    with pytest.raises(ReziUnreachable, match="ConnectError"):
        await client.list_tools()
    assert store.load() is not None  # a network problem keeps the token


# --- the module's config ------------------------------------------------------------------------------------

def test_the_config_names_rezi_and_a_token_file_outside_the_repo(tmp_path):
    s = settings(DEFAULTS)
    assert s["rezi_url"] == REZI_URL and s["callback_port"] == 33418
    assert Path(s["token_file"]) == default_token_file()
    own = settings(DEFAULTS | {"token_file": str(tmp_path / "t.json"), "rezi_url": "http://127.0.0.1:9/mcp"})
    client = rezi_client(own)
    assert client.url == "http://127.0.0.1:9/mcp" and client.store.path == tmp_path / "t.json"
    for bad in ({"token_file": str(REPO / "rezi_token.json")}, {"rezi_url": "http://api.rezi.ai/mcp"},
                {"rezi_url": "ftp://x"}, {"callback_port": 0}, {"callback_port": "x"}):  # fmt: skip
        with pytest.raises(ValueError):
            settings(DEFAULTS | bad)


async def test_the_module_loads_without_touching_the_token_file_or_rezi(tmp_path):
    token = tmp_path / "rezi_token.json"
    app = App([CvModule], {"modules": {"enabled": ["cv"], "cv": {"token_file": str(token), "agent": {"enabled": False}}}, "core": {}})
    await app.start()
    try:
        modules = {m.id: m.state for m in (await app.router.send(ListModules())).value}
        assert modules["cv"] is ModuleState.ACTIVE
    finally:
        await app.stop()
    assert not token.exists()


def test_pywin32_folders_are_added_once_when_an_old_process_missed_its_pth(tmp_path, monkeypatch):
    import sys

    from assistant.modules.cv.mcp import pywin32_paths

    if sys.platform != "win32":
        assert pywin32_paths([str(tmp_path)]) == []
        return
    for sub in ("win32", "win32/lib", "pywin32_system32"):
        (tmp_path / sub).mkdir(parents=True)
    monkeypatch.setattr(sys, "path", list(sys.path))
    added = pywin32_paths([str(tmp_path)])
    assert added == [str(tmp_path / "win32"), str(tmp_path / "win32" / "lib")]  # pythonwin isn't there
    assert pywin32_paths([str(tmp_path)]) == []  # already on sys.path: nothing again
