// CV Tool front end. One job at a time, saved to jobs/<id>/job.json.
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const TARGET = 90, MAX_ROUNDS = 5;
let pickedTool = null; // a tool chosen before any job is open, used by the next job
let job = null, lastScore = null, snapData = null, saveTimer = null, checkTimer = null, draft = null;

async function call(path, body) {
  const r = await fetch(path, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const d = await r.json();
  if (!r.ok) { status("Error: " + d.error, true); throw new Error(d.error); }
  return d;
}
function status(msg, bad) { const s = $("#status"); s.textContent = msg; s.style.color = bad ? "var(--bad)" : ""; }
function tool() { return job?.tool || pickedTool || ""; } // no default: the app waits for the pick (or the request's tool)
const PICK_FIRST = "Pick Internal or Rezi in the CV Tool tab first";
function goTab(id) {
  document.querySelectorAll("nav button, .tab").forEach((x) => x.classList.remove("on"));
  document.querySelector(`nav button[data-tab="${id}"]`).classList.add("on"); $("#" + id).classList.add("on");
  if (id === "t4") refreshLoop(true);
  if (id === "t3") openFirstDraft();
  renderBar();
}
document.querySelectorAll("nav button").forEach((b) => b.onclick = () => goTab(b.dataset.tab));

// ---------- jobs
async function loadJobs(selectId) {
  const jobs = await call("/api/jobs");
  $("#jobSel").innerHTML = jobs.length ? jobs.map((j) => `<option value="${esc(j.id)}">${esc(j.company)} – ${esc(j.role)} (${esc(j.id.slice(0, 10))})</option>`).join("")
    : `<option value="">No jobs yet: type a company and role, then New job</option>`;
  if (selectId) $("#jobSel").value = selectId;
  if ($("#jobSel").value) openJob($("#jobSel").value); else renderBar();
}
$("#jobSel").onchange = () => openJob($("#jobSel").value);
$("#newJob").onclick = async () => {
  const company = $("#newCompany").value.trim();
  if (!company) return status("Type a company name first", true);
  const j = await call("/api/job/new", { company, role: $("#newRole").value });
  $("#newCompany").value = $("#newRole").value = "";
  loadJobs(j.id);
};
async function openJob(id) {
  job = await call("/api/job?id=" + encodeURIComponent(id));
  job.rounds ||= []; job.ignored_terms ||= [];
  if (!job.tool && pickedTool) { job.tool = pickedTool; save(); }
  $("#jd").value = job.jd || "";
  showCv();
  $("#terms").innerHTML = ""; $("#recs").innerHTML = ""; degreeHint();
  $("#reziResume").value = job.rezi_resume || ""; draft = null;
  showTool(); loopSig = null; shownPdf = null; refreshLoop(true);
  status("Opened " + job.company);
  if ($("#t3").classList.contains("on")) openFirstDraft();
}
async function saveNow() {  // the server stamps content_saved_at; keep it so a later save isn't taken as stale
  clearTimeout(saveTimer); if (!job) return;
  const r = await (call("/api/job/save", job));
  if (r.content_saved_at !== undefined) job.content_saved_at = r.content_saved_at;
}
function save() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => { if (job) { await saveNow(); status("Saved " + new Date().toLocaleTimeString()); } }, 700);
}

