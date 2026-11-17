// Shared helpers. Model and document text is always inserted with textContent, never as HTML.
(function () {
  function csrfToken() {
    var m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }
  function api(method, url, body, isForm) {
    var opts = { method: method, credentials: "same-origin", headers: { "X-CSRFToken": csrfToken() } };
    if (body !== undefined) {
      if (isForm) { opts.body = body; } else { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
    }
    return fetch(url, opts).then(function (r) {
      return r.text().then(function (txt) {
        var data = null;
        try { data = txt ? JSON.parse(txt) : null; } catch (e) { data = { detail: txt.slice(0, 200) }; }
        return { ok: r.ok, status: r.status, data: data };
      });
    });
  }
  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === "text") node.textContent = attrs[k];
      else if (k === "class") node.className = attrs[k];
      else if (k === "hidden") node.hidden = attrs[k];
      else node.setAttribute(k, attrs[k]);
    });
    (children || []).forEach(function (c) { if (c) node.appendChild(c); });
    return node;
  }
  function json(id) { var n = document.getElementById(id); return n ? JSON.parse(n.textContent) : {}; }
  // Polls a job until it ends. onUpdate receives the job status body each time.
  function pollJob(jobId, onUpdate, fastMs, slowMs) {
    var stopped = false;
    function tick() {
      if (stopped) return;
      api("GET", "/api/v1/jobs/" + jobId + "/").then(function (res) {
        if (!res.ok) { onUpdate({ status: "failed", error: (res.data && res.data.detail) || "HTTP " + res.status }); return; }
        onUpdate(res.data);
        if (["completed", "failed", "dead", "cancelled"].indexOf(res.data.status) === -1) {
          setTimeout(tick, res.data.status === "running" ? (fastMs || 500) : (slowMs || 1500));
        }
      }).catch(function () { setTimeout(tick, 3000); });
    }
    tick();
    return function () { stopped = true; };
  }
  function fmtDate(iso) {
    try { return new Date(iso).toLocaleString(document.documentElement.lang === "ar" ? "ar-EG" : "en-GB"); } catch (e) { return iso; }
  }
  window.ETQA = { api: api, el: el, json: json, pollJob: pollJob, fmtDate: fmtDate };

  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest(".lang-switch");
    if (!btn) return;
    var lang = btn.getAttribute("data-lang");
    if (btn.hasAttribute("data-authenticated")) {
      api("PATCH", "/api/v1/me/", { preferred_language: lang }).then(function (r) { if (r.ok) window.location.reload(); });
    } else {
      document.cookie = "etqa_lang=" + lang + "; path=/; max-age=31536000; samesite=lax";
      window.location.reload();
    }
  });
})();
