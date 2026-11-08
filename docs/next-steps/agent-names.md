# Agent names: ids, launching named helpers, and the duplicate check

**Status:** built · 2026-11-05 · all questions decided (below); a contract changed, so the app needs a **restart** (asked after the agent-permissions and usage-tallies notes are built too)

Every agent that takes tasks has one id. The Hub, the tabs, the focus, messages, usage and the module door all find an agent by that id. This note fixes how ids are chosen, makes the Hub refuse a second agent with the same id, and lets a helper be launched by name, only with your yes.

## Three kinds of agent (kept apart)

- **The coordinator and module agents:** an agent that comes with its own module: the Main Assistant (`main_assistant`), and the job agent (`job_search_agent`, from the `job_search` module). They start with their module.
- **Helpers:** separate, parallel agents from `task_agents`, launched by name for one main task (`flight_search`), from a *kind* of helper in config (prompt, access). Not tied to any module.
- **Sub-agents:** what a `claude` session starts inside itself (its own Task tool, e.g. the `debugger`). They aren't task agents: no id, no tab, never in the Hub. Their usage is the usage-tallies note's business.

## What existed before (checked in the code)

- The Hub didn't register agents. It asked for all of them each time (`ctx.get_all(ITaskAgent)`) and took **the first** whose id matched.
- `task_agents` made one agent per profile at start; `instances = N` added `name-2`, `name-3` (a hyphen). It refused its own duplicates and a short reserved list, and couldn't see other modules' ids.
- `job_search`: id `job` by default, checked against nothing.
- Two agents with one id: both started, nothing warned, the tabs merged, everything for that id went to the first one, both used the door under one caller name, and their usage overwrote each other.

## Decided (by you)

1. **Module agent name:** the module id plus `_agent`. The job agent becomes `job_search_agent`.
2. **Conventions:** short, lowercase, letters, digits and `_` only, starting with a letter, at most 32 characters (`flight_search`, `helper_2`). Unique across all running agents.
3. **Reserved:** `main_assistant`, `talker`, `core`, `hub`, and **every module's id** (the door's caller names are agent or module ids, so an agent named like a module could act as that module). A module's own agent may carry its module's id (`main_assistant`).
4. **A taken name:** the refusal names a free one (`flight_search_2`). For a name the Main Assistant made up, it takes that one and tells you; for a name you gave, it asks you again.
5. **Config profiles become kinds of helper,** launched when needed. A kind with `autostart = true` still starts an agent at launch (with `instances`).
6. **Launching a helper is always your decision** (changed 2026-11-05; replaces "both the Main Assistant and you may launch"). `agents.launch` only *proposes* a helper: you get a card with its name and task, and the helper starts only if you allow it. Deny, or no answer before the card times out, and no helper starts. A call from the Main Assistant without your yes does nothing. When you ask for a helper through the Talker, it goes through the same card. The cap (`max_extra_agents`) still applies.
7. **Extra copies** are named `helper_2`, not `helper-2`.

## The design

**The duplicate check lives in the Hub** (every agent goes through it, whichever module owns it):
- New contract `IAgentNames`, provided by `agent_hub`: `check(agent_id, owner)` (why it can't have the name, or None), `claim(agent_id, owner) -> Result`, `release(agent_id, owner)`, `taken()`. A refusal is `invalid_arguments` with the reason and a free name ("`flight_search` is taken by task_agents; `flight_search_2` is free").
- The rules are one infra helper, `check_agent_id(agent_id, owner, module_ids)`, plus `free_agent_id(base, taken)`. `task_agents`' own `RESERVED` list is gone.
- The claims survive a Hub reload (in its handover).
- **Who claims:** `ProfileAgent.start` claims the agent's id and `stop` releases it, so the Main Assistant, every helper and the job agent get it with no code of their own. A refused claim stops that agent with the reason (at launch: its module fails to start, and the log says why).
- **Safety net:** an agent that skipped the claim and shares an id: the Hub uses the first one everywhere (`hub.agents`, `ListAgents`, routing) and logs the clash once.

**Launching a helper, with your yes (reusing the permission card):**
- `task_agents` menu: `agents.kinds` (the kinds and the helpers running), `agents.launch(name, task, kind)`, `agents.close(agent_id)` (a launched helper with no task; frees its name).
- `agents.launch` checks the kind, the name (`IAgentNames.check`) and that the caller is an agent with an open task. Then it asks that agent to put the question to you: the new `ITaskAgent.request_approval(action, run)`. `SessionTaskAgent` already asked you this way for a `RELOAD:` or `ADD_MODULE:` line: a `permission` report on its task, so the **same card** (temp UI Allow / Deny, the Talker's ALLOW / DENY) and the same `AnswerPermission`. That code is now one path for both, with one difference: a launch always asks, even in Auto.
- Allow: `run` builds the helper (`ProfileAgent`, its own sub-folder `<kind workspace>/<name>`, its own transcript), provides it, claims its name, and starts its task as the caller's child (`StartTask`, so the cap and the folder-clash check apply). The outcome ("flight_search started on task 1a2b3c4d", or why not) reaches the caller as its next message. Deny or no answer: nothing is built.
- The caller ends its turn after `agents.launch`; the turn waits for your answer (it doesn't count as done). If you answer while it's still in the turn, the outcome is sent when the turn ends.
- The Talker has no task to hang a card on, so `agents.launch` from it is refused with "hand it to the Main Assistant": you say "start a helper for X", the Talker hands it over, the Main Assistant calls `agents.launch`, and you get the card.
- The core gains `ModuleContext.withdraw(contract, impl)`, so `agents.close` can take back one helper without stopping the module.

**What changed for `job`:** its default id is `job_search_agent` (`job_search/module.py`, the prompt, `config/default.toml`'s comment and `transcript = "job_search_agent.jsonl"`, the Talker's prompt examples, tests, `docs/modules/job_search.md`).

**The Main Assistant's prompt** (the coordinator's block): `agents.kinds` / `agents.launch` / `agents.close`, launch only when you asked for a helper, name it from the task, the taken-name rule, end the turn after asking.

## Reused parts ([index](../api/reusable.md))

- `SessionTaskAgent`: its reload/add permission request became `request_approval`, used by both.
- `ProfileAgent`: builds the launched helpers and claims every agent's id.
- The permission card (temp UI, Talker) and `AnswerPermission`: unchanged.
- New reusable parts: `IAgentNames`, `check_agent_id` / `free_agent_id`, `ITaskAgent.request_approval`, `ModuleContext.withdraw`.

## What has to be built

1. `IAgentNames`, `ITaskAgent.request_approval`, `ModuleContext.withdraw` (contracts: **restart**); `check_agent_id`, `free_agent_id` (infra).
2. The Hub provides `IAgentNames`, keeps the claims (handed over on reload), dedups agents and logs a clash.
3. `ProfileAgent` claims on start, releases on stop. `SessionTaskAgent.request_approval`, one path with the reload/add request, the turn waiting for the answer.
4. `task_agents`: kinds, `autostart`, `_2` instances, `agents.kinds` / `launch` / `close`.
5. `job_search`: `job_search_agent`; config, Talker prompt examples, tests.
6. The coordinator's prompt block.
7. Tests (clash, reserved, bad form, release on stop, the safety net, launch allowed / denied / refused, approval in a turn), ruff, docs, rebuild.
