# cv module: PDF in, PDF out

> **Status: live (2026-11-09).** `cv` reloaded with your yes; the live menu takes `CV_Test_*.pdf`. The job agent's three files below now name `.pdf` (the skill's form-filling `.odt` lines are left, as planned). The cv module takes the base CV as a PDF, refuses an `.odt` in every item, and exports the final PDF into the job's folder; `odt_path` is gone from the result. The cv tests pass: 130, three of them with real LibreOffice, plus the layout and docs checks (156 in all). **Left out at your request:** the access cut. cv_agent keeps its read access to `C:\Chang\Jobs\CV`. **Waiting on you:** (1) a `cv` reload; (2) your yes to change the job agent's three files below to `.pdf`. Until then its `cv.task` calls with an `.odt` are refused.

**Asked:** the `cv` module's interface is fixed to three things: it takes a job description as text and a base CV as a PDF, and it gives back a CV as a PDF. Other modules and the job agent need to know only that. How the module reads and edits the PDF inside is its own business. The cv agent has no access to your `.odt` files.

## The interface

**In:** `cv.task`, then `hub.start` to `cv_agent`, as today.

| Field | What | Change |
|---|---|---|
| `company`, `role` | the job | none |
| `jd_text` | the job description as text | none |
| `jd_file` | instead of `jd_text`: a `.txt`, `.md` or `.html` file that `cv.task` reads into the text | none |
| `base_cv` | **a `CV_Test_*.pdf` in `C:\Chang\Jobs\CV`** (read only, never changed) | was a `.odt`; an `.odt` is now refused: "base_cv must be a CV_Test_*.pdf" |
| `jd_url`, `notes`, `degree_first`, `target_score` | optional, as today | none |

**Out:** the task's last line `CV_RESULT: <json>`, read with `cv.read_result`.

| Field | What | Change |
|---|---|---|
| `pdf_path` | **the tailored one-page CV as a PDF**, in `<output_dir>\<date>_<Company>\` | none |
| `report_path` | `report.md` next to it | none |
| `odt_path` | | **dropped**: no `.odt` comes out |
| status, scores, keywords, compare, the rest | as today | none |

## No access to the .odt files

> **Not done, at your request (2026-11-09):** the access list stays as it is. The code refusals below are built.

- The cv agent's access list (`[agent] read_dirs` in `cv/module.toml`) drops `C:\Chang\Jobs\CV`. It reaches a base CV only through the module's own `cv.read`, which opens PDFs only.
- Every `cv.*` item refuses an `.odt`. Any file the module makes on the way to the PDF stays outside the agent's folders, and only the PDF and the report reach the output folder.
- The access list changes, so its card comes up once when `cv` reloads.

## What the job agent must change to match

`job_search`'s app code and prompt don't name the CV's file type, so nothing changes in the app. Its `cv.task` call is built from files in its own project, `C:\Chang\Jobs\CV`:
- `Recruiters/scripts/save_jd.py`: the base CV map and its check name `CV_Test_*.pdf` (it now names `.odt` files, and refuses anything else).
- The `apply-session` skill: `--base <file>.pdf`, and it looks for per-company `.pdf` files instead of `.odt`.
- The saved ExampleCorp hand-off record (`Recruiters/docs/applications/jd/examplecorp-…json`): `base_cv` becomes `CV_Test_ExampleCorp.pdf`.

## Inside the module (its own business, settled here)

- **Reading the PDF:** a reader of its own, built on `pypdf`, already a dependency. A check that every word of the PDF was read stops the agent and asks you if any text can't be placed. Rezi's existing check of the final PDF stays.
- **The job agent's own `.odt` use** (form filling with `odt_bullets.py`, hand tailoring in `cv_guide.md`) isn't part of the cv module, so it's left as it is.
- **No deny rule and no restart.** The access list and the code refusals keep the `.odt` files away, and the cv agent runs in Manual mode, which asks you before any other read. So only a `cv` reload is needed.
- **The old `.odt` reader** is kept only so the builder can check, once, that the new reader matches your real CVs. The agent never uses it.
- **No second reading by Rezi** at the start: the read check and your step-3 read cover it.

**Touches:** `src/assistant/modules/cv/` (code, prompt, `module.toml`, tests, its `docs/` pages) and the three job agent files above in `C:\Chang\Jobs\CV`. Nothing in `core`, `infra` or `contracts`.

**After building:** reload `cv` once you say so; the access card follows.