// ---------- rounds bar (all tabs)
function renderBar() {
  if (!job) { $("#roundsBar").innerHTML = `<span class="step">Pick or add a job to start.</span>`; return; }
  const rs = job.rounds, n = rs.length, scores = rs.map((r) => r.score).filter((s) => s != null);
  const best = scores.length ? Math.max(...scores) : null, last = n ? rs[n - 1].score : null;
  const done = (best ?? 0) >= TARGET ? `<b style="color:var(--ok)">Target reached</b>` : n >= MAX_ROUNDS ? `<b style="color:var(--warn)">${MAX_ROUNDS} rounds used: stop and report what can't be added truthfully</b>` : "";
  // the flow: JD + base CV in → choose the tool → first draft with it → edit and re-score until the target
  const steps = [["t1", "Job & CV", !!(job.jd && job.base_cv)],
    ["t2", `CV Tool: <b>${esc(tool() || "pick one")}</b>`, !!job.tool],
    ["t3", "First Draft", !!job.content],
    ["t4", "ATS Loop", (best ?? 0) >= TARGET]];
  const on = document.querySelector("nav button.on")?.dataset.tab;
  $("#roundsBar").innerHTML = steps.map(([t, label, ok]) =>
    `<a href="#" data-go="${t}" class="${t === on ? "cur" : ""}">${ok ? "✓ " : ""}${label}</a>`).join(`<span class="sep">→</span>`) +
    `<span class="score">Edit → Export PDF → score → Save round · Round <b>${Math.min(n + 1, MAX_ROUNDS)}</b> of ${MAX_ROUNDS} · target ${TARGET} · last <b>${last ?? "–"}</b> · best <b>${best ?? "–"}</b> ${done}</span>`;
}
$("#roundsBar").addEventListener("click", (ev) => { const t = ev.target.closest("[data-go]"); if (t) { ev.preventDefault(); goTab(t.dataset.go); } });

// ---------- tab 1
async function showCv() {
  const n = job?.base_cv || "";
  $("#cvName").innerHTML = n ? `Base CV: <b>${esc(n.split(/[\\/]/).pop())}</b>` : "No base CV yet";
  if (!n) { $("#cvText").innerHTML = ""; return; }
  const d = await call("/api/cv?name=" + encodeURIComponent(n));
  $("#cvText").innerHTML = d.paras.map((p) => `<p>${esc(p)}</p>`).join("");
}
async function useCvFile(file) {
  if (!job) return status("Pick or add a job first", true);
  if (!file || !/\.(odt|docx)$/i.test(file.name)) return status("Use an .odt or .docx CV file", true);
  const data = await new Promise((ok) => { const r = new FileReader(); r.onload = () => ok(r.result); r.readAsDataURL(file); });
  const d = await call("/api/cv/upload", { id: job.id, name: file.name, data });
  job.base_cv = d.base_cv;
  $("#cvName").innerHTML = `Base CV: <b>${esc(file.name)}</b>`;
  $("#cvText").innerHTML = d.paras.map((p) => `<p>${esc(p)}</p>`).join("");
  status("Base CV set: " + file.name + ". First Draft starts from it.");
  renderBar();
}
$("#cvPick").onclick = () => $("#cvFile").click();
$("#cvFile").onchange = () => { useCvFile($("#cvFile").files[0]); $("#cvFile").value = ""; };
const drop = $("#cvDrop");
drop.addEventListener("dragover", (ev) => { ev.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
// the whole box opens the file picker, not just the button
drop.addEventListener("click", (ev) => { if (!ev.target.closest("button")) $("#cvFile").click(); });
drop.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); $("#cvFile").click(); } });
drop.addEventListener("drop", (ev) => { ev.preventDefault(); drop.classList.remove("over"); useCvFile(ev.dataTransfer.files[0]); });
// a file dropped anywhere else must not make the window navigate away
window.addEventListener("dragover", (ev) => ev.preventDefault());
window.addEventListener("drop", (ev) => ev.preventDefault());
$("#jd").oninput = () => { if (job) { job.jd = $("#jd").value; save(); degreeHint(); renderBar(); } };
function degreeHint() {
  const jd = job?.jd || "";
  $("#degreeHint").textContent = !jd ? "" : /master'?s|\bM\.?S\.?\b|\bMSc\b|graduate degree/i.test(jd)
    ? "The JD mentions a master's, so Education goes right under Skills." : "No master's ask found: Education stays after Experience.";
}
$("#toStep2").onclick = () => goTab("t2");
$("#toStep3").onclick = () => goTab("t3");
$("#toStep4").onclick = $("#toStep4r").onclick = () => goTab("t4");
// Internal mode only: ranked key terms + recommendations, run by themselves when First Draft opens
async function findTerms() {
  if (tool() !== "Internal" || !job) return;
  if (!job.jd) { $("#recs").innerHTML = "Paste the JD in Job & CV first."; $("#terms").innerHTML = ""; return; }
  const terms = await call("/api/terms", { jd: job.jd, role: job.role || "", company: job.company || "", content: job.content || null });
  $("#terms").innerHTML = rankedTable(terms, true);
  const ign = job.ignored_terms || [], use = terms.filter((t) => !ign.includes(t.term));
  if (!job.content) {
    $("#recs").innerHTML = `${use.length} ranked key terms found. The draft proposals start from the base CV.`;
    return;
  }
  const chips = (a, c) => a.map((t) => `<span class="chip ${c}">${esc(t.term)}</span>`).join("") || `<span class="muted">none</span>`;
  const missBacked = use.filter((t) => !t.in_cv && ["backed", "confirmed"].includes(t.status));
  const missNot = use.filter((t) => !t.in_cv && !["backed", "confirmed"].includes(t.status));
  const words = (job.content.summary || "").split(/\s+/).filter(Boolean).length;
  $("#recs").innerHTML = `<b>Recommendations for the first edit</b> (true edits only)
    <div style="margin-top:6px">1. Add these with the JD's exact word, where it's true. Your CVs back them, highest rank first:</div>${chips(missBacked, "b")}
    <div style="margin-top:6px">2. Leave these out, since they're not on your CVs or you declined them. Confirm one only if it's really true for you:</div>${chips(missNot, "r")}
    <div style="margin-top:6px">3. Already matched (${use.filter((t) => t.in_cv).length} of ${use.length}): spread the top ones across the Summary, Skills and bullets.</div>
    ${words < 45 || words > 75 ? `<div style="margin-top:6px">4. The Summary is ${words} words. Aim for about 60, built on the top terms.</div>` : ""}`;
}
$("#terms").addEventListener("change", (ev) => {
  const t = ev.target.dataset.term; if (!t || !job) return;
  job.ignored_terms = job.ignored_terms.filter((x) => x !== t);
  if (!ev.target.checked) job.ignored_terms.push(t);
  save();
});

