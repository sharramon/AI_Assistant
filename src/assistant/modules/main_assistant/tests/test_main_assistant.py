"""The Main Assistant's defaults in its `module.toml`. The worker itself, with the Hub, is tested
centrally (`tests/test_agents.py`, `tests/test_permission_mode.py`, `tests/test_mcp_door.py`, ...),
since every one of those tests runs it beside the Agent Hub."""

from assistant.core import App
from assistant.modules.main_assistant import MainAssistantModule
from assistant.testkit import module_config

# The old [modules.main_assistant] in config/default.toml, before its defaults moved to module.toml.
OLD_SECTION = {
    "workspace": ".",
    "tools": "default",
    "permission_mode": "acceptEdits",
    "read_dirs": ["."],
    "write_dirs": [".", ".claude/skills", ".claude/agents"],
    "allowed_commands": [
        ".\\.venv\\Scripts\\python -m pytest",
        ".\\.venv\\Scripts\\ruff check",
        ".\\.venv\\Scripts\\python scripts\\build_docs.py",
        "git status",
        "git diff",
        "git log",
        "git show",
        "Get-ChildItem",
        "Get-Content",
        "Select-String",
    ],
    "fresh_sessions": True,
    "max_handoffs": 3,
    "context_reminder": 150000,
    "edit_note": True,
    "permission_prompts": True,
    "permission_timeout": 600.0,
    "transcript": "main_assistant.jsonl",
}


def test_its_defaults_are_in_its_module_toml_under_the_apps_section():
    defaults = module_config("main_assistant")
    assert defaults["needs"] == [] and defaults["packages"] == []
    assert {k: v for k, v in defaults.items() if k not in ("needs", "packages")} == OLD_SECTION
    assert MainAssistantModule.manifest.needs == ()
    yours = {"write_dirs": ["."], "model": "opus"}
    app = App([MainAssistantModule], {"modules": {"enabled": [], "main_assistant": yours}, "core": {}})
    assert app._config_of("main_assistant") == {**defaults, **yours}  # yours wins key by key, a list whole
