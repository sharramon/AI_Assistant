---
name: app-update
description: Use whenever the user asks for a change to the assistant app itself (a feature, a UI tweak, a behavior fix, a new permission), whether in a Claude Code session or through the app's own Talker. Write and save a change note first, get the user's check, then build it, then offer to relaunch the app.
---

# App update

Every change the user asks for goes through four steps, in order. Don't skip ahead: nothing is built before the user has checked the note.

## 1. Write the change note

Create `docs/next-steps/<short-slug>.md`:

```markdown
# <Change title>

> **Status: proposed (<date>).** Waiting for the user's check.

**Asked:** what the user asked for, in their words where possible.
**Why:** the problem it solves.
**Touches:** modules, files, docs, config.
**Approach:** how, in a few bullets or a small diagram. Reuse what the API reference already has.
**Open questions:** anything the user has to decide. Recommend an answer for each.
```

Keep it short; the user reads it before anything happens.

## 2. Save it for the next session

- Add it to the **Pending changes** table in `docs/next-steps/README.md` (title linked to the note, status, date). The next session reads that page first (CLAUDE.md), so a note there is never lost when a session or the app restarts.
- Rebuild the docs (`docs-html` skill). If you can't run scripts (the app's Main Assistant has no shell), say the rebuild is still needed.
- Show the user the note (a short summary plus the path) and **ask them to check it**. Stop here until they answer.

## 3. Build it, after the user's check

- Apply their corrections to the note first, then set its status to `approved`.
- Set it to `building` and build it. For anything touching more than one function or file, follow `architecture-first`. Run the tests and `ruff`.
- Update the docs it affects, and rebuild them.
- Set the note's status, both in the note and in the Pending changes table: `built (waiting on you)` if a restart or the user's check is left (say which), else `done (<date>)`. The status values and archiving a done note are in the `next-steps-html` skill.
- If you can't make the change yourself (e.g. the app's Main Assistant can't write `src/`), leave the status at `approved` and say so in the row; the next Claude Code session picks it up from the table.

## 4. Offer to relaunch

Ask the user whether to relaunch the app with the changes. Only if they say yes, stop the running app and start it again (from a Claude Code session on this PC):

```powershell
$app = Get-CimInstance Win32_Process | Where-Object { ($_.Name -match "python" -and $_.CommandLine -match "-m assistant") -or ($_.Name -eq "powershell.exe" -and $_.CommandLine -match "Assistant: talk here") }
$claude = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq "claude.exe" -and $app.ProcessId -contains $_.ParentProcessId }
($app + $claude) | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Process powershell -WorkingDirectory "C:\Chang\Git_projects\AI_Assistant" -ArgumentList '-NoExit', '-Command', '$host.UI.RawUI.WindowTitle = ''Assistant: talk here''; .\.venv\Scripts\python -m assistant'
```

The new app closes the old temp UI window and opens one fresh one. The app's own agents can't relaunch the app they run in; they ask the user to (or to ask a Claude Code session).

## Never

- Build before the user has checked the note.
- Keep a change only in the conversation. It belongs in its note, linked from Pending changes.
- Relaunch without asking.
