# Worker gets full access

> **Status: done (2026-10-26).** Config and prompts changed; takes effect on the next launch.

**Asked:** "Worker should be able to do what you do. Which is read all the docs, and edit every file. For now. Its capabilities should be the same."

**Why:** while everything is still being built, the Main Assistant should be as capable as Claude Code in this repo. The guardrails ([repo zones](../architecture/permissions.md#repo-zones), branch workflow) come with the permissions handler.

**Touches:** `config/default.toml` (`[modules.main_assistant]`), the Main Assistant's and the Talker's prompts, and the agent docs.

**Approach:**
- `workspace = "."`: the repo is its working folder, so it loads `CLAUDE.md` and reads the docs as Claude Code does.
- `tools = "default"`: every built-in tool, shell included.
- `write_dirs = ["."]`: it edits any file in the repo without asking.
- Shell commands and `.claude/` still ask you each time (Allow / Deny, or the Talker), as they do for Claude Code.

**Open questions:** none.
