const $ = (id) => document.getElementById(id);
let tier = "";
let selected = null;
let leads = [];

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
function toast(t) { const e = $("toast"); e.textContent = t; e.style.display = "block"; setTimeout(() => (e.style.display = "none"), 1800); }
async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}

async function loadStats() {
  const s = await api("/api/stats");
  $("stats").innerHTML = [
    ["", s.total, "Total leads"], ["hot", s.hot, "Hot"], ["warm", s.warm, "Warm"], ["cold", s.cold, "Cold"], ["won", s.won, "Won"],
  ].map(([c, v, l]) => `<div class="stat ${c}"><b>${v}</b><span>${l}</span></div>`).join("");
}

function renderTabs() {
  $("tabs").innerHTML = [["", "All"], ["hot", "Hot"], ["warm", "Warm"], ["cold", "Cold"]]
    .map(([t, l]) => `<button class="${tier === t ? "on" : ""}" data-t="${t}">${l}</button>`).join("");
  $("tabs").querySelectorAll("button").forEach((b) => (b.onclick = () => { tier = b.dataset.t; load(); }));
}

function renderList() {
  if (!leads.length) {
    $("list").innerHTML = '<div class="empty">No leads yet.<br>Chat on the demo site, or click "Load sample leads".</div>';
    return;
  }
  $("list").innerHTML = leads.map((l) => `
    <div class="row ${selected === l.id ? "sel" : ""}" data-id="${l.id}">
      <div class="score ${l.tier || "none"}">${l.score ?? "-"}</div>
      <div><b>${esc(l.name || "Unknown visitor")}<span class="tag">${esc(l.status)}</span></b>
      <span>${esc(l.company || l.source)} &middot; ${esc((l.need || "").slice(0, 46))}</span></div>
    </div>`).join("");
  $("list").querySelectorAll(".row").forEach((r) => (r.onclick = () => openLead(Number(r.dataset.id))));
}

async function openLead(id) {
  selected = id;
  renderList();
  const l = await api("/api/leads/" + id);
  const chat = (l.messages || []).map((m) => `<div class="m ${m.role}">${esc(m.content)}</div>`).join("");
  $("detail").innerHTML = `
    <h2>${esc(l.name || "Unknown visitor")} ${l.tier ? `<span class="tag" style="background:${l.tier === "hot" ? "#fee2e2" : l.tier === "warm" ? "#fef3c7" : "#dbeafe"}">${l.tier.toUpperCase()} &middot; ${l.score}</span>` : ""}</h2>
    <div class="meta">${esc(l.email || l.phone || "no contact yet")} &middot; source: ${esc(l.source)} &middot; ${new Date(l.created * 1000).toLocaleString()}</div>
    <div class="grid">
      <div class="kv"><span>Needs</span>${esc(l.need || "-")}</div>
      <div class="kv"><span>Budget</span>${esc(l.budget || "-")}</div>
      <div class="kv"><span>Timeline</span>${esc(l.timeline || "-")}</div>
    </div>
    <div class="box"><h4>AI summary</h4>${esc(l.summary || "Not qualified yet")}<br><br><b>Next step:</b> ${esc(l.next_step || "-")}</div>
    <div class="box"><h4>AI follow-up email draft</h4>
      ${l.email_subject ? `<b>Subject:</b> ${esc(l.email_subject)}<br><br>` : ""}<pre>${esc(l.email_body || "Will be written when the lead is qualified.")}</pre>
      <div class="acts"><button class="b p" id="bCopy">Copy email</button>
      ${l.email ? `<a class="b" style="text-decoration:none;color:inherit" href="mailto:${encodeURIComponent(l.email)}?subject=${encodeURIComponent(l.email_subject || "")}&body=${encodeURIComponent(l.email_body || "")}">Open in mail app</a>` : ""}
      <button class="b" id="bRe">Re-score with AI</button></div></div>
    ${chat ? `<div class="box"><h4>Conversation</h4><div class="chat">${chat}</div></div>` : ""}
    <div class="acts"><label>Status: <select id="stSel">${["new", "contacted", "won", "lost"].map((s) => `<option ${s === l.status ? "selected" : ""}>${s}</option>`).join("")}</select></label>
      <button class="b d" id="bDel">Delete</button></div>`;
  $("bCopy").onclick = async () => { await navigator.clipboard.writeText((l.email_subject ? "Subject: " + l.email_subject + "\n\n" : "") + (l.email_body || "")); toast("Email copied"); };
  $("bRe").onclick = async () => { toast("Scoring..."); try { await api(`/api/leads/${id}/requalify`, { method: "POST" }); await load(); openLead(id); } catch (e) { toast(e.message); } };
  $("stSel").onchange = async (e) => { await api("/api/leads/" + id, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: e.target.value }) }); load(); };
  $("bDel").onclick = async () => { if (confirm("Delete this lead?")) { await api("/api/leads/" + id, { method: "DELETE" }); selected = null; $("detail").innerHTML = '<div class="empty">Lead deleted.</div>'; load(); } };
}

async function load() {
  leads = await api("/api/leads" + (tier ? "?tier=" + tier : ""));
  renderTabs();
  renderList();
  loadStats();
}

$("bSeed").onclick = async () => { const r = await api("/api/seed", { method: "POST" }); toast(r.added + " sample leads added"); load(); };
$("bProfile").onclick = async () => { const p = await api("/api/profile"); $("pName").value = p.business_name; $("pServ").value = p.services; $("dlg").showModal(); };
$("pClose").onclick = () => $("dlg").close();
$("pSave").onclick = async () => {
  await api("/api/profile", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ business_name: $("pName").value, services: $("pServ").value }) });
  $("dlg").close(); toast("Saved");
};

api("/api/health").then((h) => { $("mode").textContent = h.mode === "live" ? "Live AI: " + h.model : "Demo mode (no API key)"; });
load();
setInterval(() => { load(); }, 6000);
