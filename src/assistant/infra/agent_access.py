"""A task agent's access list, from its config section, asked for in one request.

A task-agent module (manifest permission `agent.access`) turns its agent's config section into
an access list (`access_items`), asks for it with `ctx.permissions.request_set` when it's turned
on, and builds its agent from the config cut down to what you allowed (`granted_config`).
`request_access` does both. A trimmed folder or command never becomes a rule, so `claude`
asks for it with a normal card.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from assistant.contracts import AccessDenied, AccessItem, AccessKind, ModuleContext, PermissionChanged


def access_items(config: dict[str, Any]) -> tuple[AccessItem, ...]:
    """The access list of an agent's config section: its `workspace` (resolved, always first),
    `read_dirs`, `write_dirs` (resolved), `python`, `allowed_commands` and `chrome`."""
    items = [AccessItem(kind=AccessKind.WORKSPACE, target=_folder(config.get("workspace", "workspace")))]
    items += [AccessItem(kind=AccessKind.READ, target=_folder(d)) for d in config.get("read_dirs", ())]
    items += [AccessItem(kind=AccessKind.WRITE, target=_folder(d)) for d in config.get("write_dirs", ())]
    if python := str(config.get("python") or "").strip():
        items.append(AccessItem(kind=AccessKind.PYTHON, target=python))
    items += [AccessItem(kind=AccessKind.COMMAND, target=str(c)) for c in config.get("allowed_commands", ())]
    if config.get("chrome"):
        items.append(AccessItem(kind=AccessKind.CHROME))
    return tuple(dict.fromkeys(items))


def granted_config(config: dict[str, Any], granted: tuple[AccessItem, ...]) -> dict[str, Any]:
    """`config` with only the `granted` items: trimmed folders, Python, commands and Chrome
    dropped; paths resolved. Granted items beyond the config's list (what its agent asked for
    itself with `permissions.request`) are added. Raises `AccessDenied` when its workspace
    wasn't granted, since an agent can't run without its working folder."""
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
    ctx: ModuleContext, config: dict[str, Any], subject: str = "", reason: str = "", wait: bool = False
) -> dict[str, Any]:
    """Ask for `config`'s access list (`ctx.permissions.request_set`) and return the config cut
    down to what you allowed. Raises `AccessPending` (with `wait=False`, while its card is
    open) or `AccessDenied`, as `request_set` does, and `AccessDenied` for a refused workspace."""
    granted = await ctx.permissions.request_set(access_items(config), reason, subject, wait)
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
