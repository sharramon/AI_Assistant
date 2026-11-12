"""A module's (or an app's) own docs folder: its settings, its pages in order, and their titles.

Each module keeps its docs in `<its folder>/docs/`: Markdown pages, HTML pages it wrote itself,
images, and an optional `docs.toml`. The main app's core reads them for `modules.docs`, and the
docs build publishes them; neither needs to know which modules exist. Standard library only.

Every module has the three standard pages, always first and in this order (`STANDARD_PAGES`):
    README.md          its overview (purpose, wrapper, config, code and tests)
    architecture.md    how it works (interface, what it owns and launches, inner workings)
    tools.md           its menu, generated from the module's own menu (`tools_page`); don't edit
                       between the markers, notes go after them
Any other page is optional. Every page is shown in the docs' standard layout (the tabs and the
sidebar): Markdown is rendered into it, an HTML page opens inside the standard frame.

`docs.toml` (the docs build requires `group` for a module; the rest is optional):
    group = "core"            # "core" or "add-on": where it sits in the docs, not where its files live
    tab = "Agents"            # the docs tab it goes in (default: the module's id)
    pages = ["a.html"]        # the order of its optional pages, after the standard three (default: by name)
    [related]                 # name = a page of the app's docs (`api/tools.md#anchor`), links only
"""

from __future__ import annotations

import html
import re
import tomllib
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

DOCS_DIR = "docs"
SETTINGS_FILE = "docs.toml"
PAGE_SUFFIXES = (".md", ".html")
SETTINGS_KEYS = frozenset({"group", "tab", "pages", "related"})
# The three pages every module has, in this order, with their name in the docs' sidebar.
STANDARD_PAGES = {"README.md": "Overview", "architecture.md": "Architecture", "tools.md": "Tools"}
TOOLS_FILE = "tools.md"
TOOLS_START = "<!-- tools:start (generated from the module's menu by scripts/build_docs.py; don't edit) -->"
TOOLS_END = "<!-- tools:end -->"
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def docs_settings(docs: str | Path) -> dict[str, Any]:
    """The docs folder's `docs.toml`, {} if it has none. Raises `tomllib.TOMLDecodeError` for invalid TOML."""
    path = Path(docs) / SETTINGS_FILE
    if not path.is_file():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def doc_pages(docs: str | Path) -> list[Path]:
    """The docs folder's pages (`.md` and `.html`, top level only): the standard pages first, in
    their order, then the ones `docs.toml` lists under `pages`, then the rest by name. [] if there's no folder."""
    folder = Path(docs)
    if not folder.is_dir():
        return []
    found = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in PAGE_SUFFIXES)
    standard = [folder / name for name in STANDARD_PAGES]
    listed = [folder / name for name in docs_settings(folder).get("pages", [])]
    first = list(dict.fromkeys(p for p in standard + listed if p in found))
    return first + [p for p in found if p not in first]


def tools_page(title: str, specs: Iterable[Mapping[str, Any]] | None, notes: str = "", intro: str = "") -> str:
    """The text of a module's tools page (`tools.md`) from its menu's specs (`name`, `description`,
    `input_schema`, as `ToolSpec.model_dump()` gives them). `specs=None`: the module has no code yet.
    `intro` and `notes`: hand-written text kept before and after the generated part."""
    lines = [f"# {title}: tools", "", *([intro.strip("\n"), ""] if intro.strip() else []), TOOLS_START, ""]
    specs = list(specs) if specs is not None else None
    if specs is None:
        lines.append("No menu yet: this module has no code.")
    elif not specs:
        lines.append("No menu: the agents can't call this module as a tool.")
    else:
        lines += ["Its menu, as the main AI sees it (`modules.menu`). Every item is called with `modules.use_item`.", ""]
        for spec in specs:
            schema = spec.get("input_schema") or {}
            props, required = schema.get("properties") or {}, set(schema.get("required") or ())
            lines += [f"## `{spec['name']}`", "", spec.get("description", ""), ""]
            if props:
                lines += ["| Argument | Type | Required | What it is |", "|---|---|---|---|"]
                for arg, prop in props.items():
                    kind = prop.get("type", "")
                    kind = " or ".join(kind) if isinstance(kind, list) else kind
                    what = " ".join(str(prop.get("description", "")).split()).replace("|", "\\|")
                    lines.append(f"| `{arg}` | {kind} | {'yes' if arg in required else 'no'} | {what} |")
            else:
                lines.append("No arguments.")
            lines.append("")
    lines += ["", TOOLS_END]
    return "\n".join(lines) + ("\n\n" + notes.strip("\n") + "\n" if notes.strip() else "\n")


def tools_notes(text: str) -> str:
    """The hand-written notes after a tools page's generated part ("" if none)."""
    return text.split(TOOLS_END, 1)[1].strip("\n") if TOOLS_END in text else ""


def tools_intro(text: str) -> str:
    """The hand-written text between a tools page's title and its generated part ("" if none)."""
    if TOOLS_START not in text:
        return ""
    head = text.split(TOOLS_START, 1)[0].split("\n", 1)
    return head[1].strip("\n") if head[0].startswith("# ") and len(head) > 1 else ""


def page_title(page: str | Path) -> str:
    """A Markdown page's first `# ` heading, an HTML page's `<title>`, else its file name without the suffix."""
    page = Path(page)
    text = page.read_text(encoding="utf-8", errors="replace")
    if page.suffix.lower() == ".md":
        for line in text.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
    else:
        match = _TITLE.search(text)
        if match and match.group(1).strip():
            return html.unescape(" ".join(match.group(1).split()))
    return page.stem
