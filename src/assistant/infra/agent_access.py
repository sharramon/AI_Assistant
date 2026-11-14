"""A task agent's access list, from its config section, asked for in one request.

A task-agent module (manifest permission `agent.access`) turns its agent's config section into
an access list (`access_items`), asks for it with `ctx.permissions.request_set` when it's turned
on, and builds its agent from the config cut down to what you allowed (`granted_config`).
`request_access` does both. A trimmed folder or command never becomes a rule, so `claude`
asks for it with a normal card.

Every module can edit itself: a module's own agent gets, by default, a write item on its own
module folder (`src/assistant/modules/<id>`, or its folder outside the repo: `module_folder`
looks in every `module_roots` folder), never a parent or another module's folder. `task_agents` asks without it (`own_folder=False`): its helpers are generic,
several run at once, and none is that module's own agent.

Your data can leave the repo (module layout step 1): a module's config names its agent's data
folder (`data_folder` in `config/<id>.toml`, yours, outside the repo), which is then its
workspace (`data_folder`). Unset, the agent works in its module's own `workspace/` as before. The
first time a data folder is used, the old workspace is copied into it (`copy_data_once`), never
moved or deleted.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from assistant.contracts import AccessDenied, AccessItem, AccessKind, ModuleContext, PermissionChanged

#: Where the modules live: one folder per module, named with its id (the loader's `assistant.modules`).
MODULES_FOLDER = Path(__file__).resolve().parents[1] / "modules"
#: The repo (the folder holding `src/`).
REPO_FOLDER = MODULES_FOLDER.parents[2]
#: The config key naming a module agent's data folder (in `config/<id>.toml`).
DATA_FOLDER_KEY = "data_folder"

log = logging.getLogger(__name__)


def module_roots() -> list[Path]:
    """Every folder holding module folders, the repo's `MODULES_FOLDER` first, then the ones
    `[core] module_folders` names (outside the repo). Read from the `assistant.modules` package's
    path, which the loader extends at startup (`loader.add_module_folders`), so the two never
    disagree; the repo's folder alone before that package is imported."""
    package = sys.modules.get("assistant.modules")
    roots = [MODULES_FOLDER, *(Path(p).resolve() for p in getattr(package, "__path__", ()))]
    seen: dict[str, Path] = {}
    for root in roots:
        seen.setdefault(os.path.normcase(str(root)), root)
    return list(seen.values())


def module_folder(module_id: str) -> Path | None:
    """Module `module_id`'s own folder (`src/assistant/modules/<id>`, or `<outside folder>/<id>`:
    the first root of `module_roots` holding it), or None when there's no such folder (a test's
    stand-in, say)."""
    if not module_id or os.sep in module_id or "/" in module_id or module_id.startswith("."):
        return None
    return next((root / module_id for root in module_roots() if (root / module_id).is_dir()), None)


def in_module_folder(module_id: str, path: Any) -> Path:
    """A configured folder of module `module_id`: `~` expanded, a relative one from that module's
    own folder (`workspace` → `src/assistant/modules/<id>/workspace`, resolved), so no shipped
    default names a personal absolute path. An absolute one is returned as given; with no such
    module folder, a relative one is from the current folder."""
    folder = Path(str(path)).expanduser()
    if folder.is_absolute():
        return folder
    return ((module_folder(module_id) or Path.cwd()) / folder).resolve()


def data_folder(module_id: str, config: dict[str, Any]) -> Path | None:
    """Module `module_id`'s data folder from its config (`data_folder`, `~` expanded, resolved), or
    None when it's unset or empty: then its agent works in its own workspace, as before. ValueError
    if it isn't a string, or isn't an absolute folder outside the repo (your data never sits in the
    repo tree once it's named)."""
    value = config.get(DATA_FOLDER_KEY)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError(f"{module_id}: {DATA_FOLDER_KEY} must be a folder, not {value!r}")
    folder = Path(value.strip()).expanduser()
    if not folder.is_absolute():
        raise ValueError(f"{module_id}: {DATA_FOLDER_KEY} must be an absolute folder, not {value!r}")
    folder = folder.resolve()
    if folder.is_relative_to(REPO_FOLDER.resolve()):
        raise ValueError(f"{module_id}: {DATA_FOLDER_KEY} must be outside the repo {REPO_FOLDER}, not {folder}")
    return folder


