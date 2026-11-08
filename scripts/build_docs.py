"""Render docs/**/*.md into browsable HTML, with Mermaid diagrams drawn.

The permanent docs (architecture, agents, api) go to docs/html/. The next-steps
notes go to their own output, docs/html-next-steps/, so they don't clutter the
main docs; docs/html/ never links to them.

Each page holds only its own content. What every page shares is written once per
output: site.css (styling), site.js (diagrams and zoom) and nav.js (the tab strip
and the sidebar), so adding a page or changing the style doesn't rewrite every page.

Navigation has two levels. The tabs across the top are the areas: Overview (the
app-wide design), the module tabs (MODULE_TABS below; a tab holds one module or a
group of them), then the project tabs (PROJECT_TABS: one docs folder each, like the
job project). The sidebar lists only the active tab's pages; a page's tab is the
one it belongs to. docs/html/ never links into next steps: it has no Next steps tab,
and a link in a page's text into next steps becomes plain text (the Markdown outside
next-steps/ shouldn't have any; tests/test_module_docs.py checks). Only the
next-steps output adds a Next steps tab, after the same tabs back to the main docs.
Its sidebar lists the active notes and one Archive link: next-steps/archive/ (finished
notes) builds as a section of that output with its own index, and its notes aren't listed
in the sidebar.

A module that carries its own docs folder (src/assistant/modules/<id>/docs/) is found by folder,
not listed here: see module_doc_folders() and module_tabs().

The Markdown files are the source of truth; never edit the generated HTML by hand.
Run after changing any doc:  python scripts/build_docs.py
"""

from __future__ import annotations

import functools
import html
import json
import os
import re
import shutil
import tomllib
from pathlib import Path

import markdown

from app_kit.module_docs import (
    DOCS_DIR,
    SETTINGS_FILE,
    SETTINGS_KEYS,
    STANDARD_PAGES,
    TOOLS_FILE,
    doc_pages,
    docs_settings,
    page_title,
    tools_intro,
    tools_notes,
    tools_page,
)

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
OUT = DOCS / "html"
NEXT_OUT = DOCS / "html-next-steps"
NEXT_STEPS = "next-steps"
ARCHIVE = f"{NEXT_STEPS}/archive"  # finished notes: done, nothing waiting on the user
# The folders built into docs/html/.
SECTIONS = ("architecture", "modules", "agents", "api", "job-project")
# Top-level tabs that each hold one docs folder about a project outside the app (not a module,
# not app-wide), after the module tabs: tab name -> folder. Its sidebar is that folder's pages.
PROJECT_TABS: dict[str, str] = {"Job project": "job-project"}
# The Overview tab's sidebar: these sections, minus pages a module tab claims, with the
# module pages' index listed right after the module library.
OVERVIEW = {"architecture": "Architecture", "agents": "Agents", "api": "API Reference"}
LIBRARY = "architecture/module-library.md"
MODULE_INDEX = "modules/README.md"

# The module tabs, in this order, keyed by tab name. Every module is in exactly one tab.
# Its sidebar: a group named after the tab with its modules' pages (docs/modules/<id>.md), then
#   modules: the module ids it owns (default: just the tab's name)
#   pages:   other docs pages about it; they belong to this tab (it lights up on them)
#   related: name -> page#anchor elsewhere (API entries, Overview pages), links only
# and always the App-wide links. A new module: add its page in docs/modules/ and one entry:
# its id in an existing tab's `modules`, or a new tab ({} if it has nothing more).
#
# Central modules: part of the main app and its window (the agent runtime, the usage tally, the
# terminals, the temp UI), so their docs stay in the main docs (docs/modules/<id>.md, their tab here)
# and never move into their own module folders; they're exempt from the three standard pages
# (user, 2026-11-06). Self-contained features (html_viewer, cv, job_search, voice_notes) move.
CENTRAL_MODULES = frozenset({"agent_hub", "talker", "main_assistant", "task_agents", "usage",
                             "console_io", "assistant_view", "temp_ui"})
