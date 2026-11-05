"""Stand-in orchestrator: replies with the input text. `/tools` lists the available tools.

Exists to prove the plumbing; replace it by enabling a different orchestrator in config.
Its menu has one item, `echo.say`, the smallest example of a module menu.
"""

from __future__ import annotations

from assistant.contracts import (
    InputReceived,
    IToolProvider,
    Manifest,
    Menu,
    ModuleContext,
    ModuleProtocol,
    ResponseReady,
    Result,
)

menu = Menu()


class EchoOrchestrator(ModuleProtocol):
    manifest = Manifest(
        id="echo_orchestrator",
        description="Stand-in orchestrator: echoes, /tools",
        optional=(IToolProvider,),
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

    async def _on_input(self, event: InputReceived) -> None:
        if event.text == "/tools":
            names = [spec.name for provider in self._ctx.get_all(IToolProvider) for spec in provider.tools()]
            reply = "Tools: " + ", ".join(names) if names else "No tools available."
        else:
            reply = f"Echo: {event.text}"
        self._ctx.publish(ResponseReady(text=reply, conversation_id=event.conversation_id, correlation_id=event.id))
