# The cv module at a glance

> **Status: built (waiting on you) (2026-11-09).** Merged into the cv module's overview (`src/assistant/modules/cv/docs/README.md`, "Design: the CV Tool flow" and "Build state"). Kept here until you say it can go. A picture of today, checked in the code and the running app. The build of [cv-uses-cv-tool.md](cv-uses-cv-tool.md) is paused partway through ([handoff](handoff-cv-tool-build.md)).

The CV Tool is the cv module's own UI half. The module owns it: it launches the app, feeds it jobs and stops it. It isn't part of the Main Assistant or the core. The app's code sits in `src/cv_tool/`, not in the module's folder: `CompanionApp` starts it with `python -m <package>`, and from inside `cv/` that would import the module's code into the app.

```mermaid
flowchart TD
    You(["<b>You</b>"])
    subgraph MainTab["Main tab"]
        MTalker["<b>Talker</b><br/>talks with you"]
        Main["<b>Main Assistant</b><br/>starts cv_agent (hub.start)"]
        MTalker -- "work · questions" --> Main
        Main -- "progress · questions" --> MTalker
    end
    subgraph JobTab["Job search agent's tab"]
        JTalker["<b>Its Talker</b>"]
        JobAgent["<b>Job search agent</b><br/>finds the job, sends it"]
        JTalker -- "work · questions" --> JobAgent
        JobAgent -- "progress · questions" --> JTalker
    end
    You <--> MTalker
    You <--> JTalker
    You <--> CTalker
    JobAgent -- "the job (cv.task's text)" --> Main
    Main -- "hub.start" --> Agent
    In["<b>Inputs</b><br/>JD as text · base CV as a PDF<br/>(cv.task)"]
    Gate["<b>Job-start gate</b><br/>work folder · copy of the PDF<br/>loads the rule files"]
    Rules["<b>rules/ folder</b><br/>style · layout · Rezi · 9 pt<br/>(today: 2 files from cv_agent's folder)"]
    Facts["<b>confirmed_facts.json</b><br/>your confirmed facts, as data"]
    Agent["<b>cv_agent</b><br/>the cv module's worker"]
    Rezi["<b>Rezi</b> (a scorer only)<br/>1 · API: write and read the text<br/>2 · your Chrome: read the score + keywords<br/>(sometimes an edit there)<br/>✗ its PDF: never downloaded"]

    subgraph CV["cv module"]
        Gate
        Rules
        Facts
        Link["<b>CompanionApp + cv.tool_* items</b><br/>the module's link to its UI"]
        subgraph CvTab["cv agent's tab"]
            CTalker["<b>Its Talker</b>"]
            Agent
            CTalker -- "work · questions" --> Agent
            Agent -- "progress · questions" --> CTalker
        end
        Rezi
        Chrome["<b>Your Chrome</b><br/>Claude in Chrome extension<br/>(you watch it here)"]
        Headless["<b>Headless Chrome</b><br/>on this PC: prints the CV's page"]
        subgraph UI["CV Tool: the module's own UI half (its own window)"]
            T1["<b>1 · Job & CV</b>"]
            T2{"<b>2 · Pick</b><br/>Internal or Rezi"}
            T3["<b>3 · First Draft</b><br/>stop for your review"]
            T4["<b>4 · ATS Loop</b><br/>to 90+, at most 5 rounds<br/>9 pt check"]
            Sub["<b>Submit</b><br/>yours, in the app"]
            T1 --> T2 --> T3 --> T4
            T4 -- "under 90, round ≤ 5" --> T4
            T4 --> Sub
        end
    end

    Out["<b>Outputs</b><br/>CV_Test_&lt;Company&gt;_final.pdf<br/>result.json · report"]

    JobAgent --> In --> Gate
    Rules --> Gate
    Facts -.-> Gate
    Gate --> Agent
    Agent -. "opens the job when you say (cv.open_tool)" .-> T1
    Link -. "launches and controls (CompanionApp) when cv_agent calls cv.open_tool · a window now, headless later" .-> UI
    Agent -. "cv.tool_round · tool_status · tool_result" .-> Link
    Link -. "the round in · status and Submit's result out" .-> T4
    Agent -- "today: request and result files (rezi_requests); you open the app by hand" --> T4
    T2 -- Rezi --> Rezi
    Agent -- "First Draft and each round: the CV text in (rezi.write_resume)" --> Rezi
    Rezi -- "score · categories · keywords out (read in your Chrome)" --> Agent
    Sub --> Out
    Agent -- "read the ATS score (Rezi), categories, keywords (sometimes an edit)" --> Chrome
    Chrome -- "app.rezi.ai, signed in as you" --> Rezi
    UI -- "the CV's own page in (export_pdf)" --> Headless
    Agent -- "today: its script build_cv_html.py" --> Headless
    Headless -- "local PDF out (9 pt check: not built)" --> T4
    T3 -. "Send JD and CV to Rezi: the request (file today · via cv.tool_status later)" .-> Link
    Agent -. "round 1: the CV text + ATS score (Rezi) + keywords (file today · cv.tool_round later)" .-> Link
    Link -. "round 1" .-> T3
    T4 -. "ask for a tweak or another run (chat today · cv.tool_status later)" .-> Link
    Agent -. "each round: score, issues, change notes (file today · cv.tool_round later)" .-> Link
    T4 -. "Submit's result (ready.flag + result.json · cv.tool_result later)" .-> Link
    Link -. "to cv_agent: the request · a tweak · Submit's result" .-> Agent
    T4 -. "Submit: yours" .-> You

    classDef live fill:#e3f1e6,stroke:#3d7f4f,color:#1d1d1b
    classDef built fill:#fff4d6,stroke:#b08900,color:#1d1d1b
    classDef notbuilt fill:#f2f1ee,stroke:#8a877c,stroke-dasharray:5 4,color:#5f5e58
    class You person
    classDef person fill:#e6f0f7,stroke:#2f6f9f,color:#1d1d1b
    class MTalker,Main,JTalker,CTalker,JobAgent,In,Gate,Agent,Rezi live
    class T1,T2,T3,T4,Sub built
    class Rules,Facts,Out,Link notbuilt
    class Chrome,Headless live
```

