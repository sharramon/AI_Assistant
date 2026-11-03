"""Helpers shared by the main app and the independent apps (the HTML viewer, the voice service).

Standard library only; never imports `assistant`. See docs/api/app_kit.md.
The window functions are imported from `app_kit.window`.
"""

from app_kit.companion import CompanionApp
from app_kit.config import load_layered

__all__ = ["CompanionApp", "load_layered"]
