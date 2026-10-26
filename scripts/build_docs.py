"""Render docs/**/*.md into browsable HTML under docs/html/, with Mermaid diagrams drawn.

The Markdown files are the source of truth; never edit docs/html/ by hand.
Run after changing any doc:  python scripts/build_docs.py
"""

from __future__ import annotations

import html
import os
import re
import shutil
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
OUT = DOCS / "html"
SECTIONS = {
    "architecture": "Architecture",
    "agents": "Agents",
    "api": "API Reference",
    "next-steps": "Next steps",
}
MERMAID_JS = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"

MD_LINK = re.compile(r'href="(?![a-z]+:)([^"#]*?\.md)(#[^"]*)?"')
README_LINK = re.compile(r'\(([^)#]*?\.md)')


def out_path(md: Path) -> Path:
    rel = md.relative_to(DOCS)
    return OUT / rel.parent / ("index.html" if rel.stem == "README" else f"{rel.stem}.html")


def title_of(md: Path) -> str:
    for line in md.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return md.stem


def section_pages(section: str) -> list[Path]:
    """The section's README first, then pages in the order the README links them, then the rest.

    If the README has a `## Pages` section, only links from there set the order.
    """
    folder = DOCS / section
    readme = folder / "README.md"
    pages = sorted(p for p in folder.glob("*.md") if p != readme)
    text = readme.read_text(encoding="utf-8") if readme.exists() else ""
    if "\n## Pages" in text:
        text = text.split("\n## Pages", 1)[1].split("\n## ", 1)[0]
    order = [(folder / link).resolve() for link in README_LINK.findall(text)]
    pages.sort(key=lambda p: order.index(p.resolve()) if p.resolve() in order else len(order))
    return ([readme] if readme.exists() else []) + pages


def nav_html(current: Path) -> str:
    here = out_path(current).parent
    parts = []
    for section, label in SECTIONS.items():
        items = []
        pages = section_pages(section)
        for page in pages:
            href = Path(os.path.relpath(out_path(page), here)).as_posix()
            # A one-page section shows its own title instead of "Overview".
            name = "Overview" if page.stem == "README" and len(pages) > 1 else title_of(page)
            active = ' aria-current="page"' if page == current else ""
            items.append(f'<li><a href="{href}"{active}>{html.escape(name)}</a></li>')
        parts.append(f"<h2>{label}</h2><ul>{''.join(items)}</ul>")
    return "".join(parts)


def fix_links(body: str) -> str:
    def repl(match: re.Match) -> str:
        path = re.sub(r"(^|/)README\.md$", r"\1index.html", match.group(1))
        path = re.sub(r"\.md$", ".html", path)
        return f'href="{path}{match.group(2) or ""}"'

    return MD_LINK.sub(repl, body)


BLOCK_START = re.compile(r"^(\||[-*] |\d+\. )")


def add_block_spacing(text: str) -> str:
    """Insert the blank line Python-Markdown needs before a table or list.

    GitHub renders a table or list directly under a line of text; Python-Markdown
    treats it as part of that paragraph unless a blank line separates them.
    """
    out: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
        elif not in_fence and BLOCK_START.match(line) and out:
            prev = out[-1]
            if prev.strip() and not BLOCK_START.match(prev) and not prev.startswith((" ", "\t")):
                out.append("")
        out.append(line)
    return "\n".join(out) + "\n"


def render(md: Path) -> str:
    converter = markdown.Markdown(extensions=["tables", "fenced_code", "toc", "sane_lists"])
    body = fix_links(converter.convert(add_block_spacing(md.read_text(encoding="utf-8"))))
    # `\|` escapes a pipe inside a table cell; GitHub drops the backslash, Python-Markdown keeps it in code.
    body = body.replace("\\|", "|")
    source = md.relative_to(ROOT).as_posix()
    return PAGE.format(
        title=html.escape(title_of(md)),
        nav=nav_html(md),
        body=body,
        source=source,
        mermaid=MERMAID_JS,
    )


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    count = 0
    for section in SECTIONS:
        for md in section_pages(section):
            target = out_path(md)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(render(md), encoding="utf-8")
            count += 1
    (OUT / "index.html").write_text(REDIRECT, encoding="utf-8")
    print(f"Wrote {count} pages to {OUT.relative_to(ROOT).as_posix()}/ (open docs/html/index.html)")