**Green: built and live. Yellow: built, not live. Grey, dashed: not built.** Dotted arrows are links that aren't built yet.

**Rezi's PDF is never downloaded.** This is your rule (2026-11-08 03:01, memory note `rezi-pdf-download-auto.md`), and the CV Tool ignores a Rezi PDF if one is sent. Rezi only scores the text; the PDF is always the CV's own page. In the Hooli run, Rezi's PDF was downloaded in rounds 2–4, before the rule.

**The ATS score comes from Rezi,** read in your Chrome. The CV Tool only shows it. With the Internal pick, the CV Tool's own estimate is used instead.

## The First Draft and ATS Loop tabs, close up

These are the same boxes as above, with the arrows between the tabs, cv_agent and Rezi. Each label ends with its state. Dotted arrows aren't built.

**First Draft (Rezi picked)**

```mermaid
flowchart LR
    You(["<b>You</b>"])
    T3["<b>Tab 3 · First Draft</b>"]
    Agent["<b>cv_agent</b>"]
    Rezi["<b>Rezi</b><br/>the ATS score"]
    Chrome["<b>Your Chrome</b><br/>Claude in Chrome"]

    You -- "Send JD and CV to Rezi · built, not live" --> T3
    T3 -- "1 · a request: text · JD · rules<br/>by file today, you tell cv_agent · built, not live" --> Agent
    T3 -. "1 · later: cv.tool_status · not built" .-> Agent
    Agent -- "2 · rezi.write_resume: the CV text (API) · live" --> Rezi
    Rezi -- "app.rezi.ai · live" --> Chrome
    Chrome -- "3 · ATS score (Rezi) + keywords, read · live" --> Agent
    Agent -- "4 · round 1: ATS score (Rezi) + keywords<br/>results file today · built, not live" --> T3
    Agent -. "4 · later: cv.tool_round · not built" .-> T3

    classDef live fill:#e3f1e6,stroke:#3d7f4f,color:#1d1d1b
    classDef built fill:#fff4d6,stroke:#b08900,color:#1d1d1b
    classDef person fill:#e6f0f7,stroke:#2f6f9f,color:#1d1d1b
    class You person
    class Agent,Rezi,Chrome live
    class T3 built
```

**One ATS Loop round**

