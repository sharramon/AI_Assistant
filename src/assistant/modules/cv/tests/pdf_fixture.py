"""A test CV as a real text PDF (Helvetica, one line per item, no LibreOffice needed), for the
items that take the base CV as a `CV_Test_*.pdf`. `pdf_read.read_pdf` reads it back to the
same sections; the lines must be short enough not to wrap (under about 90 characters).
"""

from __future__ import annotations

from pathlib import Path

from assistant.modules.cv.content import CvContent
from assistant.modules.cv.odt import BULLET, TITLES

_LEFT, _DATES, _TOP = 50.0, 470.0, 750.0
_SIZES = {"name": 18.0, "heading": 12.0, "body": 10.0}


def _text(s: str) -> bytes:
    raw = s.encode("cp1252")  # WinAnsiEncoding: • is 0x95
    return b"(" + raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


def _show(x: float, y: float, size: float, s: str) -> bytes:
    return b"BT /F1 %.1f Tf %.1f %.1f Td " % (size, x, y) + _text(s) + b" Tj ET\n"


def write_pdf(content: CvContent, order: list[str] | tuple[str, ...], path: str | Path,
              extra: tuple[tuple[float, str], ...] = ()) -> Path:  # fmt: skip
    """`content` in `order` as a one-page Letter PDF at `path`; then the `extra` lines (size, text),
    e.g. a heading the reader doesn't know, for the read check."""
    ops, y = [], _TOP
    for name in order:
        lines = content.lines(name)
        if not lines:
            continue
        if name != "contact":
            y -= 6
            ops.append(_show(_LEFT, y, _SIZES["heading"], TITLES[name]))
            y -= 16
        for i, line in enumerate(lines):
            size = _SIZES["name"] if name == "contact" and i == 0 else _SIZES["body"]
            if line.startswith(BULLET):
                ops.append(_show(_LEFT + 8, y, size, "•"))
                ops.append(_show(_LEFT + 20, y, size, line[len(BULLET):]))
            elif " | " in line and name != "contact":
                left, dates = line.rsplit(" | ", 1)
                ops.append(_show(_LEFT, y, size, left))
                ops.append(_show(_DATES, y, size, dates))
            else:
                ops.append(_show(_LEFT, y, size, line))
            y -= size + 4
    for size, text in extra:
        y -= 6
        ops.append(_show(_LEFT, y, size, text))
        y -= size + 4
    stream = b"".join(ops)
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> "
        b"/Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"endstream",
    ]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for n, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % n + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(out))
    return path
