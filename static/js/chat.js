(function () {
  var E = window.ETQA, cfg = E.json("page-config"), t = E.json("ui-strings");
  var list = document.getElementById("messages"), form = document.getElementById("ask-form");
  var input = document.getElementById("question"), banner = document.getElementById("ai-banner");
  var conversationId = null, history = [], busy = false;

  function stageText(job) {
    if (job.status === "queued") return t.queued + (job.position ? " (" + t.position + " " + job.position + ")" : "");
    if (job.status === "retrying") return t.retrying;
    if (job.status === "running") return (job.progress && job.progress.stage === "generating") ? t.checking : t.searching;
    if (job.status === "cancelled") return t.cancelled;
    if (job.status === "failed" || job.status === "dead") return t.failed + (job.error ? ": " + job.error.split("\n")[0] : "");
    return "";
  }

  function citationsBlock(citations) {
    if (!citations || !citations.length) return null;
    var items = citations.map(function (c) {
      var where = [c.title + " v" + c.version_no, c.locator, c.section_path].filter(Boolean).join(" · ");
      return E.el("li", {}, [E.el("details", {}, [E.el("summary", { text: "[" + c.marker + "] " + where, dir: "auto" }),
        E.el("p", { class: "excerpt", text: c.excerpt || "", dir: "auto" })])]);
    });
    return E.el("div", { class: "citations" }, [E.el("h3", { text: t.sources }), E.el("ol", {}, items)]);
  }

  function feedbackBlock(messageId) {
    if (!cfg.saved || !cfg.feedback || !messageId) return null;
    var status = E.el("span", { class: "muted", role: "status" });
    function send(rating) {
      E.api("POST", "/api/v1/chat/messages/" + messageId + "/feedback/", { rating: rating }).then(function (r) {
        status.textContent = r.ok ? t.thanks : t.error;
      });
    }
    var up = E.el("button", { type: "button", class: "link", text: t.helpful }), down = E.el("button", { type: "button", class: "link", text: t.not_helpful });
    up.addEventListener("click", function () { send(1); });
    down.addEventListener("click", function () { send(-1); });
    return E.el("div", { class: "feedback" }, [up, down, status]);
  }

  function renderAnswer(li, result) {
    li.textContent = "";
    li.classList.remove("pending");
    if (result.evidence === "unsupported") li.appendChild(E.el("p", { class: "notice warn", text: t.unsupported }));
    if (result.evidence === "insufficient") li.classList.add("insufficient");
    li.appendChild(E.el("div", { class: "answer", text: result.answer || "", dir: "auto" }));
    var cites = citationsBlock(result.citations);
    if (cites) li.appendChild(cites);
    (result.notes || []).filter(function (n) { return n.indexOf("review the answer") !== -1; }).forEach(function (n) {
      li.appendChild(E.el("p", { class: "notice warn", text: n }));
    });
    var fb = feedbackBlock(result.message_id);
    if (fb) li.appendChild(fb);
  }

  function addMessage(role, text) {
    var li = E.el("li", { class: "msg " + role }, [E.el("div", { class: role === "user" ? "question" : "answer", text: text, dir: "auto" })]);
    list.appendChild(li);
    li.scrollIntoView({ block: "end" });
    return li;
  }

  function ask(question) {
    busy = true;
    addMessage("user", question);
    var li = addMessage("assistant pending", "");
    var status = E.el("p", { class: "status", role: "status", text: t.queued });
    var draft = E.el("div", { class: "answer draft", dir: "auto" });
    li.textContent = "";
    li.appendChild(status);
    li.appendChild(draft);
    var body = { question: question, collection_ids: document.getElementById("collection").value ? [Number(document.getElementById("collection").value)] : [] };
    if (cfg.saved) body.conversation_id = conversationId; else body.history = history.slice(-8);
    E.api("POST", "/api/v1/chat/ask/", body).then(function (res) {
      if (!res.ok) { status.textContent = t.failed + ": " + ((res.data && res.data.detail) || res.status); busy = false; return; }
      if (res.data.immediate) { renderAnswer(li, res.data.immediate); busy = false; return; }
      banner.hidden = res.data.ai_available !== false;
      if (res.data.conversation_id) { conversationId = res.data.conversation_id; loadConversations(); }
      var cancel = E.el("button", { type: "button", class: "link", text: t.cancel });
      cancel.addEventListener("click", function () { E.api("POST", "/api/v1/jobs/" + res.data.job_id + "/cancel/"); });
      li.appendChild(cancel);
      E.pollJob(res.data.job_id, function (job) {
        status.textContent = stageText(job);
        if (job.progress && job.progress.draft) draft.textContent = job.progress.draft;
        if (job.status === "completed") {
          banner.hidden = true;
          renderAnswer(li, job.result || {});
          history.push({ role: "user", content: question }, { role: "assistant", content: (job.result || {}).answer || "" });
          busy = false;
        } else if (["failed", "dead", "cancelled"].indexOf(job.status) !== -1) {
          cancel.remove();
          busy = false;
        }
      }, cfg.poll_running_ms, cfg.poll_idle_ms);
    });
  }

  function loadConversations() {
    if (!cfg.saved) return;
    E.api("GET", "/api/v1/chat/conversations/").then(function (res) {
      var ul = document.getElementById("conversations");
      ul.textContent = "";
      (res.data || []).forEach(function (c) {
        var b = E.el("button", { type: "button", class: "conv" + (c.id === conversationId ? " active" : ""), text: c.title, dir: "auto" });
        b.addEventListener("click", function () { openConversation(c.id); });
        ul.appendChild(E.el("li", {}, [b]));
      });
    });
  }

  function openConversation(id) {
    E.api("GET", "/api/v1/chat/conversations/" + id + "/").then(function (res) {
      if (!res.ok) return;
      conversationId = id;
      list.textContent = "";
      res.data.messages.forEach(function (m) {
        if (m.role === "user") { addMessage("user", m.content); return; }
        var li = addMessage("assistant", "");
        renderAnswer(li, { answer: m.content, evidence: m.evidence, citations: m.citations, message_id: m.id });
      });
      loadConversations();
    });
  }

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var q = input.value.trim();
    if (!q || busy) return;
    input.value = "";
    ask(q);
  });
  input.addEventListener("keydown", function (ev) {
    if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); form.requestSubmit(); }
  });
  var newChat = document.getElementById("new-chat");
  if (newChat) newChat.addEventListener("click", function () { conversationId = null; list.textContent = ""; loadConversations(); input.focus(); });
  loadConversations();
})();
