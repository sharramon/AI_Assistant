"""Shared infrastructure used by the core and modules."""

from assistant.infra.config import load_config
from assistant.infra.log import setup_logging

__all__ = ["load_config", "setup_logging"]
