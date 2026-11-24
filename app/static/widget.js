/* LeadPilot chat widget. Embed on any website:
   <script src="http://127.0.0.1:8002/widget.js" data-title="Chat with us"></script> */
(function () {
  var script = document.currentScript;
  var API = new URL(script.src).origin;
  var TITLE = script.getAttribute("data-title") || "Chat with us";
  var KEY = "leadpilot_session";
  var sid = null;
  try { sid = localStorage.getItem(KEY); } catch (e) {}

  var css = document.createElement("style");
  css.textContent =
    "#lp-btn{position:fixed;right:22px;bottom:22px;width:58px;height:58px;border-radius:50%;border:0;cursor:pointer;background:linear-gradient(135deg,#6d5efc,#3b82f6);color:#fff;font-size:26px;box-shadow:0 8px 24px rgba(59,89,252,.45);z-index:99998}" +
    "#lp-box{position:fixed;right:22px;bottom:92px;width:350px;max-width:calc(100vw - 30px);height:480px;max-height:calc(100vh - 120px);background:#fff;border-radius:16px;box-shadow:0 18px 50px rgba(15,23,42,.28);display:none;flex-direction:column;overflow:hidden;z-index:99999;font-family:'Segoe UI',Arial,sans-serif}" +
    "#lp-box.open{display:flex}" +
    "#lp-head{background:linear-gradient(135deg,#6d5efc,#3b82f6);color:#fff;padding:14px 16px;font-weight:600;display:flex;justify-content:space-between;align-items:center}" +
    "#lp-head small{display:block;font-weight:400;opacity:.85;font-size:11px}" +
    "#lp-msgs{flex:1;overflow-y:auto;padding:14px;background:#f5f7fb;display:flex;flex-direction:column;gap:8px}" +
    ".lp-m{max-width:82%;padding:9px 12px;border-radius:14px;font-size:14px;line-height:1.4;white-space:pre-wrap;word-wrap:break-word}" +
    ".lp-a{background:#fff;color:#1f2937;align-self:flex-start;border-bottom-left-radius:4px;box-shadow:0 1px 2px rgba(0,0,0,.06)}" +
    ".lp-u{background:#4f5fe8;color:#fff;align-self:flex-end;border-bottom-right-radius:4px}" +
    "#lp-form{display:flex;gap:8px;padding:10px;border-top:1px solid #e5e7eb;background:#fff}" +
    "#lp-in{flex:1;border:1px solid #d1d5db;border-radius:20px;padding:9px 14px;font-size:14px;outline:none}" +
    "#lp-send{border:0;background:#4f5fe8;color:#fff;border-radius:20px;padding:0 16px;cursor:pointer;font-weight:600}" +
    "#lp-send:disabled{opacity:.5}" +
    ".lp-typing{color:#6b7280;font-size:13px;align-self:flex-start;padding:4px 8px}";
  document.head.appendChild(css);

  var btn = document.createElement("button");
  btn.id = "lp-btn";
  btn.setAttribute("aria-label", "Open chat");
  btn.textContent = "💬";
  var box = document.createElement("div");
  box.id = "lp-box";
  box.innerHTML =
    '<div id="lp-head"><div>' + TITLE + '<small>AI assistant • replies instantly</small></div></div>' +
    '<div id="lp-msgs"></div>' +
    '<form id="lp-form"><input id="lp-in" placeholder="Type your message..." autocomplete="off" maxlength="500"><button id="lp-send" type="submit">Send</button></form>';
  document.body.appendChild(btn);
  document.body.appendChild(box);

  var msgs = box.querySelector("#lp-msgs");
  var input = box.querySelector("#lp-in");
  var send = box.querySelector("#lp-send");

  function add(role, text) {
    var d = document.createElement("div");
    d.className = "lp-m " + (role === "user" ? "lp-u" : "lp-a");
    d.textContent = text;
    msgs.appendChild(d);
    msgs.scrollTop = msgs.scrollHeight;
  }

  function start() {
    var url = API + "/api/chat/start" + (sid ? "?session=" + encodeURIComponent(sid) : "");
    fetch(url, { method: "POST" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        sid = d.session;
        try { localStorage.setItem(KEY, sid); } catch (e) {}
        msgs.innerHTML = "";
        (d.history && d.history.length ? d.history : [{ role: "assistant", content: d.greeting }]).forEach(function (m) { add(m.role, m.content); });
      })
      .catch(function () { add("assistant", "Sorry, the chat is offline right now."); });
  }

  btn.onclick = function () {
    box.classList.toggle("open");
    if (box.classList.contains("open") && !msgs.children.length) start();
    if (box.classList.contains("open")) input.focus();
  };

  box.querySelector("#lp-form").onsubmit = function (e) {
    e.preventDefault();
    var text = input.value.trim();
    if (!text || !sid) return;
    input.value = "";
    add("user", text);
    send.disabled = true;
    var t = document.createElement("div");
    t.className = "lp-typing";
    t.textContent = "typing...";
    msgs.appendChild(t);
    msgs.scrollTop = msgs.scrollHeight;
    fetch(API + "/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ session: sid, message: text }) })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        t.remove();
        add("assistant", res.ok ? res.j.reply : "Sorry, something went wrong. Please try again.");
      })
      .catch(function () { t.remove(); add("assistant", "Connection problem. Please try again."); })
      .then(function () { send.disabled = false; input.focus(); });
  };
})();
