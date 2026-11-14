"""Every module has its own docs folder, a row in the generated module library, and a docs tab.

Every module's docs live in its own folder (src/assistant/modules/<id>/docs/, found by folder); its
docs.toml puts it in the core group or the add-ons (user, 2026-11-12).
"""

import importlib.util
import re
from pathlib import Path

from assistant.infra import module_folder, module_roots

ROOT = Path(__file__).resolve().parent.parent
MODULES = ROOT / "src" / "assistant" / "modules"
LIBRARY = ROOT / "docs" / "architecture" / "module-library.md"
CORE = {"agent_hub", "talker", "main_assistant", "temp_ui", "console_io", "task_agents", "usage", "voice_in",
        "assistant_view"}
ADD_ONS = {"cv", "job_search", "html_viewer", "voice_notes", "echo_orchestrator"}


def module_ids() -> list[str]:
    """Every module, in the repo and in the outside folders `[core] module_folders` names (the conftest adds them)."""
    return sorted(p.name for root in module_roots() for p in root.iterdir() if (p / "__init__.py").is_file())


def build_docs():
    spec = importlib.util.spec_from_file_location("build_docs", ROOT / "scripts" / "build_docs.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_module_has_a_docs_tab_whose_pages_exist():
    docs = build_docs()
    owner = {m: name for name, spec in docs.module_tabs().items() for m in docs.tab_modules(name, spec)}
    assert set(module_ids()) <= set(owner), "every module needs its own docs folder with a docs.toml"
    docs.check_module_tabs()  # raises SystemExit naming a missing page or folder, a bad group, a mixed tab
    tabs = {t["name"]: t for t in docs.nav_data(docs.OUT)["tabs"]}
    for module_id in module_ids():
        assert f"modules/{module_id}/index.html" in tabs[owner[module_id]]["home"], f"no tab owns {module_id}'s page"
    assert list(tabs)[0] == "Overview" and "Next steps" not in tabs


def test_the_main_docs_hold_no_module_pages():
    assert not (ROOT / "docs" / "modules").exists(), "module pages live in their module's docs/ folder"
    assert not (ROOT / "docs" / "job-project").exists(), "the job project is a page of job_search's docs"
    assert build_docs().SECTIONS == ("architecture", "agents", "api")


def test_every_module_is_in_its_group_and_the_core_tabs_come_first():
    docs = build_docs()
    groups = {m: docs.docs_settings(f).get("group") for m, f in docs.module_doc_folders().items()}
    assert {m for m, g in groups.items() if g == "core"} == CORE
    assert {m for m, g in groups.items() if g == "add-on"} == ADD_ONS
    order = [spec["group"] for spec in docs.module_tabs().values()]
    assert order == sorted(order, key=list(docs.GROUPS).index), "the core modules' tabs come before the add-ons'"
    seps = [t["name"] for t in docs.nav_data(docs.OUT)["tabs"] if t["sep"]]
    assert len(seps) == 2, "one separator before the core tabs, one before the add-ons"


def test_main_docs_never_link_into_next_steps():
    docs = build_docs()
    for tab in docs.nav_data(docs.OUT)["tabs"]:
        hrefs = [p["href"] for g in tab["groups"] for p in g["pages"]] + [tab["href"]]
        assert not [h for h in hrefs if "html-next-steps" in h], f"{tab['name']} links into next steps"
        assert "Change notes" not in [g["label"] for g in tab["groups"]]
    pages = [md for section in docs.SECTIONS for md in (docs.DOCS / section).rglob("*.md")]
    pages += [md for folder in docs.module_doc_folders().values() for md in folder.rglob("*.md")]
    # The one allowed link (the user's call, 2026-11-12): the overview's "Currently fixing" plan.
    allowed = {("docs/architecture/README.md", "../../html-next-steps/module-folders.html")}
    # The user allowed these for the Restructuring (2026-11-13; built the same day): only inside the
    # overview's "## Restructuring" section and the Pages list's one "- Restructuring (built ...)" bullet,
    # nowhere else in that file or any other page.
    restructuring = {"../../html-next-steps/core-and-hub-definition.html", "../next-steps/core-and-hub-definition.md",
                     "../../html-next-steps/piping.html", "../../html-next-steps/core-and-hub-proposal.html",
                     "../../html-next-steps/module-layouts.html", "../../html-next-steps/agent-claude-md-options.html",
                     "../next-steps/agent-claude-md-options.md"}
    link = re.compile(r"\]\(([^)\s]*next-steps/[^)\s]*)\)")
    for md in pages:
        name = md.relative_to(ROOT).as_posix()
        text = md.read_text(encoding="utf-8")
        links = []
        if name == "docs/architecture/README.md":
            section = re.search(r"^## Restructuring\n.*?(?=^## )", text, re.S | re.M)
            assert section, "the overview has no Restructuring section"
            links += [h for h in link.findall(section.group()) if h not in restructuring]
            text = text[:section.start()] + text[section.end():]
            bullet = re.search(r"^- Restructuring \(built [^)]*\):.*$", text, re.M)
            assert bullet, "the overview's Pages list has no Restructuring bullet"
            links += [h for h in link.findall(bullet.group()) if h not in restructuring]
            text = text[:bullet.start()] + text[bullet.end():]
        links += [h for h in link.findall(text) if (name, h) not in allowed]
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


def test_the_job_project_is_a_page_of_job_search_in_both_outputs():
    docs = build_docs()
    for root in (docs.OUT, docs.NEXT_OUT):
        tabs = {t["name"]: t for t in docs.nav_data(root)["tabs"]}
        assert [h for h in tabs["job_search"]["home"] if h.endswith("modules/job_search/job-project.html")]
        assert "html-next-steps" not in tabs["job_search"]["href"]


def test_a_tab_can_own_several_modules():
    docs = build_docs()
    tabs = docs.module_tabs()
    assert tabs["Agents"]["modules"] == ["agent_hub", "main_assistant", "talker", "task_agents", "usage"]
    assert tabs["Terminals and temp UI"]["modules"] == ["assistant_view", "console_io", "temp_ui"]
    assert tabs["voice_in"]["modules"] == ["voice_in"]  # no `tab`: named after its id
    # The tab's Related links are its modules' own `related`, merged.
    assert "Agents (architecture)" in tabs["Agents"]["related"] and "UsageLedger (API)" in tabs["Agents"]["related"]


def test_every_module_has_a_library_row():
    library = LIBRARY.read_text(encoding="utf-8")
    table = library.split("<!-- library:start", 1)[1].split("<!-- library:end", 1)[0]
    core, add_ons = table.split("### Add-ons", 1)
    docs = build_docs()
    for module_id in module_ids():
        assert (module_folder(module_id) / "docs" / "README.md").is_file(), f"{module_id}/docs/README.md is missing"
        if module_folder(module_id).is_relative_to(MODULES):
            assert docs.readme_link(module_id) == f"../../src/assistant/modules/{module_id}/docs/README.md"
        row = f"| [`{module_id}`]({docs.readme_link(module_id)}) |"
        assert row in (core if module_id in CORE else add_ons), f"no library row for {module_id} in its group"


def test_the_library_table_is_generated_from_the_manifests_and_menus():
    docs = build_docs()
    assert docs.library_block() in LIBRARY.read_text(encoding="utf-8"), (
        "the module library is stale: run scripts/build_docs.py"
    )
    assert [c.manifest.id for c in docs.module_classes()][:1] == ["console_io"]
    assert "`viewer.open`, `viewer.highlight`, `viewer.tabs`" in docs.library_block()


def test_the_library_core_row_names_everything_the_core_offers():
    """The core row is generated from `App.offers()`; every command, contract, menu item and
    event the core offers is on the page as built (a stale page or a hand-written row fails)."""
    docs = build_docs()
    offers = docs.core_offers()
    assert all(offers.values()), offers
    assert {"InvokeTool", "GetMenu", "StartProvider", "ShutdownRequested", "SetPermissionMode",
            "AnswerPermissionRequest", "AddCardNotes", "RemoveModule"} <= set(offers["handles"])
    assert {"modules.docs", "modules.remove", "permissions.grant"} <= set(offers["menu"])
    assert {"PermissionRequested", "PermissionChanged", "ModuleStateChanged"} <= set(offers["publishes"])
    page = LIBRARY.read_text(encoding="utf-8")
    row = next(line for line in page.splitlines() if line.startswith("**The core**"))
    missing = [n for names in offers.values() for n in names if f"`{n}`" not in row]
    assert not missing, f"the module library's core row misses {missing}: run scripts/build_docs.py"


CORE_SRC = ROOT / "src" / "assistant" / "core"
PUBLISH = re.compile(r"\.\_?publish\((\w+)\(")


def test_the_core_names_every_event_it_publishes():
    """Every literal `publish(X(...))` in the core is in `App.PUBLISHES`, so the core row lists it.
    `context.py` is left out: there a module's own events go out for it."""
    from assistant.core.app import App

    declared = {e.__name__ for e in App.PUBLISHES}
    found = {(py.name, name) for py in CORE_SRC.rglob("*.py") if py.name != "context.py"
             for name in PUBLISH.findall(py.read_text(encoding="utf-8"))}
    assert {n for _, n in found} >= {"ModuleStateChanged", "PermissionChanged", "PermissionRequested"}
    assert not [f for f in found if f[1] not in declared], "add these to App.PUBLISHES"


def test_the_core_line_names_every_core_menu_item():
    from assistant.core.app import App
    from assistant.core.door import CORE_LINE

    words = CORE_LINE["description"]
    for spec in App.core_specs():
        group, _, item = spec.name.partition(".")
        assert (item if group == "modules" else f"{group}.*") in words, f"core/door.py CORE_LINE misses {spec.name}"