```mermaid
flowchart LR
    You(["<b>You</b>"])
    T4["<b>Tab 4 · ATS Loop</b>"]
    Agent["<b>cv_agent</b>"]
    Rezi["<b>Rezi</b><br/>the ATS score"]
    Chrome["<b>Your Chrome</b><br/>Claude in Chrome"]
    Headless["<b>Headless Chrome</b><br/>on this PC"]

    T4 -. "ask for a tweak or another run<br/>today: you, in cv_agent's chat · not built as a link" .-> Agent
    Agent -- "true edits: rezi.write_resume (API) · live" --> Rezi
    Rezi -- "app.rezi.ai · live" --> Chrome
    Chrome -- "ATS score (Rezi) · issues · keywords, read · live" --> Agent
    Agent -- "each round: ATS score (Rezi), issues, change notes<br/>results file today · built, not live" --> T4
    Agent -. "later: cv.tool_round · not built" .-> T4
    Agent -- "the CV's own page in<br/>today: its script · live" --> Headless
    Headless -- "the PDF · built, not live" --> T4
    T4 -- "Submit: yours · built, not live" --> You

    classDef live fill:#e3f1e6,stroke:#3d7f4f,color:#1d1d1b
    classDef built fill:#fff4d6,stroke:#b08900,color:#1d1d1b
    classDef person fill:#e6f0f7,stroke:#2f6f9f,color:#1d1d1b
    class You person
    class Agent,Rezi,Chrome,Headless live
    class T4 built
```

## How cv_agent reaches Rezi today

There are two ways, and both are live:
- **Rezi's MCP API, through the cv module.** The `rezi.*` items (`mcp.py`) call `https://api.rezi.ai/mcp` with your OAuth sign-in token. That covers `rezi.write_resume` (make or update a resume this module made), `rezi.read_resume`, `rezi.generate_keywords`, and `rezi.list_resumes`. No browser is involved.
- **Chrome, through the Claude in Chrome extension** (`chrome = true` in `module.toml`). The prompt allows it only on app.rezi.ai, signed in as you. cv_agent uses it to read the **Rezi Score**, its categories, and the matched and missing keywords (prompt step 4), and for AI Keyword Targeting.

The CV Tool app never talks to Rezi itself (memory note `cv-tool-rezi-request.md`).

**You watch Rezi in your own Chrome.** cv_agent drives Rezi through the Claude in Chrome extension, in your normal Chrome, where you're signed in to Rezi. You look at that Chrome window to see what it's doing. The CV Tool shows no live view of Rezi.
- **Your words (2026-11-07, `logs\2026-11-06_04-28-55_open-two-extra-helpers-one\talker-cv_agent.jsonl`):**
  - L418, 21:21: tab 2 was first to have "A live view in chrome of the CV rezi is editying".
  - L874, 22:47: "Why not just embed a chrome window into the UI?"
  - L886, 22:47: "When it needs to, I can just sign in onto the chrome window on the app when you need me."
  - L910, 23:03: "Then the Rezy UX, I'll just look at the chrome broswer. It's cleaner anyway."
- **Agreed:** the Talker (L917, 23:03: "You'll watch Rezi in your own Chrome"), and cv_agent (L923, 23:07), which dropped "Arrange windows". It's written in `cv_tool\README.md` L120 and memory note `cv-tool-scope.md`. The embedded view in `cv_tool_ui_plan.md` (its own Chrome over DevTools) is out of date.
- **When Rezi opens in Chrome:** no log, note or README says. **Proposed:** with the Rezi pick, cv_agent opens the job's Rezi resume in a tab of your Chrome at First Draft and keeps that tab through the ATS Loop. When it writes through the API, it reloads the tab, so you see the same text it scores.

## The ATS loop, round by round

