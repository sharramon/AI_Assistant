# Handoff: CV Tool as the cv module's UI (task b31b8901)

> **Status: done (2026-11-09).** The "Next" edit pass is in [cv-uses-cv-tool.md](cv-uses-cv-tool.md) ("9 pt minimum", "Rules loaded on every job", recommendations on the open points) and the HTML is rebuilt. `job_start.py` needed no change: it already reads any path, `.json` too. Two CV Tool notes (`cv-tool-scope.md`, `cv-tool-rezi-request.md`) were added to the list. Waiting on the user's check of the note. Nothing in the code is built or changed.

## Done
- The change note [cv-uses-cv-tool.md](cv-uses-cv-tool.md) is written, listed in Pending changes, and the HTML is rebuilt. It covers why the CV Tool ended up separate (from `talker-cv_agent.jsonl`, 2026-11-07 21:21 to 2026-11-08 01:02), the CV Tool flow cv_agent should follow, `CompanionApp` control, what moves to `src/cv_tool/` and what stays, and the order after the PDF-only reload.
- The CV skill and notes were found and reported to the user:
  - **The only CV skill:** `C:\Jobs\rezi\cv_agent\docs\cv-writing-preferences\SKILL.md`. Its step 4 is out of date ("once the service's export is downloaded").
  - **The rest are memory notes** in `C:\Users\you\.claude\projects\C--Jobs-rezi-cv-agent\memory\`. Only `never-script-cv-folder-copy-first.md` loads in full through `job_skills`. The others reach cv_agent only as their index line.
  - `cv_tool\data\confirmed_facts.json` isn't loaded at all.
  - No separate skill for the CV Tool UI exists.
- **The user's answers:** a PDF base CV; remove `user-wants-rezi-export-not-local-build.md`; Internal or Rezi is the pick step; yes to checking 9 pt and adding it to the note; the style, layout and fact rules matter in the CV Tool and as general rules.

## Findings for the 9 pt minimum (checked, not yet in the note)
- **The cv module (AI_Assistant):** no font-size check anywhere. `pdf_read.py` already reads each text run's `font_size` (around line 208, `Run(...)`), so a check can reuse it.
- **The CV Tool (`cvlib.py`):** the job title, degree and awards lines are styled at **8.5 pt** (lines 401, 406, 408), which is under 9 pt. The only check, at line 586, warns when `BODY < 8.5` and checks nothing else.
- **cv_agent's scripts:** `C:\Jobs\rezi\cv_agent\scripts\font_sizes.py` measures sizes by hand. It isn't wired into any code path.

## Next (one edit pass on cv-uses-cv-tool.md, then rebuild)
1. Add a **"9 pt minimum"** section:
   - State today's state, with the findings above.
   - Propose a `cv` module check, `cv.check_fonts` or part of reading the final PDF. It reads every run's size with `pdf_read` and refuses a final PDF with any text under 9 pt, naming the lines. It runs before Submit's result is accepted and in the ATS Loop round.
   - Fix the CV Tool's 8.5 pt styles to 9 pt during the move. Point out that this may cost space on the one page, and the rule is "shorten or ask, never shrink".
2. Add a **"Rules loaded on every job"** section. `job_skills` lists in full:
   - `cv-style-no-parentheses-semicolons.md`, `cv-style-action-to-result.md`, `cv-min-font-9pt-measured.md` and `cv-section-order-default.md`
   - `rezi-pdf-download-auto.md` and `rezi-write-sections-scrambles-experience.md`
   - `user-fact-system-design.md`, `user-facts-soylent-no-aws.md` and `user-facts-hooli-v5-confirmed.md`
   - `C:\Jobs\rezi\cv_tool\data\confirmed_facts.json`
   - Check that `job_start.py` accepts a `.json` and a path outside the workspace. Otherwise propose that small change.
   - **Recommendation:** gather the style, layout and Rezi rules into `cv-writing-preferences\SKILL.md`, so they live as skill rules and as general rules. Keep the facts as data: the memory fact notes plus `confirmed_facts.json`, best merged into the one JSON file. Fix the skill's step 4 and remove the out-of-date export note.
3. Keep the two open points with their recommendations: wait for the user's pick unless the request names a tool, and keep the name `CV_Test_<Co>_final.pdf`.
4. Rebuild with `.\.venv\Scripts\python scripts\build_docs.py`, then ask the user to check the note again. Build nothing.