def copy_data_once(source: Path, target: Path) -> bool:
    """The first use of a data folder: copy the old workspace `source` into `target` when `target`
    is missing or empty and `source` is a folder (`__pycache__` skipped). Never moves or deletes
    anything: `source` stays as it was, and a `target` holding any file is used as it is. True when
    it copied."""
    source, target = Path(source), Path(target)
    if target.exists() and any(target.iterdir()):
        return False
    if not source.is_dir() or source.resolve() == target.resolve():
        return False
    shutil.copytree(source, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
    log.info("Copied %s into the data folder %s (the old folder is kept)", source, target)
    return True


def module_folder_of(path: Any) -> Path | None:
    """The module folder `path` is in, or is (`<root> / <id>`, a root of `module_roots`); None for
    a path outside every module's folder, a modules folder itself included. For the Hub's folder
    check."""
    here = os.path.normcase(str(Path(str(path)).resolve()))
    for root in module_roots():
        base = os.path.normcase(str(root))
        if here.startswith(base + os.sep):
            return root / here[len(base) + 1 :].split(os.sep)[0]
    return None


def access_items(config: dict[str, Any], module_id: str = "") -> tuple[AccessItem, ...]:
    """The access list of an agent's config section: its `workspace` (resolved, always first),
    `read_dirs`, `write_dirs` (resolved), with `module_id`: a write on that module's own folder
    (`module_folder`, when it exists), then `python`, `allowed_commands` and `chrome`."""
    items = [AccessItem(kind=AccessKind.WORKSPACE, target=_folder(config.get("workspace", "workspace")))]
    items += [AccessItem(kind=AccessKind.READ, target=_folder(d)) for d in config.get("read_dirs", ())]
    items += [AccessItem(kind=AccessKind.WRITE, target=_folder(d)) for d in config.get("write_dirs", ())]
    if (own := module_folder(module_id)) is not None:
        items.append(AccessItem(kind=AccessKind.WRITE, target=str(own)))
    if python := str(config.get("python") or "").strip():
        items.append(AccessItem(kind=AccessKind.PYTHON, target=python))
    items += [AccessItem(kind=AccessKind.COMMAND, target=str(c)) for c in config.get("allowed_commands", ())]
    if config.get("chrome"):
        items.append(AccessItem(kind=AccessKind.CHROME))
    return tuple(dict.fromkeys(items))


def granted_config(config: dict[str, Any], granted: tuple[AccessItem, ...]) -> dict[str, Any]:
    """`config` with only the `granted` items: trimmed folders, Python, commands and Chrome
    dropped; paths resolved. Granted items beyond the config's list (its own module folder, or
    what its agent asked for itself with `permissions.request`) are added. Raises `AccessDenied`
    when its workspace wasn't granted, since an agent can't run without its working folder."""
    keys = {i.key for i in granted}
    asked = access_items(config)
    workspace = asked[0]
    if workspace.key not in keys:
        raise AccessDenied(f"its workspace {workspace.target} was refused, so it can't start")
    listed = {i.key for i in asked}
    kept = [i for i in asked if i.key in keys]
    kept += [i for i in dict.fromkeys(granted) if i.key not in listed and i.kind is not AccessKind.WORKSPACE]
    result = dict(config)
    result["workspace"] = workspace.target
    result["read_dirs"] = [i.target for i in kept if i.kind is AccessKind.READ]
    result["write_dirs"] = [i.target for i in kept if i.kind is AccessKind.WRITE]
    result["allowed_commands"] = [i.target for i in kept if i.kind is AccessKind.COMMAND]
    result["python"] = next((i.target for i in kept if i.kind is AccessKind.PYTHON), None)
    result["chrome"] = any(i.kind is AccessKind.CHROME for i in kept)
    return result


async def request_access(
    ctx: ModuleContext, config: dict[str, Any], subject: str = "", reason: str = "", wait: bool = False,
    own_folder: bool = True,
) -> dict[str, Any]:  # fmt: skip
    """Ask for `config`'s access list (`ctx.permissions.request_set`) and return the config cut
    down to what you allowed. `own_folder`: the list includes a write on the asking module's own
    folder (`module_folder(ctx.module_id)`). Raises `AccessPending` (with `wait=False`, while
    its card is open) or `AccessDenied`, as `request_set` does, and `AccessDenied` for a refused
    workspace."""
    items = access_items(config, ctx.module_id if own_folder else "")
    granted = await ctx.permissions.request_set(items, reason, subject, wait)
    return granted_config(config, tuple(granted))


def watch_grant(
    ctx: ModuleContext,
    on_grant: Callable[[str, tuple[AccessItem, ...]], Awaitable[None]],
    subject: str | None = None,
) -> None:
    """Call `on_grant(subject, granted)` whenever one of this module's grants is saved wider or
    narrower (`PermissionChanged` with items), so its running agents can take the new access
    live (`ProfileAgent.set_access`). `subject`: only that one; None: every subject of the
    module (a kind per subject in `task_agents`). A denied list or a removed grant (no items)
    is skipped: a revoke turns the module off anyway. Subscribe in `init`; list
    `PermissionChanged` in the manifest's `listens`."""

    async def changed(event: PermissionChanged) -> None:
        if event.module_id != ctx.module_id or not event.granted:
            return
        if subject is not None and event.subject != subject:
            return
        await on_grant(event.subject, tuple(event.granted))

    ctx.subscribe(PermissionChanged, changed)


def _folder(path: Any) -> str:
    return str(Path(str(path)).resolve())
