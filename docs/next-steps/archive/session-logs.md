# Logs per session

> **Status: done (2026-10-26).** Approved in conversation, with the user's go-ahead for the code change and a relaunch. `pytest`: 85 passed, 1 deselected (the real-`claude` test); `ruff`: all checks passed. The app was relaunched to use it. Still to do: rebuild `docs/html`.

**Asked:** "I want logs to be session by session. So per session, create a folder and in that it'll have its own logs." Then: "a timestamp + a short (max 5 word) theme of my first question", and "should each module deal with its own logging? Or should I go through a handler?"

**Why:** today every launch appends to the same three files in `logs/`, so one run's lines are mixed in with every earlier run. Finding what happened in one session means scrolling by timestamp.

**Who owned logging before:** no single owner. `setup_logging` wrote `logs/assistant.log` from `[logging] file`; each agent's `ClaudeSession` wrote its transcript from its module's `transcript` path; the temp UI's Logs button opened `logs_dir`.

**Touches:** `infra/log.py` (the handler), `__main__.py`, a `SessionTheme` event in the contracts, `talker` (sends the theme, prompt names the new paths), `config/default.toml`, tests, and the docs that name the log paths. `temp_ui` and `main_assistant` code don't change.

**Decided:**
- **One owner: a log handler in the core infrastructure,** [`LogSession`](../../api/infra.md#logsession) next to `setup_logging`. Not a module (it must exist before modules start) and not the Main Assistant. It owns only *where* logs go: it creates the session folder, hands out the file paths, and renames the folder at the end. Modules still decide *what* they write, through the logging they already get; no module picks its own path.
- **Session = one app launch.** A relaunch starts a new session.
- **Layout:** `logs/<start time>_<theme>/` with `assistant.log`, `talker.jsonl`, `main_assistant.jsonl`, e.g. `logs/2026-10-26_03-06-52_session-log-folders/`.
- **Theme:** up to five words about your first question. The Talker adds it as a `<<THEME: ...>>` tag to its first reply (falling back to the question's first words) and publishes a [`SessionTheme`](../../api/messaging.md#sessiontheme) event; `__main__` passes it to the handler, which makes it folder-safe (lowercase, hyphens, letters and digits only, at most five words).
- **Rename at shutdown:** the folder is created at launch with the timestamp only (`-2` added if the name is taken). The theme is added when the app stops and the files are closed, since Windows can't rename a folder with open files. A failed rename is logged and never breaks shutdown; if the target name exists, the timestamp name stays. After a crash the folder keeps its timestamp-only name.
- **Sharing the paths:** `__main__.main()` points `[logging] file` and every module's `transcript` into the folder, and the temp UI's `logs_dir` at it. In config, `transcript` is now a file name.
- **Logs button:** opens the current session's folder.
- **`logs/relaunch.log`** stays where it is, written by `scripts/relaunch.ps1` outside the app.
- **Old files:** the flat `logs/assistant.log`, `talker.jsonl`, `main_assistant.jsonl` are left untouched. Session folders are kept, with no automatic cleanup. No "latest" pointer.

**Open questions:** none.
