"""Stand-in orchestrator: replies with the input text. `/tools` lists the available tools.

Exists to prove the plumbing; replace it by enabling a different orchestrator in config.
"""

from __future__ import annotations

from assistant.contracts import InputReceived, Manifest, Module, ModuleContext, ResponseReady, ToolProvider


class EchoOrchestrator(Module):
    manifest = Manifest(id="echo_orchestrator", optional=(ToolProvider,))

    async def init(self, ctx: ModuleContext) -> None:
        self._ctx = ctx
        ctx.subscribe(InputReceived, self._on_input)

    async def _on_input(self, event: InputReceived) -> None:
        if event.text == "/tools":
            names = [spec.name for provider in self._ctx.get_all(ToolProvider) for spec in provider.tools()]
            reply = "Tools: " + ", ".join(names) if names else "No tools available."
        else:
            reply = f"Echo: {event.text}"
        self._ctx.publish(ResponseReady(text=reply, conversation_id=event.conversation_id, correlation_id=event.id))
