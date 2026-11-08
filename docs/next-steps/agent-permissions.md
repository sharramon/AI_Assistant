# Task agents ask for their access when turned on

> **Status: built (waiting on you), 2026-11-05.** All 8 steps are in the code and 474 tests pass. The handler is part of the core (`src/assistant/core/permissions/`); the design now lives in [Permissions](../architecture/permissions.md#access-lists-built). Left: an app restart, then try the job_search card, Allow turning it on, and the rough Grants screen. Replaces the job agent's hardcoded access list ([question 1](job-agent.md#open-questions-for-you)). Builds the first real piece of the planned [permissions handler](permissions-handler.md), including grant management.

## What you decided

1. **Each task-agent module lists what it needs in its own config:** the folders it reads, the folders it writes, whether it may run Python, whether it may use Chrome.
2. **When the module is turned on, it asks for the whole list in one request** through `ctx.permissions`. One card shows the full list. You allow all of it, trim it, or deny it.
3. **Before the card shows, the Main Assistant reviews the list** and adds warnings for risky combinations. A few fixed rules give predictable warnings, and the Main Assistant adds anything else it notices.
4. **The grant is saved per module** and lasts until the module's list changes. If the list changes, you're asked again. Nothing is asked on a normal launch.
5. **After the grant, the agent works inside it.** Anything outside it still gets a normal Manual-mode card. "Never submit or send anything" stays a fixed rule.
6. **Build the real handler's first piece now**, not a card bolted onto the allow-everything stand-in. (Built: the handler is always on, so the stand-in was removed; decision 14.)
7. **If the Main Assistant is busy**, the card shows right away with the rule warnings only, marked "not reviewed".
8. **A list can't start an agent in Auto.** Every session starts in Manual; Auto stays your button.
9. **The Main Assistant's own access is not moved** to this system in this change.
10. **Several helpers (`task_agents`): one card and one saved grant per helper.**
11. **Grants are managed through calls, not by editing the file.** The handler has list / grant / revoke calls, independent of any UI, offered as a menu on the module door. Agents can call it, but only your card can widen or narrow a grant. The only screen is a rough, throwaway one in the temp UI.
12. **Revoking while the agent is running turns the module off right away** and stops its running task (like Esc); the result says so. The task isn't left to finish, since its session would keep the old access.
13. **An agent can't take access away on its own.** An agent's revoke call shows your card, the same as its grant call; only your Allow applies it.
14. **The permissions handler is part of the core, not a module** (decided 2026-11-05, during the build; replaces "as a module" below). It's always on, and no module or agent can turn it off or reload it. `ctx.permissions` is a `PermissionsPort` forwarding to the core's `PermissionsHandler`; `AllowAllPermissions` and `IPermissions` are gone, and so is the registry's start order for `IPermissions`. The grant calls `permissions.grants / grant / revoke` are on the core's menu (id `core`), beside `modules.*`. It uses only the core's generic parts (the router's `send`, the bus's `publish`, the container's `get_one` for `IAgentNames`) and shared contracts. The Main Assistant's review is a normal task (`StartTask` / `TaskUpdated` / `CancelTask`). It imports no module and has no module-specific logic: a new module only declares `agent.access` and lists its access in config. Only two defaults name agents, the reviewer `main_assistant` and you = `temp_ui`, both overridable in `[core.permissions]`.
15. **Grants are saved per kind of agent** (decided 2026-11-05; refines 4 and 10). One grant per module and subject: `helper_2` shares `helper`'s grant, and the job agent's subject is `job_search_agent`.

## How it fits what's there

