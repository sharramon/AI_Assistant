"""Show a page: through the page-opener slot (`IPageOpener`), never a viewer's own name or tools.

`open_page` is the one place that finds the provider of `IPageOpener` (asking the core to start
the module that provides it and starts on use, `StartProvider`, when none is on) and says plainly
when there is none. `show_page` turns a SHOW tag (`<<SHOW: path>>` or
`<<SHOW: path | "quote" | heading>>`) into that call. The worker (`SessionTaskAgent`), the Talker
and temp_ui use them and word their own messages from the outcome. See docs/api/infra.md#show_page.
"""

from __future__ import annotations

from typing import NamedTuple

from assistant.contracts import IPageOpener, ModuleContext, Result, StartProvider, Status
from assistant.infra.agent_tags import ShowTag, parse_show

NO_PAGE_VIEWER = "No page viewer is on"


class ShowOutcome(NamedTuple):
    show: ShowTag  # the parsed tag: path, quote, heading
    result: Result  # the page opener's result

    @property
    def quote_missing(self) -> bool:
        """The page opened, but the quote to highlight isn't on it."""
        value = self.result.value
        return self.result.is_ok and isinstance(value, dict) and value.get("found") is False


async def open_page(
    ctx: ModuleContext, path: str, quote: str | None = None, heading: str | None = None, front: bool = False
) -> Result:
    """Open `path` (highlighting `quote` under `heading`, if given) with whichever module provides
    `IPageOpener`. None on: the core starts the one that provides it and starts on use; still none:
    `not_available` with `NO_PAGE_VIEWER`. A start that failed gives its error. The caller declares
    `IPageOpener` in `manifest.uses` and `StartProvider` in `manifest.sends`."""
    opener = ctx.get_one(IPageOpener)
    if opener is None:
        started = await ctx.send(StartProvider(contract=IPageOpener.__name__))
        if not started.is_ok and started.status is not Status.NOT_AVAILABLE:
            return started
        opener = ctx.get_one(IPageOpener)
    if opener is None:
        return Result.not_available(NO_PAGE_VIEWER)
    return await opener.open(path, quote, heading, front=front)


async def show_page(ctx: ModuleContext, argument: str) -> ShowOutcome:
    """Open the page a SHOW tag's `argument` names, through `open_page`."""
    show = parse_show(argument)
    return ShowOutcome(show, await open_page(ctx, show.path, show.quote, show.heading))
