# Open in viewer brings the viewer to the front

> **Status: done (2026-10-28).** The tests pass. In a live check, the user saw the viewer window come to the front. Docs updated: [HTML viewer](../../architecture/html-viewer.md), [Tools](../../api/tools.md), [Agents](../../architecture/agents.md) (principle 11), [runtime](../../agents/runtime.md), and the `docs-html` skill.

**Asked:** "when I click on buttons that lead to html from the talker, it forces the html app to the front". If the viewer window was closed, the click opens it again, showing the page you clicked.

**The rule (user, 2026-10-28):** pages the assistant opens on its own (SHOW tags from the Talker or the Main Assistant: quick checks, debugging) open in the viewer but **don't take focus**. When a page is meant for you to see, the chat offers an **Open in viewer** button: the Talker writes the path in its reply, and the chat shows the button. **Clicking the button brings the viewer to the front.**

**Why:** the page opens in the viewer, but its window stays behind other windows, so the click looks like it did nothing.

**What happens today:**
- The button (`temp_ui/page.html`, `openButtons`) posts to `/open-in-viewer`. `temp_ui/module.py` sends `InvokeTool viewer.open`, then `html_viewer/module.py` (`show`) starts the viewer if it isn't running and posts `/api/open`.
- `ViewerServer.open` (`html_viewer/viewer.py`) makes the clicked file the active tab. It opens a window only if no page is connected. A window that's already showing is never raised.
- A gap: a new window can't open within 15 s of the last one. Close the window right after it opens and click again, and nothing appears.
- (`infra.open_app_window` is used only by the temp UI. The viewer has its own copy in `html_viewer/window.py`.)

**Does the existing button already "offer" the page?** Mostly, yes:
- The chat adds a button for every HTML path in a Talker reply (`HTML_PATH` in `temp_ui/page.html`). The Talker's prompt already says "When an HTML file matters, write its path in your reply; the chat shows an Open in viewer button." That covers pages meant for you, including ones the Main Assistant reports, because the Talker writes their path when it passes them on.
- **One gap:** `split_tags` (`talker/module.py`) takes `<<SHOW: path>>` tags out of the text you see. If the Talker opens a file with SHOW (you asked it to) and doesn't also write the path, the page opens in the background with no button, and you see nothing. **The fix:** after splitting, the Talker adds the path of each SHOW tag it hasn't already written, on its own line, so a page it opens for you always comes with a button. It's done in code, so it doesn't depend on the prompt being followed. SHOW tags in the Main Assistant's activity stay as they are, in the background with no button.
- **Always the full path (added at approval):** the Talker once wrote a bare file name. The button then looked for it in the project root and failed with "No such file". The rule is now that the Talker always writes the full absolute path of an HTML file, never a bare name. It goes in the Talker's prompt, in [Agents](../../architecture/agents.md), and in the `docs-html` skill. The button's handling of bare names doesn't change.

**Touches:** `src/html_viewer/window.py`, `src/html_viewer/viewer.py`, `src/assistant/modules/html_viewer/module.py`, `src/assistant/modules/temp_ui/module.py`, `src/assistant/modules/talker/module.py` (the SHOW path in the reply), `tests/test_html_viewer.py`, `tests/test_agents.py`, and the docs [HTML viewer](../../architecture/html-viewer.md) and [Tools](../../api/tools.md).

**Approach:**
1. **`window.py`: `raise_window(pid)`** (Windows only, ctypes, no new dependency; does nothing elsewhere). It looks through the top-level windows (`EnumWindows`) for a visible one belonging to the Edge process the viewer started (`self._edge.pid`). If that window is minimized, it restores it (`ShowWindow SW_RESTORE`), then calls `SetForegroundWindow`. Windows blocks a background process from taking the foreground. So the function first attaches to the input thread of the current foreground window (`AttachThreadInput`), sets the foreground, and then detaches. It returns whether it worked.
2. **`viewer.py`:** `/api/open` and `/api/highlight` take an optional `"front": true`. With it, `open()` raises a window that's already showing. If no page is connected, it opens a new window, which comes up in front anyway. The 15 s guard now applies only until the new page connects, so a window you closed can open again straight away.
3. **The tools:** `viewer.open` and `viewer.highlight` get an optional `front` (boolean, default false), which `HtmlViewerModule.show` and `highlight` pass on. The temp UI's `/open-in-viewer` sends `front: true`.
4. **Which page:** this already works. `open()` switches to the clicked file's tab, or adds a new tab for it, before the window is raised or opened.

**Tests:** in `tests/test_html_viewer.py`:
- `open(front=True)` with a page connected calls the raise hook once. Without `front`, it doesn't call it.
- With no page connected, it opens a window instead.
- After a page connects and disconnects, the next open opens a window again, with no 15 s wait.
- `/open-in-viewer` sends `front: true` (the existing fake-viewer test).
- In `tests/test_agents.py`: a Talker reply with only `<<SHOW: x.html>>` shows `x.html` in its text, and a reply that already has the path doesn't show it twice. SHOW calls `viewer.open` without `front`.

The tests swap in fakes for the window functions, the same way `capture` is swapped in today, so no real window is needed in CI. After that, run `pytest` and `ruff`, then check it by hand: put another window over the viewer and click; minimize the viewer and click; close the viewer and click.

**Open questions:** none. Whether SHOW tags take focus is decided above: they don't.
