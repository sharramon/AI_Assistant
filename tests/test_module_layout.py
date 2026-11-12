"""A module's own folder carries its config defaults (module.toml) and its docs (docs/): the core reads
them through the module's class (ctx.config, modules.docs), the docs build finds them by folder."""

import importlib
import uuid
from pathlib import Path

import pytest

from app_kit.module_docs import STANDARD_PAGES, doc_pages, page_title, tools_intro, tools_notes, tools_page
from assistant.contracts import InvokeTool, Status
from assistant.core import App
from tests.test_module_docs import ROOT, build_docs

MODULE = '''
from assistant.contracts import Manifest, ModuleProtocol


class Probe(ModuleProtocol):
    manifest = Manifest(id="probe")
    seen = None

    async def init(self, ctx):
        type(self).seen = dict(ctx.config)
'''


def probe(tmp_path: Path, monkeypatch, defaults: str | None, docs: dict[str, str] | None = None) -> type:
    """A module package written to tmp: its module.toml and docs/ pages as given."""
    name = f"probe_{uuid.uuid4().hex[:8]}"
    folder = tmp_path / name
    folder.mkdir()
    (folder / "__init__.py").write_text(MODULE, encoding="utf-8")
    if defaults is not None:
        (folder / "module.toml").write_text(defaults, encoding="utf-8")
    for page, text in (docs or {}).items():
        (folder / "docs").mkdir(exist_ok=True)
        (folder / "docs" / page).write_text(text, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    return importlib.import_module(name).Probe  # stays imported, like a real module (unique name per test)


def config(section: dict | None = None) -> dict:
    modules = {"enabled": ["probe"]} | ({"probe": section} if section is not None else {})
    return {"modules": modules, "core": {}}


async def started(cls: type, cfg: dict) -> App:
    app = App([cls], cfg)
    await app.start()
    return app


async def test_the_app_config_is_merged_over_the_modules_own_defaults(tmp_path, monkeypatch):
    cls = probe(tmp_path, monkeypatch, 'port = 1\nname = "a"\n[deep]\nx = 1\ny = 2\n')
    app = await started(cls, config({"port": 2, "deep": {"y": 3}}))
    await app.stop()
    assert cls.seen == {"port": 2, "name": "a", "deep": {"x": 1, "y": 3}}


async def test_with_no_module_toml_the_config_is_the_section(tmp_path, monkeypatch):
    cls = probe(tmp_path, monkeypatch, None)
    app = await started(cls, config({"port": 2}))
    await app.stop()
    assert cls.seen == {"port": 2}


async def test_modules_docs_gives_its_pages_in_order_with_titles(tmp_path, monkeypatch):
    cls = probe(tmp_path, monkeypatch, None, {
        "b.md": "# Second\n", "README.md": "# The probe\n", "a.html": "<title>A page</title>", "docs.toml": "",
    })
    app = await started(cls, config())
    try:
        listed = await app.router.send(InvokeTool(name="modules.docs", args={"module_id": "probe"}))
        assert [p["title"] for p in listed.value] == ["The probe", "A page", "Second"]
        unknown = await app.router.send(InvokeTool(name="modules.docs", args={"module_id": "nope"}))
        assert unknown.status is Status.INVALID_ARGUMENTS
    finally:
        await app.stop()


async def test_a_module_without_docs_lists_none(tmp_path, monkeypatch):
    app = await started(probe(tmp_path, monkeypatch, None), config())
    try:
        assert (await app.router.send(InvokeTool(name="modules.docs", args={"module_id": "probe"}))).value == []
    finally:
        await app.stop()


def test_page_titles_and_listed_order(tmp_path):
    (tmp_path / "x.html").write_text("<html><head><TITLE> Two\n words </TITLE>", encoding="utf-8")
    (tmp_path / "y.html").write_text("<p>no title</p>", encoding="utf-8")
    (tmp_path / "docs.toml").write_text('pages = ["y.html"]\n', encoding="utf-8")
    assert page_title(tmp_path / "x.html") == "Two words"
    assert page_title(tmp_path / "y.html") == "y"
    assert [p.name for p in doc_pages(tmp_path)] == ["y.html", "x.html"]


def test_a_modules_own_html_page_is_published_as_written(tmp_path, monkeypatch):
    docs = build_docs()
    folder = tmp_path / "src" / "docs"
    folder.mkdir(parents=True)
    (folder / "page.html").write_bytes(b"<title>Its own</title><p>as written</p>\r\n")
    (folder / "docs.toml").write_text("", encoding="utf-8")
    out = tmp_path / "out"
    monkeypatch.setattr(docs, "OUT", out)
    monkeypatch.setattr(docs, "module_doc_folders", lambda: {"probe": folder.resolve()})
    docs.write_module_pages()  # (Markdown rendering is covered by the real build: the moved modules' pages)
    assert (out / "modules" / "probe" / "page.html").read_bytes() == (folder / "page.html").read_bytes()
    assert not (out / "modules" / "probe" / "docs.toml").exists()


def test_every_html_page_opens_inside_the_standard_frame(tmp_path, monkeypatch):
    docs = build_docs()
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "page.html").write_text("<title>Framed</title>", encoding="utf-8")  # no setting needed
    (folder / "README.md").write_text("# Its overview\n", encoding="utf-8")
    monkeypatch.setattr(docs, "module_doc_folders", lambda: {"framed": folder.resolve()})
    entry = docs.nav_item(docs.OUT, docs.docs_rel(folder / "page.html"))
    assert entry == {"name": "Framed", "href": "frame.html?src=modules/framed/page.html"}
    assert docs.nav_item(docs.OUT, docs.docs_rel(folder / "README.md"))["name"] == "Overview"  # standard name
    assert 'indexOf("..") < 0' in docs.FRAME_PAGE  # the frame refuses pages outside the docs


