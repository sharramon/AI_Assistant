# Permission mode button

> **Status: done (2026-11-02).** The spike passed (findings below). The code, `page.html`, and `tests/test_permission_mode.py` are built: ruff is clean and all tests pass. Updated docs: [Agents API](../api/agents.md#permissionmode), [Infrastructure API](../api/infra.md#sessiontaskagent), [reusable parts](../api/reusable.md) (Used by lines checked against the imports), `api/README.md`, [Permissions](../architecture/permissions.md#permission-mode-built), [Agent runtime](../agents/runtime.md#permission-mode), and `next-steps/README.md`. **Restart the app** to get it.
>
> After an Auto switch is deferred (`next_task`), the running session is still in Manual, so a later Manual click sends no control request. The test starts the task in Auto to check the live switch.

**Asked:** a button to switch the Main Assistant between **manual** permissions (it asks you before each tool use outside its standing rules, as today) and **auto** (it doesn't ask), like the permission modes in Claude Code.

**Why:** long, trusted tasks stop on every shell command until you click Allow. Some tasks should run unattended, but the default has to stay safe.

**Touches:** `contracts/agents.py`, `infra/claude_session.py`, `infra/session_agent.py`, `agent_hub`, `main_assistant` (command and prompt), `talker` (what it's told), `temp_ui` (module and `page.html`), and tests. Docs: `api/agents.md`, `api/infra.md`, `api/reusable.md`, `api/README.md`, `agents/runtime.md`, `architecture/permissions.md`.

## Decided (2026-11-02)

- **Two modes, Manual and Auto.** Today's Manual already accepts edits, so a separate accept-edits mode would add nothing.
- **Manual at every launch.** The mode isn't saved.
- **Only you switch to Auto,** with the button. The Talker can switch back to Manual (`<<MODE: manual>>`), never to Auto.
- **A switch that can't apply mid-task applies from the next task,** and the UI says so.
- **The button is in the Talker pane** of the temp UI, marked as a stand-in, and the Talker is told the current mode.
- **Auto means full permissions** (`bypassPermissions`), with no block list as the main design. The Main Assistant pauses on its own and asks before very risky steps.
- **One hard backstop in Auto: `git push` is blocked.** It is refused, not asked about, and you push yourself. The spike confirmed that the block holds with every prompt off.

## Spike findings (2026-11-02, real `claude`)

Run against a throwaway bare repo and clone in a temp folder (`%TEMP%\pm-spike\`), never the project's remote.

- **The `git push` block holds under `bypassPermissions`.** The command line was `--permission-mode bypassPermissions --disallowedTools "PowerShell(git push)" "PowerShell(git push *)" "Bash(git push)" "Bash(git push *)"`, passed as separate arguments. `git push origin HEAD:refs/heads/main` and a bare `git push` were both refused ("Permission to use PowerShell with command git push has been denied"). No `can_use_tool` request arrived, and the bare remote stayed empty. The result was the same with `--permission-prompt-tool stdio` on, so Auto keeps the prompt tool.
- **`set_permission_mode` works over our stdio session.** A session started in `bypassPermissions` got `{"subtype": "set_permission_mode", "mode": "acceptEdits"}` and answered `success`. After that, `git tag spike-tag` arrived as a `can_use_tool` request (and was denied). `git status` is no test, because it's read-only and allowed in any mode. The request was sent between turns; mid-turn wasn't tried.
- **Limit:** the block only catches a direct `git push` (not `git -C x push` or a script that pushes), as section 2 already says.

## Approach

### 1. The modes

| Mode | What it does | `claude` flags |
|------|--------------|----------------|
| **Manual** (default) | Exactly today: edits in the repo and the read-only commands run without asking, and everything else shows an Allow / Deny card | `--permission-mode acceptEdits`, the `--allowedTools` standing rules, `--permission-prompt-tool stdio` |
| **Auto** | Full permissions for every tool, with no cards, except `git push`, which is refused. The Main Assistant pauses on its own before very risky steps (section 2) | `--permission-mode bypassPermissions`, `--disallowedTools` with `git push` and `git push *` for both PowerShell and Bash, the same standing rules and prompt tool (so a switch back to Manual asks again), plus the risky-step rule in its prompt |

**Auto removes every prompt.** With `bypassPermissions`, `claude` never sends a `can_use_tool` request, so no Allow / Deny card appears. Only two things stand between the Main Assistant and a risky step: its own judgment, and the `git push` block.

### 2. In Auto, the Main Assistant asks before very risky steps

In Auto, the access section of its prompt says it has full permissions except `git push`, then adds this rule:

> Before a very risky step, stop and ask first: end your turn with `NEED: Risky: <what you want to do and why>`. Continue once the user answers. Very risky means:
> - deleting data or files beyond what the task needs
> - rewriting git history (`reset --hard`, `rebase`, force anything, deleting branches)
> - changing secrets, credentials, or settings (`config/`, `.env`, `.claude/settings*`, system or account settings)
> - installing, upgrading, or removing packages or programs
> - spending money, or calling a paid service
> - sending anything outside this machine (email, posts, uploads)
> - anything else that's hard to undo
>
> If you're unsure whether a step counts, ask. `git push` is blocked: if the task needs one, say so in your summary and the user pushes.

- **It reuses the NEED path.** `SessionTaskAgent` already turns `NEED:` into a `need` report, and the task waits for your answer. Your answer continues it (`SendToTask`). Nothing new is needed in the Hub or the Talker.
- **How the pause shows:**
  - In the Talker pane, a `need` whose text starts with `Risky:` shows as an amber card: "⚠ Risky step, paused: …". You answer in words or with Go ahead / Don't buttons, and the buttons send the same answer as typing it would.
  - The Talker says it out loud too, so voice and glasses get it.
  - In the worker pane, it shows as "paused: risky step".
- **The rule is in the prompt only in Auto.** In Manual, risky shell steps already ask through the card, and the rule would double the questions.

**This is not a guarantee.** The pause depends on the model judging each step correctly, every time. It can miss a step that is risky, for example a delete inside a script, a command whose effect it misreads, or a long task where the rule fades from its attention. Auto trusts the Main Assistant the way bypass mode trusts Claude Code. Use it for tasks you'd be fine with running unattended. The transcript and the worker pane show what it did. The `git push` block is the one hard limit, and it only catches a direct `git push` command.

### 3. When a switch takes effect

- **Per session (the normal case):** each task already starts a fresh `claude` process, and so does each handoff. `ClaudeSession` takes its command as a callable that it reads on every `start`, so a new session gets the current mode's flags and prompt together. This costs nothing extra.
- **To Auto while a task runs:** it applies from the next task (or the next handoff session), because the risky-step rule lives in the session's prompt, which is fixed when the session starts. The UI shows "Auto from the next task".
- **To Manual while a task runs:** it applies at once, through the `set_permission_mode` control request (confirmed by the spike), when the running session is in Auto. If Auto was still waiting for the next task, the session is already in Manual and nothing is sent. If the request fails, it applies from the next task, and the UI says so.
- **No app restart is ever needed** to switch. Getting this feature at all needs one restart.

### 4. Where the button lives: the Talker pane of the temp UI, marked as a stand-in

- **Now:** a toggle in the Talker pane's header, `Main Assistant: Manual | Auto`. Its tooltip and the code comment say it's a stand-in. It sets what the Main Assistant may do. It sits on the Talker's side because the Talker side is where you answer permission requests already.
- **The Talker is told the mode.** It gets `PermissionModeChanged` and puts a short `[Mode] worker: auto (from the next task)` line before your next message, once, like the `[Viewer]` note. Its prompt says the worker starts in Manual at every launch. So it knows the mode, can tell you, and mentions Auto when it hands over a task.
- **Later:** the button only sends `SetPermissionMode` and shows `PermissionModeChanged`, so the control panel and the chat window reuse both as they are. When the permissions handler is built, it owns the mode as a grant per module ("main_assistant: auto") and handles `SetPermissionMode` in place of the Hub. No UI changes then.

### 5. Reusable parts: what's reused and what's new

**Reused:** `claude_command` (it already takes `permission_mode`), `ClaudeSession`, `SessionTaskAgent` and its `NEED` handling, `path_rule`, the Hub route (it handles `SetPermissionMode` the same way as `AnswerPermission`), `SendToTask` for your answer to a risky-step pause, the Event Bus, `agent_tags` (for the Talker's `<<MODE: manual>>`), and the temp UI's SSE "current state" items (the usage meters work the same way).

**New:**

| Item | Kind | Where |
|------|------|-------|
| `PermissionMode` (`manual`, `auto`) | enum | `contracts/agents.py` |
| `SetPermissionMode(agent_id, mode)` | command, handled by the Agent Hub | `contracts/agents.py` |
| `PermissionModeChanged(agent_id, mode, applies: "now" \| "next_task")` | event, for the UIs and the Talker | `contracts/agents.py` |
| `ITaskAgent.set_permission_mode(mode) -> Result` | contract method with a default that refuses (`not_available`); implemented in `SessionTaskAgent` | `contracts/agents.py` |
| `AgentInfo.permission_mode` | field, so `ListAgents` shows it | `contracts/agents.py` |
| `ClaudeSession(command=callable)` and `set_permission_mode(mode)` | the command read on each start; the control request | `infra/claude_session.py` |
| `claude_command(disallowed=...)` | argument (`--disallowedTools`, separate arguments), for the `git push` block in Auto | `infra/claude_session.py` |
| `build_command(config, workspace, mode)` | the worker's command line and prompt for a mode | `modules/main_assistant/module.py` |

- **Where the mode is stored:** in memory, in `SessionTaskAgent`.
- **Index:** each new part is in `docs/api/reusable.md` with its Used by line, checked against the imports.

### 6. Build steps and tests

1. **Spike:** done, passed (see the findings above).
2. **Contracts**, 3. **`infra`**, 4. **`SessionTaskAgent`**, 5. **`main_assistant`**, 6. **`agent_hub`**, 7. **`talker`**, 8. **`temp_ui`** (module and `page.html`): done.
9. **Tests:** done, `tests/test_permission_mode.py`:
   - `build_command` per mode: acceptEdits with no `--disallowedTools` and no risky rule, against bypassPermissions with the four `AUTO_BLOCKED` rules as separate arguments and the risky rule; both keep the standing rules and the prompt tool
   - `ClaudeSession` calls a callable command on every start
   - Manual at launch in `ListAgents`; the Hub refuses an unknown agent
   - Auto when idle applies now, and the session's command is built for Auto; the task then starts in Auto, Manual mid-task sends one `set_permission_mode` control request (`acceptEdits`, seen in the transcript) and applies now, and Auto mid-task applies from the next task
   - the Talker: `<<MODE: auto>>` gets the `[Status]` and the mode stays Manual; after your Auto switch it hears `[Mode] worker: auto` once, and `<<MODE: manual>>` switches back
   - the temp UI: `POST /permission-mode` gives `ok`, plus the `mode` state item, the `note`, the `risky` card, and the worker lines
10. **Docs**, the docs build, and this note set to done: done.

### 7. Safety

- **The default stays Manual,** at every launch and whatever happened in the last one.
- **The mode is always visible.** In Auto, the Talker pane's header turns amber and reads "Main Assistant: AUTO, no permission prompts", the worker pane shows the same tag, and the Talker knows the mode.
- **Switching to Auto takes a deliberate click:** a confirm dialog says Auto gives full permissions except `git push`, that the Main Assistant pauses before risky steps on its own judgment only, and that this is not a guarantee. Switching back to Manual is one click, with no dialog.
- **Only you switch to Auto.** The Main Assistant has no route to `SetPermissionMode`, and the Talker can only switch to Manual.
- **`git push` is refused in Auto,** not asked about. You push yourself.
- **Every switch is logged,** in both panes and in the log.

## Next

- **Restart the app** to get the mode (and the earlier `config/default.toml` permission changes).
- **A manual try** with the real worker: switch to Auto, give it a harmless task with one risky step (say, deleting a scratch folder it made), and check that it pauses with `NEED: Risky:` and that the amber card shows.
