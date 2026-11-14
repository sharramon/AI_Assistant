# Module flow and piping: one page with only the flowcharts

Status: **round 5 (picture 1 redrawn) built 2026-11-13, waiting for the user's check.**

## What and why

The user wants the flowcharts from [module-layouts.html](module-layouts.html) and [piping.html](piping.html) on one page, without the long text around them, so the main flow is easy to read. Round 2: the page shows only the current piping, none of the state before the piping fix.

## The change

- New hand-written page `docs/next-steps/module-flow-and-piping.html` (copied as written to `docs/html-next-steps/` by the build), in the same style as the two pages.
- The pictures are copied as they are, with no redrawing, in this order:
  1. Layouts 0: how modules talk through the core
  2. Piping 2 and 2b: "The piping, as built (differences marked ≠)", with the piping legend first
  3. Layouts 1a (before step 1) and 1b (the core's piping as built, in full, with the ≠ marks)
  4. Layouts 2a/2b: "Step 1, built: add-ons in the repo, the line made hard"
  5. Layouts 3a/3b: "Step 2, mechanism built, nothing moved yet: add-ons in their own folder"
  6. Layouts Appendix B: the rules for the core line
- Each picture keeps its heading, a one-line caption, its legend, and the numbered-arrow list it needs to be read. The ≠ and ! marks keep their explanations.
- Dropped: the long prose, the loader tables, the decision cards, the approve cards, the use-case lists, the appendices' text and the checklists.
- Listed in the next-steps README table next to the two pages.

## Round 2: old piping removed

- Removed: Piping 1 and Piping 1b (piping.html's "Today" pictures, the state before the piping fix), with their arrow table (1 to 14), step table (A1 to A14) and permission-steps table (P1 to P12).
- Kept and relabelled: no heading or caption says "today", "suggested", "now" or "later". The piping-side tables say "Checks it passes" and "What the fix changed".
- References fixed: the legend speaks of the two piping pictures and P1 to P14 in 2b only; the gap list G1 to G20 points to the piping page; 2b's "as in 1b" notes now say "via the Hub" or point to the piping page for the unchanged steps (A1, A8, A11, P7, P12); 1b's arrow list points to Piping 2 above. Every "1b" left on the page means Layouts 1b.
- (Layouts 1a was kept in round 2 by mistake; removed in round 3.)

## Round 3: only current pictures

- Removed Layouts 1a (the sessions and their CLAUDE.md before layout step 1: an old state) with its caption and arrow list 1 to 3.
- Removed Layouts 3a (step 2's sessions view): its core box only pointed at 3b, and its red "Would need to change" box was out of date, since that change is built.
- Renamed: Layouts 1b is now **Layouts 1**, Layouts 3b is now **Layouts 3**. Every cross reference was updated to match ("≠1 to ≠6: Layouts 1", "as in Layouts 1", "(in Layouts 1)"), and the legend line "in the b pictures" now says "in Layouts 1, 2b and 3". Piping 2 and 2b keep their names, so they still match piping.html.
- The layout legend stays as it is: 2a still uses the session boxes, teal and red.
- Order now: Layouts 0, Piping 2, Piping 2b, Layouts 1, Layouts 2a, Layouts 2b, Layouts 3, Appendix B.

## Round 4: a one-sweep guide for a newcomer

The user asked for the page to work as a guide for someone who doesn't know the system: pictures ordered simple to detailed, one title scheme, and no before/after or "difference" wording.

**Done (the page `docs/next-steps/module-flow-and-piping.html` is rewritten):**
- Top: a one-paragraph intro, a "Who is who" list, and one shared legend (boxes, lines, marks).
- New order and titles:
  1. Core and add-ons: the three rules (was Appendix B)
  2. How modules talk through the core (was Layouts 0)
  3. Inside the core: every tool call and every card (was Layouts 2b's picture, which is Layouts 1 plus the module-agent start)
  4. How an add-on is found, turned on and reached (was Piping 2b)
  5. The agents: where each works and which CLAUDE.md it loads (was Layouts 2a)
  6. Add-ons kept in a folder outside the repo (was Layouts 3)
- Dropped: **Piping 2** (the piping design, with "Callers (new port)" and a review drawn as a listener) and **Layouts 1** (the same core as 2b's picture, minus the module-agent box). Picture 3 takes over Piping 2's arrow table, rewritten as "What travels / What is checked", with a P7 row.
- The ≠1 to ≠6 notes are now "Good to know" under picture 3, written as how it works. The !1 to !5 notes are now "Known gaps" under picture 6, along with the microphone note (A12) and G17 as "your open decision". The marks stay in the pictures and the legend explains them.
- Picture 4's tables are merged into one table for all of A1 to A14 and P1 to P14 ("What happens / What is checked"), filled in from piping.html's step table. The "what the fix changed", "unchanged" and "checks it passes" wording is gone.
- In-picture labels: "as in Layouts 1", "(unchanged)", "Step 1: cv and job agents", "Callers (new port)", "drawn in full in 2b", "picture 0", "appendix B" and "step 0 runs before step 1" were all replaced with the new picture numbers and neutral words.
- Corrected against the code: picture 5 said the module agents work in "your data folder (outside the repo)". They actually work in `modules/<id>/workspace` (gitignored), or in your data folder if `config/<id>.toml` names one (cv and job_search `module.toml`). Gap !2 now names the `cv_output` link in `job_paths.json`.
- Changes in meaning: the note that `claudeMdExcludes` was "not yet tried in a live session" was dropped as history. The "Rendering not checked by eye" notes were dropped too.

**Next (for the fresh session):**
1. Rebuild with `.\.venv\Scripts\python scripts\build_docs.py`, then check that the built `docs/html-next-steps/module-flow-and-piping.html` has no "Layouts", "Piping 2", "step 1", "unchanged", "new port", "differ" or "what the fix" left. Use `Select-String`. Expect hits only in CSS or comments.
2. Open the page: `<<SHOW: C:\Chang\Git_projects\AI_Assistant\docs\html-next-steps\module-flow-and-piping.html | "1 · Core and add-ons: the three rules">>`.
3. Report back briefly: the new order with titles, what was dropped or merged and why (above), and the meaning changes (above).
4. Set the status line to "round 4 built, waiting for the user's check".

No Chrome tabs were used.

## Round 5: picture 1 redrawn

The user found picture 1 unclear: the red "never names an add-on" arrow pointed at nothing, the "needs" label on the cv arrow sat on the arrow, the dashed "import its code ✕" line was hard to read, and the three rules below weren't tied to anything in the picture. Redrawn (same title, caption and rules list):

- The core box on the left lists what's inside: the host, the core modules, the door + one gate, the 7 ports. Mark **1** sits on it.
- The two add-ons (job_search, cv) are on the right, dashed as in the legend.
- Rule **2**: a two-headed teal link between the add-ons, "tools · events · contracts only", and below it a short red arrow ending on an X, "import code".
- Rule **3**: job_search → core "needs ✓", job_search → cv "needs ✓", and a short red arrow from the core ending on an X, "core never names an add-on". Each carries mark **3**.
- Every label sits clear of its arrow. The viewBox is 1100 × 300, the same width as the neighbouring pictures.

## Not changed

No code. The two original pages and the step 3 checklist state stay as they are. Deleting the originals is up to the user once they've checked the new page.
