"""Helpers shared by the main app and the independent apps (the HTML viewer, the voice service).

Standard library only; never imports `assistant`. See docs/api/app_kit.md.
The window functions are imported from `app_kit.window`; a module's own docs folder from
`app_kit.module_docs`.
"""

from app_kit.companion import CompanionApp, CompanionHandover
from app_kit.config import load_layered, local_path, merge
from app_kit.local_guard import LOOPBACK_HOSTS, local_request, require_loopback

__all__ = [
    "LOOPBACK_HOSTS",
    "CompanionApp",
    "CompanionHandover",
    "load_layered",
    "local_path",
    "local_request",
    "merge",
    "require_loopback",
]
