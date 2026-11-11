"""Build the one page: write an `.odt`, export the PDF, check it, and fit it to one page.

The `.odt` and LibreOffice's export are made in a temporary folder, outside the agent's folders,
and removed after: only the checked PDF is copied to `pdf_path` (no `.odt` comes out).

The fit, in this order, stopping at the first one-page result:
1. the layouts from roomy to tight (`odt.LAYOUTS`: font size, margins, gaps);
2. then, if allowed, the next section of the drop list (Publications, then Awards), with the
   layouts again.
If nothing fits, the last (tightest) try is returned with its page count: the worker then
tightens older bullets (its edit, not a rule here) and builds again.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from assistant.modules.cv.content import CvContent
from assistant.modules.cv.odt import LAYOUTS, TITLES, Layout, OdtWriter
from assistant.modules.cv.order import OrderChoice, SectionOrder
from assistant.modules.cv.pdf import PageCheck, PageReport, PdfExport


@dataclass(frozen=True)
class Built:
    """One build: the PDF, the order and layout used, and what the page check found."""

    pdf_path: Path
    paper: str
    layout: Layout
    choice: OrderChoice
    report: PageReport
    tries: int

    @property
    def one_page(self) -> bool:
        return self.report.one_page

    def as_value(self) -> dict[str, Any]:
        """Plain data for the menu item's result."""
        return {
            "pdf_path": str(self.pdf_path),
            "pages": self.report.pages, "one_page": self.one_page, "problems": list(self.report.problems),
            "paper": self.paper, "layout": self.layout.describe(), "tries": self.tries,
            "section_order": list(self.choice.order), "order_reason": self.choice.reason,
            "dropped": list(self.choice.dropped), "text": self.report.text,
        }  # fmt: skip


def build_cv(
    content: CvContent,
    order: SectionOrder,
    pdf_path: str | Path,
    export: PdfExport,
    *,
    paper: str = "letter",
    degree_first: bool = False,
    drop: int = 0,
    auto_drop: bool = True,
    check: PageCheck | None = None,
) -> Built:
    """Write, export and check `content`, fitted to one page, and save the PDF as `pdf_path`.

    `drop`: sections of the drop list left out from the start; `auto_drop`: leave out more, one at a
    time, when the tightest layout is still over a page. Raises what `PdfExport.export` raises."""
    check = check or PageCheck()
    if "contact" not in content.names():
        raise ValueError("the CV has no contact section (its first line is the name)")
    if Path(pdf_path).suffix.lower() != ".pdf":
        raise ValueError(f"the output must be a .pdf, not {Path(pdf_path).name}")
    name = content.lines("contact")[0].strip()
    can_drop = len([s for s in order.drop_first if s in content.names()])
    pdf_path = Path(pdf_path)
    with tempfile.TemporaryDirectory(prefix="assistant-cv-build-") as tmp:
        odt_path = Path(tmp) / pdf_path.with_suffix(".odt").name
        last: Built | None = None
        tries = 0
        for n in range(drop, max(drop, can_drop if auto_drop else drop) + 1):
            choice = order.choose(content, degree_first, n)
            if last is not None and choice.dropped == last.choice.dropped:
                break  # nothing more to leave out
            titles = [TITLES[s] for s in choice.order if s in TITLES]
            for layout in LAYOUTS:
                tries += 1
                odt = OdtWriter(paper, layout).write(content, choice.order, odt_path)
                pdf = export.export(odt)
                last = Built(pdf, paper, layout, choice, check.read(pdf, paper, titles, name), tries)
                if last.one_page:
                    break
            if last is not None and last.one_page:
                break
        assert last is not None
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(last.pdf_path, pdf_path)
    return Built(pdf_path, last.paper, last.layout, last.choice, last.report, last.tries)