REDIRECT = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Assistant Docs</title><meta http-equiv="refresh" content="0; url=architecture/index.html"></head>
<body style="margin:0;background:#fbfbfa;font-family:system-ui,sans-serif;padding:16px">
<a href="architecture/index.html">Open the architecture overview</a></body></html>
"""

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<!-- Generated from {source} by scripts/build_docs.py. Edit the Markdown, not this file. -->
<style>
:root {{
  --bg: #fbfbfa; --panel: #f2f1ee; --text: #1f2328; --muted: #5d6470;
  --border: #dedcd6; --accent: #2f62c8; --code-bg: #ecebe6;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg: #16181c; --panel: #1d2025; --text: #e6e6e3; --muted: #9aa1ab;
    --border: #30343b; --accent: #82aaff; --code-bg: #23272e;
  }}
}}
:root[data-theme="dark"] {{
  --bg: #16181c; --panel: #1d2025; --text: #e6e6e3; --muted: #9aa1ab;
  --border: #30343b; --accent: #82aaff; --code-bg: #23272e;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; background: var(--bg); color: var(--text);
  font: 16px/1.6 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}}
.layout {{ display: grid; grid-template-columns: 250px minmax(0, 1fr); min-height: 100vh; }}
nav {{
  background: var(--panel); border-right: 1px solid var(--border);
  padding: 24px 16px; position: sticky; top: 0; height: 100vh; overflow-y: auto;
}}
nav h2 {{ font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin: 20px 8px 6px; }}
nav h2:first-child {{ margin-top: 0; }}
nav ul {{ list-style: none; margin: 0; padding: 0; }}
nav a {{ display: block; padding: 5px 8px; border-radius: 6px; color: var(--text); text-decoration: none; font-size: 14px; }}
nav a:hover {{ background: var(--border); }}
nav a[aria-current="page"] {{ background: var(--accent); color: var(--bg); }}
main {{ padding: 32px 40px 64px; max-width: 980px; width: 100%; }}
h1 {{ font-size: 2rem; line-height: 1.2; margin: 0 0 16px; }}
h2 {{ font-size: 1.4rem; margin: 40px 0 12px; padding-bottom: 6px; border-bottom: 1px solid var(--border); }}
h3 {{ font-size: 1.1rem; margin: 28px 0 8px; }}
a {{ color: var(--accent); }}
code {{ font: 0.88em ui-monospace, "Cascadia Code", Consolas, monospace; background: var(--code-bg); padding: 1px 5px; border-radius: 4px; }}
pre {{ background: var(--code-bg); padding: 14px 16px; border-radius: 8px; overflow-x: auto; }}
pre code {{ background: none; padding: 0; }}
table {{ display: block; overflow-x: auto; border-collapse: collapse; margin: 12px 0 20px; font-size: 14px; }}
th, td {{ border: 1px solid var(--border); padding: 7px 11px; text-align: left; vertical-align: top; }}
th {{ background: var(--panel); }}
.diagram {{
  background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
  padding: 20px; margin: 16px 0 24px; overflow-x: auto; text-align: center;
}}
.diagram svg {{ max-width: 100%; height: auto; }}
.diagram.offline {{ text-align: left; white-space: pre; font: 13px ui-monospace, Consolas, monospace; }}
.diagram:not(.offline) {{ cursor: zoom-in; }}
.zoom {{ position: fixed; inset: 0; z-index: 10; background: var(--bg); overflow: hidden; cursor: grab; touch-action: none; }}
.zoom.dragging {{ cursor: grabbing; }}
.zoom-stage {{ position: absolute; left: 0; top: 0; transform-origin: 0 0; }}
.zoom-stage svg {{ display: block; max-width: none !important; }}
.zoom-close {{
  position: absolute; top: 12px; left: 12px; z-index: 1; width: 40px; height: 40px;
  border: 1px solid var(--border); border-radius: 8px; background: var(--panel); color: var(--text);
  font-size: 22px; line-height: 1; cursor: pointer;
}}
.zoom-close:hover {{ background: var(--border); }}
footer {{ margin-top: 48px; color: var(--muted); font-size: 13px; }}
@media (max-width: 760px) {{
  .layout {{ grid-template-columns: 1fr; }}
  nav {{ position: static; height: auto; border-right: 0; border-bottom: 1px solid var(--border); padding: 16px; }}
  nav ul {{ display: flex; flex-wrap: wrap; gap: 4px; }}
  main {{ padding: 20px 16px 48px; }}
}}
</style>
</head>
<body>
<div class="layout">
<nav>{nav}</nav>
<main>
{body}
<footer>Generated from <code>{source}</code>. Edit the Markdown, then run <code>python scripts/build_docs.py</code>.</footer>
</main>
</div>
<script src="{mermaid}"></script>
<script>
(function () {{
  var blocks = document.querySelectorAll("pre > code.language-mermaid");
  blocks.forEach(function (code) {{
    var div = document.createElement("div");
    div.className = "diagram";
    div.textContent = code.textContent;
    code.parentElement.replaceWith(div);
  }});
  if (!window.mermaid) {{
    // Offline: show the diagram source instead.
    document.querySelectorAll(".diagram").forEach(function (d) {{ d.classList.add("offline"); }});
    return;
  }}
  var dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  mermaid.initialize({{ startOnLoad: false, theme: dark ? "dark" : "neutral", securityLevel: "strict" }});
  mermaid.run({{ querySelector: ".diagram" }});

  // Click a diagram to view it full screen: wheel zooms at the cursor, drag pans, X or Esc closes.
  var overlay = null, stage, scale, x, y;
  function place() {{ stage.style.transform = "translate(" + x + "px," + y + "px) scale(" + scale + ")"; }}
  function close() {{
    if (!overlay) return;
    overlay.remove();
    overlay = null;
    document.body.style.overflow = "";
  }}
  function open(svg) {{
    var box = svg.viewBox.baseVal, w = box && box.width ? box.width : svg.getBBox().width;
    var h = box && box.height ? box.height : svg.getBBox().height;
    var clone = svg.cloneNode(true);
    clone.removeAttribute("style");
    clone.setAttribute("width", w);
    clone.setAttribute("height", h);
    overlay = document.createElement("div");
    overlay.className = "zoom";
    var btn = document.createElement("button");
    btn.className = "zoom-close";
    btn.setAttribute("aria-label", "Close");
    btn.textContent = "\\u00d7";
    btn.addEventListener("click", close);
    stage = document.createElement("div");
    stage.className = "zoom-stage";
    stage.appendChild(clone);
    overlay.appendChild(btn);
    overlay.appendChild(stage);
    document.body.appendChild(overlay);
    document.body.style.overflow = "hidden";
    scale = Math.min(innerWidth * 0.92 / w, innerHeight * 0.92 / h);
    x = (innerWidth - w * scale) / 2;
    y = (innerHeight - h * scale) / 2;
    place();
    overlay.addEventListener("wheel", function (e) {{
      e.preventDefault();
      var f = Math.exp(-e.deltaY * 0.0015), s = Math.min(40, Math.max(0.05, scale * f));
      f = s / scale;
      x = e.clientX - (e.clientX - x) * f;
      y = e.clientY - (e.clientY - y) * f;
      scale = s;
      place();
    }}, {{ passive: false }});
    var drag = null;
    overlay.addEventListener("pointerdown", function (e) {{
      if (e.target === btn) return;
      drag = {{ px: e.clientX, py: e.clientY, x: x, y: y }};
      overlay.setPointerCapture(e.pointerId);
      overlay.classList.add("dragging");
    }});
    overlay.addEventListener("pointermove", function (e) {{
      if (!drag) return;
      x = drag.x + e.clientX - drag.px;
      y = drag.y + e.clientY - drag.py;
      place();
    }});
    overlay.addEventListener("pointerup", function () {{ drag = null; overlay.classList.remove("dragging"); }});
  }}
  document.addEventListener("click", function (e) {{
    var d = e.target.closest && e.target.closest(".diagram");
    var svg = d && d.querySelector("svg");
    if (svg && !overlay) open(svg);
  }});
  document.addEventListener("keydown", function (e) {{ if (e.key === "Escape") close(); }});
}})();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
