# Logs button

> **Status: done (2026-10-26).** Approved with the label "Logs".

**Asked:** "A button on this UI that is just 'open logs in explorer'. Or something shorter that would make the UI nicer."

**Why:** the transcripts (`logs/talker.jsonl`, `logs/main_assistant.jsonl`) and `logs/assistant.log` are the main debugging tool, and finding the folder by hand is slow.

**Touches:** `temp_ui` only (`module.py`, `page.html`), plus one config key. Throwaway like the rest of the [temp UI](../../agents/runtime.md#temp-ui).

**Approach:**
- A small **Logs** button in the header, right side, next to the connection status, with a folder icon.
- Clicking it sends `POST /open-logs`; the module opens the folder in Explorer (`os.startfile`).
- The folder comes from `[modules.temp_ui] logs_dir` (default `"logs"`).
- Only works when the browser and the app are on the same PC, which is true for the temp UI.

**Open questions:**
- Label: **"Logs"** with a folder icon (recommended), or "Open logs".
