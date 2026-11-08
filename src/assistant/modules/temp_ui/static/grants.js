// ROUGH, THROWAWAY grants screen for the temp UI (agent-permissions note, step 7).
// Everything about it lives in this file: its header button, its panel, its styles. It lists the
// saved access grants (permissions.grants) and takes back a whole grant or single items
// (permissions.revoke) through POST /grants; the caller is temp_ui, which is you clicking, so a
// revoke applies at once: the module turns off and its running task is stopped.
// Delete this file and its <script> tag when the real UI handler has a grants view.
(() => {
  const css = `
  #grants-panel { position: fixed; top: 56px; right: 16px; width: min(560px, 92vw); max-height: 75vh; overflow: auto;
    background: var(--bg, #fff); color: var(--text, #222); border: 2px dashed #b07a00; border-radius: 8px; padding: 10px 12px;
    box-shadow: 0 6px 24px rgba(0,0,0,.25); z-index: 50; font-size: 13px; }
  #grants-panel h2 { font-size: 14px; margin: 0 0 6px; }
  #grants-panel .rough { font-size: 11px; color: #b07a00; font-weight: 600; text-transform: uppercase; }
  #grants-panel .grant { border-top: 1px solid var(--border, #ddd); padding: 6px 0; }
  #grants-panel .item { display: flex; gap: 8px; align-items: baseline; font: 12px/1.5 ui-monospace, Consolas, monospace; }
  #grants-panel .item button, #grants-panel .head button { height: 22px; font-size: 11px; }
  #grants-panel .head { display: flex; gap: 8px; align-items: center; justify-content: space-between; }
  #grants-panel .meta { color: var(--muted, #777); font-size: 11.5px; }`;
  document.head.append(Object.assign(document.createElement("style"), { textContent: css }));

  const call = (body) => fetch("/grants", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
    .then((r) => r.json()).catch(() => ({ ok: false, error: "no connection" }));
  const el = (tag, props = {}, ...kids) => { const e = Object.assign(document.createElement(tag), props); e.append(...kids); return e; };

  const panel = el("div", { id: "grants-panel", hidden: true });
  document.body.append(panel);
  const button = el("button", { className: "ghost", title: "Rough, throwaway: the saved access grants", textContent: "Grants (rough)" });
  document.querySelector("header").append(button);
  button.onclick = () => { panel.hidden = !panel.hidden; if (!panel.hidden) show(); };

  async function revoke(g, items) {
    const what = items ? items.join(", ") : "its whole grant";
    if (!confirm(`Take back ${what} from ${g.module_id} (${g.subject})?\nIt turns off right away and its running task is stopped.`)) return;
    const r = await call({ action: "revoke", module_id: g.module_id, subject: g.subject, items });
    alert(r.ok ? r.value : "Couldn't take it back: " + (r.error || "unknown error"));
    show();
  }

  async function show() {
    const r = await call({ action: "list" });
    const head = el("div", { className: "head" }, el("h2", { textContent: "Saved access grants" }),
      el("span", { className: "rough", textContent: "rough · throwaway" }), el("button", { textContent: "Close", onclick: () => (panel.hidden = true) }));
    if (!r.ok) return panel.replaceChildren(head, el("div", { textContent: "Couldn't load: " + (r.error || "unknown error") }));
    if (!r.value.length) return panel.replaceChildren(head, el("div", { className: "meta", textContent: "No saved grants yet." }));
    panel.replaceChildren(head, ...r.value.map((g) => {
      const state = g.denied ? "denied" : g.waiting ? "waiting on a card" : g.matches === false ? "its list changed: asks again at turn-on" : "";
      const rows = g.granted.map((key, n) => el("div", { className: "item" },
        el("button", { textContent: "Take back", onclick: () => revoke(g, [key]) }), g.labels[n] || key));
      const all = g.granted.length ? el("button", { textContent: "Take back all", onclick: () => revoke(g, null) }) : "";
      return el("div", { className: "grant" },
        el("div", { className: "head" }, el("b", { textContent: `${g.module_id} → ${g.subject}` }), all),
        el("div", { className: "meta", textContent: [g.date && "saved " + g.date, `${g.granted.length} of ${g.asked.length} items`, state].filter(Boolean).join(" · ") }),
        ...rows);
    }));
  }
})();
