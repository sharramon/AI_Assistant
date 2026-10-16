# Infrastructure

Shared services. All items: `from assistant.infra import ...`. Back to the [API index](README.md).

## `load_config`

`load_config(config_dir: str | Path | None = None) -> dict[str, Any]`

Load `default.toml`, then deep-merge `local.toml` over it if it exists. Tables merge key by key; other values (including lists) are replaced.

**Parameters**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| `config_dir` | `str \| Path \| None` | no | Directory holding the files. Defaults to `ASSISTANT_CONFIG_DIR`, then `./config` |

**Returns:** the merged config as nested dicts.

**Raises:** `FileNotFoundError` if `default.toml` is missing; `tomllib.TOMLDecodeError` for invalid TOML.

**Defined in:** `src/assistant/infra/config.py`
**See also:** [configuration keys](../architecture/core.md#configuration)

## `setup_logging`

`setup_logging(settings: dict[str, Any]) -> None`

Configure root logging from the `[logging]` config section. Replaces any existing configuration.

**Settings**
| Key | Default | Description |
|-----|---------|-------------|
| `level` | `"INFO"` | Standard level name |
| `file` | none | Log file path; parent directories are created |
| `stderr` | `false` | Also log to the terminal. Keep off while `console_io` is enabled |

With neither `file` nor `stderr`, logs are discarded.

**Defined in:** `src/assistant/infra/log.py`
