# Module pages

One page per module: how it works inside, what it owns and launches, and how it fits the [wrapper](../architecture/modules.md#a-module-is-a-wrapper-with-a-menu). The general design (core, wrapper, directory and menu, chaining, the agents) stays on the [architecture pages](../architecture/README.md). For every module's interface side by side, see the [module library](../architecture/module-library.md).

A module that launches its own app (the voice service, the HTML viewer app) shares a page with that app. The app's full design stays on its architecture page ([voice](../architecture/voice.md), [HTML viewer](../architecture/html-viewer.md)).

## Page template

Every module page has these sections, in this order. Keep each short; link to the architecture and API pages for detail.

| Section | What goes in it |
|---------|-----------------|
| Purpose | One or two lines, and its status: on by default, off by default, or planned |
| Wrapper | Its manifest: id, provides, requires, optional, permissions |
| Interface | Tools (its menu), commands it handles, commands it calls, events it publishes, events it listens to |
| Owns and launches | Processes, windows, ports, files, and companion apps it starts and stops |
| Inner workings | One diagram, plus a few lines |
| Config | Its `[modules.<id>]` section in `config/default.toml` |
| Code and tests | Paths only |
| Planned | What the module-shape refactor changes for it |

The Interface section is written by hand from the code (checked 2026-11-04). When the manifest carries the description, the handled commands and the events, it is generated like the [library](../architecture/module-library.md#generated-later).

## Pages

- [voice_in](voice_in.md): voice input, and the voice service app it launches
- [voice_notes](voice_notes.md): speak into a page of notes
- [html_viewer](html_viewer.md): the HTML viewer's thin module, and the viewer app
- [talker](talker.md): the agent that talks with you
- [main_assistant](main_assistant.md): the worker agent
- [agent_hub](agent_hub.md): who is doing what
- [temp_ui](temp_ui.md): the temporary two-pane web page
- [console_io](console_io.md): terminal 1, type and read
- [assistant_view](assistant_view.md): terminal 2, view only (off by default)
- [echo_orchestrator](echo_orchestrator.md): stand-in orchestrator (off by default)