// ---------- tab 2: CV tool
function showTool() {
  document.querySelectorAll(".tool").forEach((el) => el.classList.toggle("on", el.dataset.tool === tool()));
  $("#internalPanel").style.display = tool() === "Internal" ? "" : "none";
  $("#reziPanel").style.display = tool() === "Rezi" ? "" : "none";
  if (tool() !== "Internal") { $("#terms").innerHTML = ""; $("#recs").innerHTML = ""; }
  if (!draft) { $("#draftOut").style.display = "none"; $("#draftOut").innerHTML = ""; }
  showRezi();
  renderBar();
}
// First Draft tab: Internal ranks the terms and makes the proposals by itself; Rezi shows the request state
let drafting = false;
async function openFirstDraft() {
  if (!job) return;
  if (!tool()) return status(PICK_FIRST, true);
  if (tool() !== "Internal") return showRezi();
  await findTerms();
  if (draft || drafting || !job.jd || !(job.content || job.base_cv)) return;
  drafting = true;
  try { await draftFromScore(); } finally { drafting = false; }
}
function showRezi() {
  const o = $("#reziOut"); if (!job) { o.innerHTML = ""; return; }
  const rr = (job.rounds || []).filter((r) => r.request_id), last = rr[rr.length - 1];
  let h = job.rezi_pending ? `<div>Waiting for cv_agent's Rezi result for request <b>${esc(job.rezi_pending)}</b>. cv_agent picks it up (cv.tool_status).</div>` : "";
  if (last) h += `<div style="margin-top:6px">Last Rezi result: Rezi Score <b>${last.score ?? "?"}</b>, ${last.matched.length} matched, ${last.missing_backed.length + last.missing_not_backed.length} missing.
    <span class="muted">Feedback only: Rezi's PDF is never downloaded. The ATS Loop shows your local PDF.</span></div>`;
  if (job.rezi_content) h += `<div class="bar" style="margin-top:6px"><button id="useRezi">Use the text cv_agent read back from Rezi as the draft</button> <span class="muted">Every word still goes through the truth check in the ATS Loop.</span></div>`;
  o.innerHTML = h || `<span class="muted">Nothing sent to Rezi yet.</span>`;
}
$("#reziOut").addEventListener("click", (ev) => {
  const f = ev.target.dataset.open; if (f) { ev.preventDefault(); call("/api/open", { path: f }); return; }
  if (ev.target.id !== "useRezi" || !job?.rezi_content) return;
  if (job.content && !confirmReplace()) return;
  job.content = structuredClone(job.rezi_content); save(); renderBar(); status("Rezi's text is the draft now: see the issues in the ATS Loop");
});

