"""Opening a page: the slot an add-on fills so the core group never names a viewer.

The Talker, the worker's SHOW tags and temp_ui's Open in viewer button ask the container for
`IPageOpener` at each call (`uses`, no start order). Whichever add-on provides it (the HTML
viewer today) opens the page; with none on, the caller says so. A module that provides it and
has `start_on_use = true` in its config is turned on by the core when a caller asks for it
(`StartProvider`), so callers name a contract, never a module or its tools.
"""

from __future__ import annotations

from abc import abstractmethod

from assistant.contracts.messages import Result
from assistant.contracts.module import Contract


class IPageOpener(Contract):
    """Opens a page (an HTML file) for you to look at, optionally highlighting a quote on it.

    One provider at a time. Look it up at each call (`ctx.get_one(IPageOpener)`), never keep
    it: a reload swaps the provider. `assistant.infra.open_page` does the lookup, the start on
    use and the "none is on" answer in one place.
    """

    @abstractmethod
    async def open(
        self, path: str, quote: str | None = None, heading: str | None = None, front: bool = False
    ) -> Result:
        """Open `path` (switching to it if it's already open). With `quote`, highlight that short
        text on the page, in `heading`'s section if given, and scroll to it. `front`: bring the
        window to the front (your own click), not for agents' pages.

        Result: ok once the page is open; with a quote, its value has `found` False when the
        quote isn't on the page (the page is open, nothing marked). `invalid_arguments` for a
        missing file; `failed` (retryable) when the viewer can't be reached."""