MODULE_TABS: dict[str, dict] = {
    "Agents": {
        "modules": ["talker", "main_assistant", "agent_hub", "task_agents", "job_search"],
        "related": {
            "Agents (architecture)": "architecture/agents.md",
            "Agents: code layout": "architecture/agents-code.md",
            "Agents docs": "agents/README.md",
            "Agent runtime": "agents/runtime.md",
            "The Talker on its own": "agents/runtime.md#the-talker-on-its-own",
            "The Main Assistant on its own": "agents/runtime.md#the-main-assistant-on-its-own",
            "Messaging to and from the main app": "agents/runtime.md#messaging-to-and-from-the-main-app",
            "Agents API": "api/agents.md",
            "SessionTaskAgent (API)": "api/infra.md#sessiontaskagent",
        },
    },
    "usage": {
        "related": {
            "SessionUsage (API)": "api/agents.md#sessionusage",
            "UsageLedger (API)": "api/infra.md#usageledger",
        },
    },
    "voice_in": {
        "pages": ["architecture/voice.md"],
        "related": {
            "Voice messages (API)": "api/messaging.md#voice",
            "Voice service protocol (API)": "api/messaging.md#the-voice-service-protocol",
            "Voice service parts (API)": "api/messaging.md#the-voice-services-parts",
        },
    },
    "voice_notes": {
        "related": {
            "Voice messages (API)": "api/messaging.md#voice",
            "Chaining modules": "architecture/modules.md#chaining-modules",
        },
    },
    "html_viewer": {
        "pages": ["architecture/html-viewer.md"],
        "related": {
            "Viewer tools (API)": "api/tools.md#tools-offered-today",
            "Viewer events (API)": "api/messaging.md#viewertabschanged",
            "CompanionApp (API)": "api/app_kit.md#companionapp",
            "The viewer in the runtime": "agents/runtime.md#html-viewer",
        },
    },
    "Stand-ins and terminals": {
        "modules": ["temp_ui", "console_io", "assistant_view"],  # echo_orchestrator: its docs.toml
        "related": {
            "What runs": "agents/runtime.md#what-runs",
            "The temp UI in the runtime": "agents/runtime.md#temp-ui",
            "AgentActivity (API)": "api/agents.md#agentactivity",
        },
    },
}


TAB_KEYS = {"modules", "pages", "related"}
# A module that carries its own docs (src/assistant/modules/<id>/docs/, see app_kit.module_docs) is
# found here by folder: its pages publish to docs/html/modules/<id>/ (Markdown rendered, HTML and
# images copied as written) and its tab comes from its docs.toml. Every page is in the standard
# layout: its three standard pages (overview, architecture, tools; the tools page generated from its
# menu) first, in its own sidebar group, and its HTML pages open inside the standard frame. It needs
# no MODULE_TABS entry and no docs/modules/<id>.md; those stay for the central modules and the ones
# that haven't moved yet.
MODULES_DIR = ROOT / "src" / "assistant" / "modules"
FRAME = "frame.html"  # opens a module's own HTML page inside the docs' tabs and sidebar: frame.html?src=<page>


def tab_modules(name: str, spec: dict) -> list[str]:
    """The module ids a tab owns: its `modules`, or just the tab's name."""
    return spec.get("modules", [name])


@functools.cache
def module_doc_folders() -> dict[str, Path]:
    """Every module folder's own docs/ by module id, a docs-only folder with no code yet too."""
    return {p.name: (p / DOCS_DIR).resolve() for p in sorted(MODULES_DIR.iterdir())
            if p.is_dir() and not p.name.startswith(("_", ".")) and (p / DOCS_DIR).is_dir()}


def module_of(path: Path) -> str | None:
    """The module whose own docs folder holds `path`, else None."""
    p = path.resolve()
    return next((m for m, folder in module_doc_folders().items() if p.is_relative_to(folder)), None)


def docs_rel(path: Path) -> str:
    """A page as a path relative to docs/ (`../src/assistant/modules/<id>/docs/README.md` for a module's own)."""
    return Path(os.path.relpath(path, DOCS)).as_posix()


def module_pages(module_id: str) -> list[str]:
    """A module's pages, relative to docs/: its own docs folder's, else docs/modules/<id>.md."""
    folder = module_doc_folders().get(module_id)
    return [docs_rel(p) for p in doc_pages(folder)] if folder else [f"modules/{module_id}.md"]


def framed_pages(module_id: str) -> set[str]:
    """The names of a module's HTML pages: every one opens inside the standard frame."""
    folder = module_doc_folders().get(module_id)
    return {p.name for p in doc_pages(folder) if p.suffix.lower() == ".html"} if folder else set()


def module_tabs() -> dict[str, dict]:
    """MODULE_TABS, then each module with its own docs added to the tab its docs.toml names (default:
    its id); a tab no one named before comes after, in folder order."""
    tabs = {name: {**spec, "related": dict(spec.get("related", {}))} for name, spec in MODULE_TABS.items()}
    for module_id, folder in module_doc_folders().items():
        settings = docs_settings(folder)
        name = settings.get("tab", module_id)
        spec = tabs.setdefault(name, {"modules": [], "related": {}})
        spec["modules"] = list(dict.fromkeys(tab_modules(name, spec) + [module_id]))
        spec["related"].update(settings.get("related", {}))
    return tabs


MERMAID_JS = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"

MD_ANCHOR = re.compile(r'<a href="(?![a-z]+:)([^"#]*?\.md)(#[^"]*)?"([^>]*)>(.*?)</a>', re.S)
README_LINK = re.compile(r'\(([^)#]*?\.md)')


def is_next_steps(md: Path) -> bool:
    return md.resolve().is_relative_to((DOCS / NEXT_STEPS).resolve())


