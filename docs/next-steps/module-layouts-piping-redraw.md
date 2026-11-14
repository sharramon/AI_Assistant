# Module layouts: redraw the flowcharts with the full piping

Status: **draft drawn 2026-11-13, waiting for the user's check.** Step 3 of the [restructuring checklist](restructuring-checklist.md) is reopened until the user approves it.

## What and why

`module-layouts.html` drew the core as one box ("Core: door · gate · Callers"). The piping page (`piping.html`, sections 2 and 2b) was meant to guide how the parts fit together and in what order, so the layout pictures should show it. The user asked for the full piping in each section, drawn as the code is built, so the layout work can be checked against it.

## The change

- Each section gets two pictures. **a** shows the sessions and which CLAUDE.md each loads, as before; its core box now points to **b**. **b** shows the core's piping: Module door D1, Callers D2, Router D3, one gate `dispatch_tool` D4, Bus D5, Permissions handler and cards D6, arrows 1 to 13 numbered as on `piping.html`, and the Agent Hub as coordination only.
- **1b, today:** the matches are drawn plainly. The six places where the code differs from the piping diagram are marked ≠1 to ≠6, from the read-only check of 2026-11-13: (1) risky core-menu items ask even in Auto; (2) the gate answers "asked on a card" at once; (3) the review is a task the Hub starts; (4) the Talker may answer cards (G17, open); (5) `modules.off` asks only with dependents and is sent as core; (6) the gate starts an off module before it checks the caller.
- **2b, step 1:** no new pipe. Shows how the module agents start and the access card for their folders (P7).
- **3b, step 2:** an add-on in a `module_folders` folder is found by `loader.find_modules` (A1), started by the LifecycleManager (A9), and reached through the same door, gate and cards. Five gaps are marked !1 to !5: "you" trusted by module id; job_search reads cv's output by path; the duplicate-folder check runs only at startup; the `modules.add` card doesn't show the folder; the CLAUDE.md exclude list covers only repo files.
- The step 3 line in the checklist is reopened as "redrawn, waiting for the user's check".

## Round 2 (2026-11-13): the main flow, and the bus inside the core

The user said 3b doesn't show the main data flow plainly (how a module calls another's tool, how events are subscribed to and triggered), and that the older pictures drew the Event bus as a box outside the core.

- **Picture 0, new, before 1a:** the core as one container (door D1, router D3, gate D4, cards D6, bus D5) and real modules on each side. Tool call T1 to T4: job_search `ctx.send(InvokeTool("cv.task"))` → router → gate → cv's item → Result back. Command C1 to C3: job_search `DeliverMessage` → router → the Agent Hub's handler (`ctx.handle`) → Result back. Event E1, E2: voice_in `ctx.publish(VoiceTranscript)` → bus → voice_notes (`ctx.subscribe` in `start()`, `listens` in its manifest) and any other listener. Never: an import between modules.
- **1a, 2a, 3a:** the Bus row moved inside the core box. The modules box says they reach each other only through the core.
- **1b, 2b, 3b:** a second teal arrow 2 from the gate into the add-ons, and arrow 5 two-headed (a module's own sends come in through the router).
- **Found while drawing, marked on the page:** the door sends `InvokeTool` through the router, not straight to the gate (`core/app.py:110,134`). Listening isn't strict: an undeclared subscription or named event works and is only logged (`core/context.py:224-231`).

## Not changed

No code. The page's text parts (the approve cards, the loader list L/A/D/T/C/P, the appendices) stay as they were. The loader list and the red "would need to change" box were written before step 6 built `module_folders`, so they're now stale. That's named on the page for the user to decide on.
