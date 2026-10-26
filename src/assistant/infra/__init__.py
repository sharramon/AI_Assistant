"""Shared infrastructure used by the core and modules."""

from assistant.infra.claude_session import ClaudeSession, claude_command
from assistant.infra.config import load_config
from assistant.infra.log import setup_logging
from assistant.infra.session_agent import SessionTaskAgent

__all__ = ["ClaudeSession", "SessionTaskAgent", "claude_command", "load_config", "setup_logging"]
