(function () {
  var E = window.ETQA, cfg = E.json("page-config"), t = E.json("ui-strings");
  var form = document.getElementById("tc-form"), setsUl = document.getElementById("sets");

  function modeSwitch() {
    var mode = form.querySelector("input[name=mode]:checked").value;
    form.querySelectorAll("[data-mode]").forEach(function (n) { n.hidden = n.getAttribute("data-mode") !== mode; });
  }
  form.querySelectorAll("input[name=mode]").forEach(function (r) { r.addEventListener("change", modeSwitch); });

  E.api("GET", "/api/v1/documents/").then(function (res) {
    var sel = form.querySelector("select[name=document]");
    (res.data || []).filter(function (d) { return d.current_version && d.current_version.ingest_status !== "failed"; }).forEach(function (d) {
      sel.appendChild(E.el("option", { value: d.id, text: d.title + " (" + d.collection_name + ")" }));
    });
  });
  E.api("GET", "/api/v1/testcases/templates/").then(function (res) {
    var sel = form.querySelector("select[name=template]");
    (res.data || []).forEach(function (tpl) {
      var o = E.el("option", { value: tpl.id, text: tpl.name });
      if (tpl.is_default) o.selected = true;
      sel.appendChild(o);
    });
  });

  function statusLabel(s) { return t[s] || s; }

  function loadSets() {
    E.api("GET", "/api/v1/testcases/sets/").then(function (res) {
      setsUl.textContent = "";
      var sets = res.data || [];
      if (!sets.length) setsUl.appendChild(E.el("li", { class: "muted", text: t.no_sets }));
      sets.forEach(function (s) {
        var kept = s.summary && s.summary.kept !== undefined ? " · " + s.summary.kept + " " + t.cases : "";
        var b = E.el("button", { type: "button", class: "link", text: t.view });
        b.addEventListener("click", function () { openSet(s.id); });
        setsUl.appendChild(E.el("li", {}, [E.el("span", { text: s.title, dir: "auto" }),
          E.el("span", { class: "chip " + s.status, text: statusLabel(s.status) }), E.el("span", { class: "muted", text: kept }), b]));
      });
    });
  }

  function openSet(id) {
    E.api("GET", "/api/v1/testcases/sets/" + id + "/").then(function (res) {
      if (!res.ok) return;
      var s = res.data, view = document.getElementById("set-view");
      view.hidden = false;
      document.getElementById("set-title").textContent = s.title;
      var sm = s.summary || {};
      document.getElementById("set-summary").textContent = sm.kept !== undefined
        ? sm.kept + " " + t.cases + " · " + (sm.duplicates || 0) + " " + t.duplicates + " · " + (sm.invalid || 0) + " " + t.invalid
        : statusLabel(s.status);
      var exp = document.getElementById("export-link");
      exp.hidden = !(cfg.export && s.cases.length);
      exp.href = "/api/v1/testcases/sets/" + id + "/export.xlsx";
      var head = document.getElementById("cases-head"), body = document.getElementById("cases-body");
      head.textContent = ""; body.textContent = "";
      var cols = s.columns.concat([{ key: "_sources", label: t.sources }]);
      head.appendChild(E.el("tr", {}, cols.map(function (c) { return E.el("th", { text: c.label }); })));
      s.cases.forEach(function (tc) {
        body.appendChild(E.el("tr", { class: tc.assumption ? "assumption" : "" }, cols.map(function (c) {
          var text;
          if (c.key === "steps") text = tc.steps.map(function (st, i) { return (i + 1) + ". " + st.action; }).join("\n");
          else if (c.key === "expected_result") text = tc.steps.map(function (st, i) { return (i + 1) + ". " + st.expected; }).join("\n") + "\n" + (tc.fields.expected_result || "");
          else if (c.key === "_sources") text = tc.sources.length ? tc.sources.map(function (x) { return x.title + " · " + x.locator; }).join("\n") : t.assumption;
          else text = tc.fields[c.key] || "";
          return E.el("td", { text: text, dir: "auto" });
        })));
      });
      view.scrollIntoView({ block: "start" });
    });
  }

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    if (!cfg.allowed) return;
    var fd = new FormData(form), mode = fd.get("mode"), msg = document.getElementById("tc-msg");
    var body = { instructions: fd.get("instructions") || "", template: Number(fd.get("template")) || undefined,
                 fill_priority: !!fd.get("fill_priority"), lang: document.documentElement.lang === "ar" ? "ar" : "en" };
    if (mode === "document") body.document = Number(fd.get("document"));
    else { body.collection = Number(fd.get("collection")); body.requirement = fd.get("requirement") || ""; }
    msg.textContent = t.queued;
    E.api("POST", "/api/v1/testcases/sets/", body).then(function (res) {
      if (!res.ok) { msg.textContent = (res.data && res.data.detail) || t.error; return; }
      loadSets();
      E.pollJob(res.data.job_id, function (job) {
        var stage = job.progress && job.progress.stage ? " · " + job.progress.stage : "";
        msg.textContent = statusLabel(job.status) + (job.position ? " (" + t.position + " " + job.position + ")" : "") + stage;
        if (job.status === "completed") { msg.textContent = ""; loadSets(); openSet(res.data.id); }
        if (job.status === "failed" || job.status === "dead") { msg.textContent = t.failed + ": " + (job.error || "").split("\n")[0]; loadSets(); }
      }, 1500, 2500);
    });
  });
  modeSwitch();
  loadSets();
})();
