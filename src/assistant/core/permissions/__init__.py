"""The permissions handler, part of the core (always on; no module or agent turns it off or
reloads it): `PermissionsHandler`, every module's `PermissionsPort` (`ctx.permissions`), and the
grant calls on the core's menu (`PermissionsMenu`)."""

from assistant.core.permissions.handler import GRANTS_FILE, PermissionsHandler
from assistant.core.permissions.menu import PermissionsMenu
from assistant.core.permissions.port import PermissionsPort

__all__ = ["GRANTS_FILE", "PermissionsHandler", "PermissionsMenu", "PermissionsPort"]
