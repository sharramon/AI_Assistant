// The agent tabs' + and × (plus-agent-tab note). Everything about them lives in this file; the
// page calls window.agentTabsExtras(tabs, item) after it draws the tabs. Both go through
// POST /agent-tabs as temp_ui, which is you clicking:
// - +: a small panel to open your own helper: its kind (agents.kinds), a name (filled with a free
//   one), an optional first task. Your click is the yes, so no launch card; the kind's access card
//   still shows unless its grant is saved. The new tab takes the focus when it appears.
// - ×: on every tab but the Main Assistant's. It asks first ("Close this agent?", Close / Cancel);
//   a close cancels the agent's running task, then closes it (a launched helper) or turns off
//   the module it belongs to (the job agent).
(() => {
  const css = `
  .tab-plus { min-width: 28px; font-weight: 700; }
  .tab .tab-x { margin-left: 6px; padding: 0 3px; border-radius: 4px; opacity: .6; font-weight: 700; }
  .tab .tab-x:hover { opacity: 1; background: rgba(0,0,0,.12); }
  #agent-panel, #agent-confirm { position: fixed; top: 96px; left: 16px; width: min(420px, 92vw); z-index: 60;
    background: var(--panel, #fff); color: var(--text, #222); border: 1px solid var(--border, #ddd); border-radius: 10px;
    padding: 12px 14px; box-shadow: 0 6px 24px rgba(0,0,0,.25); font-size: 13px; display: flex; flex-direction: column; gap: 8px; }
  #agent-panel[hidden], #agent-confirm[hidden] { display: none; }  /* display: flex above beats the hidden attribute */
  #agent-panel h2, #agent-confirm h2 { font-size: 14px; margin: 0; }
  #agent-panel label { display: flex; flex-direction: column; gap: 3px; font-size: 12px; color: var(--muted, #777); }
  #agent-panel input, #agent-panel select, #agent-panel textarea { font: inherit; color: var(--text, #222);
    background: var(--bg, #fff); border: 1px solid var(--border, #ddd); border-radius: 6px; padding: 5px 7px; }
  #agent-panel textarea { min-height: 54px; resize: vertical; }
  #agent-panel .why, #agent-confirm .why { font-size: 12px; color: var(--muted, #777); }
  #agent-panel .error { color: #b3261e; font-size: 12px; }
  .agent-buttons { display: flex; gap: 8px; justify-content: flex-end; }
  .agent-buttons button { height: 30px; padding: 0 14px; border-radius: 8px; border: 1px solid var(--border, #ddd);
    background: transparent; color: var(--text, #222); font: inherit; cursor: pointer; }
  .agent-buttons button.go { background: var(--accent, #6b4fa0); border-color: var(--accent, #6b4fa0); color: #fff; }
  .agent-buttons button.danger { background: #b3261e; border-color: #b3261e; color: #fff; }`;
  document.head.append(Object.assign(document.createElement("style"), { textContent: css }));

  const el = (tag, props = {}, ...kids) => { const e = Object.assign(document.createElement(tag), props); e.append(...kids); return e; };
  const call = (body) => post("/agent-tabs", body).then((r) => r.json()).catch(() => ({ ok: false, error: "no connection" }));
  const free = (error) => (/`([a-z][a-z0-9_]*)` is free/.exec(error || "") || [])[1];

  const panel = el("div", { id: "agent-panel", hidden: true });
  const confirmBox = el("div", { id: "agent-confirm", hidden: true, role: "alertdialog" });
  document.body.append(panel, confirmBox);

  // --- the +: open your own helper ---

  async function openPanel() {
    confirmBox.hidden = true;
    panel.hidden = false;
    panel.replaceChildren(el("h2", { textContent: "Open a new agent" }), el("div", { className: "why", textContent: "Loading the kinds…" }));
    const r = await call({ action: "kinds" });
    if (!r.ok) return r.off ? showOff() : showError("Couldn't load the kinds: " + (r.error || "unknown error"));
    if (!r.value.kinds.length) return showError("No kinds of helper in the config ([modules.task_agents.agents]).");
    showForm(r.value.kinds);
  }

  function showError(text) {
    panel.replaceChildren(el("h2", { textContent: "Open a new agent" }), el("div", { className: "error", textContent: text }),
      el("div", { className: "agent-buttons" }, el("button", { textContent: "Close", onclick: () => (panel.hidden = true) })));
  }

  function showOff() {
    const on = el("button", { className: "go", textContent: "Turn them on" });
    on.onclick = async () => {
      on.disabled = true;
      const r = await call({ action: "turn_on" });
      r.ok ? openPanel() : showError("Couldn't turn the helpers on: " + (r.error || "unknown error"));
    };
    panel.replaceChildren(el("h2", { textContent: "Open a new agent" }),
      el("div", { className: "why", textContent: "Helpers are off (the task_agents module)." }),
      el("div", { className: "agent-buttons" }, el("button", { textContent: "Cancel", onclick: () => (panel.hidden = true) }), on));
  }

  function showForm(kinds) {
    const kind = el("select", {}, ...kinds.map((k) => el("option", { value: k.kind, textContent: k.kind })));
    const about = el("div", { className: "why" });
    const name = el("input", { type: "text", maxLength: 32, spellcheck: false });
    const task = el("textarea", { placeholder: "Optional. Leave empty to open an idle tab and type to it." });
    const error = el("div", { className: "error" });
    const pick = () => { const k = kinds.find((k) => k.kind === kind.value); about.textContent = k.description || ""; name.value = k.free_name; };
    kind.onchange = pick;
    pick();
    const open = el("button", { className: "go", textContent: "Open" });
    open.onclick = async () => {
      open.disabled = true;
      error.textContent = "";
      const r = await call({ action: "open", kind: kind.value, name: name.value.trim(), task: task.value.trim() });
      open.disabled = false;
      if (r.ok) return (panel.hidden = true);
      error.textContent = r.error || "unknown error";
      const suggested = free(r.error);
      if (suggested) name.value = suggested;  // you gave the name: the free one is filled in, you click Open again
    };
    panel.replaceChildren(el("h2", { textContent: "Open a new agent" }),
      el("label", {}, "Kind", kind), about,
      el("label", {}, "Name (lowercase letters, digits and _)", name),
      el("label", {}, "First task", task), error,
      el("div", { className: "agent-buttons" }, el("button", { textContent: "Cancel", onclick: () => (panel.hidden = true) }), open));
    name.focus();
  }

  // --- the ×: close an agent, after a warning ---

  function askClose(id) {
    panel.hidden = true;
    const close = el("button", { className: "danger", textContent: "Close" });
    const cancel = el("button", { textContent: "Cancel", onclick: () => (confirmBox.hidden = true) });
    const why = el("div", { className: "why", textContent: `${label(id)} will be closed. Any task it's running will be cancelled.` });
    close.onclick = async () => {
      close.disabled = cancel.disabled = true;
      why.textContent = "Closing…";
      const r = await call({ action: "close", agent_id: id });
      if (r.ok) return (confirmBox.hidden = true);
      why.textContent = "Couldn't close it: " + (r.error || "unknown error");
      cancel.disabled = false;
      cancel.textContent = "OK";
    };
    confirmBox.replaceChildren(el("h2", { textContent: "Close this agent?" }), why, el("div", { className: "agent-buttons" }, cancel, close));
    confirmBox.hidden = false;
    cancel.focus();
  }

  window.agentTabsExtras = (tabsEl, item) => {
    for (const b of tabsEl.querySelectorAll(".tab[data-agent]")) {
      if (b.dataset.agent === item.coordinator) continue;
      const x = el("span", { className: "tab-x", textContent: "×", title: "Close " + b.dataset.agent });
      x.setAttribute("role", "button");
      x.onclick = (e) => { e.stopPropagation(); askClose(b.dataset.agent); };
      b.append(x);
    }
    const plus = el("button", { type: "button", className: "tab tab-plus", textContent: "+", title: "Open a new agent of your own" });
    plus.onclick = openPanel;
    tabsEl.append(plus);
  };
  if (typeof agents !== "undefined") showAgents(agents);  // draw the + now, if the tabs came before this file
})();
