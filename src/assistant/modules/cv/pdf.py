"""The PDF side of the one page: export the `.odt` with headless LibreOffice, then check the PDF.

`PdfExport` runs `soffice --headless --convert-to pdf` with its own LibreOffice profile (so a
LibreOffice you have open doesn't take the job over), removes an old PDF first (so a stale file
is never returned) and serializes the runs. `PageCheck` reads the PDF with `pypdf`: page count,
page size, the text, and what is wrong with it (`assess`, plain so it's tested without a PDF).
"""

from __future__ import annotations

import re
import subprocess
import tempfile
import threading
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

PAPER_SIZES_PT = {"letter": (612.0, 792.0), "a4": (595.3, 841.9)}
_SIZE_SLACK_PT = 3.0


class ExportError(RuntimeError):
    """LibreOffice ran but gave no PDF (the reason is in the message)."""


class PdfExport:
    """`.odt` -> PDF with headless LibreOffice (`soffice`), one run at a time."""

    _lock = threading.Lock()  # one LibreOffice profile, so one run at a time across copies

    def __init__(self, soffice: str | Path, timeout: float = 120.0, profile: str | Path | None = None) -> None:
        self.soffice = Path(soffice)
        self.timeout = timeout
        self.profile = Path(profile) if profile else Path(tempfile.gettempdir()) / "assistant-cv-soffice"

    def available(self) -> bool:
        return self.soffice.is_file()

    def export(self, odt: str | Path) -> Path:
        """The PDF next to `odt` (same name). FileNotFoundError: no soffice; ExportError: no PDF came out."""
        odt = Path(odt).resolve()
        if not self.available():
            raise FileNotFoundError(f"LibreOffice not found at {self.soffice} (the cv module's `soffice` setting)")
        pdf = odt.with_suffix(".pdf")
        with self._lock:
            pdf.unlink(missing_ok=True)
            command = [str(self.soffice), f"-env:UserInstallation={self.profile.resolve().as_uri()}",
                       "--headless", "--norestore", "--nolockcheck",
                       "--convert-to", "pdf", "--outdir", str(odt.parent), str(odt)]  # fmt: skip
            try:
                done = subprocess.run(command, capture_output=True, text=True, timeout=self.timeout, check=False)
            except subprocess.TimeoutExpired as exc:
                raise ExportError(f"LibreOffice took over {self.timeout:g} s on {odt.name}") from exc
        if not pdf.is_file():
            said = " ".join((done.stderr or done.stdout or "").split())[:300]
            raise ExportError(f"LibreOffice gave no PDF for {odt.name} (exit {done.returncode}){': ' + said if said else ''}")
        return pdf


@dataclass(frozen=True)
class PageReport:
    """What the PDF is: its pages, its text, and what's wrong with it (empty when it's clean)."""

    pages: int
    text: str
    problems: tuple[str, ...] = field(default=())

    @property
    def one_page(self) -> bool:
        return self.pages == 1


class PageCheck:
    """Reads a PDF (`pypdf`) and says whether it is one clean page."""

    def read(self, pdf: str | Path, paper: str, titles: Iterable[str] = (), name: str = "") -> PageReport:
        from pypdf import PdfReader  # imported on use: only this part needs it

        reader = PdfReader(str(pdf))
        sizes = [(float(page.mediabox.width), float(page.mediabox.height)) for page in reader.pages]
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return PageReport(pages=len(sizes), text=text, problems=tuple(assess(sizes, text, paper, titles, name)))


def assess(sizes: list[tuple[float, float]], text: str, paper: str, titles: Iterable[str] = (), name: str = "") -> list[str]:
    """What's wrong with a PDF of these page sizes and this text (the page count is the caller's)."""
    problems: list[str] = []
    want = PAPER_SIZES_PT[paper]
    wrong = sorted({(round(w), round(h)) for w, h in sizes
                    if abs(w - want[0]) > _SIZE_SLACK_PT or abs(h - want[1]) > _SIZE_SLACK_PT})  # fmt: skip
    if wrong:
        problems.append(f"page size {wrong[0][0]} x {wrong[0][1]} pt is not {paper}")
    flat = re.sub(r"\s+", " ", text).strip().lower()
    if not flat:
        return [*problems, "no text in the PDF (only images?)"]
    if "�" in text:
        problems.append("unreadable characters (�) in the text")
    missing = [title for title in titles if re.sub(r"\s+", " ", title).strip().lower() not in flat]
    if missing:
        problems.append(f"headings not found in the text: {', '.join(missing)}")
    if name and re.sub(r"\s+", " ", name).strip().lower() not in flat:
        problems.append(f"the name {name!r} not found in the text")
    return problems
