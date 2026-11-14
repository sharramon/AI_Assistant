"""Move one add-on out of the repo into a module folder of yours (module layout step 2).

Run by hand only, with an explicit target; nothing in the app or the tests runs it:

    .\\.venv\\Scripts\\python scripts\\move_add_on.py cv C:/AddOns           # a dry run: says what it would do
    .\\.venv\\Scripts\\python scripts\\move_add_on.py cv C:/AddOns --yes     # copies src/assistant/modules/cv to C:/AddOns/cv
    .\\.venv\\Scripts\\python scripts\\move_add_on.py cv C:/AddOns --yes --delete-old   # ... then deletes the repo's copy

It refuses a core module (only add-ons leave the repo), a relative or in-repo target, and a target
that already holds the module. The copy keeps everything in the folder, its gitignored `workspace/`
too (`__pycache__` skipped). Without `--delete-old` the repo's copy stays, and the app then refuses
to start while `[core] module_folders` names the target (an id in two folders): delete it yourself
(`git rm -r src/assistant/modules/<id>`, after checking its uncommitted work is in the copy).

Afterwards: add the target to `[core] module_folders` in config/local.toml, restart the app. The
how-to is in docs/next-steps/module-layout-step2-checklist.md.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULES = ROOT / "src" / "assistant" / "modules"


def plan(module_id: str, target: str) -> tuple[Path, Path]:
    """The source and destination folders, or SystemExit saying why not."""
    source = MODULES / module_id
    if not (source / "__init__.py").is_file():
        raise SystemExit(f"No module folder {source}")
    docs = source / "docs" / "docs.toml"
    group = tomllib.loads(docs.read_text(encoding="utf-8")).get("group") if docs.is_file() else None
    if group != "add-on":
        raise SystemExit(f"{module_id} is in the group {group!r}: only add-ons leave the repo (the core stays)")
    folder = Path(target).expanduser()
    if not folder.is_absolute():
        raise SystemExit(f"The target must be an absolute folder, not {target!r}")
    folder = folder.resolve()
    if folder.is_relative_to(ROOT):
        raise SystemExit(f"The target must be outside the repo {ROOT}, not {folder}")
    destination = folder / module_id
    if destination.exists():
        raise SystemExit(f"{destination} already exists: nothing copied")
    return source, destination


def files(folder: Path) -> list[Path]:
    return sorted(p.relative_to(folder) for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Move one add-on out of the repo (module layout step 2).")
    parser.add_argument("module_id", help="the add-on's id, e.g. cv")
    parser.add_argument("target", help="an absolute folder outside the repo, e.g. C:/AddOns")
    parser.add_argument("--yes", action="store_true", help="really copy (without it: a dry run)")
    parser.add_argument("--delete-old", action="store_true", help="after a checked copy, delete the repo's copy")
    args = parser.parse_args(argv)

    source, destination = plan(args.module_id, args.target)
    count = len(files(source))
    print(f"{'Copying' if args.yes else 'Would copy'} {source} -> {destination} ({count} files)")
    if not args.yes:
        print("A dry run: nothing changed. Add --yes to copy.")
        return 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__"))
    if files(destination) != files(source):
        raise SystemExit(f"The copy in {destination} doesn't match {source}: the repo's copy is kept")
    print(f"Copied and checked ({count} files).")
    if args.delete_old:
        shutil.rmtree(source)
        print(f"Deleted {source}. `git status` shows it as deleted; commit that in the repo.")
    else:
        print(f"Kept {source}: delete it (git rm -r) before the app can start with the new folder.")
    print(f'Next: in config/local.toml, [core] module_folders = ["{destination.parent.as_posix()}"]; restart the app.')
    return 0


if __name__ == "__main__":
    sys.exit(main())
