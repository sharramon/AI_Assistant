"""A module's menu: the actions an assistant or another module may call on it.

A `Menu` is plain data built when the module's file is imported, so the core can read it
without starting the module (for the directory and the generated module library). When the
module is on, the core links the menu to that copy and calls its methods through `InvokeTool`,
after checking the arguments against each item's schema. Reloading a module re-imports its
file, so a reloaded module's menu runs its new methods.

    menu = Menu()

    class HtmlViewerModule(ModuleProtocol):
        manifest = Manifest(id="html_viewer", ...)
        menu = menu

        @menu.item("viewer.open", "Open an HTML file in the viewer",
                   {"path": {"type": "string"}}, required=["path"])
        async def open(self, path: str) -> Result: ...

Every call knows its caller (`InvokeTool.caller`: the sending module, or the agent the module
door proved). An item may list the `callers` allowed to use it; a method with a `caller`
parameter receives it (it is never one of the item's properties).
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from assistant.contracts.messages import Result
from assistant.contracts.tools import ToolSpec

# JSON Schema type name -> the Python types that satisfy it (bool is not an integer here).
_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "boolean": (bool,),
    "integer": (int,),
    "number": (int, float),
    "array": (list, tuple),
    "object": (dict,),
    "null": (type(None),),
}


@dataclass(frozen=True)
class MenuItem:
    """One action: its `ToolSpec`, the name of the module method that runs it, who may use it
    (`callers`, empty for anyone), and whether the method takes the `caller`."""

    spec: ToolSpec
    method: str
    callers: tuple[str, ...] = ()
    takes_caller: bool = False


class Menu:
    """The actions a module offers, one item per action. Declare it once per module class."""

    def __init__(self) -> None:
        self._items: dict[str, MenuItem] = {}

    def item(
        self,
        name: str,
        description: str,
        properties: Mapping[str, dict[str, Any]] | None = None,
        required: Iterable[str] = (),
        callers: Iterable[str] = (),
    ) -> Callable[[Callable], Callable]:
        """Decorate an async module method that returns a `Result`; its keyword arguments are
        the item's `properties` (JSON Schema per argument), `required` the ones it must get.
        `callers`: the only callers allowed (module or agent ids); empty means anyone."""
        properties = dict(properties or {})
        required = list(required)
        callers = tuple(callers)
        if name in self._items:
            raise ValueError(f"menu item {name!r} is declared twice")
        if "\n" in description or not description.strip():
            raise ValueError(f"menu item {name!r}: description must be one line of text")
        if "caller" in properties:
            raise ValueError(f"menu item {name!r}: 'caller' is passed by the core, not a property")
        missing = [r for r in required if r not in properties]
        if missing:
            raise ValueError(f"menu item {name!r}: required {missing} not in its properties")
        schema: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required

        def mark(method: Callable) -> Callable:
            takes_caller = "caller" in inspect.signature(method).parameters
            spec = ToolSpec(name=name, description=description, input_schema=schema)
            self._items[name] = MenuItem(spec, method.__name__, callers, takes_caller)
            return method

        return mark

    def items(self) -> list[MenuItem]:
        return list(self._items.values())

    def specs(self) -> list[ToolSpec]:
        """Every item as a `ToolSpec`, in the order they were declared."""
        return [item.spec for item in self._items.values()]

    def names(self) -> list[str]:
        return list(self._items)

    def allowed(self, name: str, caller: str) -> bool:
        """Whether `caller` may use item `name` (any caller when the item lists none)."""
        item = self._items.get(name)
        return item is not None and (not item.callers or caller in item.callers)

    def check(self, name: str, args: Mapping[str, Any]) -> str | None:
        """What's wrong with `args` for item `name`, or None when they fit its schema."""
        item = self._items.get(name)
        if item is None:
            return f"no menu item {name!r}"
        if not isinstance(args, Mapping):
            return f"{name}: arguments must be an object"
        schema = item.spec.input_schema
        properties = schema.get("properties", {})
        for arg in schema.get("required", ()):
            if arg not in args or args[arg] is None:
                return f"{name} needs {arg!r}"
        for arg, value in args.items():
            prop = properties.get(arg)
            if prop is None:
                return f"{name} takes no argument {arg!r}"
            problem = _check_value(prop, value)
            if problem:
                return f"{name}: {arg!r} {problem}"
        return None

    async def call(self, module: Any, name: str, args: Mapping[str, Any], caller: str = "") -> Result:
        """Check the caller and `args`, then run item `name` on `module` (a running copy)."""
        item = self._items.get(name)
        if item is not None and not self.allowed(name, caller):
            return Result.not_available(f"{name} is only for: {', '.join(item.callers)}")
        problem = self.check(name, args)
        if problem:
            return Result.invalid_arguments(problem)
        method = getattr(module, item.method)
        result = await (method(**args, caller=caller) if item.takes_caller else method(**args))
        return result if isinstance(result, Result) else Result.ok(result)


def _check_value(prop: dict[str, Any], value: Any) -> str | None:
    kind = prop.get("type")
    if kind is not None:
        kinds = kind if isinstance(kind, list) else [kind]
        allowed = tuple(t for k in kinds for t in _TYPES.get(k, (object,)))
        if not isinstance(value, allowed) or (isinstance(value, bool) and "boolean" not in kinds):
            return f"must be {' or '.join(kinds)}"
    if "enum" in prop and value not in prop["enum"]:
        return f"must be one of {prop['enum']}"
    if isinstance(value, str):
        if len(value.strip()) < prop.get("minLength", 0):
            return "can't be empty" if prop.get("minLength") == 1 else f"needs at least {prop['minLength']} characters"
    return None
