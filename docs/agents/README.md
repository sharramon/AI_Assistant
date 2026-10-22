# Agents

How we run and work with the agents: setup, experiments, and what we've learned. How they fit the system is on the [Agents architecture page](../architecture/agents.md).

> **Status:** designed, not built. The [spike](spike.md) is done: interrupting a session works as the design assumes. Next: build the modules.

## Roles

| Agent | Job | First implementation |
|-------|-----|----------------------|
| **Talker** | Talks with you; hands off work; reports progress; relays questions | `claude -p` session, faster model (`sonnet`), no built-in tools |
| **Main Assistant** | Your main AI: reasons, plans, does the work, delegates | `claude -p` session (Claude Code) with file tools |
| **Subagents** | Specialized workers the Main Assistant delegates to | Later |

## How the sessions run

- Each agent is one **long-lived** `claude -p --input-format stream-json --output-format stream-json` process, so it keeps its conversation.
- Messages in and out are **JSON lines** over stdin and stdout. The owning module (later: through `infra/ClaudeSession`) writes the agent's input and reads its event stream.
- Agents never talk to each other directly; everything goes through the Hub and the core.
- Started with `--strict-mcp-config`, so your claude.ai MCP connectors aren't loaded.
- Runs on your **Claude subscription** (terms checked for personal use). The session layer stays swappable to an API key.

## Permissions

- **Talker:** no tools.
- **Main Assistant:** reads anywhere, writes only inside its workspace folder, no shell, `dontAsk` mode, until a confirmation mechanism exists.

## First implementation limits

- One Main Assistant and **one active task**; another request gets "busy". No queue.
- No scheduling or distributed machinery until needed.

## Pages

- [Agent runtime](runtime.md): how the two agents are spawned, behave, and talk to each other (planned, for review)
- [Two-Claude spike](spike.md): the disposable experiment and its findings