def out_path(md: Path) -> Path:
    module_id = module_of(md)
    if module_id:  # a module's own page: docs/html/modules/<id>/, README as index, HTML keeping its name
        rel = md.resolve().relative_to(module_doc_folders()[module_id])
        name = rel.name if rel.suffix.lower() == ".html" else "index.html" if rel.stem == "README" else f"{rel.stem}.html"
        return OUT / "modules" / module_id / rel.parent / name
    rel = md.resolve().relative_to(DOCS.resolve())
    name = "index.html" if rel.stem == "README" else f"{rel.stem}.html"
    if rel.parts[0] == NEXT_STEPS:
        return NEXT_OUT / Path(*rel.parts[1:-1]) / name
    return OUT / rel.parent / name


def out_root(md: Path) -> Path:
    return NEXT_OUT if is_next_steps(md) else OUT


def title_of(md: Path) -> str:
    return page_title(md)


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


def link(root: Path, rel: str) -> str:
    """A docs page (`architecture/voice.md#anchor`) as a link relative to the output root `root`."""
    path, _, anchor = rel.partition("#")
    href = Path(os.path.relpath(out_path(DOCS / path), root)).as_posix()
    return href + (f"#{anchor}" if anchor else "")


def item(root: Path, rel: str, name: str | None = None) -> dict:
    return {"name": name or title_of(DOCS / rel.partition("#")[0]), "href": link(root, rel)}


def framed_href(root: Path, rel: str) -> str:
    """The link that opens a module's HTML page inside the frame, relative to the output root `root`."""
    frame = Path(os.path.relpath(OUT / FRAME, root)).as_posix()
    return f"{frame}?src={Path(os.path.relpath(out_path(DOCS / rel), OUT)).as_posix()}"


def nav_item(root: Path, rel: str) -> dict:
    """A module page's sidebar link: a standard page under its standard name, an HTML page through the frame."""
    module_id = module_of(DOCS / rel)
    entry = item(root, rel, STANDARD_PAGES.get(Path(rel).name) if module_id else None)
    if module_id and Path(rel).name in framed_pages(module_id):
        entry["href"] = framed_href(root, rel)
    return entry


def check_module_tabs() -> None:
    """Every module page is in exactly one tab, every page a tab names exists, and a module's own docs
    folder is valid (known docs.toml keys, its listed pages there) and is its only layout."""
    pages = {p.stem for p in (DOCS / "modules").glob("*.md") if p.stem != "README"}
    own = module_doc_folders()
    listed = {m for name, spec in MODULE_TABS.items() for m in tab_modules(name, spec)}
    problems = [f"{m}: has both docs/modules/{m}.md and its own docs folder; keep one" for m in sorted(pages & set(own))]
    problems += [f"MODULE_TABS: {m} has its own docs folder; its docs.toml sets its tab" for m in sorted(listed & set(own))]
    problems += [f"{m} is a central module: its docs stay in docs/modules/{m}.md, not its own folder"
                 for m in sorted(CENTRAL_MODULES & set(own))]
    problems += [f"{m} is a central module and needs docs/modules/{m}.md" for m in sorted(CENTRAL_MODULES - pages)]
    for m, folder in own.items():
        where = f"src/assistant/modules/{m}/{DOCS_DIR}"
        try:
            settings = docs_settings(folder)
        except tomllib.TOMLDecodeError as exc:
            problems.append(f"{where}/{SETTINGS_FILE}: {exc}")
            continue
        problems += [f"{where}/{SETTINGS_FILE}: unknown keys {sorted(extra)}" for extra in [set(settings) - SETTINGS_KEYS] if extra]
        names = {p.name for p in doc_pages(folder)}
        problems += [f"{where} has no {p} (every module has the standard pages: {', '.join(STANDARD_PAGES)})"
                     for p in STANDARD_PAGES if p not in names]
        problems += [f"{where}/{SETTINGS_FILE}: page {n} not found" for n in settings.get("pages", []) if n not in names]
        problems += [f"{where}/{SETTINGS_FILE}: related {r} not found" for r in settings.get("related", {}).values()
                     if not (DOCS / r.partition("#")[0]).is_file()]
    if problems:
        raise SystemExit("\n".join(problems))
    owned = [m for name, spec in module_tabs().items() for m in tab_modules(name, spec)]
    problems = [f"docs/modules/{m}.md has no entry in MODULE_TABS" for m in sorted(pages - set(owned))]
    problems += [f"MODULE_TABS: {m} is in more than one tab" for m in sorted({m for m in owned if owned.count(m) > 1})]
    for name, spec in MODULE_TABS.items():
        problems += [f"MODULE_TABS['{name}']: {m} has no docs/modules/{m}.md" for m in tab_modules(name, spec) if m not in pages]
        problems += [f"MODULE_TABS['{name}']: unknown keys {sorted(extra)}" for extra in [set(spec) - TAB_KEYS] if extra]
        refs = spec.get("pages", []) + list(spec.get("related", {}).values())
        problems += [f"MODULE_TABS['{name}']: {r} not found" for r in refs if not (DOCS / r.partition("#")[0]).is_file()]
    if problems:
        raise SystemExit("\n".join(problems))


