"""The stable host. Controls communication and lifecycle; contains no module-specific logic."""

from assistant.core.app import App
from assistant.core.loader import add_app_folders, find_modules
from assistant.core.registry import StartupError

__all__ = ["App", "StartupError", "add_app_folders", "find_modules"]