def test_the_standard_pages_come_first_in_their_order(tmp_path):
    for name in ("a.html", "tools.md", "README.md", "architecture.md", "z.md"):
        (tmp_path / name).write_text("# x\n", encoding="utf-8")
    (tmp_path / "docs.toml").write_text('pages = ["z.md"]\n', encoding="utf-8")
    assert [p.name for p in doc_pages(tmp_path)] == ["README.md", "architecture.md", "tools.md", "z.md", "a.html"]


def test_a_tools_page_is_made_from_the_menu_and_keeps_its_notes():
    spec = {"name": "x.go", "description": "Go somewhere.",
            "input_schema": {"properties": {"to": {"type": "string", "description": "where"}}, "required": ["to"]}}
    page = tools_page("probe", [spec], "My notes.", "Read me first.")
    assert "## `x.go`" in page and "| `to` | string | yes | where |" in page
    assert tools_notes(page) == "My notes." and tools_intro(page) == "Read me first."
    assert tools_page("probe", [spec], tools_notes(page), tools_intro(page)) == page
    assert "no code" in tools_page("probe", None) and "No menu" in tools_page("probe", [])


def test_every_modules_tools_page_is_current():
    docs = build_docs()
    classes = {c.manifest.id: c for c in docs.module_classes()}
    for module_id, folder in docs.module_doc_folders().items():
        cls = classes.get(module_id)
        specs = None if cls is None else [s.model_dump() for s in (cls.menu.specs() if cls.menu else [])]
        text = (folder / "tools.md").read_text(encoding="utf-8")
        assert text == tools_page(module_id, specs, tools_notes(text), tools_intro(text)), \
            f"{module_id}: run scripts/build_docs.py"


def test_every_module_has_the_three_standard_pages():
    # Every module, the core ones too (user, 2026-11-12): no exemptions.
    docs = build_docs()
    folders = docs.module_doc_folders()
    ids = {c.manifest.id for c in docs.module_classes()} | set(folders)
    missing = {m: [p for p in STANDARD_PAGES if not (folders.get(m, ROOT / "-") / p).is_file()] for m in sorted(ids)}
    assert not {m: p for m, p in missing.items() if p}, "every module has overview, architecture and tools"


@pytest.mark.parametrize("settings, problem", [
    ('group = "core"\ncolour = "red"\n', "unknown keys ['colour']"),
    ('group = "core"\nframe = true\n', "unknown keys ['frame']"),  # every HTML page is framed; nothing to set
    ('group = "core"\npages = ["gone.md"]\n', "page gone.md not found"),
    ('group = "core"\n', "has no architecture.md"),
    ('', "group must be one of 'core', 'add-on', not None"),
    ('group = "extra"\n', "group must be one of 'core', 'add-on', not 'extra'"),
])
def test_the_build_refuses_a_bad_docs_toml(tmp_path, monkeypatch, settings, problem):
    docs = build_docs()
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "README.md").write_text("# Bad\n", encoding="utf-8")
    (folder / "docs.toml").write_text(settings, encoding="utf-8")
    monkeypatch.setattr(docs, "module_doc_folders", lambda: {"bad": folder.resolve()})
    with pytest.raises(SystemExit, match=problem.replace("[", r"\[").replace("]", r"\]")):
        docs.check_module_tabs()
