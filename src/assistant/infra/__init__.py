"""Shared infrastructure used by the core and modules."""

from assistant.infra.agent_access import (
    MODULES_FOLDER,
    access_items,
    granted_config,
    in_module_folder,
    module_folder,
    module_folder_of,
    request_access,
    watch_grant,
)
from assistant.infra.agent_kit import AGENT_LISTENS, AGENT_PUBLISHES, AGENT_SENDS, AGENT_USES, AgentKit
from assistant.infra.agent_names import check_agent_id, free_agent_id
from assistant.infra.agent_profile import AgentProfile, prompt_block
from assistant.infra.agent_tags import LastLineTags, ShowTag, Tag, find_tags, last_line, parse_show, status_lines
from assistant.infra.claude_session import ClaudeSession, claude_command
from assistant.infra.config import load_config
from assistant.infra.context_watch import ContextWatch
from assistant.infra.handoff_keeper import HandoffKeeper
from assistant.infra.log import LogSession, LogSink, setup_logging, theme_slug
from assistant.infra.milestone_feed import MilestoneFeed
from assistant.infra.permission_gate import PermissionGate
from assistant.infra.profile_agent import ProfileAgent
from assistant.infra.session_agent import SessionTaskAgent, session_usage, subagent_usage
from assistant.infra.show_pages import NO_PAGE_VIEWER, ShowOutcome, open_page, show_page
from assistant.infra.usage_ledger import UsageLedger

__all__ = [
    "AgentProfile",
    "MODULES_FOLDER",
    "access_items",
    "granted_config",
    "in_module_folder",
    "module_folder",
    "module_folder_of",
    "watch_grant",
    "request_access",
    "check_agent_id",
    "free_agent_id",
    "ProfileAgent",
    "AgentKit",
    "AGENT_LISTENS",
    "AGENT_PUBLISHES",
    "AGENT_SENDS",
    "AGENT_USES",
    "ClaudeSession",
    "ContextWatch",
    "LogSession",
    "LogSink",
    "MilestoneFeed",
    "HandoffKeeper",
    "LastLineTags",
    "PermissionGate",
    "SessionTaskAgent",
    "ShowOutcome",
    "ShowTag",
    "Tag",
    "NO_PAGE_VIEWER",
    "open_page",
    "show_page",
    "session_usage",
    "subagent_usage",
    "UsageLedger",
    "claude_command",
    "find_tags",
    "last_line",
    "parse_show",
    "prompt_block",
    "status_lines",
    "load_config",
    "setup_logging",
    "theme_slug",
]
