# Tools

Capabilities invocable by name, by the AI or any module. All items: `from assistant.contracts import ...`. Back to the [API index](README.md).

**A module offers tools with a [`Menu`](modules.md#menu)**, not by providing `IToolProvider` itself: the core links each running module's menu through its adapter [`MenuTools`](core.md#menutools) into its own private [`MenuTable`](core.md#menutable), so `InvokeTool` reaches it. **Menus are never in the container** (G16): no module can look one up as a plain `IToolProvider` and call it with a caller of its choosing. `IToolProvider` stays for providers whose tools change at runtime (a remote client's, later), and for tests.

## `IToolProvider`

**Reusable** · Used by: the core's `MenuTools` (every module menu, in the `MenuTable`); the core's `dispatch_tool`, `talker`, `temp_ui` and `echo_orchestrator` call through `InvokeTool` or list the tools (`echo_orchestrator`'s `/tools`: `get_all(IToolProvider)` plus `ListModules` / `GetMenu`)

`class IToolProvider(Contract)`

A contract for things that offer tools. Any number may be provided (`multiple = True`). A module with a fixed set of actions uses a [`Menu`](modules.md#menu) instead; providing `IToolProvider` directly means declaring it in `manifest.provides` and calling `ctx.provide(IToolProvider, self)` in `init`. Such a provider is in the container, and `dispatch_tool` finds it there as well as in the menu table. It checks its own arguments: the gate's argument and `callers` checks are a menu's.

### `IToolProvider.tools`

`tools(self) -> list[ToolSpec]`

Abstract. The tools currently offered. Called on every lookup, never cached, so the list may change at runtime.

### `IToolProvider.invoke`

`async invoke(self, name: str, args: dict[str, Any]) -> Result`

Abstract. Run tool `name`. Called by the core when an [`InvokeTool`](#invoketool) command arrives for one of this provider's tools, with the command's timeout and cancellation applying.

**Returns:** a [`Result`](messaging.md#result). Use `Result.invalid_arguments` for bad `args`.

### `IToolProvider.invoke_as`

`async invoke_as(self, name: str, args: dict[str, Any], caller: str) -> Result`

Not abstract. `invoke` with the caller ([`InvokeTool.caller`](#invoketool)); the core's `dispatch_tool` calls this. The default ignores `caller` and calls `invoke`. [`MenuTools`](core.md#menutools) overrides it to pass the caller to [`Menu.call`](modules.md#menu).

**Example**

    class Calculator(ModuleProtocol, IToolProvider):
        manifest = Manifest(id="calculator", provides=(IToolProvider,))

        async def init(self, ctx):
            ctx.provide(IToolProvider, self)

        def tools(self):
            return [ToolSpec(
                name="add",
                description="Add a and b",
                input_schema={"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}}, "required": ["a", "b"]},
            )]

        async def invoke(self, name, args):
            try:
                return Result.ok(args["a"] + args["b"])
            except KeyError as exc:
                return Result.invalid_arguments(f"missing argument {exc}")

**Defined in:** `src/assistant/contracts/tools.py`
**See also:** [`dispatch_tool`](core.md#dispatch_tool)

## `ToolSpec`

`ToolSpec(name: str, description: str, input_schema: dict = {"type": "object", "properties": {}})`

Describes one tool. Frozen.

**Fields**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `name` | `str` | yes | Unique across all providers |
| `description` | `str` | yes | What it does; shown to the AI |
| `input_schema` | `dict` | no | JSON Schema for `args`, in the format Claude tool use accepts |

**Defined in:** `src/assistant/contracts/tools.py`

## `InvokeTool`

`InvokeTool(name: str, args: dict[str, Any] = {}, caller: str = "")` (command)

Run the tool called `name`. Handled by the core, which routes it to the provider currently offering that tool (`invoke_as`, with `caller`), through [the ask-first gate](#the-ask-first-gate).

**Who sets `caller`:** the sender's context does. `ScopedContext.send` always overwrites it with the sending module's id, so a module can't pass itself off as another. Only the core's own [door](#imoduledoor) passes on another: the caller its token proved (an agent's id, e.g. `talker` or `main_assistant`), sent through the router as the core's own send. Empty when sent straight to the router (tests, the core itself). Menu items use it to decide who may call them ([`Menu`](modules.md#menu) `callers`), and the gate to decide whether to ask.

**Returns:** the provider's `Result`, or `not_available` if no provider offers `name`, or `failed` if more than one does. When `name` is on the menu of a module that's off (and not started on use), the `not_available` error says so: "The <id> module isn't on, so '<name>' can't run. Ask the user whether to turn <id> on; on their yes, use modules.on with module_id '<id>', then call '<name>' again" (`module_off_text` in `core/tools.py`). Every agent's prompt (`BASICS_BLOCK`) tells it to ask the user and, on their yes, run `modules.on` itself. Any other unknown name: "No tool named '<name>'". An item that asks first returns "Asked the user on a card (<id>) to confirm …" at once (below).

**Example**

    result = await ctx.send(InvokeTool(name="add", args={"a": 1, "b": 2}), timeout=10)

**Defined in:** `src/assistant/contracts/tools.py`

## The ask-first gate

**Reusable** · Used by: the core's `dispatch_tool` (every `InvokeTool`, from a module or through the door: the Talker's `use_item` too, G14); the core's menu marks `modules.add`, `modules.remove`, `modules.reload` (`ask="always"`) and `modules.off` (`ask="always", ask_when="with_dependents"`) · decision D4

One checked gate for every menu call, in [`dispatch_tool`](core.md#dispatch_tool). A menu item may be marked `ask` ([`Menu.item`](modules.md#menu)):

1. A tool nobody offers, on the menu of a module that is off and has `start_on_use`, turns that module on first. This runs before the `callers` check, so a caller the item refuses can still switch the module on.
2. The arguments are checked against the item's schema, then its `callers`: a bad or forbidden call never reaches a card (`invalid_arguments`, `not_available`). For an item that asks, the gate checks before the card; for any other item, `Menu.call` checks the same way.
3. The item asks only when `MenuItem.asks(args)` is true: it has an `ask` mark and, with `ask_when`, that boolean argument is true.
4. The core's permissions handler [`confirm`](core.md#permissionshandler)s it on a `confirm` card ([`PermissionRequested`](messaging.md#permissionrequested), `action="confirm"`, the reason naming the call: `modules.add (package: x)`). A caller that is you (`[core.permissions] you`, `temp_ui` by default) runs at once. `ask="always"`: **Auto never skips it**. `ask="risky"`: a caller the [Callers port](core.md#callers) holds in Auto runs at once.
5. The call returns `ok` at once ("Asked the user on a card (<id>) to confirm …; the answer reaches you as a note"), since the router's 30 s timeout would cut a waiting call. On Allow the handler runs the call itself and the outcome reaches the caller as an [`AgentNotice`](agents.md#agentnotice); on Deny nothing runs.

No module item is marked `risky` ([decisions](../architecture/decisions.md)). The core's menu sends each control command as `core`, so the card stands in for the control-command check; `modules.off` without `with_dependents` shows no card. The agents' own Claude Code tool asks stay as they are; an agent's `RELOAD:` / `ADD_MODULE:` line keeps its own permission card, in Auto too ([`PermissionGate.ask(always=True)`](infra.md#permissiongate)).

    @menu.item("modules.off", "Turn a module off", {"module_id": {"type": "string"}, "with_dependents": {"type": "boolean"}},
               required=["module_id"], ask="always", ask_when="with_dependents")
    async def off(self, module_id: str, with_dependents: bool = False) -> Result: ...

**Defined in:** `src/assistant/core/tools.py` (`dispatch_tool`), `src/assistant/contracts/menu.py` (`MenuItem.ask`, `ask_when`, `asks`) · **Tests:** `tests/test_risky_steps_ask.py`

## `IModuleDoor`

**Reusable** · Used by: the core provides (`CoreDoor`, decision D1); `main_assistant`, `talker` and every `ProfileAgent` read it at each session start

`class IModuleDoor(Contract)`, single provider, in `assistant.contracts`.

| Method | Does |
|--------|------|
| `mcp_config(caller: str) -> dict` | The `--mcp-config` for one `claude` session of `caller` (the agent's id): the door's stdio relay ([`mcp_door`](infra.md#mcp_door)) with a token made for that caller, or `{}` while it's down. Pass it to [`claude_command(mcp_config=...)`](infra.md#claude_command). Every `use_item` the session makes reaches the menus as an `InvokeTool` with that caller; a session can't claim another name |

**A module asks only for itself or for an agent it claimed** (G11): its context hands it a [`ModuleDoor`](core.md#coredoor-moduledoor) bound to its id, not the core's own door. `mcp_config(caller)` for any other caller logs a warning and returns `{}`. Claim the agent's id first with [`IAgentNames.claim`](agents.md#iagentnames). The door opens before any module starts (`[core.door]`), so an agent's first session has it.

    door = ctx.get_one(IModuleDoor)            # a ModuleDoor bound to this module
    config = door.mcp_config(self.agent_id)    # {} unless agent_id is this module or one it claimed

The session then has three fixed tools, the same whatever modules are on: `mcp__modules__list_modules` (one line per module, plus `core`), `mcp__modules__show_menu(module_id)` (that module's `ToolSpec`s) and `mcp__modules__use_item(name, args)` (`InvokeTool`). They go through the core (door → router → gate), so the directory, the menus' argument checks, the ask-first gate, permissions and hot swap all apply. Modules never provide it: MCP stays at the agents' edge.

**Defined in:** `src/assistant/contracts/door.py` · **Tests:** `tests/test_mcp_door.py`

## Tools offered today

Every item of every module's menu; the [module library](../architecture/module-library.md) lists them per module (generated). Arguments are checked against the item's schema first: a missing or empty required one, a wrong type or an unknown one gives `invalid_arguments`.

| Tool | Provider | Args | Returns |
|------|----------|------|---------|
| `echo.say` | `echo_orchestrator` (off by default) | `{"text": str}` | `ok("Echo: <text>")`; the smallest example of a menu |
| `viewer.open` | `html_viewer` | `{"path": str, "front"?: bool}` | Opens an HTML file in the [HTML viewer](../../src/assistant/modules/html_viewer/docs/viewer-app.md), starting it if needed; switches to the file's tab if it's open, and reloads it if the file changed. `path` should be absolute: a relative one resolves against the app's folder. `front` (default false; the chat's button sends true) brings the viewer window to the front, or opens a new one if it was closed; leave it off for pages an agent opens on its own. `ok({"tab", "path", "reloaded"})`; `invalid_arguments` for a missing file; `failed` if the viewer can't start or refuses the file (not HTML) |
| `viewer.highlight` | `html_viewer` | `{"path": str, "text": str, "heading"?: str, "front"?: bool}` | Opens the file like `viewer.open` (including `front`) and highlights `text`, a short quote of the page's words (case and whitespace ignored), in `heading`'s section if given; scrolls to it. Highlights stay until you clear them and are never saved into the file. `ok({"tab", "path", "found", "matches"})`; `found` false means the file is open but the quote isn't on the page; `invalid_arguments` without a path or text, or for a missing file |
| `modules.list`, `modules.menu`, `modules.docs`, `modules.on`, `modules.off`, `modules.reload`, `modules.add`, `modules.remove`; `permissions.grants`, `permissions.grant`, `permissions.request`, `permissions.revoke` | the core (id `core`) | see [the core's menu](control.md#the-cores-menu) | the matching control command's result; `modules.add / remove / reload`, and `modules.off` with dependents, ask first |
| `hub.agents`, `hub.status`, `hub.start`, `hub.send`, `hub.cancel`, `hub.focus`, `hub.suggest_focus`, `hub.answer`, `hub.mode` | `agent_hub` | see [the Hub's menu](agents.md#the-hubs-menu) | some items are for one caller only |
| `talker.reset` | `talker` | `{"session": str}` | Starts that Talker session fresh; only for a caller that is you (`IAgentNames.is_you`), else `not_available` |
| `viewer.tabs` | `html_viewer` | none | `ok([{"path", "active", "unsaved", "highlights"}])` (`highlights`: the quoted texts), empty if the viewer isn't running |
