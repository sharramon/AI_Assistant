# Permission requests on the Talker side

> **Status: done (2026-10-26).** Approved as proposed, keeping the log line in the Main Assistant pane.

**Asked:** "The permission should appear on the talker side, not the worker side."

**Why:** You talk to the assistant through the Talker, so that's where you should answer it. Today the Allow / Deny card appears in the temp UI's **Main Assistant** pane (left). The Talker also asks you in the chat on the right, so the same question shows up in two places and the buttons are in the pane you only watch.

**Current behavior:**
- `temp_ui/module.py` (`_on_task`) puts a `permission` `TaskUpdated` in the `worker` pane. `page.html` draws it there as the Allow / Deny card (`POST /permission` → `AnswerPermission`).
- The Talker gets the same update and asks you in one sentence. A `<<ALLOW>>` / `<<DENY>>` tag answers it. Either way of answering settles the card.

**Intended behavior:**
- The card appears in the **Talker** pane (right), in line with the conversation, next to the Talker's question. It works the same way otherwise: Allow / Deny buttons, or answer the Talker in words.
- The Main Assistant pane keeps one plain log line (`asks permission: <tool and path>`, then `permission allowed/denied`), with no buttons, so its activity log stays complete.
- Nothing changes in the Hub, the contracts, or the Main Assistant: `ReportTask(permission)` → `TaskUpdated` → `AnswerPermission` stays the same. Only where the UI shows the request moves. The planned [permissions handler](../permissions-handler.md) already has "the UI / Talker" asking you, so this matches it.

**Touches:**
- Code: `src/assistant/modules/temp_ui/module.py` (push the card to the `talker` pane, plus a log line to `worker`) and `src/assistant/modules/temp_ui/page.html` (draw the card and its "answered" state in the Talker pane).
- Talker prompt (`talker/module.py`): one small wording fix so it says the buttons are "right here in the chat". No change in behavior.
- Tests: `tests/test_temp_ui.py` gets a case for a `permission` update: the card is in the `talker` pane and the log line is in the `worker` pane.
- Docs: `docs/agents/runtime.md` (Temp UI section), `docs/agents/README.md` (Permission requests line), and a one-line pointer in `docs/next-steps/archive/permission-requests.md` (step 6). Then rebuild the HTML.

**Decided:**
- **Keep a log line in the Main Assistant pane:** yes, a plain line without buttons, so the worker's log shows what it asked (the user's answer, 2026-10-26).
