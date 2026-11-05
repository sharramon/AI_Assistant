# Tools

Capabilities invocable by name, by the AI or any module. All items: `from assistant.contracts import ...`. Back to the [API index](README.md).

**A module offers tools with a [`Menu`](modules.md#menu)**, not by providing `IToolProvider` itself: the core links each running module's menu to `IToolProvider` through its adapter [`MenuTools`](core.md#menutools), so `InvokeTool` reaches it. `IToolProvider` stays for providers whose tools change at runtime (a remote client's, later), and for tests.

## `IToolProvider`

**Reusable** · Used by: the core's `MenuTools` (every module menu); the core's `dispatch_tool`, `talker`, `temp_ui` and `echo_orchestrator` call through `InvokeTool` or list the tools

`class IToolProvider(Contract)`

A contract for things that offer tools. Any number may be provided (`multiple = True`). A module with a fixed set of actions uses a [`Menu`](modules.md#menu) instead; providing `IToolProvider` directly means declaring it in `manifest.provides` and calling `ctx.provide(IToolProvider, self)` in `init`.

### `IToolProvider.tools`

`tools(self) -> list[ToolSpec]`

Abstract. The tools currently offered. Called on every lookup, never cached, so the list may change at runtime.

### `IToolProvider.invoke`

`async invoke(self, name: str, args: dict[str, Any]) -> Result`

Abstract. Run tool `name`. Called by the core when an [`InvokeTool`](#invoketool) command arrives for one of this provider's tools, with the command's timeout and cancellation applying.

**Returns:** a [`Result`](messaging.md#result). Use `Result.invalid_arguments` for bad `args`.

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

`InvokeTool(name: str, args: dict[str, Any] = {})` (command)

Run the tool called `name`. Handled by the core, which routes it to the provider currently offering that tool.

**Returns:** the provider's `Result`, or `not_available` if no provider offers `name`, or `failed` if more than one does.

**Example**

    result = await ctx.send(InvokeTool(name="add", args={"a": 1, "b": 2}), timeout=10)

**Defined in:** `src/assistant/contracts/tools.py`

## Tools offered today

Every item of every module's menu; the [module library](../architecture/module-library.md) lists them per module (generated). Arguments are checked against the item's schema first: a missing or empty required one, a wrong type or an unknown one gives `invalid_arguments`.

| Tool | Provider | Args | Returns |
|------|----------|------|---------|
| `echo.say` | `echo_orchestrator` (off by default) | `{"text": str}` | `ok("Echo: <text>")`; the smallest example of a menu |
| `viewer.open` | `html_viewer` | `{"path": str, "front"?: bool}` | Opens an HTML file in the [HTML viewer](../architecture/html-viewer.md), starting it if needed; switches to the file's tab if it's open, and reloads it if the file changed. `path` should be absolute: a relative one resolves against the app's folder. `front` (default false; the chat's button sends true) brings the viewer window to the front, or opens a new one if it was closed; leave it off for pages an agent opens on its own. `ok({"tab", "path", "reloaded"})`; `invalid_arguments` for a missing file; `failed` if the viewer can't start or refuses the file (not HTML) |
| `viewer.highlight` | `html_viewer` | `{"path": str, "text": str, "heading"?: str, "front"?: bool}` | Opens the file like `viewer.open` (including `front`) and highlights `text`, a short quote of the page's words (case and whitespace ignored), in `heading`'s section if given; scrolls to it. Highlights stay until you clear them and are never saved into the file. `ok({"tab", "path", "found", "matches"})`; `found` false means the file is open but the quote isn't on the page; `invalid_arguments` without a path or text, or for a missing file |
| `modules.list`, `modules.menu`, `modules.on`, `modules.off`, `modules.reload`, `modules.add` | the core (id `core`) | see [the core's menu](control.md#the-cores-menu) | the matching control command's result |
| `viewer.tabs` | `html_viewer` | none | `ok([{"path", "active", "unsaved", "highlights"}])` (`highlights`: the quoted texts), empty if the viewer isn't running |
