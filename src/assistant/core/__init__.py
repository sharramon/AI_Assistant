"""The stable host. Controls communication and lifecycle; contains no module-specific logic."""

from assistant.core.app import App
from assistant.core.loader import LoadError, add_app_folders, configured_module_folders, find_modules
from assistant.core.registry import StartupError

__all__ = ["App", "LoadError", "StartupError", "add_app_folders", "configured_module_folders", "find_modules"]
