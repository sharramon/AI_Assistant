# Tools

Capabilities invocable by name, by the AI or any module. All items: `from assistant.contracts import ...`. Back to the [API index](README.md).

## `IToolProvider`

`class IToolProvider(Contract)`

A contract for modules that offer tools. Any number of modules may provide it (`multiple = True`). Declare it in `manifest.provides` and call `ctx.provide(IToolProvider, self)` in `init`.

### `IToolProvider.tools`

`tools(self) -> list[ToolSpec]`

Abstract. The tools currently offered. Called on every lookup, never cached, so the list may change at runtime.

### `IToolProvider.invoke`

`async invoke(self, name: str, args: dict[str, Any]) -> Result`

Abstract. Run tool `name`. Called by the core when an [`InvokeTool`](#invoketool) command arrives for one of this provider's tools, with the command's timeout and cancellation applying.

**Returns:** a [`Result`](messaging.md#result). Use `Result.invalid_arguments` for bad `args`.

**Example**

    class Calculator(Module, IToolProvider):
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