def nav_data(root: Path) -> dict:
    """The tabs and each tab's sidebar, with links relative to the output root `root`.

    Each tab lists its `home` pages: on those pages it is the active tab.
    """
    claimed = {p for spec in MODULE_TABS.values() for p in spec.get("pages", [])}
    groups = []
    for section, label in OVERVIEW.items():
        rels = [p.relative_to(DOCS).as_posix() for p in section_pages(section)]
        rels = [r for r in rels if r not in claimed]
        if LIBRARY in rels:
            rels.insert(rels.index(LIBRARY) + 1, MODULE_INDEX)
        names = {r: "Overview" for r in rels if r.endswith("/README.md") and r != MODULE_INDEX}
        groups.append({"label": label, "pages": [item(root, r, names.get(r)) for r in rels]})
    tabs = [_tab("Overview", groups)]
    for i, (name, spec) in enumerate(module_tabs().items()):
        # A module with its own docs gets its own group (overview, architecture, tools, then its other
        # pages); the tab's own group holds the modules that haven't moved, and is left out when empty.
        mods, moved = tab_modules(name, spec), module_doc_folders()
        old = [nav_item(root, r) for m in mods if m not in moved for r in module_pages(m)]
        old += [item(root, r) for r in spec.get("pages", [])]
        mod_groups = [{"label": name, "pages": old}] if old else []
        mod_groups += [{"label": m, "pages": [nav_item(root, r) for r in module_pages(m)]} for m in mods if m in moved]
        own = [p for g in mod_groups for p in g["pages"]]
        if spec.get("related"):
            mod_groups.append({"label": "Related", "pages": [item(root, r, n) for n, r in spec["related"].items()]})
        app_wide = [item(root, "architecture/README.md", "Architecture overview"), item(root, LIBRARY)]
        mod_groups.append({"label": "App-wide", "pages": app_wide})
        tabs.append(_tab(name, mod_groups, home=[p["href"] for p in own], sep=i == 0))
    for i, (name, section) in enumerate(PROJECT_TABS.items()):
        rels = [p.relative_to(DOCS).as_posix() for p in section_pages(section)]
        pages = [item(root, r, "Overview" if r.endswith("/README.md") else None) for r in rels]
        tabs.append(_tab(name, [{"label": name, "pages": pages}], sep=i == 0))
    if root == NEXT_OUT:  # the main docs have no Next steps tab; only the next-steps output does
        next_pages = [p.relative_to(DOCS).as_posix() for p in section_pages(NEXT_STEPS)]
        next_items = [item(root, r, "Overview" if r.endswith("/README.md") else None) for r in next_pages]
        next_items.append(item(root, f"{ARCHIVE}/README.md", "Archive"))  # its notes stay out of the sidebar
        archived = [link(root, p.relative_to(DOCS).as_posix()) for p in section_pages(ARCHIVE)]
        home = [p["href"] for p in next_items] + [h for h in archived if h not in {p["href"] for p in next_items}]
        tabs.append(_tab("Next steps", [{"label": "Next steps", "pages": next_items}], home=home, sep=True))
    return {"tabs": tabs}


def _tab(name: str, groups: list[dict], home: list[str] | None = None, sep: bool = False) -> dict:
    """A tab: it opens its first page; by default every sidebar page is home."""
    pages = [p["href"] for g in groups for p in g["pages"]]
    return {"name": name, "href": (home or pages)[0], "home": home or pages, "sep": sep, "groups": groups}


def fix_links(body: str, md: Path) -> str:
    """Point `.md` links at their generated pages; links from the main docs into next steps become plain text."""
    here = out_path(md).parent

    def repl(match: re.Match) -> str:
        link, anchor, attrs, text = match.groups()
        target = (md.parent / link).resolve()
        inside_docs = target.is_relative_to(DOCS.resolve()) or module_of(target) is not None
        if inside_docs and is_next_steps(target) and not is_next_steps(md):
            return text
        # Docs pages go to their generated page; anything else (a skill, say) to the Markdown file itself.
        dest = out_path(target) if inside_docs else target
        href = Path(os.path.relpath(dest, here)).as_posix()
        return f'<a href="{href}{anchor or ""}"{attrs}>{text}</a>'

    return MD_ANCHOR.sub(repl, body)


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
    body = fix_links(converter.convert(add_block_spacing(md.read_text(encoding="utf-8"))), md)
    # `\|` escapes a pipe inside a table cell; GitHub drops the backslash, Python-Markdown keeps it in code.
    body = body.replace("\\|", "|")
    target = out_path(md)
    root = out_root(md)
    up = Path(os.path.relpath(root, target.parent)).as_posix()
    return PAGE.format(
        title=html.escape(title_of(md)),
        root="" if up == "." else up + "/",
        page=target.relative_to(root).as_posix(),
        body=body,
        source=md.relative_to(ROOT).as_posix(),
        mermaid=MERMAID_JS,
    )


def write_pages(sections) -> int:
    count = 0
    for section in sections:
        for md in section_pages(section):
            target = out_path(md)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(render(md), encoding="utf-8")
            count += 1
    return count