```mermaid
flowchart TD
    Draft["<b>First Draft</b><br/>in the CV Tool"]
    Edit["<b>1 · cv_agent edits</b><br/>true edits only, with the module's rules in front of it:<br/>truth · style · layout · 9 pt"]
    Write["<b>2 · Write to Rezi</b><br/>rezi.write_resume (API)<br/>into the resume cv_agent made"]
    Score["<b>3 · Read Rezi's feedback</b><br/>in your own Chrome (you watch there):<br/>score · categories · issues · matched · missing"]
    NoPdf["✗ <b>Rezi's PDF: never downloaded</b><br/>feedback only"]
    Round["<b>4 · Send the round to the CV Tool</b><br/>cv.tool_round: the edited content + Rezi's score and lists"]
    Print["<b>5 · The CV Tool prints its own page</b><br/>headless Chrome on this PC → CV_Test_&lt;Co&gt;_vN.pdf<br/>9 pt check on that PDF"]
    Tab["<b>6 · ATS Loop tab</b><br/>that local PDF · score · issues · rounds"]
    Check{"90 or more?<br/>or 5 rounds used?<br/>or only unbacked terms left?"}
    Ask["A missing term your CVs don't back<br/>→ a question to you, never added"]
    Submit["<b>Your Submit</b><br/>copies the current local PDF to<br/>CV_Test_&lt;Co&gt;_final.pdf + result.json + ready.flag"]
    Back["cv.tool_result → cv_agent → CV_RESULT"]

    Draft --> Edit --> Write --> Score --> Round --> Print --> Tab --> Check
    Score -.- NoPdf
    Check -- "no" --> Edit
    Check -- "yes" --> Submit --> Back
    Score -. "unbacked term" .-> Ask

    classDef live fill:#e3f1e6,stroke:#3d7f4f,color:#1d1d1b
    classDef built fill:#fff4d6,stroke:#b08900,color:#1d1d1b
    classDef notbuilt fill:#f2f1ee,stroke:#8a877c,stroke-dasharray:5 4,color:#5f5e58
    classDef rule fill:#fbe9e7,stroke:#b3261e,color:#1d1d1b
    class Write,Score live
    class Draft,Tab,Check,Submit,Print built
    class Edit,Round,Back,Ask notbuilt
    class NoPdf rule
```

**Where the PDF comes from:** at every round, and for the final PDF, it's the CV Tool's own page. The app's code (`export_pdf` in `cvlib.py`) prints it with headless Chrome on this PC. Submit copies that local PDF to `_final.pdf`. Rezi only scores the text. Its PDF is never downloaded (the rule in memory note `rezi-pdf-download-auto.md`, 2026-11-08), and the app ignores a Rezi PDF if one is sent (`apply_result`).

**What each colour means here:**
- **Green:** writing to Rezi and reading its feedback are live today.
- **Yellow:** the First Draft, the printing of the app's own page, the ATS Loop tab and Submit work in the old standalone app, driven by hand through result files.
- **Grey, not built:** sending a round with `cv.tool_round`, `cv.tool_result`, the 9 pt check, the rules in front of cv_agent each round (the `rules/` folder), and the prompt that runs this loop.

**Today's live prompt is different.** It still runs the old steps: edit in Rezi, score in Chrome, and build the final PDF with LibreOffice (`cv.build`). It then imports that PDF into Rezi as a check, and has no Submit.

## Each box today

| Box | State | What the code shows |
|---|---|---|
| Main tab: Talker and Main Assistant | Built, live | `talker` and `main_assistant` are on; `hub.agents` lists `main_assistant`. It starts cv_agent with `hub.start`, using the text `cv.task` returns |
| Each agent's own Talker (job search agent, cv agent) | Built, live | Every agent tab is a pair, its own Talker and its own worker (`talker`: "one Talker per agent tab"). A tab's Talker starts the first time you use the tab |
| Job search agent | Built, live | `job_search` is on; `hub.agents` lists `job_search_agent`. Its `save_jd.py` names the base CV as a `.pdf` |
| Inputs (cv.task) | Built, live | `cv.task` takes the JD as text and a `CV_Test_*.pdf`; `cv` is on |
| Job-start gate | Built, live | `job_start.py` makes the work folder, copies the PDF, loads `job_skills` |
| rules/ folder | Not built | No `cv/rules/` yet. `job_skills` loads two files from cv_agent's folder and memory |
| confirmed_facts.json | Not built (the link) | The file exists in `C:\Chang\Jobs\rezi\cv_tool\data\`, but nothing in the module loads it |
| cv_agent | Built, live, old flow | Its prompt (`worker.py`) still runs the old 8 steps straight in Rezi, with no CV Tool |
| Rezi | Built, live | The `rezi.*` items |
| CV Tool, four tabs, the pick, First Draft, ATS Loop, Submit | Built, not live | They work in the old standalone app (`C:\Chang\Jobs\rezi\cv_tool`), opened by hand. The module doesn't launch it or feed it. The copy in `src/cv_tool/` has its main code and pages, but no server yet |
| Links: open the job, `cv.tool_*` items | Not built | No `CompanionApp` and no `cv.open_tool` / `cv.tool_*` items in `module.py` |
| 9 pt check | Not built in the module | Only the new copy of the app can measure sizes (`font_sizes`); nothing calls it |
| Outputs: final PDF, result.json, report | Not built (the link) | Submit writes them in the old app, but nothing returns them to the module. Today's path is the old one: `cv.build` (LibreOffice) and `cv.report` |
