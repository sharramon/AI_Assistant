"""Show a page an agent named with a SHOW tag: open it in the HTML viewer, highlighting a quote if given.

The one place that turns `<<SHOW: path>>` or `<<SHOW: path | "quote" | heading>>` into the viewer's
tool call (`viewer.open` or `viewer.highlight`, sent as `InvokeTool`, so the core starts the viewer
if it's off). The worker (`SessionTaskAgent`) and the Talker both use it and word their own
messages from the outcome. See docs/api/infra.md#show_page.
"""

from __future__ import annotations

from typing import NamedTuple

from assistant.contracts import InvokeTool, ModuleContext, Result
from assistant.infra.agent_tags import ShowTag, parse_show

VIEWER_OPEN = "viewer.open"
VIEWER_HIGHLIGHT = "viewer.highlight"


class ShowOutcome(NamedTuple):
    show: ShowTag  # the parsed tag: path, quote, heading
    result: Result  # the viewer tool's result

    @property
    def quote_missing(self) -> bool:
        """The page opened, but the quote to highlight isn't on it."""
        value = self.result.value
        return self.result.is_ok and isinstance(value, dict) and value.get("found") is False


def show_command(show: ShowTag) -> InvokeTool:
    """The viewer tool call for a parsed SHOW tag."""
    if show.quote:
        args = {"path": show.path, "text": show.quote, **({"heading": show.heading} if show.heading else {})}
        return InvokeTool(name=VIEWER_HIGHLIGHT, args=args)
    return InvokeTool(name=VIEWER_OPEN, args={"path": show.path})


async def show_page(ctx: ModuleContext, argument: str) -> ShowOutcome:
    """Open the page a SHOW tag's `argument` names, through `ctx.send`."""
    show = parse_show(argument)
    return ShowOutcome(show, await ctx.send(show_command(show)))