def write_shared(root: Path) -> None:
    """The files every page of one output shares: styling, scripts, the tabs and the sidebar."""
    (root / "site.css").write_text(SITE_CSS, encoding="utf-8")
    (root / "site.js").write_text(SITE_JS, encoding="utf-8")
    nav = json.dumps(nav_data(root), indent=2, ensure_ascii=False)
    (root / "nav.js").write_text(NAV_JS.replace("NAV_DATA", nav), encoding="utf-8")


def copy_images(sections) -> None:
    """Copy each section's img/ folder (diagrams drawn by hand, as SVG) next to its pages."""
    for section in sections:
        src = DOCS / section / "img"
        if src.is_dir():
            shutil.copytree(src, OUT / section / "img")


def write_module_pages() -> int:
    """Each module's own docs into docs/html/modules/<id>/: Markdown rendered, everything else (the
    HTML pages it wrote itself, images) copied as written. Returns the number of pages."""
    count = 0
    for module_id, folder in module_doc_folders().items():
        shutil.copytree(folder, OUT / "modules" / module_id, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("*.md", SETTINGS_FILE))
        for page in doc_pages(folder):
            if page.suffix.lower() == ".md":
                target = out_path(page)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(render(page), encoding="utf-8")
            count += 1
    return count


LIBRARY_START = "<!-- library:start (generated from the manifests and menus by scripts/build_docs.py; don't edit) -->"
LIBRARY_END = "<!-- library:end -->"
CORE_LINE = (
    "The core itself handles the [module control](../api/control.md) commands (`ListModules`, `ActivateModule`, "
    "`DeactivateModule`, `ReloadModule`, `AddModule`), routes `InvokeTool` to the module whose menu has the item, "
    "and publishes `ModuleStateChanged`."
)


def module_classes() -> list[type]:
    """Each module folder's module class (its manifest id is the folder name), in the
    default config's `modules.enabled` order, then the modules that are off by name."""
    import importlib
    import tomllib

    from assistant.contracts import ModuleProtocol

    folder = ROOT / "src" / "assistant" / "modules"
    found = {}
    for package in sorted(p.name for p in folder.iterdir() if (p / "__init__.py").is_file()):
        mod = importlib.import_module(f"assistant.modules.{package}")
        classes = [c for c in vars(mod).values() if isinstance(c, type) and issubclass(c, ModuleProtocol)
                   and c is not ModuleProtocol and getattr(c, "manifest", None) and c.manifest.id == package]
        if len(classes) != 1:
            raise SystemExit(f"assistant.modules.{package} must export one module class with manifest id {package!r}")
        found[package] = classes[0]
    enabled = tomllib.loads((ROOT / "config" / "default.toml").read_text(encoding="utf-8"))["modules"]["enabled"]
    order = [m for m in enabled if m in found] + [m for m in found if m not in enabled]
    return [found[m] for m in order]


def library_block() -> str:
    """The module library's table, generated from every module's manifest and menu."""
    import tomllib

    enabled = tomllib.loads((ROOT / "config" / "default.toml").read_text(encoding="utf-8"))["modules"]["enabled"]

    def names(items) -> str:
        return ", ".join(f"`{getattr(i, '__name__', i)}`" for i in items) or "none"

    rows = [
        "| Module | What it does | On | Menu | Contracts | Handles | Calls | Publishes | Listens to |",
        "|--------|--------------|----|------|-----------|---------|-------|-----------|------------|",
    ]
    for cls in module_classes():
        m = cls.manifest
        contracts = "; ".join(f"{word} {names(group)}" for word, group in
                              (("provides", m.provides), ("requires", m.requires), ("optional", m.optional),
                               ("uses", m.uses)) if group)
        menu = names(cls.menu.names()) if cls.menu else "none"
        own = module_doc_folders().get(m.id)
        page = (f"../../src/assistant/modules/{m.id}/{DOCS_DIR}/README.md" if own and (own / "README.md").is_file()
                else f"../modules/{m.id}.md")
        rows.append(
            f"| [`{m.id}`]({page}) | {m.description or '(no description)'} | "
            f"{'yes' if m.id in enabled else 'no'} | {menu} | {contracts or 'none'} | {names(m.handles)} | "
            f"{names(m.sends)} | {names(m.publishes)} | {names(m.listens)} |"
        )
    return "\n".join([LIBRARY_START, "", *rows, "", CORE_LINE, "", LIBRARY_END])


def write_library() -> bool:
    """Rewrite the table between the module library's markers. True if it changed."""
    path = DOCS / LIBRARY
    text = path.read_text(encoding="utf-8")
    start, end = text.index("<!-- library:start"), text.index(LIBRARY_END) + len(LIBRARY_END)
    new = text[:start] + library_block() + text[end:]
    if new != text:
        path.write_text(new, encoding="utf-8")
    return new != text


