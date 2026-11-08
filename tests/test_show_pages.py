"""The shared SHOW helper (assistant.infra.show_pages): one place for the viewer's tool call."""

import asyncio

from assistant.contracts import Result
from assistant.infra import parse_show, show_command, show_page


def test_show_command_opens_or_highlights():
    plain = show_command(parse_show(r"C:\docs\page.html"))
    assert (plain.name, plain.args) == ("viewer.open", {"path": r"C:\docs\page.html"})
    quoted = show_command(parse_show(r'C:\docs\page.html | "exact words" | Heading'))
    assert quoted.name == "viewer.highlight"
    assert quoted.args == {"path": r"C:\docs\page.html", "text": "exact words", "heading": "Heading"}
    no_heading = show_command(parse_show(r'C:\docs\page.html | "exact words"'))
    assert "heading" not in no_heading.args


def test_show_page_sends_it_and_reports_a_missing_quote():
    sent = []

    class Ctx:
        async def send(self, command):
            sent.append(command)
            return Result.ok({"found": False})

    outcome = asyncio.run(show_page(Ctx(), r'C:\p.html | "gone"'))
    assert sent[0].name == "viewer.highlight" and outcome.show.path == r"C:\p.html"
    assert outcome.quote_missing
    failed = asyncio.run(_with(Result.failed("off")))
    assert not failed.quote_missing and not failed.result.is_ok


async def _with(result):
    class Ctx:
        async def send(self, command):
            return result

    return await show_page(Ctx(), r"C:\p.html")