| Part | Today | With this change |
|---|---|---|
| Config (`[modules.job_search]`, `[modules.task_agents.agents.<id>]`) | `workspace`, `read_dirs`, `write_dirs`, `allowed_commands`, `chrome`, `permission_mode`, read by `AgentProfile.from_config` | Stays the source of the list, with one key added: `python` (the Python it may run, or none). `permission_mode` no longer starts a session in Auto |
| `Manifest.permissions` | Fixed names in code (`microphone`, `files.write:docs`) | Unchanged. A task-agent module adds one name, `agent.access`, saying "I ask for a config list when turned on". The list itself lives in config, because it differs per agent |
| `ctx.permissions` | `has` / `request` one name; the stand-in allows and logs | Gains `request_set(items, reason) -> granted items`: one request for a whole list, answered with what you allowed. Built: it forwards to the core's handler (decision 14); there's no stand-in |
| [Permissions handler](../architecture/permissions.md) | Designed, not built | Its first piece is built in the core (decision 14): saved grants, the one-card list request, the review step, and the grant menu. Single permissions (`location`, etc.) and permission sources come later, as designed |
| `AgentProfile` / `ProfileAgent` | Built straight from config | Built from the **granted** list. A trimmed folder never becomes a rule, so `claude` asks for it with a normal card |
| Permission mode | Manual every launch; Auto only by your button | Unchanged |

## Where the grant is stored

`data/permissions.toml`, the file the handler design already names. It's in the [protected zone](../architecture/permissions.md#repo-zones), so no agent can write it, and you don't edit it by hand either: it changes only through the handler's calls. One section per module (and per helper, for `task_agents`) holds:
- what you granted: the folders, Python and Chrome you kept;
- the fingerprint of the list it asked for;
- the date.

## How a changed list is noticed

Each time the module is turned on, it builds its list from config: paths resolved, sorted, and the flags. A hash of that list is the fingerprint. If it matches the saved one, the saved grant is used and nothing is asked. If it differs, or there's no saved grant, the card shows again. Any change asks again, including a narrower list, so the rule stays simple.

## What the card shows

- **Who:** the module and agent (`job_search` → `job_search_agent`, renamed by [agent-names](agent-names.md)) and its one-line description.
- **The list**, one line per item, each with a tick box: read `C:\Chang\Jobs`, write `C:\Chang\Jobs\CV`, run `<JobRadar's python.exe>`, use Chrome.
- **Warnings**, each next to the items it's about. The rule warnings come first, then the Main Assistant's notes, marked as its own, or "not reviewed" if it was busy.
- **The fixed rules**, in one line: never submit or send anything; protected paths are never granted; sessions start in Manual.
- **Buttons:** Allow (the ticked items), Deny. A denied or unanswered card leaves the module off, with the reason shown.

The same card works through the Talker ("job search wants these; allow?") using the existing `<<ALLOW>>` / `<<DENY>>` tags.

## The warning rules

Simple and predictable, checked in code before the Main Assistant sees the list:

| If the list has | Warning |
|---|---|
| Write to any folder **and** Chrome | It can change files there and put them on a website (for example your CV) |
| Read outside its workspace **and** Chrome | It can read those folders and paste what it reads into a website |
| Run Python | Python with any arguments can run any code, so it can do anything your account can |
| A folder in the protected zone | Refused, not just warned; it's taken off the list |

## The Main Assistant's review

The handler sends the list and the rule warnings to the Main Assistant as a short review task through the Hub, and puts its reply on the card under the rule warnings. If the Main Assistant is busy or doesn't answer within a short time, the card shows right away with the rule warnings only, marked "not reviewed by the Main Assistant".

## Managing grants

The calls live in the handler itself, with no UI in them, so any later UI and any agent use the same ones. They're offered as a `permissions.*` menu on the module door. Each call knows its caller (`InvokeTool.caller`).

| Call | Does | Who |
|---|---|---|
| `permissions.grants` | Lists the saved grants per module (and helper): what was granted, the date, and whether the module's current list still matches | Anyone |
| `permissions.grant` | Grants items to a module, then it turns on with them | From you: applied. From an agent: shows the same card, and only your Allow widens it |
| `permissions.revoke` | Takes back a module's grant (all, or some items). The module asks again the next time it's turned on | From you: applied. From an agent: shows the same card first, and only your Allow applies it; an agent can't take access away on its own (decision 13) |