// ---------- "Draft from score": Internal proposals you tick, or a Rezi score request for cv_agent
async function draftFromScore() {
  if (!job) return status("Pick or add a job first", true);
  if (!tool()) return status(PICK_FIRST, true);
  if (!job.content && job.base_cv) job.content = await call("/api/parse_cv", { name: job.base_cv });
  await saveNow();
  return tool() === "Internal" ? draftInternal() : draftRezi();
}
$("#draftScore").onclick = () => { draft = null; draftFromScore(); };
$("#draftRezi").onclick = () => draftFromScore();

async function draftInternal() {
  draft = await call("/api/draft/internal", { id: job.id });
  const d = draft, o = $("#draftOut"); o.style.display = "";
  const lineSel = (k, i, sel) => `<select data-line="${k}.${i}">${d.skills_labels.map((l, j) => `<option value="${j}" ${j === sel ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`;
  o.innerHTML = `<b>Draft from score: proposals</b> <span class="muted">(only facts already on your CVs. Nothing changes until you click Apply.)</span>
    <h4>1. Reorder Skills by JD rank (same items, new order)</h4>
    ${d.reorder.map((r, i) => `<div class="prop"><label><input type="checkbox" data-k="re" data-i="${i}" checked><b>${esc(r.label)}:</b> ${esc(r.after)}</label></div>`).join("") || `<div class="muted">Already in rank order.</div>`}
    <h4>2. Add, the word is on your CVs (the JD's exact word). Tick only where the Skills line stays true</h4>
    ${d.add.map((a, i) => `<div class="prop"><label><input type="checkbox" data-k="add" data-i="${i}">#${a.rank} <b>${esc(a.term)}</b></label> to ${lineSel("add", i, a.line)}</div>`).join("") || `<div class="muted">None missing.</div>`}
    <h4>3. Not on your CVs: tick only if it's really true for you</h4>
    ${d.ask.map((a, i) => `<div class="prop"><label><input type="checkbox" data-k="ask" data-i="${i}">#${a.rank} <b>${esc(a.term)}</b>: yes, this is true for me</label> → ${lineSel("ask", i, a.line)}</div>`).join("") || `<div class="muted">None.</div>`}
    ${d.declined.length ? `<h4>Declined by you, never added</h4>${d.declined.map((t) => `<span class="chip r">${esc(t)}</span>`).join("")}` : ""}
    <div class="muted" style="margin-top:6px">Bullets and the Summary aren't rewritten here: reword them in the ATS Loop, using the JD's words only for what you really did.</div>
    <div class="bar" style="margin-top:8px"><button id="applyDraft" class="main">Apply ticked and re-score</button></div>
    <div id="draftScoreOut"></div>`;
  status("Draft proposals ready");
}
$("#draftOut").addEventListener("click", async (ev) => {
  if (ev.target.id !== "applyDraft" || !draft) return;
  const d = draft, c = structuredClone(d.content), o = $("#draftOut");
  if (!c.skills?.length) c.skills = [["Skills", ""]];
  const ticked = (k) => [...o.querySelectorAll(`input[data-k="${k}"]:checked`)].map((x) => +x.dataset.i);
  const lineOf = (k, i) => +o.querySelector(`select[data-line="${k}.${i}"]`).value;
  ticked("re").forEach((i) => { c.skills[d.reorder[i].line][1] = d.reorder[i].after; });
  const confirmNow = ticked("ask").map((i) => d.ask[i].term);
  if (confirmNow.length) await call("/api/confirm", { phrases: confirmNow, words: confirmNow.flatMap((t) => t.split(/\s+/)) });
  const adds = [...ticked("add").map((i) => [d.add[i].term, lineOf("add", i)]), ...ticked("ask").map((i) => [d.ask[i].term, lineOf("ask", i)])];
  adds.forEach(([t, l]) => { const s = c.skills[l]; s[1] = s[1].trim() ? s[1].replace(/[,\s]+$/, "") + ", " + t : t; });
  job.content = c; draft = null;
  await saveNow();
  lastScore = await call("/api/score/internal", { id: job.id }); lastScore.tool = "Internal";
  o.innerHTML = `Applied ${ticked("re").length} reorder(s) and ${adds.length} addition(s)${confirmNow.length ? `, and saved ${confirmNow.length} fact(s) you confirmed` : ""}.
    Internal score now <b>${lastScore.score}</b> (Keywords ${lastScore.categories.Keywords}). Next, in the ATS Loop: run a round to make the PDF and score it.`;
  findTerms(); renderBar(); status("Draft applied");
});

async function draftRezi() {
  if (!job.content) return status("No CV yet: drop a base CV in Job & CV", true);
  const r = await call("/api/draft/rezi", { id: job.id });
  job.rezi_pending = r.request_id;
  let clip = false;
  try { await navigator.clipboard.writeText(r.text); clip = true; } catch (e) { /* the request file still has the text */ }
  showRezi();
  const o = $("#reziOut");
  o.innerHTML = `<b>Rezi request made</b> (score only: no Rezi AI writer, chat or suggested edits).
    <div>Request: <code>${esc(r.file)}</code></div>
    <div style="margin-top:6px">Next: the cv module has told cv_agent (this click is your yes for the Rezi write), so it starts the First Draft by itself. It puts the text into ${job.rezi_resume ? `the Rezi resume <b>${esc(job.rezi_resume)}</b>` : "a new Rezi resume for this job (none is named above)"}, reads it back, and takes the Rezi Score and keywords. The score, keywords and a PDF come back to First Draft, and the score is saved as a round. Any missing keyword your CVs don't back comes to you as a question, not an edit.</div>
    <div class="muted" style="margin-top:6px">${clip ? "The CV text is also on your clipboard, if you'd rather paste it into Rezi yourself and use Rezi yourself." : ""}</div>` + o.innerHTML;
  status("Rezi request made: " + r.request_id);
}
function chooseTool(el) {
  pickedTool = el.dataset.tool;
  if (!job) { showTool(); renderBar(); return status(pickedTool + " chosen. It applies to the job you add or open next."); }
  const changed = job.tool !== pickedTool;
  job.tool = pickedTool; showTool(); renderBar(); // the check and outline move at once, the save follows
  if (changed) { draft = null; lastScore = null; save(); refreshLoop(true); }
  status("CV tool: " + job.tool + (changed ? "" : " (already chosen)"));
}
document.querySelectorAll(".tool").forEach((el) => {
  el.addEventListener("click", () => chooseTool(el));
  el.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); chooseTool(el); } });
});
$("#reziResume").oninput = () => { if (job) { job.rezi_resume = $("#reziResume").value; save(); } };

let replaceArmed = 0;
function confirmReplace() { // no browser dialogs: click twice within 4 s to replace
  if (Date.now() - replaceArmed < 4000) return true;
  replaceArmed = Date.now(); status("This replaces the current CV. Click again to confirm.", true); return false;
}

// ranked core keywords: rank, term, weight, where in the JD, in our CV now, on your CVs
function rankedTable(terms, withUse) {
  const cls = { "backed": "s-backed", "confirmed": "s-confirmed", "not on CVs": "s-not", "declined": "s-not" };
  const ign = job?.ignored_terms || [];
  const inCv = (t) => t.in_cv == null ? `<span class="muted">no CV yet</span>` : t.in_cv ? `<span class="s-backed">matched</span>` : `<span class="s-not">missing</span>`;
  return `<tr>${withUse ? "<th>Use</th>" : ""}<th>#</th><th>Term</th><th>Weight</th><th>Where in JD</th><th>Our CV</th><th>On your CVs?</th></tr>` +
    terms.map((t) => `<tr>${withUse ? `<td><input type="checkbox" style="width:auto" data-term="${esc(t.term)}" ${ign.includes(t.term) ? "" : "checked"}></td>` : ""}<td>${t.rank}</td><td>${esc(t.term)}</td><td>${t.weight}</td><td class="muted">${esc([t.title ? "title" : "", ...t.where].filter(Boolean).join(", "))} · ${t.count}×</td><td>${inCv(t)}</td><td class="${cls[t.status]}">${esc(t.status)}</td></tr>`).join("");
}

// ---------- ATS Loop: the current PDF, score, biggest issues and change notes. Refreshes itself on any change.
let loopSig = null, loopBusy = false, shownPdf = null;
async function refreshLoop(force) {
  if (!job || loopBusy) return;
  loopBusy = true;
  try {
    const id = job.id, { sig } = await call("/api/loop/sig?id=" + encodeURIComponent(id));
    if (!force && sig === loopSig) return;
    if (loopSig !== null && sig !== loopSig) {  // changed on disk (agent, Rezi, a round): take the server's parts
      const fresh = await call("/api/job?id=" + encodeURIComponent(id));
      if (job?.id !== id) return;
      for (const k of ["rounds", "versions", "loop", "submitted", "rezi_content", "rezi_pending", "content", "content_saved_at"]) {
        if (k in fresh) job[k] = fresh[k]; else delete job[k];
      }
      renderBar(); showRezi();
    }
    loopSig = sig;
    const st = await call("/api/loop?id=" + encodeURIComponent(id));
    if (job?.id === id) renderLoop(st);
  } finally { loopBusy = false; }
}
// The PDF on screen: with "Highlight" on, page images with boxes over Rezi's matched keywords
// (drawn by the page, the PDF file is never changed); with it off, the plain PDF in the browser's viewer.
let lastLoop = null, shownPages = null;
function renderPdf(p, kw) {
  const hl = !!(p && $("#hlOn").checked);
  $("#pdfView").style.display = hl ? "none" : "";
  $("#pdfPages").style.display = hl ? "block" : "none";
  if (!hl) {
    const src = p ? `/api/file?id=${encodeURIComponent(job.id)}&name=${encodeURIComponent(p.name)}&t=${p.mtime}#view=FitH` : "about:blank";
    if (src !== shownPdf) { shownPdf = src; $("#pdfView").src = src; }
    return;
  }
  const marks = kw && kw.pdf === p.name ? kw.marks : [];
  const key = job.id + p.name + p.mtime + JSON.stringify(marks);
  if (key === shownPages) return;
  shownPages = key;
  const terms = (kw?.matched || []).map((m) => m.term), pct = (a, b) => (a / b * 100).toFixed(3) + "%";
  const pages = marks.length ? marks : Array.from({ length: p.pages }, () => ({ w: 1, h: 1, rects: [] }));
  $("#pdfPages").innerHTML = pages.map((pg, i) => `<div class="pg"><img alt="page ${i + 1}" src="/api/pdfpage?id=${encodeURIComponent(job.id)}&name=${encodeURIComponent(p.name)}&p=${i}&t=${p.mtime}">` +
    pg.rects.map((r) => `<div class="hl" data-kw="${r[4]}" title="${esc(terms[r[4]])}" style="left:${pct(r[0], pg.w)};top:${pct(r[1], pg.h)};width:${pct(r[2] - r[0], pg.w)};height:${pct(r[3] - r[1], pg.h)}"></div>`).join("") + "</div>").join("");
}
function renderKeywords(kw) {
  if (!kw) return `<span class="muted">No Rezi keyword lists for this job yet.</span>`;
  const g = { backed: [], declined: [], unconfirmed: [] };
  kw.missing.forEach((x) => (g[x.status] || g.unconfirmed).push(x.term));
  const chips = (list, cls) => list.map((t) => `<span class="chip kw ${cls}">${esc(t)}</span>`).join("") || `<span class="muted">none</span>`;
  return `<div class="muted">From ${esc(kw.source)}${kw.score != null ? ` (score ${kw.score})` : ""}. Hover a matched keyword to find it on the page.</div>
    <div class="kwgroup">Matched (${kw.matched.length})</div>
    ${kw.matched.map((m, i) => `<span class="chip kw g" data-kw="${i}">${esc(m.term)}<small>${m.hits ? "×" + m.hits : "not word for word on this PDF"}</small></span>`).join("") || `<span class="muted">none</span>`}
    <div class="kwgroup">Missing (${kw.missing.length}): backed by your CVs (${g.backed.length})</div>${chips(g.backed, "b")}
    <div class="kwgroup">Missing: declined by you (${g.declined.length})</div>${chips(g.declined, "d")}
    <div class="kwgroup">Missing: unconfirmed, not on your CVs (${g.unconfirmed.length})</div>${chips(g.unconfirmed, "y")}`;
}
$("#hlOn").onchange = () => { if (lastLoop) renderPdf(lastLoop.pdf, lastLoop.keywords); };
$("#loopKeywords").addEventListener("mouseover", (ev) => {
  const i = ev.target.closest("[data-kw]")?.dataset.kw;
  document.querySelectorAll("#pdfPages .hl").forEach((h) => h.classList.toggle("on", i !== undefined && h.dataset.kw === i));
});
$("#loopKeywords").addEventListener("mouseleave", () => document.querySelectorAll("#pdfPages .hl.on").forEach((h) => h.classList.remove("on")));
function renderLoop(s) {
  const p = s.pdf, sc = s.score;
  lastLoop = s;
  renderPdf(p, s.keywords);
  $("#loopKeywords").innerHTML = renderKeywords(s.keywords);
  $("#pdfInfo").innerHTML = p ? `<b>${esc(p.name)}</b> · ${p.pages} page${p.pages === 1 ? "" : "s"} · <a href="#" data-open="${esc(p.file)}">open outside</a>`
    : "No PDF yet. Run a round, or let the agent send one.";
  $("#loopScore").innerHTML = sc ? `<div class="big">${sc.score ?? "?"}<small> / 100 · ${sc.tool === "Internal" ? "Internal estimate, not a Rezi Score" : esc(sc.tool) + " score"} · target ${s.target}${sc.reached ? ` <b style="color:var(--ok)">reached</b>` : ""}</small></div>
    <div>${Object.entries(sc.categories || {}).map(([k, v]) => `<span class="chip">${esc(k)} ${v}</span>`).join("")} <span class="muted">${sc.matched} keywords matched · ${esc(sc.at)}${sc.version ? " · " + esc(sc.version) : ""}</span></div>`
    : `<span class="muted">No score yet.</span>`;
  const cls = { agent: "b", parse: "r", missing: "b", truth: "r", style: "r" };
  $("#loopIssues").innerHTML = s.issues.length ? s.issues.map((i) => `<div class="issue"><span class="chip ${cls[i.kind] || ""}">${esc(i.kind)}</span> ${esc(i.text)}</div>`).join("")
    : `<span class="muted">No issues found.</span>`;
  $("#loopNotes").innerHTML = s.notes.text ? `<div class="notes">${esc(s.notes.text)}</div><div class="muted">${esc(s.notes.by)} · ${esc(s.notes.at.replace("T", " "))}</div>`
    : `<span class="muted">No change notes yet.</span>`;
  $("#rounds").innerHTML = s.rounds.length ? "<tr><th>#</th><th>When</th><th>Tool</th><th>Score</th><th>What changed</th></tr>" +
    s.rounds.slice().reverse().map((r) => `<tr><td>${r.n}</td><td>${esc(r.at)}</td><td>${esc(r.tool)}</td><td><b>${r.score ?? "?"}</b></td><td>${esc(r.changes)}</td></tr>`).join("")
    : `<tr><td class="muted">No rounds yet</td></tr>`;
  $("#submitCv").disabled = !(p && sc && sc.score != null);
  $("#submitCv").title = $("#submitCv").disabled ? "Needs a PDF and a score first" : "Hand this PDF and its notes to the caller";
  const sub = s.submitted;
  $("#submitInfo").innerHTML = !sub ? "" : sub.changed
    ? `<div class="box warnbox">Changed since you submitted at ${esc(sub.at.replace("T", " "))}. Submit again to hand over this version.</div>`
    : `<div class="box okbox">✓ Submitted ${esc(sub.at.replace("T", " "))} with score ${sub.score ?? "?"}. Ready for the caller: <a href="#" data-open="${esc(sub.pdf)}">${esc(sub.pdf.split(/[\\/]/).pop())}</a> and result.json in the job folder.</div>`
      + (sub.small_text ? `<div class="box warnbox">Warning only: ${sub.small_text} text piece${sub.small_text === 1 ? "" : "s"} print under ${sub.min_pt || 10} pt. Your Submit went through as it is; the caller is told.</div>` : "");
  $("#loopRun").textContent = !tool() ? PICK_FIRST : tool() === "Internal" ? "Run a round here (PDF + Internal score)" : "Send to Rezi to score";
  $("#loopHint").innerHTML = s.pending ? `Waiting for cv_agent's Rezi result. cv_agent picks it up (cv.tool_status).`
    : "Ask the agent to tweak the CV or run it again. This tab refreshes by itself when a new PDF, score, issues or notes come in.";
}
$("#loopRun").onclick = async () => {
  if (!job?.content) return status("No CV yet: make the First Draft first", true);
  if (!tool()) return status(PICK_FIRST, true);
  if (tool() !== "Internal") { await draftFromScore(); return refreshLoop(true); }
  await saveNow(); status("Making the PDF and scoring it…");
  await call("/api/loop/internal", { id: job.id }); await refreshLoop(true); status("Round saved");
};
$("#submitCv").onclick = async () => {
  if (!job) return;
  await saveNow();
  const r = await call("/api/submit", { id: job.id });
  await refreshLoop(true);
  const small = (r.small_text || []).length;
  status(`Submitted: ${r.pdf_path.split(/[\\/]/).pop()} and result.json are ready for the caller`
    + (small ? ` (warning: ${small} text piece${small === 1 ? "" : "s"} under ${r.min_pt || 10} pt)` : ""));
};
$("#t4").addEventListener("click", (ev) => { const f = ev.target.dataset.open; if (f) { ev.preventDefault(); call("/api/open", { path: f }); } });

// jobs from outside: ?job=<id> when started with a request, and inbox\*.json while open
async function checkInbox() {
  try {
    const made = await call("/api/inbox");
    if (made.length) { const j = made[made.length - 1]; await loadJobs(j.id); status(`New job from outside: ${j.company} – ${j.role}`); }
    const scored = await call("/api/rezi/results");  // Rezi results and agent updates
    const mine = scored.filter((s) => s.id === job?.id);
    if (mine.length) status(`New result in${mine[0].score != null ? ": score " + mine[0].score : ": new PDF or notes"}`);
    else if (scored.length) status(`New result in for ${scored[0].company}`);
    await refreshLoop();
  } catch (e) { /* shown in the status line by call() */ }
}
loadJobs(new URLSearchParams(location.search).get("job")).then(() => setInterval(checkInbox, 3000));
