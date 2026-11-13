"""Named module events (`ModuleEvent`): `ctx.publish_named`, `ctx.subscribe_named`, `ctx.unsubscribe`,
and the manifest's `publishes_named` / `listens_named` (docs/next-steps/named-module-events.md)."""

from __future__ import annotations

import asyncio
import logging

import pytest

from assistant.contracts import InputReceived, Manifest, ModuleEvent, SubscriptionHandle, event_name_ok
from assistant.core.bus import EventBus
from assistant.core.container import Container
from assistant.core.context import ScopedContext
from assistant.core.router import CommandRouter


def ctx_on(bus: EventBus, manifest: Manifest) -> ScopedContext:
    return ScopedContext(manifest, CommandRouter(), bus, Container(), {}, logging.getLogger(manifest.id))


async def settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


async def test_publish_and_hear_by_name(bus: EventBus) -> None:
    cv = ctx_on(bus, Manifest(id="cv", publishes_named=("cv.job_finished",)))
    js = ctx_on(bus, Manifest(id="job_search", listens_named=("cv.job_finished",)))
    heard: list[ModuleEvent] = []

    async def keep(event: ModuleEvent) -> None:
        heard.append(event)

    handle = js.subscribe_named("cv.job_finished", keep)
    assert isinstance(handle, SubscriptionHandle)
    cv.publish_named("cv.job_finished", {"reply_to": "job_search_agent", "n": 1})
    cv.publish_named("cv.other", {})  # undeclared, still published; another name
    await settle()
    assert [(e.name, e.source, e.data) for e in heard] == [
        ("cv.job_finished", "cv", {"reply_to": "job_search_agent", "n": 1})]
    cv.close()
    js.close()


async def test_wildcard_takes_every_event_of_one_module(bus: EventBus) -> None:
    cv = ctx_on(bus, Manifest(id="cv"))
    cvx = ctx_on(bus, Manifest(id="cvx"))
    js = ctx_on(bus, Manifest(id="job_search", listens_named=("cv.*",)))
    heard: list[str] = []

    async def keep(event: ModuleEvent) -> None:
        heard.append(event.name)

    js.subscribe_named("cv.*", keep)
    cv.publish_named("cv.a", {})
    cv.publish_named("cv.b", {})
    cvx.publish_named("cvx.c", {})  # "cvx." doesn't start with "cv."
    await settle()
    assert heard == ["cv.a", "cv.b"]
    for c in (cv, cvx, js):
        c.close()


async def test_names_and_data_are_checked(bus: EventBus) -> None:
    cv = ctx_on(bus, Manifest(id="cv"))
    with pytest.raises(ValueError, match="may publish only 'cv."):
        cv.publish_named("job_search.done", {})
    with pytest.raises(ValueError, match="may publish only"):
        cv.publish_named("cv", {})
    with pytest.raises(ValueError, match="plain JSON"):
        cv.publish_named("cv.x", {"obj": object()})
    with pytest.raises(ValueError, match="plain JSON"):
        cv.publish_named("cv.x", {"nan": float("nan")})
    with pytest.raises(ValueError, match="Not an event name"):
        cv.subscribe_named("not a name", lambda e: None)
    cv.close()


async def test_data_is_a_copy(bus: EventBus) -> None:
    cv = ctx_on(bus, Manifest(id="cv"))
    js = ctx_on(bus, Manifest(id="job_search"))
    heard: list[dict] = []

    async def keep(event: ModuleEvent) -> None:
        heard.append(event.data)

    js.subscribe_named("cv.x", keep)
    data = {"items": [1, 2]}
    cv.publish_named("cv.x", data)
    data["items"].append(3)
    await settle()
    assert heard == [{"items": [1, 2]}]
    cv.close()
    js.close()


async def test_unsubscribe_drops_one_named_and_one_typed(bus: EventBus) -> None:
    cv = ctx_on(bus, Manifest(id="cv"))
    js = ctx_on(bus, Manifest(id="job_search", listens=(InputReceived,)))
    named: list[str] = []
    typed: list[str] = []

    async def keep_named(event: ModuleEvent) -> None:
        named.append(event.name)

    async def keep_typed(event: InputReceived) -> None:
        typed.append(event.text)

    named_handle = js.subscribe_named("cv.x", keep_named)
    other = js.subscribe_named("cv.y", keep_named)
    typed_handle = js.subscribe(InputReceived, keep_typed)
    js.unsubscribe(named_handle)
    js.unsubscribe(typed_handle)
    js.unsubscribe(typed_handle)  # already gone: nothing happens
    cv.publish_named("cv.x", {})
    cv.publish_named("cv.y", {})
    bus.publish(InputReceived(text="hi", source="test"))
    await settle()
    assert named == ["cv.y"] and typed == []
    assert list(js._subscriptions) == [other]
    cv.close()
    js.close()


async def test_undeclared_named_events_are_logged_once(bus: EventBus, caplog: pytest.LogCaptureFixture) -> None:
    cv = ctx_on(bus, Manifest(id="cv", listens_named=("job_search.*",)))
    with caplog.at_level(logging.WARNING):
        cv.publish_named("cv.x", {})
        cv.publish_named("cv.x", {})
        cv.subscribe_named("other.y", lambda e: None)
        cv.subscribe_named("other.y", lambda e: None)
        cv.subscribe_named("job_search.z", lambda e: None)  # covered by job_search.*
    assert [r.getMessage() for r in caplog.records] == [
        "cv uses cv.x without declaring it in its manifest (publishes_named)",
        "cv uses other.y without declaring it in its manifest (listens_named)",
    ]
    cv.close()


async def test_nothing_after_close(bus: EventBus) -> None:
    cv = ctx_on(bus, Manifest(id="cv"))
    js = ctx_on(bus, Manifest(id="job_search"))
    heard: list[str] = []

    async def keep(event: ModuleEvent) -> None:
        heard.append(event.name)

    js.subscribe_named("cv.x", keep)
    js.close()
    cv.publish_named("cv.x", {})
    await settle()
    assert heard == []
    cv.close()


def test_manifest_checks_the_names() -> None:
    Manifest(id="cv", publishes_named=("cv.job_finished",), listens_named=("job_search.*", "x.y"))
    with pytest.raises(ValueError, match="publishes_named"):
        Manifest(id="cv", publishes_named=("job_search.done",))
    with pytest.raises(ValueError, match="publishes_named"):
        Manifest(id="cv", publishes_named=("cv.*",))
    with pytest.raises(ValueError, match="listens_named"):
        Manifest(id="cv", listens_named=("cv",))


def test_event_name_ok() -> None:
    assert event_name_ok("cv.job_finished")
    assert event_name_ok("cv.a.b")
    assert not event_name_ok("cv")
    assert not event_name_ok("cv.*")
    assert event_name_ok("cv.*", pattern=True)
    assert not event_name_ok("cv.a b")
    assert not event_name_ok(3)  # type: ignore[arg-type]
