"""The manifest carries a module's description and its inputs and outputs, checked when it's made."""

import importlib
import logging

import pytest

from assistant.contracts import (
    InputReceived,
    Manifest,
    ModuleContext,
    ModuleProtocol,
    Result,
    StartListening,
)
from assistant.core import App
from assistant.core.loader import find_module_class

from .test_module_docs import module_ids


def test_new_fields_default_to_empty():
    m = Manifest(id="plain")
    assert (m.description, m.handles, m.sends, m.publishes, m.listens) == ("", (), (), (), ())


@pytest.mark.parametrize(
    "fields",
    [
        {"handles": (InputReceived,)},  # an event where a command belongs
        {"publishes": (StartListening,)},  # a command where an event belongs
        {"listens": ("InputReceived",)},  # a name, not a type
    ],
)
def test_wrong_kinds_are_refused(fields):
    with pytest.raises(TypeError):
        Manifest(id="bad", **fields)


@pytest.mark.parametrize("fields", [{"id": "has space"}, {"id": ""}, {"id": "ok", "description": "two\nlines"}])
def test_bad_id_or_description_is_refused(fields):
    with pytest.raises(ValueError):
        Manifest(**fields)


class Unlisted(ModuleProtocol):
    manifest = Manifest(id="unlisted")

    async def init(self, ctx: ModuleContext) -> None:
        ctx.handle(StartListening, self._start)

    async def _start(self, command: StartListening) -> Result:
        return Result.ok()


class Listed(Unlisted):
    manifest = Manifest(id="listed", handles=(StartListening,))


@pytest.mark.parametrize("module, warned", [(Unlisted, True), (Listed, False)])
async def test_handling_an_unlisted_command_warns(module, warned, caplog):
    app = App(available=[module], config={"modules": {"enabled": [module.manifest.id]}})
    with caplog.at_level(logging.WARNING):
        await app.start()
        await app.stop()
    assert ("without listing it in manifest.handles" in caplog.text) is warned


@pytest.mark.parametrize("module_id", module_ids())
def test_every_module_describes_itself(module_id):
    cls = find_module_class(importlib.import_module(f"assistant.modules.{module_id}"), module_id)
    assert issubclass(cls, ModuleProtocol)
    assert cls.manifest.description, f"{module_id} has no manifest.description"