def write_tools_pages() -> list[str]:
    """Each module's tools page (docs/tools.md in its own folder) from its own menu, so it is always
    right and the core's `modules.docs` lists it too; notes after the generated part are kept.
    Returns the ids whose page changed."""
    classes = {c.manifest.id: c for c in module_classes()}
    changed = []
    for module_id, folder in module_doc_folders().items():
        cls = classes.get(module_id)
        specs = None if cls is None else [s.model_dump() for s in (cls.menu.specs() if cls.menu else [])]
        path = folder / TOOLS_FILE
        old = path.read_text(encoding="utf-8") if path.is_file() else ""
        new = tools_page(module_id, specs, tools_notes(old), tools_intro(old))
        if new != old:
            with path.open("w", encoding="utf-8", newline="\n") as f:
                f.write(new)
            changed.append(module_id)
    return changed


def main() -> None:
    for module_id in write_tools_pages():
        print(f"Regenerated the tools page of {module_id}")
    check_module_tabs()
    if write_library():
        print(f"Regenerated the module table in docs/{LIBRARY}")
    for folder in (OUT, NEXT_OUT):
        if folder.exists():
            shutil.rmtree(folder)
    count = write_pages(SECTIONS)
    copy_images(SECTIONS)
    count += write_module_pages()
    write_shared(OUT)
    (OUT / "index.html").write_text(REDIRECT, encoding="utf-8")
    (OUT / FRAME).write_text(FRAME_PAGE, encoding="utf-8")
    # The next-steps README becomes that output's index.html.
    next_count = write_pages([NEXT_STEPS, ARCHIVE])
    write_shared(NEXT_OUT)
    print(f"Wrote {count} pages to {OUT.relative_to(ROOT).as_posix()}/ (open docs/html/index.html)")
    print(f"Wrote {next_count} pages to {NEXT_OUT.relative_to(ROOT).as_posix()}/ (open docs/html-next-steps/index.html)")


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
<link rel="stylesheet" href="{root}site.css">
</head>
<body>
<div class="layout">
<nav data-root="{root}" data-page="{page}"></nav>
<main>
{body}
<footer>Generated from <code>{source}</code>. Edit the Markdown, then run <code>python scripts/build_docs.py</code>.</footer>
</main>
</div>
<script src="{root}nav.js"></script>
<script src="{mermaid}"></script>
<script src="{root}site.js"></script>
</body>
</html>
"""

FRAME_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Assistant Docs</title>
<!-- Generated by scripts/build_docs.py: a module's own HTML page (?src=) inside the docs' menu. -->
<link rel="stylesheet" href="site.css">
</head>
<body>
<div class="layout">
<nav data-root="" data-page="frame.html"></nav>
<main class="framed"><iframe title="Module page"></iframe></main>
</div>
<script>
(function () {
  // Only a page of these docs: a relative path to an .html file, with no "..", no scheme, no leading slash.
  var src = new URLSearchParams(location.search).get("src") || "";
  var ok = /^[A-Za-z0-9_\\-.\\/]+\\.html$/.test(src) && src.charAt(0) !== "/" && src.split("/").indexOf("..") < 0;
  var main = document.querySelector("main");
  if (!ok) { main.className = ""; main.textContent = "This page can't be opened in the frame: " + src; return; }
  document.querySelector("nav").setAttribute("data-page", "frame.html?src=" + src);
  var frame = main.querySelector("iframe");
  frame.addEventListener("load", function () {
    try { document.title = frame.contentDocument.title || src; } catch (e) {}
  });
  frame.src = src;
})();
</script>
<script src="nav.js"></script>
</body>
</html>
"""

NAV_JS = """// The tab strip and the sidebar for every page, generated by scripts/build_docs.py. Edit the Markdown, not this file.
(function () {
  var NAV = NAV_DATA;
  var nav = document.querySelector("nav[data-page]");
  if (!nav) return;
  var root = nav.getAttribute("data-root"), page = nav.getAttribute("data-page");
  function link(p) {
    var a = document.createElement("a");
    a.href = root + p.href;
    a.textContent = p.name;
    if (p.href === page) a.setAttribute("aria-current", "page");
    return a;
  }
  function headings() {
    var ul = document.createElement("ul");
    ul.className = "toc";
    document.querySelectorAll("main h2[id]").forEach(function (h) {
      var a = document.createElement("a");
      a.href = "#" + h.id;
      a.textContent = h.textContent;
      var li = document.createElement("li");
      li.appendChild(a);
      ul.appendChild(li);
    });
    return ul;
  }
  // The active tab is the one this page belongs to.
  var tab = NAV.tabs.filter(function (t) { return t.home.indexOf(page) >= 0; })[0] || NAV.tabs[0];
  // Tabs across the top, one per area; the strip scrolls sideways when it doesn't fit.
  var bar = document.createElement("div"), current = null;
  bar.className = "topbar";
  NAV.tabs.forEach(function (t) {
    if (t.sep) {
      var s = document.createElement("span");
      s.className = "sep";
      bar.appendChild(s);
    }
    var a = link(t);
    if (t === tab) { a.classList.add("active"); current = a; }
    bar.appendChild(a);
  });
  document.body.insertBefore(bar, document.body.firstChild);
  if (current) bar.scrollLeft = current.offsetLeft - (bar.clientWidth - current.offsetWidth) / 2;
  // The sidebar: only the active tab's pages; the page you're on also lists its headings.
  tab.groups.forEach(function (g) {
    var h = document.createElement("h2");
    h.textContent = g.label;
    var ul = document.createElement("ul");
    g.pages.forEach(function (p) {
      var li = document.createElement("li");
      li.appendChild(link(p));
      if (p.href === page) li.appendChild(headings());
      ul.appendChild(li);
    });
    nav.appendChild(h);
    nav.appendChild(ul);
  });
})();
"""