**A running agent on revoke:** its rules are fixed when its `claude` session starts, so a running session would keep the old access. So revoke turns the module off right away: a running task is stopped (like Esc), and the result says so ("job_search turned off; its running task was stopped"). The task isn't left to finish (decision 12).

**You** means the caller is a UI you click in: today only `temp_ui`.

**The screen:** a deliberately rough grants screen in the temp UI: the list of grants with a Revoke button per module or item. It only calls the menu above and holds no logic. It sits in its own file (for example `temp_ui/static/grants.js` and one marked section in the page), labelled throwaway, so it goes away with the temp UI when the [UI handler](../architecture/decisions.md#open-decisions) is designed. This is an exception to "build nothing on the temp UI", which you asked for.

## "Never submit or send anything"

It stays in the agent's prompt as a fixed rule, shown on the card, and you can't trim it. Chrome can't be limited to some actions, so this rule depends on the model following it. It isn't enforced in code. The card says so.

## Reused parts

From the [reusable parts index](../api/reusable.md):
- `ctx.permissions` (`ModulePermissions`), extended with `request_set` (the stand-in `AllowAllPermissions` was replaced by the core's `PermissionsPort` in the build);
- `Manifest.permissions`;
- `Menu` with `callers`, and `InvokeTool.caller`, for the grant menu and telling you from an agent;
- the module door (`IModuleDoor`), so agents reach the grant menu with no new code;
- the core's `modules.off` (`DeactivateModule`) and the Hub's `CancelTask`, for revoke;
- `AgentProfile.from_config`, `ProfileAgent`, `path_rule`, `command_rules` and `claude_command` (with `chrome`), which turn the granted list into rules;
- the Allow / Deny card in the temp UI and the Talker's `<<ALLOW>>` / `<<DENY>>` tags;
- the Hub's `StartTask` for the review.

## What has to be built

1. **Contract:** `ModulePermissions.request_set`, and the `PermissionRequested` / `AnswerPermissionRequest` messages from the handler design, extended to carry a list, warnings and the kept items. This is a contract change, so it needs an app restart.
2. **The handler's first piece** (planned as `src/assistant/modules/permissions/`; built in the core as `src/assistant/core/permissions/`, decision 14): saved grants in `data/permissions.toml`, fingerprints, the warning rules, the review request (with the busy fallback), and the protected-zone check.
3. **The grant menu** in the handler: `permissions.grants / grant / revoke`, with the caller rules (an agent's grant or revoke waits for your card), and revoke turning the module off and stopping its running task.
4. **`AgentProfile`:** build from a granted list. Add the `python` key; sessions always start in Manual.
5. **`job_search` and `task_agents`:** call `request_set` on start (one per helper), and stay off when denied.
6. **The cards:** a list card with tick boxes and warnings in the temp UI, plus the Talker's wording.
7. **The throwaway grants screen** in the temp UI, in its own labelled file.
8. **Config:** move the job agent's list into the new keys. Tests for each step, then update the docs: permissions, the API pages, the module library and the job-agent note.

## Open questions for you

None left. The token-usage check below is for later.

## Later check: token usage for a wrapped tool (not decided)

You asked whether a module that wraps a tool, like `job_search`, can report the tokens of its own session **plus** the sub-agents it starts, as one number. Not part of this change. Its own session already reports through `SessionUsage`. What's unknown is whether a `claude` session's output includes its sub-agents' usage. To check later: run a session that starts a sub-agent and inspect its stream-json output (the `result` and usage fields) for the sub-agent's tokens. Plain code a module runs (like JobRadar's API sweep) burns no tokens. If it works, a module-level usage report that rolls up sub-agents would be settled once in the module architecture, not only for the job agent.
