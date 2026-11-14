"""Stand-in orchestrator: replies with the input text. `/tools` lists the available tools.

Exists to prove the plumbing; replace it by enabling a different orchestrator in config.
Its menu has one item, `echo.say`, the smallest example of a module menu. `/tools` reads the
menus through the directory (`ListModules`, `GetMenu`, the core's own as `core`), like any
caller, plus the modules that provide `IToolProvider` themselves.
"""

from __future__ import annotations

from assistant.contracts import (
    GetMenu,
    InputReceived,
    IToolProvider,
    ListModules,
    Manifest,
    Menu,
    ModuleContext,
    ModuleProtocol,
    ModuleState,
    ResponseReady,
    Result,
)

menu = Menu()


class EchoOrchestrator(ModuleProtocol):
    manifest = Manifest(
        id="echo_orchestrator",
        description="Stand-in orchestrator: echoes, /tools",
        optional=(IToolProvider,),
        sends=(ListModules, GetMenu),
        publishes=(ResponseReady,),
        listens=(InputReceived,),
    )
    menu = menu

    async def init(self, ctx: ModuleContext) -> None:
        self._ctx = ctx
        ctx.subscribe(InputReceived, self._on_input)

    @menu.item("echo.say", "Echo the text back", {"text": {"type": "string"}}, required=["text"])
    async def say(self, text: str) -> Result:
        return Result.ok(f"Echo: {text}")

    async def _tool_names(self) -> list[str]:
        names = [spec.name for provider in self._ctx.get_all(IToolProvider) for spec in provider.tools()]
        listed = await self._ctx.send(ListModules())
        ids = [m.id for m in (listed.value or []) if m.state is ModuleState.ACTIVE] if listed.is_ok else []
        for module_id in [*ids, "core"]:
            menu_result = await self._ctx.send(GetMenu(module_id=module_id))
            names += [spec.name for spec in (menu_result.value or [])] if menu_result.is_ok else []
        return names

    async def _on_input(self, event: InputReceived) -> None:
        if event.text == "/tools":
            names = await self._tool_names()
            reply = "Tools: " + ", ".join(names) if names else "No tools available."
        else:
            reply = f"Echo: {event.text}"
        self._ctx.publish(ResponseReady(text=reply, conversation_id=event.conversation_id, correlation_id=event.id))