SITE_CSS = """/* Styling for every page, generated by scripts/build_docs.py. */
:root {
  --bg: #fbfbfa; --panel: #f2f1ee; --text: #1f2328; --muted: #5d6470;
  --border: #dedcd6; --accent: #2f62c8; --code-bg: #ecebe6;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #16181c; --panel: #1d2025; --text: #e6e6e3; --muted: #9aa1ab;
    --border: #30343b; --accent: #82aaff; --code-bg: #23272e;
  }
}
:root[data-theme="dark"] {
  --bg: #16181c; --panel: #1d2025; --text: #e6e6e3; --muted: #9aa1ab;
  --border: #30343b; --accent: #82aaff; --code-bg: #23272e;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--text);
  font: 16px/1.6 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}
:root { --top: 42px; }
.topbar {
  position: sticky; top: 0; z-index: 5; height: var(--top); display: flex; flex-wrap: nowrap; align-items: flex-end;
  gap: 2px; padding: 0 12px; overflow-x: auto; overflow-y: hidden; scrollbar-width: thin;
  background: var(--panel); border-bottom: 1px solid var(--border);
}
.topbar a {
  flex: none; white-space: nowrap; padding: 6px 12px; border: 1px solid transparent; border-bottom: 0;
  border-radius: 6px 6px 0 0; color: var(--muted); text-decoration: none; font-size: 14px;
}
.topbar a:hover { background: var(--border); color: var(--text); }
.topbar a.active { background: var(--bg); border-color: var(--border); color: var(--text); font-weight: 600; margin-bottom: -1px; }
.topbar .sep { flex: none; align-self: center; width: 1px; height: 20px; margin: 0 6px; background: var(--border); }
.layout { display: grid; grid-template-columns: 250px minmax(0, 1fr); min-height: calc(100vh - var(--top)); }
nav {
  background: var(--panel); border-right: 1px solid var(--border);
  padding: 24px 16px; position: sticky; top: var(--top); height: calc(100vh - var(--top)); overflow-y: auto;
}
nav ul.toc { margin: 2px 0 6px; }
nav ul.toc a { padding: 3px 8px 3px 20px; font-size: 13px; color: var(--muted); }
nav h2 { font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin: 20px 8px 6px; }
nav h2:first-child { margin-top: 0; }
nav ul { list-style: none; margin: 0; padding: 0; }
nav a { display: block; padding: 5px 8px; border-radius: 6px; color: var(--text); text-decoration: none; font-size: 14px; }
nav a:hover { background: var(--border); }
nav a[aria-current="page"] { background: var(--accent); color: var(--bg); }
main { padding: 32px 40px 64px; max-width: 980px; width: 100%; }
h1 { font-size: 2rem; line-height: 1.2; margin: 0 0 16px; }
h2 { font-size: 1.4rem; margin: 40px 0 12px; padding-bottom: 6px; border-bottom: 1px solid var(--border); }
h3 { font-size: 1.1rem; margin: 28px 0 8px; }
a { color: var(--accent); }
code { font: 0.88em ui-monospace, "Cascadia Code", Consolas, monospace; background: var(--code-bg); padding: 1px 5px; border-radius: 4px; }
pre { background: var(--code-bg); padding: 14px 16px; border-radius: 8px; overflow-x: auto; }
pre code { background: none; padding: 0; }
table { display: block; overflow-x: auto; border-collapse: collapse; margin: 12px 0 20px; font-size: 14px; }
th, td { border: 1px solid var(--border); padding: 7px 11px; text-align: left; vertical-align: top; }
th { background: var(--panel); }
main img { max-width: 100%; height: auto; border: 1px solid var(--border); border-radius: 10px; }
.diagram {
  background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
  padding: 20px; margin: 16px 0 24px; overflow-x: auto; text-align: center;
}
.diagram svg { max-width: 100%; height: auto; }
.diagram.offline { text-align: left; white-space: pre; font: 13px ui-monospace, Consolas, monospace; }
.diagram:not(.offline), main img { cursor: zoom-in; }
.zoom { position: fixed; inset: 0; z-index: 10; background: var(--bg); overflow: hidden; cursor: grab; touch-action: none; }
.zoom.dragging { cursor: grabbing; }
.zoom-stage { position: absolute; left: 0; top: 0; transform-origin: 0 0; }
.zoom-stage svg, .zoom-stage img { display: block; max-width: none !important; }
.zoom-stage img { border: 0; user-select: none; -webkit-user-drag: none; }
.zoom-close {
  position: absolute; top: 12px; left: 12px; z-index: 1; width: 40px; height: 40px;
  border: 1px solid var(--border); border-radius: 8px; background: var(--panel); color: var(--text);
  font-size: 22px; line-height: 1; cursor: pointer;
}
.zoom-close:hover { background: var(--border); }
main.framed { max-width: none; padding: 0; }
main.framed iframe { display: block; width: 100%; height: calc(100vh - var(--top)); border: 0; background: #fff; }
footer { margin-top: 48px; color: var(--muted); font-size: 13px; }
@media (max-width: 760px) {
  .layout { grid-template-columns: 1fr; }
  nav { position: static; height: auto; border-right: 0; border-bottom: 1px solid var(--border); padding: 16px; }
  nav ul { display: flex; flex-wrap: wrap; gap: 4px; }
  main { padding: 20px 16px 48px; }
}
"""

