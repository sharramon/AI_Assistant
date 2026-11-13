"""The shared page helpers (assistant.infra.show_pages): SHOW tags and the Open in viewer button open
pages through the page-opener slot (`IPageOpener`), never a viewer's name or tools."""

import asyncio

from assistant.contracts import IPageOpener, Result, StartProvider, Status
from assistant.infra import NO_PAGE_VIEWER, open_page, show_page


class Opener(IPageOpener):
    def __init__(self, result: Result | None = None) -> None:
        self.calls: list[tuple] = []
        self.result = result or Result.ok({})

    async def open(self, path, quote=None, heading=None, front=False):
        self.calls.append((path, quote, heading, front))
        return self.result


class Ctx:
    """A context with the given opener on, or none; `starts` gives one when StartProvider comes."""

    def __init__(self, opener=None, starts=None, start_result=None):
        self.opener, self.starts, self.sent = opener, starts, []
        self.start_result = start_result

    def get_one(self, contract):
        assert contract is IPageOpener
        return self.opener

    async def send(self, command):
        self.sent.append(command)
        if self.start_result is not None:
            return self.start_result
        if self.starts is not None:
            self.opener = self.starts
            return Result.ok()
        return Result.not_available("nobody starts on use")


def test_show_page_opens_or_highlights_through_the_opener():
    opener = Opener(Result.ok({"found": False}))
    outcome = asyncio.run(show_page(Ctx(opener), r'C:\p.html | "gone" | Parts'))
    assert opener.calls == [(r"C:\p.html", "gone", "Parts", False)]
    assert outcome.show.path == r"C:\p.html" and outcome.quote_missing
    opener.result = Result.ok({})
    plain = asyncio.run(show_page(Ctx(opener), r"C:\docs\page.html"))
    assert opener.calls[-1] == (r"C:\docs\page.html", None, None, False)
    assert not plain.quote_missing


def test_open_page_passes_front():
    opener = Opener()
    assert asyncio.run(open_page(Ctx(opener), "a.html", front=True)).is_ok
    assert opener.calls == [("a.html", None, None, True)]


def test_no_page_viewer_says_so_plainly():
    ctx = Ctx()
    outcome = asyncio.run(show_page(ctx, r"C:\p.html"))
    assert outcome.result.status is Status.NOT_AVAILABLE and outcome.result.error == NO_PAGE_VIEWER
    assert not outcome.quote_missing
    assert [(type(c), c.contract) for c in ctx.sent] == [(StartProvider, "IPageOpener")]


def test_none_on_asks_the_core_to_start_its_provider():
    opener = Opener()
    ctx = Ctx(starts=opener)
    assert asyncio.run(open_page(ctx, "a.html")).is_ok
    assert [type(c) for c in ctx.sent] == [StartProvider] and opener.calls == [("a.html", None, None, False)]


def test_a_failed_start_gives_its_error():
    ctx = Ctx(start_result=Result.failed("The pages module couldn't start: no window"))
    result = asyncio.run(open_page(ctx, "a.html"))
    assert result.status is Status.FAILED and "no window" in result.error
