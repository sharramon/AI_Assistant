"""Every module has its own docs page, a row in the generated module library, and a docs tab.

A module's page is in one of two layouts while the modules move: its own folder
(src/assistant/modules/<id>/docs/, found by folder) or the older docs/modules/<id>.md.
"""

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULES = ROOT / "src" / "assistant" / "modules"
PAGES = ROOT / "docs" / "modules"
LIBRARY = ROOT / "docs" / "architecture" / "module-library.md"


def module_ids() -> list[str]:
    return sorted(p.name for p in MODULES.iterdir() if (p / "__init__.py").is_file())


def build_docs():
    spec = importlib.util.spec_from_file_location("build_docs", ROOT / "scripts" / "build_docs.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def own_docs(module_id: str) -> bool:
    return (MODULES / module_id / "docs").is_dir()


def test_every_module_has_a_docs_tab_whose_pages_exist():
    docs = build_docs()
    owner = {m: name for name, spec in docs.module_tabs().items() for m in docs.tab_modules(name, spec)}
    assert set(module_ids()) <= set(owner), "every module needs a tab: its docs.toml, or MODULE_TABS in build_docs.py"
    docs.check_module_tabs()  # raises SystemExit naming a missing page, a module in two tabs or in both layouts
    tabs = {t["name"]: t for t in docs.nav_data(docs.OUT)["tabs"]}
    for module_id in module_ids():
        page = f"modules/{module_id}/index.html" if own_docs(module_id) else f"modules/{module_id}.html"
        assert page in tabs[owner[module_id]]["home"], f"no tab owns {module_id}'s page"
    assert list(tabs)[0] == "Overview" and "Next steps" not in tabs


def test_main_docs_never_link_into_next_steps():
    docs = build_docs()
    for tab in docs.nav_data(docs.OUT)["tabs"]:
        hrefs = [p["href"] for g in tab["groups"] for p in g["pages"]] + [tab["href"]]
        assert not [h for h in hrefs if "html-next-steps" in h], f"{tab['name']} links into next steps"
        assert "Change notes" not in [g["label"] for g in tab["groups"]]
    assert all("notes" not in spec for spec in docs.MODULE_TABS.values())
    pages = [md for section in docs.SECTIONS for md in (docs.DOCS / section).rglob("*.md")]
    pages += [md for folder in docs.module_doc_folders().values() for md in folder.rglob("*.md")]
    for md in pages:
        links = re.findall(r"\]\(([^)\s]*next-steps/[^)\s]*)\)", md.read_text(encoding="utf-8"))
        assert not links, f"{md.relative_to(ROOT)} links into docs/next-steps/: {links}"


def test_the_next_steps_output_keeps_its_tab():
    docs = build_docs()
    tabs = [t["name"] for t in docs.nav_data(docs.NEXT_OUT)["tabs"]]
    assert tabs[0] == "Overview" and tabs[-1] == "Next steps"


NOTE_LINK = re.compile(r"\]\(([^)\s]+)\)")


def test_every_link_between_notes_resolves():
    notes = ROOT / "docs" / "next-steps"
    broken = []
    for md in notes.rglob("*.md"):
        for target in NOTE_LINK.findall(md.read_text(encoding="utf-8")):
            path = target.partition("#")[0]
            if not path or "://" in target or target.startswith("mailto:"):
                continue
            if not (md.parent / path).exists():
                broken.append(f"{md.relative_to(ROOT).as_posix()} -> {target}")
    assert not broken, "broken links in docs/next-steps:\n" + "\n".join(broken)


def test_the_archive_is_linked_once_and_its_notes_stay_out_of_the_sidebar():
    docs = build_docs()
    tab = docs.nav_data(docs.NEXT_OUT)["tabs"][-1]
    hrefs = [p["href"] for g in tab["groups"] for p in g["pages"]]
    assert hrefs.count("archive/index.html") == 1
    archived = sorted((docs.DOCS / docs.ARCHIVE).glob("*.md"))
    assert archived, "docs/next-steps/archive/ has no notes"
    for md in archived:
        href = f"archive/{'index' if md.stem == 'README' else md.stem}.html"
        assert href in tab["home"], f"{href} doesn't open the Next steps tab"
        if md.stem != "README":
            assert href not in hrefs, f"{href} is listed in the Next steps sidebar"
            assert not (docs.DOCS / docs.NEXT_STEPS / md.name).exists(), f"{md.name} is in both places"


def test_the_job_project_has_its_own_tab_in_both_outputs():
    docs = build_docs()
    assert docs.PROJECT_TABS["Job project"] in docs.SECTIONS
    for root in (docs.OUT, docs.NEXT_OUT):
        tabs = {t["name"]: t for t in docs.nav_data(root)["tabs"]}
        assert [h for h in tabs["Job project"]["home"] if h.endswith("job-project/index.html")]
        assert "html-next-steps" not in tabs["Job project"]["href"]


def test_a_tab_can_own_several_modules():
    docs = build_docs()
    assert docs.tab_modules("Agents", docs.MODULE_TABS["Agents"]) == ["talker", "main_assistant", "agent_hub", "task_agents", "job_search"]
    assert docs.tab_modules("voice_in", docs.MODULE_TABS["voice_in"]) == ["voice_in"]
    # A module with its own docs joins the tab its docs.toml names.
    assert "echo_orchestrator" in docs.module_tabs()["Stand-ins and terminals"]["modules"]


def test_every_module_has_a_page_linked_from_the_pages_list():
    index = (PAGES / "README.md").read_text(encoding="utf-8")
    for module_id in module_ids():
        if own_docs(module_id):
            assert (MODULES / module_id / "docs" / "README.md").is_file(), f"{module_id}/docs/README.md is missing"
            link = f"](../../src/assistant/modules/{module_id}/docs/README.md)"
        else:
            assert (PAGES / f"{module_id}.md").is_file(), f"docs/modules/{module_id}.md is missing"
            link = f"]({module_id}.md)"
        assert link in index, f"docs/modules/README.md doesn't link {module_id}"


def test_every_module_has_a_library_row():
    library = LIBRARY.read_text(encoding="utf-8")
    table = library.split("<!-- library:start", 1)[1].split("<!-- library:end", 1)[0]
    for module_id in module_ids():
        page = f"../../src/assistant/modules/{module_id}/docs/README.md" if own_docs(module_id) else f"../modules/{module_id}.md"
        assert f"| [`{module_id}`]({page}) |" in table, f"no library row for {module_id}"


def test_the_library_table_is_generated_from_the_manifests_and_menus():
    docs = build_docs()
    assert docs.library_block() in LIBRARY.read_text(encoding="utf-8"), (
        "the module library is stale: run scripts/build_docs.py"
    )
    assert [c.manifest.id for c in docs.module_classes()][:1] == ["console_io"]
    assert "`viewer.open`, `viewer.highlight`, `viewer.tabs`" in docs.library_block()
