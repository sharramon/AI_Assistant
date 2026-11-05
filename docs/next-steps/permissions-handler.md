# Permissions handler

> **Status: proposed (2026-10-26).** Design: [Permissions](../architecture/permissions.md). Since 2026-11-02 ([reusable parts](archive/reusable-parts.md#decided)) the `ctx.permissions` stand-in comes first (allow and log; built 2026-11-02, [note](archive/permissions-stand-in.md)); this handler later plugs in behind it, with no module changes.

**Asked:** "Should permissions work through its own permissions handler? Since different sub-apps / functionality will need different permissions?" Each module should get only what it needs (a map feature gets location, nothing else does), and a missing permission should only affect the module that needs it.

**Why:**
- Today only the Main Assistant can ask for permission, and it goes through the Agent Hub. Other modules (location, microphone, accounts) will need the same thing.
- Giving the whole app every permission means any feature can use anything.

**Touches:** the core (`Manifest`, `ModuleContext`, `ScopedContext`, `LifecycleManager`, a `blocked` module state), new contracts (`IPermissions`, `IPermissionSource`, the messages), a new `permissions` module, `main_assistant`, `SessionTaskAgent`, `agent_hub` (its permission part goes away), `talker`, `temp_ui`, and the docs for each.

**Also asked:** mark which parts are the core app and which are modules, as guardrails for the Main Assistant writing its own code. Recorded as [repo zones](../architecture/permissions.md#repo-zones); core and modules share one rule for now.

**Approach:** see [Permissions](../architecture/permissions.md). In short: every module calls `ctx.permissions.has` / `request`; the core fills in which module is asking; the handler checks what the app has and what you've granted, and asks you otherwise.

**Open questions:** listed on the [design page](../architecture/permissions.md#open-questions).
