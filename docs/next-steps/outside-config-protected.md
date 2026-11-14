# A config folder outside the repo is protected like the repo's config/

Status: **built, waiting for the app restart** (batched with the other pending changes; not restarted). 2026-11-13. Decision 1 approved: same way as `config/`. Built as the recommended fix below; tests `test_an_outside_config_folder_is_protected_like_config` and `test_the_app_refuses_a_write_into_its_outside_config_folder` in `tests/test_permissions_handler.py`. Audit question 4 ([architecture docs audit](architecture-docs-audit.md#for-the-user-to-decide)).

## The problem

Your settings can live outside the repo: `ASSISTANT_CONFIG_DIR` (or `App(config_dir=...)`) points the app at another folder, for example on a server. The rule that no agent is ever granted a write to `config/` only knows the repo's `config/`. An outside config folder holds the same files (`default.toml`, `local.toml`, `<id>.toml`), including `[core.permissions] you`, `relays` and `reviewer`, so an agent with a write grant there could make itself "you" at the next launch.

**What the docs say now:** permissions.md, Known gaps: "the protected zone is the repo's `config/`. A folder set by `ASSISTANT_CONFIG_DIR` isn't in it (to confirm with you)". The audit lists it at `rules.py:21-27`, and decisions.md has it under Known gaps.

## What the code does today

- **Where the config folder comes from:** `config_folder()` in `src/assistant/infra/config.py:40-42` (`config_dir`, else `ASSISTANT_CONFIG_DIR`, else `./config`). `App.__init__` keeps it as `self._config_dir` (`core/app.py:81`), used only for `RemoveModule`'s purge.
- **How the repo's config/ is protected:** `PROTECTED` in `core/permissions/rules.py:21-27` holds paths *relative to the repo* (`"config"` among them). `protected_paths(grants_file)` (`rules.py:39-41`) turns them into `REPO / p` and adds the grants file in use. `PermissionsHandler.__init__` stores that as `self._protected` (`handler.py:173`). `refusals()` (`rules.py:52-64`) takes a write off any access list when the folder is in the zone or holds part of it, in all four places it's used (`handler.py:224` Auto, `:352`, `:383`, `:481`).
- **What's missing:** `PermissionsHandler.from_config` (`handler.py:194-207`) is never told the config folder, so `protected_paths` never adds it. App builds the handler (`app.py:102-105`) right after it has `self._config_dir`, but doesn't pass it.
- **The grants file isn't affected:** `GRANTS_FILE` is `REPO / "config" / "permissions.toml"` (`handler.py:76`), whatever `ASSISTANT_CONFIG_DIR` says, and a custom `grants_file` is protected already (`protected_paths` adds it).
- **Not involved:** `infra/agent_access.py` (builds the lists; refusing is the handler's job) and the Hub's folder check (`agent_hub/tasks.py:515-534`, `folders_clash`: two agents writing the same folder, nothing about protection).
- **Text only, not enforced:** the fixed card warning (`rules.py:32`) and the Auto risky-step rule (`infra/agent_profile.py:96`, `AUTO_ACCESS`) both say `config/`. Neither names an outside folder.
- **Same limit as today:** the protection holds for access lists (task agents). The Main Assistant isn't on an access list; in Auto it has full permissions, so for it the risky-step text is the only guard, for the repo's `config/` too.

## Options

1. **Protect the outside folder by the same rule (recommended).** The handler adds the config folder in use to its protected zone. A write into it, or into a folder holding it, is refused on every list, in Manual and Auto. Reading stays allowed, as for the repo's `config/`.
2. **Refuse agents any access to it**, reads too. Stricter than the repo's own `config/`, and it would break an agent that reads its module's choices file. No need found.
3. **Both:** option 1, plus refusing reads. Same cost as 2.

## Recommended fix (option 1)

- **`core/permissions/rules.py`:** `protected_paths(grants_file, config_dir=None)` adds the resolved `config_dir` when given (deduplicated, as now). Update its docstring and the module docstring. Change `FIXED_RULES[1]` from "config/" to "the config folder (config/, or the one ASSISTANT_CONFIG_DIR names)".
- **`core/permissions/handler.py`:** `PermissionsHandler.__init__` takes `config_dir: Path | None = None` and passes it to `protected_paths`. `from_config(..., config_dir=None)` passes it on. Docstrings say so.
- **`core/app.py`:** pass `config_dir=self._config_dir` in the `PermissionsHandler.from_config` call (`app.py:102-105`).
- **`infra/agent_profile.py`:** `AUTO_ACCESS`'s risky-step line names "the app's config folder (`config/`, or the one `ASSISTANT_CONFIG_DIR` names)". Kept as text: the prompt doesn't need the path filled in.

**Tests:**
- `tests/test_permissions_handler.py`: extend `test_protected_zone_is_refused_and_the_three_warnings` (or add one beside it). With `protected_paths(tmp_path / "permissions.toml", tmp_path / "outside_config")`, a write to `outside_config/x` and a write to its parent are refused; a read of it is not; a sibling folder is not.
- One through the app: an `App(config_dir=tmp)` whose fake agent module asks for a write on `tmp` gets it refused (reuse `jobs_module` in the same file).
- Check that the existing tests still pass with `config_dir` defaulting to None.

**Docs:**
- `docs/architecture/permissions.md`: the Protected row of the repo-zones table adds "or the config folder `ASSISTANT_CONFIG_DIR` names"; drop the Known gaps bullet.
- `docs/architecture/decisions.md`: drop the gap from Known gaps.
- `docs/api/core.md` (`App` `config_dir` row): add that the permissions handler protects it.
- `docs/next-steps/architecture-docs-audit.md`: question 4 marked answered, with a link here.
- Rebuild the docs.

**Restart:** an **app restart** (core and infra code). No module reload.

## Decisions for the user

1. Protect an outside config folder the same way as the repo's `config/` (writes refused, reads allowed), or also refuse reads? **Recommended: same way as `config/`, writes refused only.**
