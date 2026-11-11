# Handoff e519644c: CV page layout settings, read per print (cv_agent, 2026-11-10)

## Done (tests pass: `pytest src/assistant/modules/cv/tests` → 157 passed)
- **Skills rule** (user): core keywords only, at most 5 one-line Skills lines, at most 6 entries each, about 25 in all.
  Saved in `C:\Chang\Jobs\CV_Module\.claude\skills\cv-writing\SKILL.md` ("Skills section"),
  `rules\cv-style-skills-core-keywords.md`, and memory.
- **Line spacing 1.1 → 1.15** (user-approved). SKILL.md "Layout" and memory say 1.15.
- **Layout settings file:** `C:\Chang\Jobs\CV_Module\cv_tool\page_settings.json` (the CV Tool's data_dir). It's read on every
  call of `cvlib.layout()`, with no cache: every render, preview and PDF, every `fill()`/`lint()`/`fills()`, every `font_sizes()`
  default and the Submit's `min_pt`. Its keys and defaults are `LAYOUT_DEFAULTS` in `src/cv_tool/cvlib.py`: line_height 1.15,
  body_pt 10, name_pt 15, heading_pt 10.8, min_pt 10, margin_top_pt 36, margin_side_pt 36, entry_gap_pt 4. A value that is
  missing, not a number, a bool or outside `LAYOUT_RANGES` falls back to its default on its own. A bad file gives all the defaults.
- Removed from cvlib: `TOP, SIDE, GAP, BODY, TEXT_W, MIN_PT, LINE_H, line_height()`. Added `PAGE_W, PAGE_H, text_width(lay)`.
  `server.py` page_h_pt uses `layout()`.
- Warning 9 → 10 pt: `cv/tool.py` MIN_PT = 10, plus the "under 10 pt" texts in module.py, worker.py, reply.py, tool.py and
  cvlib docstrings. Tests updated, and a new test `test_the_layout_settings_are_read_at_every_render` checks a change with no reload.
  Note: `docs/next-steps/cv-submit-notice.md` records the user's earlier choice of 9 pt. The user asked for 10 on 2026-11-10 (later).
- `cv/module.toml` [tool] has a comment pointing to page_settings.json.
- Nothing is committed in git. The CV Tool (port 8771) was NOT restarted and still runs the old code (prints at 1.1).
- Untouched: the AcmeBio CV, every draft and job, Rezi.

## Done in the follow-up session (2026-11-10)
The "Next" list below is finished. Added paper, bold_weight, the gaps, text_color, heading_rule_pt and link_color, plus
`PAPERS`, `page_size()` and `text_height()`. `PAGE_W`/`PAGE_H` are gone, and server.py page_h_pt uses `text_height()`.
pytest: 157 passed. The copy test passes (3 prints in one process, AcmeBio v17 1 page at 10.0 pt). page_settings.json has every key.
Caveat found: `fills()` measures about 4% under Chrome's print width. A bigger body_pt or A4 makes Chrome shrink the page.
Then the Send JD and CV to Rezi click event was built: see `cv-rezi-click-signal.md` (status: built). 159 passed.
Open: one CV Tool restart plus a reload of the cv module ONLY (the core's module reload for cv, never the whole app),
covering both changes.

## Next (the user said YES, 2026-11-10: restart + reload approved). Nothing done yet; no half-done edits.
1. `use_item modules.reload {"module_id": "cv"}` (core menu). Never reload or restart the whole app. Per
   `cv/docs/architecture.md`, a cv reload quits the CV Tool when its code changed, and the next call starts the new code.
   So check the old 8771 process is gone (or stop it with `POST /api/quit`), then let a cv.* call (for example
   `cv.tool_status` on job 2026-11-10_Acme_Bio) start it again. Note: cv_agent is this module's worker, so the
   reload may end this session. If it does, the next session picks up from here.
2. Check the settings file on the next print: change one value in `C:\Chang\Jobs\CV_Module\cv_tool\page_settings.json`
   (e.g. line_height 1.2), POST `/api/check` on 8771 with a job's content (or print a test job), confirm `line-height: 1.2`,
   then put 1.15 back. Use a test job (HandCheckCo / SubmitCheckCo), never a real job's PDF.
3. Check that the click reaches cv_agent: on a test job (2026-11-10_HandCheckCo), POST `/api/draft/rezi` on 8771 and look for
   "cv: the Rezi request ... for cv_agent:" in assistant.log, and the "[Message from cv] The user pressed Send JD and CV
   to Rezi" message reaching cv_agent. Don't act on that message (it's a test). Say so in the report.
4. Confirm that the AcmeBio Submit's final file is v17 with the new lab name: find `CV_Test_AcmeBio*_final.pdf` in the CV Tool's job
   folder (`cv_tool\jobs\2026-11-10_Acme_Bio`), read its text (cv.read or pymupdf), and check that it says
   "Center for Resilient Autonomous Systems" and not the old Al-Faruque lab name. Check that it matches the v17 version (the job's
   versions or rounds). If not, tell the user.
5. Report all four to the user. No NEED needed unless something fails.

## Next (user-approved 2026-11-10: "make all the ones you recommended into settings")
Add these to `LAYOUT_DEFAULTS`/`LAYOUT_RANGES` and to page_settings.json, use them in `render()`, and keep the current
values as defaults:
- `paper`: "letter" (612×792) or "a4" (595.28×841.89). Make PAGE_W/PAGE_H come from layout, and use them in `text_width`
  and server.py page_h_pt. (`module.toml paper = "letter"` is unused.)
- `bold_weight` 600: the h1, h2, .title, .row, .edu .deg and .aw weights.
- `header_gap_pt` 4 (.contact margin-bottom), `section_before_pt` 5 and `section_after_pt` 2.5 (h2 margin),
  `skill_gap_pt` 1 (.skill), `degree_gap_pt` 3 (.edu), `award_gap_pt` 1.5 (.aw).
- `text_color` "#2e3a4b" (body and h2 border), `heading_rule_pt` 0.9, `link_color` "#1F4E79" (a.vis).
  Validate colours with a regex like `^#[0-9A-Fa-f]{6}$`. Non-numbers need their own check in layout(), which only takes numbers now.
- Keep fixed: the font family, the 2 pt under the name, the 1 pt heading padding, the tight gap = 0.55 × entry gap, the bullet
  mark and separators, the headings' words, alignment, nowrap bullets, FILL_TARGET, the .over colour, the link underline details.
- Then: extend the test, run `pytest src/assistant/modules/cv/tests`, and test on a copy (work\2026-11-10_line_spacing_check\setting,
  test_setting.py with its own data_dir): change a value between two prints in one process, and check that AcmeBio v17 with Skills
  trimmed is still 1 page at 10.0 pt. Rewrite page_settings.json with every key. Update memory `cv-line-spacing-proposal.md`.
- Then tell the user that the config file is `C:\Chang\Jobs\CV_Module\cv_tool\page_settings.json`, and ask again about the
  one restart of the CV Tool. Don't restart without their yes. A cv module reload would also be needed for the module-side 10 pt texts.
