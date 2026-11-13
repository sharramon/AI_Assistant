"""console_io (terminal 1): its defaults in its `module.toml`, and a restart (off, then on) reusing
its one input thread. Uses only the shared test kit."""

import queue
import threading

from assistant.contracts import ActivateModule, DeactivateModule, InputReceived
from assistant.core import App
from assistant.modules.console_io import ConsoleIO
from assistant.modules.console_io import module as console_module
from assistant.testkit import make_config, module_config, wait_until

# The old [modules.console_io] in config/default.toml, before its defaults moved to module.toml.
OLD_SECTION = {"prompt": "> "}


def test_its_defaults_are_in_its_module_toml_under_the_apps_section():
    defaults = module_config("console_io")
    assert defaults["needs"] == [] and defaults["packages"] == []  # a core module never needs an add-on
    assert {k: v for k, v in defaults.items() if k not in ("needs", "packages")} == OLD_SECTION
    assert ConsoleIO.manifest.needs == ()
    yours = {"prompt": "you> "}
    app = App([ConsoleIO], {"modules": {"enabled": [], "console_io": yours}, "core": {}})
    assert app._config_of("console_io") == {**defaults, **yours}

async def test_console_io_restart_reuses_one_input_thread(monkeypatch):
    lines: queue.Queue[str | None] = queue.Queue()

    def fake_input() -> str:
        line = lines.get()
        if line is None:
            raise EOFError
        return line

    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setattr(console_module, "_stdin", console_module._StdinReader())
    app = App([ConsoleIO], make_config("console_io"))
    inputs: list[str] = []

    async def record(event: InputReceived) -> None:
        inputs.append(event.text)

    app.bus.subscribe(InputReceived, record)
    await app.start()
    assert (await app.router.send(DeactivateModule(module_id="console_io"))).is_ok
    assert (await app.router.send(ActivateModule(module_id="console_io"))).is_ok
    lines.put("hello")
    await wait_until(lambda: inputs == ["hello"])
    assert sum(t.name == "console-input" for t in threading.enumerate()) == 1
    await app.stop()
    lines.put(None)  # end the reader thread