SITE_JS = """// Diagrams for every page, generated by scripts/build_docs.py.
(function () {
  var blocks = document.querySelectorAll("pre > code.language-mermaid");
  blocks.forEach(function (code) {
    var div = document.createElement("div");
    div.className = "diagram";
    div.textContent = code.textContent;
    code.parentElement.replaceWith(div);
  });
  if (!window.mermaid) {
    // Offline: show the diagram source instead.
    document.querySelectorAll(".diagram").forEach(function (d) { d.classList.add("offline"); });
    return;
  }
  var dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  mermaid.initialize({ startOnLoad: false, theme: dark ? "dark" : "neutral", securityLevel: "strict" });
  mermaid.run({ querySelector: ".diagram" });

})();

// Click a diagram or an image to view it full screen: wheel zooms at the cursor, drag pans,
// X or Esc closes; for an image, a click outside it closes too. Runs offline as well.
(function () {
  var overlay = null, stage, scale, x, y;
  function place() { stage.style.transform = "translate(" + x + "px," + y + "px) scale(" + scale + ")"; }
  function close() {
    if (!overlay) return;
    overlay.remove();
    overlay = null;
    document.body.style.overflow = "";
  }
  function open(el) {
    var w, h, clone = el.cloneNode(true), isImg = el.tagName === "IMG";
    if (isImg) {
      var r = el.getBoundingClientRect();
      w = el.naturalWidth || r.width;
      h = el.naturalHeight || r.height;
      clone.removeAttribute("width");
      clone.removeAttribute("height");
      clone.style.width = w + "px";
      clone.style.height = h + "px";
      clone.draggable = false;
    } else {
      var box = el.viewBox.baseVal;
      w = box && box.width ? box.width : el.getBBox().width;
      h = box && box.height ? box.height : el.getBBox().height;
      clone.removeAttribute("style");
      clone.setAttribute("width", w);
      clone.setAttribute("height", h);
    }
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
    overlay.addEventListener("wheel", function (e) {
      e.preventDefault();
      var f = Math.exp(-e.deltaY * 0.0015), s = Math.min(40, Math.max(0.05, scale * f));
      f = s / scale;
      x = e.clientX - (e.clientX - x) * f;
      y = e.clientY - (e.clientY - y) * f;
      scale = s;
      place();
    }, { passive: false });
    var drag = null, outside = false;
    overlay.addEventListener("pointerdown", function (e) {
      if (e.target === btn) return;
      drag = { px: e.clientX, py: e.clientY, x: x, y: y, inside: clone.contains(e.target), moved: false };
      overlay.setPointerCapture(e.pointerId);
      overlay.classList.add("dragging");
    });
    overlay.addEventListener("pointermove", function (e) {
      if (!drag) return;
      if (Math.abs(e.clientX - drag.px) + Math.abs(e.clientY - drag.py) > 4) drag.moved = true;
      x = drag.x + e.clientX - drag.px;
      y = drag.y + e.clientY - drag.py;
      place();
    });
    overlay.addEventListener("pointerup", function () {
      // A click (no drag) outside an image closes it; diagrams keep closing only by X or Esc.
      outside = isImg && drag !== null && !drag.inside && !drag.moved;
      drag = null;
      overlay.classList.remove("dragging");
    });
    overlay.addEventListener("click", function (e) {
      if (!outside) return;
      outside = false;
      e.stopPropagation();
      close();
    });
  }
  document.addEventListener("click", function (e) {
    if (overlay || !e.target.closest) return;
    var img = e.target.closest("main img");
    if (img) {
      e.preventDefault(); // the image's link would open the bare file, with no way back
      open(img);
      return;
    }
    var d = e.target.closest(".diagram");
    var svg = d && d.querySelector("svg");
    if (svg) open(svg);
  });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") close(); });
})();
"""


if __name__ == "__main__":
    main()
