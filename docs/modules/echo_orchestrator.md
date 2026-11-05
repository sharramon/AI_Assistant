# echo_orchestrator: stand-in orchestrator

## Purpose

Replies with the input text; `/tools` lists the available tools. It exists to prove the plumbing without an AI. Off by default; enable it instead of the Talker in `modules.enabled`.

## Wrapper

| Field | Value |
|-------|-------|
| id | `echo_orchestrator` |
| provides / requires | nothing |
| optional | [`IToolProvider`](../api/tools.md#itoolprovider) (to list tools) |
| permissions | none |

## Interface

| | |
|---|---|
| Tools · Handles · Calls | none |
| Publishes | [`ResponseReady`](../api/messaging.md#responseready) |
| Listens to | [`InputReceived`](../api/messaging.md#inputreceived) |

## Owns and launches

Nothing.

## Inner workings

```mermaid
flowchart LR
    In["InputReceived"] --> Echo["echo_orchestrator<br/>Echo: text · /tools"] --> Out["ResponseReady"]
```

## Config

None.

## Code and tests

- `src/assistant/modules/echo_orchestrator/module.py`
- `tests/test_app.py`

## Planned

Nothing specific.
