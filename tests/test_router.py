import asyncio

import pytest

from assistant.contracts import Command, Result, Status
from assistant.core.router import CommandRouter


class Ping(Command):
    value: int = 0


async def test_no_handler_returns_not_available():
    result = await CommandRouter().send(Ping())
    assert result.status is Status.NOT_AVAILABLE


async def test_returns_handler_result():
    router = CommandRouter()

    async def double(cmd: Ping) -> Result:
        return Result.ok(cmd.value * 2)

    router.register(Ping, double)
    result = await router.send(Ping(value=21))
    assert result.is_ok and result.value == 42


async def test_handler_exception_becomes_failed():
    router = CommandRouter()

    async def boom(cmd):
        raise RuntimeError("broken")

    router.register(Ping, boom)
    result = await router.send(Ping())
    assert result.status is Status.FAILED
    assert "broken" in result.error


async def test_non_result_return_becomes_failed():
    router = CommandRouter()

    async def wrong(cmd):
        return 42

    router.register(Ping, wrong)
    assert (await router.send(Ping())).status is Status.FAILED


async def test_timeout_returns_timed_out_and_cancels_handler():
    router = CommandRouter()
    cancelled = asyncio.Event()

    async def slow(cmd):
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    router.register(Ping, slow)
    result = await router.send(Ping(), timeout=0.05)
    assert result.status is Status.TIMED_OUT and result.retryable
    await asyncio.wait_for(cancelled.wait(), 1)


async def test_per_type_timeout_from_config():
    router = CommandRouter(default_timeout=10, timeouts={"Ping": 0.05})

    async def slow(cmd):
        await asyncio.sleep(10)

    router.register(Ping, slow)
    assert (await router.send(Ping())).status is Status.TIMED_OUT


async def test_cancel_by_correlation_id():
    router = CommandRouter()
    started = asyncio.Event()

    async def slow(cmd):
        started.set()
        await asyncio.sleep(10)
        return Result.ok()

    router.register(Ping, slow)
    pending = asyncio.create_task(router.send(Ping(correlation_id="job-1")))
    await started.wait()
    assert router.cancel("job-1") == 1
    assert (await pending).status is Status.CANCELLED


async def test_duplicate_handler_rejected():
    router = CommandRouter()

    async def handler(cmd):
        return Result.ok()

    router.register(Ping, handler)
    with pytest.raises(ValueError):
        router.register(Ping, handler)


async def test_unregister_only_removes_matching_handler():
    router = CommandRouter()

    async def first(cmd):
        return Result.ok("first")

    async def other(cmd):
        return Result.ok("other")

    router.register(Ping, first)
    router.unregister(Ping, other)
    assert (await router.send(Ping())).value == "first"
    router.unregister(Ping, first)
    assert (await router.send(Ping())).status is Status.NOT_AVAILABLE
