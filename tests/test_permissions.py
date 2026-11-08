"""The ctx.permissions stand-in: allows everything, logs the first use of each permission."""

import logging

from assistant.contracts import Manifest, ModuleContext, ModuleProtocol
from assistant.core import App
from assistant.core.permissions import PermissionsPort
from tests.support import make_config

LOGGER = "assistant.core.permissions"


def records(caplog, level=logging.WARNING):
    return [r.getMessage() for r in caplog.records if r.name == LOGGER and r.levelno == level]


async def test_has_and_request_allow_any_name():
    perms = PermissionsPort("map")
    assert perms.has("location")
    assert await perms.request("files.write:src", reason="Fix the bug")


async def test_first_use_warns_with_module_and_reason(caplog):
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    perms = PermissionsPort("voice_in")
    await perms.request("microphone", reason="You clicked the mic")
    assert records(caplog) == ["not checked yet: allowing voice_in microphone (You clicked the mic)"]


async def test_later_uses_of_the_same_permission_log_at_debug(caplog):
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    perms = PermissionsPort("map")
    perms.has("location")
    perms.has("location")
    await perms.request("location")
    perms.has("network")
    assert records(caplog) == [
        "not checked yet: allowing map location",
        "not checked yet: allowing map network",
    ]
    assert len(records(caplog, logging.DEBUG)) == 2


class Asker(ModuleProtocol):
    manifest = Manifest(id="asker", optional_permissions=("microphone",))

    async def init(self, ctx: ModuleContext) -> None:
        self.allowed = await ctx.permissions.request("microphone", reason="test")


class OtherAsker(Asker):
    manifest = Manifest(id="other_asker")


async def test_each_module_context_is_bound_to_its_own_id(caplog):
    caplog.set_level(logging.WARNING, logger=LOGGER)
    app = App([Asker, OtherAsker], make_config("asker", "other_asker"))
    await app.start()
    await app.stop()
    assert sorted(records(caplog)) == [
        "not checked yet: allowing asker microphone (test)",
        "not checked yet: allowing other_asker microphone (test)",
    ]


def test_manifest_permission_fields():
    assert Manifest(id="plain").permissions == ()
    assert Manifest(id="plain").optional_permissions == ()
    m = Manifest(id="map", permissions=("location",), optional_permissions=("network",))
    assert m.permissions == ("location",)
    assert m.optional_permissions == ("network",)
