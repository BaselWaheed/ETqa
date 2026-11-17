(function () {
  var E = window.ETQA, cfg = E.json("page-config"), t = E.json("ui-strings");
  var rows = document.getElementById("doc-rows"), form = document.getElementById("upload-form"), timer = null;

  function statusCell(v) {
    if (!v) return E.el("td", { text: "-" });
    var label = t[v.ingest_status] || v.ingest_status;
    var td = E.el("td", {}, [E.el("span", { class: "chip " + v.ingest_status, text: label })]);
    if (v.ingest_status === "ready" && !v.embedded) td.appendChild(E.el("small", { class: "muted block", text: t.semantic_pending }));
    if (v.ingest_error) td.appendChild(E.el("small", { class: "muted block", text: v.ingest_error }));
    return td;
  }

  function load() {
    E.api("GET", "/api/v1/documents/").then(function (res) {
      rows.textContent = "";
      var docs = res.data || [], busy = false;
      if (!docs.length) rows.appendChild(E.el("tr", {}, [E.el("td", { colspan: "5", class: "muted", text: t.no_documents })]));
      docs.forEach(function (d) {
        var v = d.current_version;
        if (v && (v.ingest_status === "pending" || v.ingest_status === "processing" || (v.ingest_status === "ready" && !v.embedded))) busy = true;
        var actions = E.el("td", { class: "actions" });
        if (v) actions.appendChild(E.el("a", { href: "/api/v1/documents/" + d.id + "/versions/" + v.id + "/file/", text: t.download }));
        if (cfg.manage.indexOf(d.collection) !== -1 || cfg.can_delete) {
          var re = E.el("button", { type: "button", class: "link", text: t.reingest });
          re.addEventListener("click", function () { E.api("POST", "/api/v1/documents/" + d.id + "/reingest/").then(load); });
          actions.appendChild(re);
        }
        if (cfg.can_delete) {
          var ar = E.el("button", { type: "button", class: "link", text: t.archive });
          ar.addEventListener("click", function () { if (window.confirm(t.confirm_archive)) E.api("DELETE", "/api/v1/documents/" + d.id + "/").then(load); });
          actions.appendChild(ar);
        }
        rows.appendChild(E.el("tr", {}, [E.el("td", { text: d.title, dir: "auto" }), E.el("td", { text: d.collection_name }),
          statusCell(v), E.el("td", { text: E.fmtDate(d.updated_at) }), actions]));
      });
      clearTimeout(timer);
      if (busy) timer = setTimeout(load, 3000);
    });
  }

  if (form) form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var msg = document.getElementById("upload-msg");
    msg.textContent = t.processing;
    E.api("POST", "/api/v1/documents/", new FormData(form), true).then(function (res) {
      msg.textContent = res.ok ? "" : ((res.data && res.data.detail) || t.error);
      if (res.ok) form.reset();
      load();
    });
  });
  load();
})();
