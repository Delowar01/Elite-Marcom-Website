/* Elite Marcom admin — Phase 0 shell: dashboard, users, audit, settings, security */
(function () {
  "use strict";
  var main = document.getElementById("admin-main");
  var toastEl = document.getElementById("admin-toast");
  var me = null;

  function esc(s) {
    var d = document.createElement("div");
    d.textContent = String(s == null ? "" : s);
    return d.innerHTML;
  }
  function when(ts) {
    if (!ts) return "—";
    return new Date(ts * 1000).toLocaleString();
  }
  var toastTimer = null;
  function toast(msg, isErr) {
    toastEl.textContent = msg;
    toastEl.className = "admin-toast" + (isErr ? " err" : "");
    toastEl.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.hidden = true; }, 3500);
  }
  function api(path, body) {
    var opts = { method: body ? "POST" : "GET", headers: {} };
    if (body) {
      opts.headers["Content-Type"] = "application/json";
      opts.headers["X-CSRF"] = me ? me.csrf : "";
      opts.body = JSON.stringify(body);
    }
    return fetch(path, opts).then(function (res) {
      if (res.status === 401) { location.replace("/admin"); throw new Error("signed out"); }
      return res.json().catch(function () { return {}; }).then(function (data) {
        return { ok: res.ok, data: data };
      });
    });
  }
  function apiErr(r) {
    toast((r.data && r.data.detail) || "That did not work — try again.", true);
  }
  function apiUpload(path, formData) {
    return fetch(path, {
      method: "POST", headers: { "X-CSRF": me ? me.csrf : "" }, body: formData
    }).then(function (res) {
      if (res.status === 401) { location.replace("/admin"); throw new Error("signed out"); }
      return res.json().catch(function () { return {}; }).then(function (data) {
        return { ok: res.ok, data: data };
      });
    });
  }
  function fmtBytes(n) {
    if (!n) return "0 B";
    if (n < 1024) return n + " B";
    if (n < 1048576) return (n / 1024).toFixed(0) + " KB";
    return (n / 1048576).toFixed(1) + " MB";
  }
  function can(perm) {
    return me && me.permissions.indexOf(perm) !== -1;
  }

  var KIND_LABELS = {
    giveaway_enquiry: "Gift enquiry", rental_enquiry: "Rental enquiry",
    contact: "Contact", career: "Career", giveaway_notification: "Gift stock alert",
    rental_notification: "Rental alert"
  };
  var STATUS_LABELS = {
    new: "New", in_progress: "In progress", quoted: "Quoted",
    won: "Won", lost: "Lost", closed: "Closed"
  };
  function statusPill(s) {
    return '<span class="status-pill status-' + esc(s) + '">' + esc(STATUS_LABELS[s] || s) + "</span>";
  }
  function fieldLabel(k) {
    return k.replace(/([A-Z])/g, " $1").replace(/^./, function (c) { return c.toUpperCase(); });
  }

  var reqState = { kind: "", status: "", q: "", offset: 0, sel: {} };

  /* ---------- floating row menu (⋮) ---------- */
  var openMenuEl = null;
  function closeMenu() {
    if (openMenuEl) { openMenuEl.remove(); openMenuEl = null; }
  }
  document.addEventListener("click", function (e) {
    if (openMenuEl && !openMenuEl.contains(e.target)) closeMenu();
  });
  function showMenu(anchor, entries) {
    closeMenu();
    var pop = document.createElement("div");
    pop.className = "menu-pop";
    entries.forEach(function (en) {
      if (en === "-") {
        var sep = document.createElement("div");
        sep.className = "menu-sep";
        pop.appendChild(sep);
        return;
      }
      if (en.children) {
        var wrap = document.createElement("div");
        wrap.className = "menu-item has-sub";
        var parent = document.createElement("button");
        parent.type = "button";
        parent.innerHTML = esc(en.label) + '<span class="sub-caret">▸</span>';
        var sub = document.createElement("div");
        sub.className = "menu-sub-pop";
        en.children.forEach(function (child) {
          var cel = document.createElement("button");
          cel.type = "button";
          cel.textContent = child.label;
          if (child.danger) cel.className = "menu-danger";
          cel.addEventListener("click", function (ev) {
            ev.stopPropagation();
            closeMenu();
            child.action();
          });
          sub.appendChild(cel);
        });
        parent.addEventListener("click", function (ev) {
          ev.stopPropagation();
          var was = wrap.classList.contains("open");
          pop.querySelectorAll(".has-sub.open").forEach(function (o) { o.classList.remove("open"); });
          if (!was) wrap.classList.add("open");
        });
        wrap.appendChild(parent);
        wrap.appendChild(sub);
        pop.appendChild(wrap);
        return;
      }
      var el = document.createElement("button");
      el.type = "button";
      el.textContent = en.label;
      if (en.danger) el.className = "menu-danger";
      el.addEventListener("click", function (ev) {
        ev.stopPropagation();
        closeMenu();
        en.action();
      });
      pop.appendChild(el);
    });
    document.body.appendChild(pop);
    var r = anchor.getBoundingClientRect();
    pop.style.top = Math.max(10, Math.min(window.innerHeight - pop.offsetHeight - 10, r.bottom + 4)) + "px";
    pop.style.left = Math.max(10, r.right - pop.offsetWidth) + "px";
    openMenuEl = pop;
  }

  function exportChildren(urlFor) {
    return ["csv", "xlsx", "pdf"].map(function (fmt) {
      var names = { csv: "CSV (spreadsheet)", xlsx: "Excel (.xlsx)", pdf: "PDF (branded)" };
      return { label: names[fmt], action: function () { location.href = urlFor(fmt); } };
    });
  }

  function requestAction(ref, body, after) {
    api("/api/admin/requests/" + encodeURIComponent(ref), body).then(function (r) {
      r.ok ? (toast("Saved."), after && after()) : apiErr(r);
    });
  }

  /* ---------- request detail ---------- */
  function requestDetail(ref) {
    api("/api/admin/requests/" + encodeURIComponent(ref)).then(function (r) {
      if (!r.ok) { apiErr(r); location.hash = "#requests"; return; }
      var d = r.data, p = d.payload || {}, meta = d.meta || {};
      var items = p.items || [];
      var skip = { items: 1, consentVersion: 1, sourcePage: 1, logoAttached: 1 };
      var kv = Object.keys(p).filter(function (k) { return !skip[k] && p[k] != null && p[k] !== ""; })
        .map(function (k) {
          var v = p[k];
          if (typeof v === "object") v = JSON.stringify(v);
          return '<div class="kv-row"><span>' + esc(fieldLabel(k)) + "</span><strong>" + esc(v) + "</strong></div>";
        }).join("");
      var itemRows = items.map(function (it) {
        var extra = [];
        if (it.quantity) extra.push("qty " + it.quantity);
        if (it.days) extra.push(it.days + " day(s)");
        if (it.color) extra.push(it.color);
        var brand = it.brandingPreference
          ? '<div class="admin-inline-note">Branding: ' + esc([it.brandingPreference.area, it.brandingPreference.method,
              it.brandingPreference.note].filter(Boolean).join(" · ")) + "</div>" : "";
        return "<tr><td>" + esc(it.name || it.productId || it.id || "—") + brand + "</td>" +
          '<td class="muted">' + esc(it.code || it.productId || it.id || "") + "</td>" +
          "<td>" + esc(extra.join(" · ") || "—") + "</td></tr>";
      }).join("");
      var noteRows = (meta.notes || []).map(function (n) {
        return '<div class="note-item"><div class="admin-inline-note">' + esc(when(n.ts)) + " · " + esc(n.by) + "</div>" +
          "<p>" + esc(n.text) + "</p></div>";
      }).join("");
      var manage = can("requests.manage");
      main.innerHTML =
        '<p><a href="#requests" class="btn btn--ghost btn--small">&larr; Back to inbox</a></p>' +
        '<h1 class="admin-h1">' + esc(d.reference) + "</h1>" +
        '<p class="admin-sub">' + esc(KIND_LABELS[d.kind] || d.kind) + " · received " + esc(when(d.createdAt)) +
        " · " + statusPill(meta.status || "new") + "</p>" +
        '<div class="req-detail">' +
        '<div><div class="admin-panel"><h2>Submission</h2>' + (kv || '<p class="admin-inline-note">No details.</p>') +
        (d.hasFile ? '<div class="admin-actions"><a class="btn btn--primary btn--small" href="/api/admin/requests/' +
          esc(d.reference) + '/file">Download attached file</a></div>' : "") + "</div>" +
        (items.length
          ? '<div class="admin-panel"><h2>Requested items (' + items.length + ')</h2><div class="table-scroll">' +
            '<table class="admin-table"><thead><tr><th>Item</th><th>Code</th><th>Details</th></tr></thead><tbody>' +
            itemRows + "</tbody></table></div></div>" : "") + "</div>" +
        '<div><div class="admin-panel"><h2>Workflow</h2>' +
        '<div class="admin-form">' +
        '<div class="full"><label for="rd-status">Status</label><select id="rd-status"' + (manage ? "" : " disabled") + ">" +
        Object.keys(STATUS_LABELS).map(function (s) {
          return '<option value="' + s + '"' + (s === meta.status ? " selected" : "") + ">" + esc(STATUS_LABELS[s]) + "</option>";
        }).join("") + "</select></div>" +
        '<div class="full"><label for="rd-assignee">Assigned to</label>' +
        '<input id="rd-assignee" maxlength="200" value="' + esc(meta.assignee || "") + '"' + (manage ? "" : " disabled") + "></div>" +
        '<div class="full"><label for="rd-note">Add a note</label>' +
        '<textarea id="rd-note" rows="3" maxlength="2000"' + (manage ? "" : " disabled") + "></textarea></div>" +
        (manage ? '<div class="full admin-actions"><button class="btn btn--primary btn--small" id="rd-save">Save</button></div>' : "") +
        "</div></div>" +
        '<div class="admin-panel"><h2>Notes (' + (meta.notes || []).length + ")</h2>" +
        (noteRows || '<p class="admin-inline-note">No notes yet.</p>') + "</div></div></div>";
      var save = document.getElementById("rd-save");
      if (save) save.addEventListener("click", function () {
        api("/api/admin/requests/" + encodeURIComponent(d.reference), {
          status: document.getElementById("rd-status").value,
          assignee: document.getElementById("rd-assignee").value.trim(),
          note: document.getElementById("rd-note").value.trim()
        }).then(function (r2) {
          r2.ok ? (toast("Saved."), requestDetail(d.reference)) : apiErr(r2);
        });
      });
    });
  }

  /* ---------- page editor ---------- */
  var pageLang = "en";

  function pageEditor(page) {
    api("/api/admin/pages/" + encodeURIComponent(page) + "?lang=" + pageLang).then(function (r) {
      if (!r.ok) { apiErr(r); location.hash = "#pages"; return; }
      var d = r.data;
      function fieldHtml(f, idx, group) {
        var id = group + "-" + idx;
        var input = f.kind === "multiline"
          ? '<textarea id="' + id + '" rows="3" maxlength="2000" placeholder="' + esc(f.original) + '">' + esc(f.value) + "</textarea>"
          : '<input id="' + id + '" maxlength="' + (f.max || 300) + '" placeholder="' + esc(f.original) + '" value="' + esc(f.value) + '">';
        return '<div class="full page-field" data-key="' + esc(f.key) + '" data-group="' + group + '">' +
          '<label for="' + id + '">' + esc(f.label) +
          (f.value ? ' <span class="badge-ok">edited</span>' : "") + "</label>" + input +
          '<span class="admin-inline-note">Original: ' + esc(f.original || "—") + "</span></div>";
      }
      main.innerHTML =
        '<p><a href="#pages" class="btn btn--ghost btn--small">&larr; All pages</a></p>' +
        '<h1 class="admin-h1">' + esc(d.label) + "</h1>" +
        '<p class="admin-sub">Leave a field empty to keep the original design text. Saved changes go live only when you publish.</p>' +
        '<div class="lang-tabs">' +
        '<button class="btn btn--small ' + (pageLang === "en" ? "btn--primary" : "btn--ghost") + '" data-lang="en">English</button>' +
        '<button class="btn btn--small ' + (pageLang === "ar" ? "btn--primary" : "btn--ghost") + '" data-lang="ar">العربية (Arabic)</button>' +
        (pageLang === "ar" ? '<span class="admin-inline-note">Arabic is saved as a draft and publishes once Arabic is enabled in Settings.</span>' : "") +
        "</div>" +
        '<form id="page-form">' +
        (d.regions.length
          ? '<div class="admin-panel"><h2>Content</h2><div class="admin-form">' +
            d.regions.map(function (f, i) { return fieldHtml(f, i, "rg"); }).join("") + "</div></div>" : "") +
        (d.seo.length
          ? '<div class="admin-panel"><h2>SEO &amp; sharing</h2><div class="admin-form">' +
            d.seo.map(function (f, i) { return fieldHtml(f, i, "seo"); }).join("") + "</div></div>" : "") +
        '<div class="admin-actions"><button class="btn btn--primary btn--small" type="submit">Save draft</button>' +
        (d.page !== "_global"
          ? '<a class="btn btn--ghost btn--small" href="/admin/preview/' + esc(d.page) + "?lang=" + pageLang + '" target="_blank" rel="noopener">Preview</a>' : "") +
        '<span class="admin-inline-note">Publish from the Pages overview when you are ready.</span></div></form>';

      main.querySelectorAll("[data-lang]").forEach(function (btn) {
        btn.addEventListener("click", function (e) {
          e.preventDefault();
          pageLang = btn.getAttribute("data-lang");
          pageEditor(page);
        });
      });
      document.getElementById("page-form").addEventListener("submit", function (e) {
        e.preventDefault();
        var values = {};
        main.querySelectorAll(".page-field").forEach(function (wrap) {
          values[wrap.getAttribute("data-key")] =
            wrap.querySelector("input, textarea").value.trim();
        });
        api("/api/admin/pages/" + encodeURIComponent(page), { lang: pageLang, values: values })
          .then(function (r2) {
            r2.ok ? (toast("Draft saved."), pageEditor(page)) : apiErr(r2);
          });
      });
    });
  }

  /* ---------- views ---------- */
  var views = {
    dashboard: function () {
      api("/api/admin/dashboard").then(function (r) {
        if (!r.ok) return apiErr(r);
        var d = r.data;
        var reqRows = Object.keys(d.requests || {}).map(function (k) {
          var labels = { giveaway_enquiry: "Gift enquiries", rental_enquiry: "Rental enquiries",
                         contact: "Contact messages", career: "Career applications" };
          return '<div class="stat-card"><b>' + esc(d.requests[k]) + "</b><span>" + esc(labels[k] || k) + "</span></div>";
        }).join("");
        main.innerHTML =
          '<h1 class="admin-h1">Welcome back, ' + esc(d.user.name) + "</h1>" +
          '<p class="admin-sub">Everything on the public site is running. Open Requests to work the inbox, or Jasani for supplier status.</p>' +
          '<div class="stat-row">' + reqRows +
            '<div class="stat-card"><b>' + esc(d.adminUsers) + "</b><span>Admin accounts</span></div></div>" +
          '<div class="admin-panel"><h2>Recent activity</h2><div class="table-scroll"><table class="admin-table"><thead>' +
          "<tr><th>When</th><th>Who</th><th>Action</th><th>Module</th></tr></thead><tbody>" +
          (d.audit || []).map(function (a) {
            return "<tr><td class=\"muted\">" + esc(when(a.ts)) + "</td><td>" + esc(a.user_email) +
                   "</td><td>" + esc(a.action) + "</td><td class=\"muted\">" + esc(a.module) + "</td></tr>";
          }).join("") + "</tbody></table></div></div>";
      });
    },

    requests: function (param) {
      if (param) return requestDetail(param);
      var qs = "limit=30&offset=" + reqState.offset +
        (reqState.kind ? "&kind=" + encodeURIComponent(reqState.kind) : "") +
        (reqState.status ? "&status=" + encodeURIComponent(reqState.status) : "") +
        (reqState.q ? "&q=" + encodeURIComponent(reqState.q) : "");
      api("/api/admin/requests?" + qs).then(function (r) {
        if (!r.ok) return apiErr(r);
        var d = r.data;
        var counts = d.statusCounts || {};
        var manage = can("requests.manage");
        var kindOpts = Object.keys(KIND_LABELS).map(function (k) {
          return '<option value="' + k + '"' + (reqState.kind === k ? " selected" : "") + ">" +
                 esc(KIND_LABELS[k]) + "</option>";
        }).join("");
        var statusOpts = (d.statuses || []).map(function (s) {
          return '<option value="' + s + '"' + (reqState.status === s ? " selected" : "") + ">" +
                 esc(STATUS_LABELS[s] || s) + "</option>";
        }).join("");
        var selCount = Object.keys(reqState.sel).length;
        main.innerHTML =
          '<h1 class="admin-h1">Requests inbox</h1>' +
          '<p class="admin-sub">Customer submissions decrypt on view — every view is recorded in the activity log.</p>' +
          '<div class="stat-row">' + (d.statuses || []).map(function (s) {
            return '<div class="stat-card stat-card--click" data-status="' + s + '"><b>' + esc(counts[s] || 0) +
                   "</b><span>" + esc(STATUS_LABELS[s] || s) + "</span></div>";
          }).join("") + "</div>" +
          '<div class="admin-panel"><div class="req-filters">' +
          '<select id="rq-kind"><option value="">All types</option>' + kindOpts + "</select>" +
          '<select id="rq-status"><option value="">All statuses</option>' + statusOpts + "</select>" +
          '<input id="rq-q" placeholder="Search reference (e.g. GV-XXXX)" maxlength="20" value="' + esc(reqState.q) + '">' +
          '<span class="admin-inline-note">' + esc(d.total) + " request(s)</span>" +
          '<span class="req-export"><button class="btn btn--ghost btn--small" id="rq-export">Export ▾</button></span></div>' +
          '<div class="bulk-bar" id="bulk-bar"' + (selCount ? "" : " hidden") + '><b id="bulk-count">' + selCount +
          '</b> selected — use <b>Export</b> to download them ' +
          '<button class="btn btn--ghost btn--small" id="bulk-clear">Clear selection</button></div>' +
          '<div class="table-scroll"><table class="admin-table"><thead>' +
          '<tr><th class="cell-check"><input type="checkbox" id="sel-all" aria-label="Select all"></th>' +
          "<th>Received</th><th>Reference</th><th>Type</th><th>From</th><th>Status</th><th>Notes</th><th></th></tr></thead><tbody>" +
          (d.requests || []).map(function (x) {
            var who = [x.summary.fullName, x.summary.company].filter(Boolean).join(" · ");
            return '<tr data-ref="' + esc(x.reference) + '">' +
              '<td class="cell-check"><input type="checkbox" data-sel' +
              (reqState.sel[x.reference] ? " checked" : "") + ' aria-label="Select ' + esc(x.reference) + '"></td>' +
              '<td class="muted">' + esc(when(x.createdAt)) + "</td>" +
              "<td><strong>" + esc(x.reference) + "</strong>" + (x.hasFile ? " 📎" : "") + "</td>" +
              '<td>' + esc(KIND_LABELS[x.kind] || x.kind) + (x.summary.items ? ' <span class="muted">(' + x.summary.items + " items)</span>" : "") + "</td>" +
              "<td>" + esc(who || "—") + "</td>" +
              "<td>" + statusPill(x.status) + "</td>" +
              '<td class="muted">' + (x.noteCount || 0) + "</td>" +
              '<td class="cell-actions"><a class="btn btn--ghost btn--small" href="#requests/' + esc(x.reference) + '">Open</a> ' +
              '<button class="icon-btn dots-btn" data-dots aria-label="Actions for ' + esc(x.reference) + '">⋮</button></td></tr>';
          }).join("") + "</tbody></table></div>" +
          '<div class="admin-actions">' +
          (reqState.offset > 0 ? '<button class="btn btn--ghost btn--small" id="rq-prev">Newer</button>' : "") +
          (reqState.offset + 30 < d.total ? '<button class="btn btn--ghost btn--small" id="rq-next">Older</button>' : "") +
          "</div></div>";

        function filterQs() {
          return (reqState.kind ? "&kind=" + encodeURIComponent(reqState.kind) : "") +
            (reqState.status ? "&status=" + encodeURIComponent(reqState.status) : "") +
            (reqState.q ? "&q=" + encodeURIComponent(reqState.q) : "");
        }
        function updateBulk() {
          var n = Object.keys(reqState.sel).length;
          document.getElementById("bulk-bar").hidden = !n;
          document.getElementById("bulk-count").textContent = n;
          document.getElementById("rq-export").textContent =
            n ? "Export " + n + " selected ▾" : "Export ▾";
        }
        document.getElementById("rq-kind").addEventListener("change", function () {
          reqState.kind = this.value; reqState.offset = 0; views.requests();
        });
        document.getElementById("rq-status").addEventListener("change", function () {
          reqState.status = this.value; reqState.offset = 0; views.requests();
        });
        document.getElementById("rq-q").addEventListener("change", function () {
          reqState.q = this.value.trim(); reqState.offset = 0; views.requests();
        });
        main.querySelectorAll(".stat-card--click").forEach(function (card) {
          card.addEventListener("click", function () {
            reqState.status = reqState.status === card.getAttribute("data-status") ? "" : card.getAttribute("data-status");
            reqState.offset = 0; views.requests();
          });
        });
        document.getElementById("rq-export").addEventListener("click", function (e) {
          e.stopPropagation();
          showMenu(this, exportChildren(function (fmt) {
            var refs = Object.keys(reqState.sel);
            return "/api/admin/requests/export?format=" + fmt +
              (refs.length ? "&refs=" + encodeURIComponent(refs.join(",")) : filterQs());
          }));
        });
        document.getElementById("bulk-clear").addEventListener("click", function () {
          reqState.sel = {};
          main.querySelectorAll("[data-sel], #sel-all").forEach(function (cb) { cb.checked = false; });
          updateBulk();
        });
        document.getElementById("sel-all").addEventListener("change", function () {
          var on = this.checked;
          main.querySelectorAll("tr[data-ref]").forEach(function (row) {
            var ref = row.getAttribute("data-ref");
            row.querySelector("[data-sel]").checked = on;
            if (on) reqState.sel[ref] = true; else delete reqState.sel[ref];
          });
          updateBulk();
        });
        main.querySelectorAll("tr[data-ref]").forEach(function (row) {
          var ref = row.getAttribute("data-ref");
          row.querySelector("[data-sel]").addEventListener("change", function () {
            if (this.checked) reqState.sel[ref] = true; else delete reqState.sel[ref];
            updateBulk();
          });
          row.querySelector("[data-dots]").addEventListener("click", function (e) {
            e.stopPropagation();
            var entries = [{ label: "View", action: function () { location.hash = "#requests/" + ref; } }];
            if (manage) {
              entries.push({ label: "Set status", children: Object.keys(STATUS_LABELS).map(function (s) {
                return { label: STATUS_LABELS[s], action: function () {
                  requestAction(ref, { status: s }, views.requests);
                } };
              }) });
              entries.push({ label: "Assign…", action: function () {
                var who = prompt("Assign this request to:");
                if (who !== null) requestAction(ref, { assignee: who.trim() }, views.requests);
              } });
            }
            entries.push({ label: "Download", children: exportChildren(function (fmt) {
              return "/api/admin/requests/" + encodeURIComponent(ref) + "/export?format=" + fmt;
            }) });
            if (manage) {
              entries.push("-", { label: "Delete request", danger: true, action: function () {
                if (!confirm("Delete " + ref + " permanently? The submission and any attached file are removed and cannot be recovered.")) return;
                api("/api/admin/requests/" + encodeURIComponent(ref) + "/delete", {}).then(function (r2) {
                  if (!r2.ok) return apiErr(r2);
                  delete reqState.sel[ref];
                  toast("Request deleted.");
                  views.requests();
                });
              } });
            }
            showMenu(this, entries);
          });
        });
        var prev = document.getElementById("rq-prev"), next = document.getElementById("rq-next");
        if (prev) prev.addEventListener("click", function () { reqState.offset -= 30; views.requests(); });
        if (next) next.addEventListener("click", function () { reqState.offset += 30; views.requests(); });
      });
    },

    jasani: function () {
      api("/api/admin/jasani").then(function (r) {
        if (!r.ok) return apiErr(r);
        var d = r.data;
        var b = d.budget || {};
        var pct = b.limit ? Math.min(100, Math.round((b.used / b.limit) * 100)) : 0;
        var resetH = Math.floor((b.resetInSeconds || 0) / 3600);
        var resetM = Math.floor(((b.resetInSeconds || 0) % 3600) / 60);
        function marketCard(key, label) {
          var m = (d.markets || {})[key] || {};
          return '<div class="admin-panel jz-market"><h2>' + label + "</h2>" +
            (m.cached
              ? '<div class="stat-row stat-row--tight">' +
                '<div class="stat-card"><b>' + esc(m.products) + "</b><span>Products cached</span></div>" +
                '<div class="stat-card"><b>' + esc(m.inStock) + "</b><span>In stock</span></div></div>" +
                '<p class="admin-inline-note">Products: ' + esc(when(m.fetchedAt)) +
                (m.productsFresh ? ' <span class="badge-ok">fresh</span>' : ' <span class="badge-bad">due</span>') +
                "<br>Stock: " + esc(when(m.stockAt)) +
                (m.stockFresh ? ' <span class="badge-ok">fresh</span>' : ' <span class="badge-bad">due</span>') + "</p>"
              : '<p class="admin-inline-note">Nothing cached yet for this market.</p>') +
            (can("jasani.refresh")
              ? '<div class="admin-actions">' +
                '<button class="btn btn--ghost btn--small" data-refresh="stock" data-market="' + key + '">Refresh stock (1 call)</button>' +
                '<button class="btn btn--ghost btn--small" data-refresh="products" data-market="' + key + '">Full refresh (2 calls)</button></div>'
              : "") + "</div>";
        }
        main.innerHTML =
          '<h1 class="admin-h1">Jasani console</h1>' +
          '<p class="admin-sub">The supplier allows ' + esc(b.limit) + " primary calls per day (UAE time). The website serves the cached snapshot; refresh only when needed.</p>" +
          (d.tokenConfigured ? "" : '<div class="admin-panel"><p class="badge-bad">No supplier token configured — set JASANI_API_TOKEN in .env.</p></div>') +
          '<div class="admin-panel"><h2>Daily call budget</h2>' +
          '<div class="gauge"><div class="gauge__fill' + (b.remaining === 0 ? " gauge__fill--max" : "") + '" style="width:' + pct + '%"></div></div>' +
          '<p class="admin-inline-note">' + esc(b.used) + " of " + esc(b.limit) + " used · " + esc(b.remaining) +
          " remaining · resets in about " + resetH + "h " + resetM + "m (UAE day " + esc(b.day) + ")</p></div>" +
          '<div class="jz-grid">' + marketCard("ksa", "Saudi Arabia — giftsksa.com") + marketCard("uae", "UAE — jasani.ae") + "</div>" +
          '<div class="admin-panel"><h2>Printing manuals cache</h2><p class="admin-inline-note">' +
          esc(d.manuals.cachedPdfs) + " PDF(s) cached (" + (d.manuals.bytes / (1024 * 1024)).toFixed(1) + " MB) · " +
          esc(d.manuals.validVerdicts) + " valid · " + esc(d.manuals.failedVerdicts) + " marked unavailable</p></div>" +
          '<div class="admin-panel"><h2>Search the cached catalog</h2><div class="req-filters">' +
          '<select id="jz-market"><option value="ksa">Saudi Arabia</option><option value="uae">UAE</option></select>' +
          '<input id="jz-q" placeholder="Name, SKU or id" maxlength="80">' +
          '<button class="btn btn--ghost btn--small" id="jz-search">Search</button></div>' +
          '<div id="jz-results"></div></div>';

        main.querySelectorAll("[data-refresh]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var what = btn.getAttribute("data-refresh"), market = btn.getAttribute("data-market");
            var cost = what === "products" ? 2 : 1;
            if (!confirm("This uses " + cost + " of the " + b.limit + " daily supplier calls (" +
                         b.remaining + " remaining). Continue?")) return;
            btn.disabled = true;
            api("/api/admin/jasani/refresh", { market: market, what: what }).then(function (r2) {
              btn.disabled = false;
              if (!r2.ok) return apiErr(r2);
              toast("Refreshed " + what + " for " + market.toUpperCase() + ".");
              views.jasani();
            });
          });
        });
        function search() {
          var market = document.getElementById("jz-market").value;
          var q = document.getElementById("jz-q").value.trim();
          api("/api/admin/jasani/products?market=" + market + "&q=" + encodeURIComponent(q)).then(function (r2) {
            if (!r2.ok) return apiErr(r2);
            var rows = r2.data.products || [];
            document.getElementById("jz-results").innerHTML = rows.length
              ? '<div class="table-scroll"><table class="admin-table"><thead><tr><th></th><th>SKU</th><th>Name</th><th>Brand</th><th>Colour</th><th>Available</th><th>Incoming</th></tr></thead><tbody>' +
                rows.map(function (p) {
                  return "<tr><td>" + (p.image ? '<img class="jz-thumb" src="' + esc(p.image) + '" alt="" loading="lazy">' : "") + "</td>" +
                    "<td>" + esc(p.code || p.id) + "</td><td>" + esc(p.name) + "</td>" +
                    '<td class="muted">' + esc(p.brand || "—") + '</td><td class="muted">' + esc(p.color || "—") + "</td>" +
                    "<td>" + esc(p.available) + "</td><td class=\"muted\">" + esc(p.incoming) + "</td></tr>";
                }).join("") + "</tbody></table></div>"
              : '<p class="admin-inline-note">No cached products match.</p>';
          });
        }
        document.getElementById("jz-search").addEventListener("click", search);
        document.getElementById("jz-q").addEventListener("keydown", function (e) {
          if (e.key === "Enter") { e.preventDefault(); search(); }
        });
      });
    },

    pages: function (param) {
      if (param) return pageEditor(param);
      api("/api/admin/pages").then(function (r) {
        if (!r.ok) return apiErr(r);
        var d = r.data;
        var lp = d.lastPublish;
        main.innerHTML =
          '<h1 class="admin-h1">Pages &amp; SEO</h1>' +
          '<p class="admin-sub">Edit text and SEO per page, preview privately, then publish the whole site in one click. The original design always stays safe in the code.</p>' +
          '<div class="admin-panel"><h2>Publishing</h2>' +
          '<p class="admin-inline-note" style="margin-bottom:12px;">' +
          (d.published
            ? "The site is serving your published version" + (lp ? " (published " + esc(when(lp.ts)) + " by " + esc(lp.by) + ")" : "") + "."
            : "The site is serving the original design — nothing published yet.") + "</p>" +
          '<div class="admin-actions">' +
          '<button class="btn btn--primary btn--small" id="pub-btn">Publish site</button>' +
          (d.published ? '<button class="btn btn--ghost btn--small" id="unpub-btn">Unpublish (serve original)</button>' : "") +
          "</div>" +
          ((d.history || []).length
            ? '<h2 style="margin-top:22px;">Version history</h2><div class="table-scroll"><table class="admin-table"><thead>' +
              "<tr><th>Version</th><th>Published</th><th>By</th><th>Pages</th><th></th></tr></thead><tbody>" +
              d.history.map(function (h, i) {
                return "<tr><td>#" + h.id + "</td><td class=\"muted\">" + esc(when(h.ts)) + "</td>" +
                  "<td class=\"muted\">" + esc(h.by) + "</td><td class=\"muted\">" + h.pages + "</td>" +
                  "<td>" + (i === 0 ? '<span class="badge-ok">current</span>'
                    : '<button class="btn btn--ghost btn--small" data-rollback="' + h.id + '">Restore</button>') + "</td></tr>";
              }).join("") + "</tbody></table></div>" : "") + "</div>" +
          '<div class="admin-panel"><h2>Header &amp; Footer</h2>' +
          '<p class="admin-inline-note" style="margin-bottom:10px;">Menu labels, header button, footer text and contact details — applied to every page.</p>' +
          '<a class="btn btn--ghost btn--small" href="#pages/_global">Edit (' + esc(d.globalRegions) + " fields)</a></div>" +
          '<div class="admin-panel"><h2>Pages</h2><div class="table-scroll"><table class="admin-table"><thead>' +
          "<tr><th>Page</th><th>Text fields</th><th>State</th><th></th></tr></thead><tbody>" +
          (d.pages || []).map(function (p) {
            return "<tr><td>" + esc(p.label) + ' <span class="muted">(' + esc(p.file) + ")</span></td>" +
              '<td class="muted">' + (p.regions ? p.regions + " + SEO" : "SEO only") + "</td>" +
              "<td>" + (p.dirty ? '<span class="badge-bad">unpublished edits</span>' : '<span class="muted">up to date</span>') + "</td>" +
              '<td class="cell-actions"><a class="btn btn--ghost btn--small" href="#pages/' + esc(p.page) + '">Edit</a> ' +
              '<a class="btn btn--ghost btn--small" href="/admin/preview/' + esc(p.page) + '" target="_blank" rel="noopener">Preview</a></td></tr>';
          }).join("") + "</tbody></table></div></div>";
        document.getElementById("pub-btn").addEventListener("click", function () {
          if (!confirm("Publish all pages to the live site now?")) return;
          api("/api/admin/pages-publish", {}).then(function (r2) {
            r2.ok ? (toast("Published " + r2.data.pages + " pages — live now."), views.pages()) : apiErr(r2);
          });
        });
        var unpub = document.getElementById("unpub-btn");
        if (unpub) unpub.addEventListener("click", function () {
          if (!confirm("Serve the original design again? Your drafts are kept and can be re-published any time.")) return;
          api("/api/admin/pages-unpublish", {}).then(function (r2) {
            r2.ok ? (toast("Original design restored."), views.pages()) : apiErr(r2);
          });
        });
        main.querySelectorAll("[data-rollback]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var id = btn.getAttribute("data-rollback");
            if (!confirm("Restore version #" + id + " and publish it now?")) return;
            api("/api/admin/pages-rollback", { id: parseInt(id, 10) }).then(function (r2) {
              r2.ok ? (toast("Version #" + id + " restored and published."), views.pages()) : apiErr(r2);
            });
          });
        });
      });
    },

    rentals: function () {
      api("/api/admin/rentals").then(function (r) {
        if (!r.ok) return apiErr(r);
        var d = r.data;
        main.innerHTML =
          '<h1 class="admin-h1">Rental inventory</h1>' +
          '<p class="admin-sub">Items shown on the public Rental page. ' +
          (d.source === "custom" ? 'You are editing a custom inventory. <button class="btn btn--ghost btn--small" id="rent-reset">Restore shipped list</button>'
                                 : "Currently showing the shipped list — saving any change creates your editable copy.") + "</p>" +
          '<div class="admin-panel"><h2>Items (' + (d.products || []).length + ')</h2>' +
          '<div class="admin-actions" style="margin-bottom:14px;"><button class="btn btn--primary btn--small" id="rent-new">Add new item</button></div>' +
          '<div class="table-scroll"><table class="admin-table"><thead>' +
          "<tr><th></th><th>Name</th><th>Category</th><th>Stock KSA</th><th>Stock UAE</th><th>Featured</th><th></th></tr></thead><tbody>" +
          (d.products || []).map(function (p) {
            return '<tr data-id="' + esc(p.id) + '"><td>' +
              (p.image ? '<img class="jz-thumb" src="' + esc(p.image) + '" alt="" loading="lazy">' : "") + "</td>" +
              "<td>" + esc(p.name) + ' <span class="muted">' + esc(p.code || "") + "</span></td>" +
              '<td class="muted">' + esc(p.category) + "</td>" +
              "<td>" + esc(p.stockByMarket.ksa) + "</td><td>" + esc(p.stockByMarket.uae) + "</td>" +
              "<td>" + (p.featured ? '<span class="badge-ok">yes</span>' : '<span class="muted">no</span>') + "</td>" +
              '<td class="cell-actions"><button class="btn btn--ghost btn--small" data-edit>Edit</button> ' +
              '<button class="btn btn--ghost btn--small" data-del>Delete</button></td></tr>';
          }).join("") + "</tbody></table></div></div>" +
          '<div class="admin-panel" id="rent-form-panel" hidden><h2 id="rent-form-title">Edit item</h2>' +
          '<form class="admin-form" id="rent-form">' +
          '<div><label for="rf-id">ID (lowercase-with-dashes, fixed once created)</label><input id="rf-id" required maxlength="60" pattern="[a-z0-9][a-z0-9\\-]+"></div>' +
          '<div><label for="rf-code">Code</label><input id="rf-code" maxlength="40"></div>' +
          '<div><label for="rf-name">Name</label><input id="rf-name" required maxlength="160"></div>' +
          '<div><label for="rf-category">Category</label><input id="rf-category" required maxlength="80"></div>' +
          '<div class="full"><label for="rf-images">Images — one path per line (/assets/… or /media/…, first is the card image)</label><textarea id="rf-images" rows="3"></textarea></div>' +
          '<div class="full"><label for="rf-desc">Description</label><textarea id="rf-desc" rows="3" maxlength="2000"></textarea></div>' +
          '<div class="full"><label for="rf-specs">Specifications — one per line</label><textarea id="rf-specs" rows="4"></textarea></div>' +
          '<div><label for="rf-tags">Search tags (comma separated)</label><input id="rf-tags" maxlength="300"></div>' +
          '<div><label for="rf-featured">Featured</label><select id="rf-featured"><option value="no">No</option><option value="yes">Yes — show first</option></select></div>' +
          '<div><label for="rf-ksa">Stock — Saudi Arabia</label><input id="rf-ksa" type="number" min="0" max="100000" value="0"></div>' +
          '<div><label for="rf-uae">Stock — UAE</label><input id="rf-uae" type="number" min="0" max="100000" value="0"></div>' +
          '<div class="full admin-actions"><button class="btn btn--primary btn--small" type="submit">Save item</button>' +
          '<button class="btn btn--ghost btn--small" type="button" id="rent-cancel">Cancel</button>' +
          '<span class="admin-inline-note">Changes appear on the public Rental page immediately.</span></div></form></div>';

        var byId = {};
        (d.products || []).forEach(function (p) { byId[p.id] = p; });
        function openForm(p) {
          document.getElementById("rent-form-panel").hidden = false;
          document.getElementById("rent-form-title").textContent = p ? "Edit — " + p.name : "Add new item";
          document.getElementById("rf-id").value = p ? p.id : "";
          document.getElementById("rf-id").readOnly = !!p;
          document.getElementById("rf-code").value = p ? p.code || "" : "";
          document.getElementById("rf-name").value = p ? p.name : "";
          document.getElementById("rf-category").value = p ? p.category : "";
          document.getElementById("rf-images").value = p ? (p.images || []).join("\n") : "";
          document.getElementById("rf-desc").value = p ? p.description || "" : "";
          document.getElementById("rf-specs").value = p ? (p.specs || []).join("\n") : "";
          document.getElementById("rf-tags").value = p ? (p.tags || []).join(", ") : "";
          document.getElementById("rf-featured").value = p && p.featured ? "yes" : "no";
          document.getElementById("rf-ksa").value = p ? p.stockByMarket.ksa : 0;
          document.getElementById("rf-uae").value = p ? p.stockByMarket.uae : 0;
          document.getElementById("rent-form-panel").scrollIntoView({ behavior: "smooth", block: "start" });
        }
        document.getElementById("rent-new").addEventListener("click", function () { openForm(null); });
        document.getElementById("rent-cancel").addEventListener("click", function () {
          document.getElementById("rent-form-panel").hidden = true;
        });
        main.querySelectorAll("tr[data-id]").forEach(function (row) {
          var id = row.getAttribute("data-id");
          row.querySelector("[data-edit]").addEventListener("click", function () { openForm(byId[id]); });
          row.querySelector("[data-del]").addEventListener("click", function () {
            if (!confirm("Delete this rental item from the public site?")) return;
            api("/api/admin/rentals/delete", { id: id }).then(function (r2) {
              r2.ok ? (toast("Item deleted."), views.rentals()) : apiErr(r2);
            });
          });
        });
        var reset = document.getElementById("rent-reset");
        if (reset) reset.addEventListener("click", function () {
          if (!confirm("Discard your custom inventory and restore the shipped list?")) return;
          api("/api/admin/rentals/reset", {}).then(function (r2) {
            r2.ok ? (toast("Shipped list restored."), views.rentals()) : apiErr(r2);
          });
        });
        document.getElementById("rent-form").addEventListener("submit", function (e) {
          e.preventDefault();
          var images = document.getElementById("rf-images").value.split("\n")
            .map(function (x) { return x.trim(); }).filter(Boolean);
          api("/api/admin/rentals/save", { product: {
            id: document.getElementById("rf-id").value.trim(),
            code: document.getElementById("rf-code").value.trim(),
            name: document.getElementById("rf-name").value.trim(),
            category: document.getElementById("rf-category").value.trim(),
            image: images[0] || "",
            images: images,
            description: document.getElementById("rf-desc").value.trim(),
            specs: document.getElementById("rf-specs").value.split("\n")
              .map(function (x) { return x.trim(); }).filter(Boolean),
            tags: document.getElementById("rf-tags").value.split(",")
              .map(function (x) { return x.trim(); }).filter(Boolean),
            featured: document.getElementById("rf-featured").value === "yes",
            stockByMarket: { ksa: document.getElementById("rf-ksa").value,
                             uae: document.getElementById("rf-uae").value }
          } }).then(function (r2) {
            r2.ok ? (toast("Item saved — live on the site."), views.rentals()) : apiErr(r2);
          });
        });
      });
    },

    media: function () {
      api("/api/admin/media").then(function (r) {
        if (!r.ok) return apiErr(r);
        var d = r.data;
        var u = d.usage || {};
        main.innerHTML =
          '<h1 class="admin-h1">Media</h1>' +
          '<p class="admin-sub">Library uploads convert to WebP with metadata stripped. Site assets can be replaced safely — the original always stays and one click restores it.</p>' +
          '<div class="stat-row">' +
          '<div class="stat-card"><b>' + esc(fmtBytes(u.libraryBytes)) + "</b><span>Library storage</span></div>" +
          '<div class="stat-card"><b>' + esc(fmtBytes(u.overridesBytes)) + "</b><span>Site replacements</span></div>" +
          '<div class="stat-card"><b>' + esc(fmtBytes(u.glbBytes)) + "</b><span>3D model versions</span></div></div>" +
          '<div class="admin-panel"><h2>Upload to library</h2><form class="admin-form" id="media-upload">' +
          '<div><label for="mu-file">Image (PNG, JPEG or WebP · max 15 MB)</label><input id="mu-file" type="file" accept="image/png,image/jpeg,image/webp" required></div>' +
          '<div><label for="mu-alt">Alt text (what the image shows)</label><input id="mu-alt" maxlength="300"></div>' +
          '<div class="full admin-actions"><button class="btn btn--primary btn--small" type="submit">Upload</button></div></form></div>' +
          '<div class="admin-panel"><h2>Library (' + (d.library || []).length + ')</h2>' +
          ((d.library || []).length ? '<div class="media-grid">' + d.library.map(function (m) {
            return '<figure class="media-card" data-id="' + m.id + '">' +
              '<img src="/media/' + esc(m.file) + '" alt="" loading="lazy">' +
              '<figcaption><strong>' + esc(m.name) + "</strong>" +
              '<span class="admin-inline-note">' + m.width + "×" + m.height + " · " + esc(fmtBytes(m.bytes)) + "</span>" +
              '<input data-alt maxlength="300" placeholder="Alt text" value="' + esc(m.alt) + '">' +
              '<span class="media-actions"><button class="btn btn--ghost btn--small" data-save-alt>Save alt</button>' +
              '<button class="btn btn--ghost btn--small" data-copy>Copy URL</button>' +
              '<button class="btn btn--ghost btn--small" data-del>Delete</button></span></figcaption></figure>';
          }).join("") + "</div>" : '<p class="admin-inline-note">Nothing uploaded yet.</p>') + "</div>" +
          '<div class="admin-panel"><h2>Site assets</h2>' +
          '<p class="admin-inline-note" style="margin-bottom:12px;">Replacing keeps the same address, so every page using the file updates instantly.</p>' +
          '<div class="table-scroll"><table class="admin-table"><thead><tr><th></th><th>File</th><th>Size</th><th>Used on</th><th>State</th><th></th></tr></thead><tbody>' +
          (d.siteAssets || []).map(function (a) {
            var img = a.ext === "glb" ? "" : '<img class="jz-thumb" src="/' + esc(a.path) + '?t=' + (a.overridden ? a.overrideBytes : 0) + '" alt="" loading="lazy">';
            return '<tr data-path="' + esc(a.path) + '"><td>' + img + "</td>" +
              "<td>" + esc(a.path.replace("assets/", "")) + "</td>" +
              '<td class="muted">' + esc(fmtBytes(a.overridden ? a.overrideBytes : a.bytes)) + "</td>" +
              '<td class="muted">' + esc((a.usedOn || []).slice(0, 3).join(", ")) + (a.usedOn && a.usedOn.length > 3 ? "…" : "") + "</td>" +
              "<td>" + (a.overridden ? '<span class="badge-ok">replaced</span>' : '<span class="muted">original</span>') + "</td>" +
              '<td class="cell-actions">' + (a.ext === "glb"
                ? '<a class="btn btn--ghost btn--small" href="#brand">3D manager</a>'
                : '<button class="btn btn--ghost btn--small" data-replace>Replace</button>' +
                  (a.overridden ? ' <button class="btn btn--ghost btn--small" data-reset>Restore original</button>' : "")) +
              "</td></tr>";
          }).join("") + "</tbody></table></div></div>" +
          '<input type="file" id="asset-file" accept="image/png,image/jpeg,image/webp,image/svg+xml" hidden>';

        document.getElementById("media-upload").addEventListener("submit", function (e) {
          e.preventDefault();
          var f = document.getElementById("mu-file").files[0];
          if (!f) return;
          var fd = new FormData();
          fd.append("file", f);
          fd.append("alt", document.getElementById("mu-alt").value.trim());
          apiUpload("/api/admin/media/upload", fd).then(function (r2) {
            r2.ok ? (toast("Uploaded."), views.media()) : apiErr(r2);
          });
        });
        main.querySelectorAll(".media-card").forEach(function (card) {
          var id = card.getAttribute("data-id");
          card.querySelector("[data-save-alt]").addEventListener("click", function () {
            api("/api/admin/media/" + id + "/alt", { alt: card.querySelector("[data-alt]").value.trim() })
              .then(function (r2) { r2.ok ? toast("Alt text saved.") : apiErr(r2); });
          });
          card.querySelector("[data-copy]").addEventListener("click", function () {
            var url = location.origin + "/media/" + card.querySelector("img").getAttribute("src").split("/").pop();
            (navigator.clipboard ? navigator.clipboard.writeText(url) : Promise.reject())
              .then(function () { toast("URL copied."); }, function () { prompt("Media URL:", url); });
          });
          card.querySelector("[data-del]").addEventListener("click", function () {
            if (!confirm("Delete this image from the library?")) return;
            api("/api/admin/media/" + id + "/delete", {}).then(function (r2) {
              r2.ok ? views.media() : apiErr(r2);
            });
          });
        });
        var assetFile = document.getElementById("asset-file");
        var pendingPath = null;
        main.querySelectorAll("[data-replace]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            pendingPath = btn.closest("tr").getAttribute("data-path");
            assetFile.value = "";
            assetFile.click();
          });
        });
        assetFile.addEventListener("change", function () {
          var f = assetFile.files[0];
          if (!f || !pendingPath) return;
          var fd = new FormData();
          fd.append("path", pendingPath);
          fd.append("file", f);
          apiUpload("/api/admin/media/replace-asset", fd).then(function (r2) {
            r2.ok ? (toast("Asset replaced — the site now serves the new file."), views.media()) : apiErr(r2);
          });
        });
        main.querySelectorAll("[data-reset]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var p = btn.closest("tr").getAttribute("data-path");
            if (!confirm("Restore the original file for " + p + "?")) return;
            api("/api/admin/media/reset-asset", { path: p }).then(function (r2) {
              r2.ok ? (toast("Original restored."), views.media()) : apiErr(r2);
            });
          });
        });
      });
    },

    brand: function () {
      api("/api/admin/brand").then(function (r) {
        if (!r.ok) return apiErr(r);
        var d = r.data;
        var t = d.tokens || {};
        var hero = d.hero || {};
        var glb = d.glb || {};
        var warn = (d.warnings || []).map(function (w) {
          return '<p class="brand-warn">⚠ ' + esc(w) + "</p>";
        }).join("");
        main.innerHTML =
          '<h1 class="admin-h1">Website &amp; Brand</h1>' +
          '<p class="admin-sub">Colours, motion, identity assets and the 3D hero. Changes go live immediately and can always be reset.</p>' +
          '<div class="admin-panel"><h2>Brand colours</h2><div id="brand-warnings">' + warn + "</div>" +
          '<form class="admin-form" id="tokens-form">' +
          Object.keys(d.labels || {}).map(function (k) {
            return '<div><label for="tk-' + k + '">' + esc(d.labels[k]) + "</label>" +
              '<span class="color-row"><input type="color" id="tk-' + k + '" value="' + esc(t[k] || d.defaults[k]) + '">' +
              '<code>' + esc(t[k] || d.defaults[k]) + "</code></span></div>";
          }).join("") +
          '<div><label for="tk-radius">Corner radius scale (0–2 · 1 = default)</label>' +
          '<input type="number" id="tk-radius" min="0" max="2" step="0.1" value="' + esc(t.radius == null ? 1 : t.radius) + '"></div>' +
          '<div><label for="tk-motion">Animations</label><select id="tk-motion">' +
          '<option value="on"' + (t.motion === false ? "" : " selected") + '>On (default)</option>' +
          '<option value="off"' + (t.motion === false ? " selected" : "") + '>Off — calm site</option></select></div>' +
          '<div class="full admin-actions"><button class="btn btn--primary btn--small" type="submit">Save brand</button>' +
          '<button class="btn btn--ghost btn--small" type="button" id="tokens-reset">Reset to defaults</button>' +
          '<span class="admin-inline-note">Contrast is checked on save — warnings never block you.</span></div></form></div>' +
          '<div class="admin-panel"><h2>Identity</h2><div class="table-scroll"><table class="admin-table"><thead>' +
          "<tr><th>Asset</th><th>Preview</th><th>State</th><th></th></tr></thead><tbody>" +
          (d.identity || []).map(function (s) {
            var prev = s.kind === "pdflogo" ? '<span class="muted">used inside generated PDFs</span>'
              : '<img class="ident-prev' + (s.slot === "logoDark" ? " ident-prev--dark" : "") + '" src="/' + esc(s.path) + '?t=' + Date.now() + '" alt="">';
            return '<tr data-slot="' + esc(s.slot) + '"><td>' + esc(s.label) + "</td><td>" + prev + "</td>" +
              "<td>" + (s.overridden ? '<span class="badge-ok">custom</span>' : '<span class="muted">default</span>') + "</td>" +
              '<td class="cell-actions"><button class="btn btn--ghost btn--small" data-up>Upload new</button>' +
              (s.overridden ? ' <button class="btn btn--ghost btn--small" data-rst>Reset</button>' : "") + "</td></tr>";
          }).join("") + "</tbody></table></div>" +
          '<input type="file" id="ident-file" hidden></div>' +
          '<div class="admin-panel"><h2>3D hero model</h2>' +
          '<p class="admin-inline-note" style="margin-bottom:12px;">Current model: ' +
          (glb.overrideActive ? '<span class="badge-ok">custom upload</span>' : "original (" + esc(fmtBytes(glb.originalBytes)) + ")") +
          ' · <a href="/" target="_blank" rel="noopener">preview homepage</a></p>' +
          '<form class="admin-form" id="glb-upload-form">' +
          '<div><label for="glb-file">Upload .glb (glTF 2.0 · max 40 MB)</label><input type="file" id="glb-file" accept=".glb" required></div>' +
          '<div class="full admin-actions"><button class="btn btn--primary btn--small" type="submit">Upload version</button>' +
          (glb.overrideActive ? '<button class="btn btn--ghost btn--small" type="button" id="glb-reset">Switch back to original</button>' : "") +
          "</div></form>" +
          ((glb.versions || []).length
            ? '<div class="table-scroll"><table class="admin-table"><thead><tr><th>Version</th><th>Size</th><th>Uploaded</th><th>State</th><th></th></tr></thead><tbody>' +
              glb.versions.map(function (v) {
                return '<tr data-file="' + esc(v.file) + '"><td>' + esc(v.file) + "</td><td class=\"muted\">" + esc(fmtBytes(v.bytes)) + "</td>" +
                  '<td class="muted">' + esc(when(v.uploadedAt)) + "</td>" +
                  "<td>" + (v.active ? '<span class="badge-ok">live</span>' : "") + "</td>" +
                  '<td class="cell-actions">' + (v.active ? "" :
                    '<button class="btn btn--ghost btn--small" data-glb-act>Make live</button> ' +
                    '<button class="btn btn--ghost btn--small" data-glb-del>Delete</button>') + "</td></tr>";
              }).join("") + "</tbody></table></div>" : "") + "</div>" +
          '<div class="admin-panel"><h2>Hero camera</h2><form class="admin-form" id="hero-form">' +
          '<div><label for="hc-camz">Distance (camz ' + d.heroRanges.camz[0] + "–" + d.heroRanges.camz[1] + ")</label>" +
          '<input type="number" id="hc-camz" step="0.1" min="' + d.heroRanges.camz[0] + '" max="' + d.heroRanges.camz[1] + '" value="' + esc(hero.camz != null ? hero.camz : 5.2) + '"></div>' +
          '<div><label for="hc-camy">Height (camy ' + d.heroRanges.camy[0] + "–" + d.heroRanges.camy[1] + ")</label>" +
          '<input type="number" id="hc-camy" step="0.05" min="' + d.heroRanges.camy[0] + '" max="' + d.heroRanges.camy[1] + '" value="' + esc(hero.camy != null ? hero.camy : 0.9) + '"></div>' +
          '<div><label for="hc-fov">Field of view (' + d.heroRanges.fov[0] + "–" + d.heroRanges.fov[1] + ")</label>" +
          '<input type="number" id="hc-fov" step="1" min="' + d.heroRanges.fov[0] + '" max="' + d.heroRanges.fov[1] + '" value="' + esc(hero.fov != null ? hero.fov : 38) + '"></div>' +
          '<div class="full admin-actions"><button class="btn btn--primary btn--small" type="submit">Save camera</button>' +
          '<span class="admin-inline-note">Reload the homepage after saving to see the new framing.</span></div></form></div>';

        document.getElementById("tokens-form").addEventListener("submit", function (e) {
          e.preventDefault();
          var values = { radius: document.getElementById("tk-radius").value,
                         motion: document.getElementById("tk-motion").value === "on" };
          Object.keys(d.labels).forEach(function (k) {
            values[k] = document.getElementById("tk-" + k).value;
          });
          api("/api/admin/brand/tokens", { values: values }).then(function (r2) {
            if (!r2.ok) return apiErr(r2);
            toast("Brand saved — live on the site now.");
            document.getElementById("brand-warnings").innerHTML =
              (r2.data.warnings || []).map(function (w) { return '<p class="brand-warn">⚠ ' + esc(w) + "</p>"; }).join("");
          });
        });
        document.getElementById("tokens-reset").addEventListener("click", function () {
          if (!confirm("Reset colours, radius and motion to the original design?")) return;
          api("/api/admin/brand/tokens", { values: { motion: true } }).then(function (r2) {
            r2.ok ? (toast("Brand reset."), views.brand()) : apiErr(r2);
          });
        });
        var identFile = document.getElementById("ident-file");
        var identSlot = null, identAccept = {
          logoLight: "image/svg+xml", logoDark: "image/svg+xml",
          favicon: "image/png,image/jpeg,image/webp", pdfLogo: "image/png,image/jpeg,image/webp"
        };
        main.querySelectorAll("[data-up]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            identSlot = btn.closest("tr").getAttribute("data-slot");
            identFile.setAttribute("accept", identAccept[identSlot] || "");
            identFile.value = "";
            identFile.click();
          });
        });
        identFile.addEventListener("change", function () {
          var f = identFile.files[0];
          if (!f || !identSlot) return;
          var fd = new FormData();
          fd.append("slot", identSlot);
          fd.append("file", f);
          apiUpload("/api/admin/brand/identity", fd).then(function (r2) {
            r2.ok ? (toast("Updated."), views.brand()) : apiErr(r2);
          });
        });
        main.querySelectorAll("[data-rst]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var slot = btn.closest("tr").getAttribute("data-slot");
            if (!confirm("Reset this asset to the original?")) return;
            api("/api/admin/brand/identity/reset", { slot: slot }).then(function (r2) {
              r2.ok ? (toast("Reset."), views.brand()) : apiErr(r2);
            });
          });
        });
        document.getElementById("glb-upload-form").addEventListener("submit", function (e) {
          e.preventDefault();
          var f = document.getElementById("glb-file").files[0];
          if (!f) return;
          var fd = new FormData();
          fd.append("file", f);
          toast("Uploading model…");
          apiUpload("/api/admin/glb/upload", fd).then(function (r2) {
            r2.ok ? (toast("Model uploaded — press “Make live” to publish it."), views.brand()) : apiErr(r2);
          });
        });
        var glbReset = document.getElementById("glb-reset");
        if (glbReset) glbReset.addEventListener("click", function () {
          if (!confirm("Switch the homepage back to the original 3D model?")) return;
          api("/api/admin/glb/reset", {}).then(function (r2) {
            r2.ok ? (toast("Original model restored."), views.brand()) : apiErr(r2);
          });
        });
        main.querySelectorAll("[data-glb-act]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var f = btn.closest("tr").getAttribute("data-file");
            if (!confirm("Publish this model to the live homepage?")) return;
            api("/api/admin/glb/activate", { file: f }).then(function (r2) {
              r2.ok ? (toast("Model is live."), views.brand()) : apiErr(r2);
            });
          });
        });
        main.querySelectorAll("[data-glb-del]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var f = btn.closest("tr").getAttribute("data-file");
            if (!confirm("Delete this uploaded version?")) return;
            api("/api/admin/glb/delete", { file: f }).then(function (r2) {
              r2.ok ? views.brand() : apiErr(r2);
            });
          });
        });
        document.getElementById("hero-form").addEventListener("submit", function (e) {
          e.preventDefault();
          api("/api/admin/hero", { values: {
            camz: document.getElementById("hc-camz").value,
            camy: document.getElementById("hc-camy").value,
            fov: document.getElementById("hc-fov").value
          } }).then(function (r2) {
            r2.ok ? toast("Camera saved — reload the homepage to see it.") : apiErr(r2);
          });
        });
      });
    },

    users: function () {
      api("/api/admin/users").then(function (r) {
        if (!r.ok) return apiErr(r);
        var roleOpts = r.data.roles.map(function (x) { return '<option value="' + esc(x) + '">' + esc(x) + "</option>"; }).join("");
        main.innerHTML =
          '<h1 class="admin-h1">Users &amp; roles</h1>' +
          '<p class="admin-sub">Every account requires two-factor authentication on first sign-in.</p>' +
          '<div class="admin-panel"><h2>Team</h2><div class="table-scroll"><table class="admin-table"><thead>' +
          "<tr><th>Name</th><th>Email</th><th>Role</th><th>2FA</th><th>Status</th><th>Last sign-in</th><th></th></tr></thead>" +
          "<tbody>" + r.data.users.map(function (u) {
            return "<tr data-id=\"" + u.id + "\"><td>" + esc(u.name) + "</td><td>" + esc(u.email) + "</td>" +
              "<td><select data-role>" + r.data.roles.map(function (x) {
                return '<option value="' + esc(x) + '"' + (x === u.role ? " selected" : "") + ">" + esc(x) + "</option>";
              }).join("") + "</select></td>" +
              "<td>" + (u.totp_enabled ? '<span class="badge-ok">on</span>' : '<span class="muted">pending</span>') + "</td>" +
              "<td>" + (u.active ? '<span class="badge-ok">active</span>' : '<span class="badge-bad">disabled</span>') + "</td>" +
              "<td class=\"muted\">" + esc(when(u.last_login_at)) + "</td>" +
              "<td><button class=\"btn btn--ghost btn--small\" data-save>Save</button> " +
              "<button class=\"btn btn--ghost btn--small\" data-toggle>" + (u.active ? "Disable" : "Enable") + "</button> " +
              "<button class=\"btn btn--ghost btn--small\" data-reset2fa>Reset 2FA</button></td></tr>";
          }).join("") + "</tbody></table></div></div>" +
          '<div class="admin-panel"><h2>Invite a new user</h2><form class="admin-form" id="user-create">' +
          '<div><label for="nu-name">Name</label><input id="nu-name" required minlength="2" maxlength="120"></div>' +
          '<div><label for="nu-email">Email</label><input id="nu-email" type="email" required maxlength="200"></div>' +
          '<div><label for="nu-pass">Temporary password (12+)</label><input id="nu-pass" type="password" required minlength="12" maxlength="200"></div>' +
          '<div><label for="nu-role">Role</label><select id="nu-role">' + roleOpts + "</select></div>" +
          '<div class="full admin-actions"><button class="btn btn--primary btn--small" type="submit">Create account</button>' +
          '<span class="admin-inline-note">They set up 2FA on first sign-in; ask them to change the password right away.</span></div>' +
          "</form></div>";

        main.querySelectorAll("tr[data-id]").forEach(function (row) {
          var id = row.getAttribute("data-id");
          row.querySelector("[data-save]").addEventListener("click", function () {
            api("/api/admin/users/" + id, { role: row.querySelector("[data-role]").value })
              .then(function (r2) { r2.ok ? toast("Saved.") : apiErr(r2); });
          });
          row.querySelector("[data-toggle]").addEventListener("click", function () {
            var enable = this.textContent === "Enable";
            api("/api/admin/users/" + id, { active: enable })
              .then(function (r2) { r2.ok ? views.users() : apiErr(r2); });
          });
          row.querySelector("[data-reset2fa]").addEventListener("click", function () {
            if (!confirm("Reset two-factor for this user? They will re-enrol on next sign-in.")) return;
            api("/api/admin/users/" + id, { resetTotp: true })
              .then(function (r2) { r2.ok ? views.users() : apiErr(r2); });
          });
        });
        document.getElementById("user-create").addEventListener("submit", function (e) {
          e.preventDefault();
          api("/api/admin/users", {
            name: document.getElementById("nu-name").value.trim(),
            email: document.getElementById("nu-email").value.trim(),
            password: document.getElementById("nu-pass").value,
            role: document.getElementById("nu-role").value
          }).then(function (r2) { r2.ok ? views.users() : apiErr(r2); });
        });
      });
    },

    audit: function () {
      api("/api/admin/audit?limit=150").then(function (r) {
        if (!r.ok) return apiErr(r);
        var chain = r.data.chain || {};
        main.innerHTML =
          '<h1 class="admin-h1">Activity log</h1>' +
          '<p class="admin-sub">Append-only and hash-chained — ' +
          (chain.ok ? '<span class="badge-ok">chain intact (' + esc(chain.checked) + " entries verified)</span>"
                    : '<span class="badge-bad">chain broken at entry ' + esc(chain.brokenAt) + "!</span>") + "</p>" +
          '<div class="admin-panel"><div class="table-scroll"><table class="admin-table"><thead>' +
          "<tr><th>When</th><th>Who</th><th>Action</th><th>Module</th><th>Detail</th></tr></thead><tbody>" +
          (r.data.entries || []).map(function (a) {
            return "<tr><td class=\"muted\">" + esc(when(a.ts)) + "</td><td>" + esc(a.user_email) +
              "</td><td>" + esc(a.action) + "</td><td class=\"muted\">" + esc(a.module) +
              "</td><td class=\"muted\">" + esc(a.detail) + "</td></tr>";
          }).join("") + "</tbody></table></div></div>";
      });
    },

    settings: function () {
      api("/api/admin/settings").then(function (r) {
        if (!r.ok) return apiErr(r);
        var s = r.data;
        var langs = s["site.languages"] || ["en"];
        main.innerHTML =
          '<h1 class="admin-h1">Settings</h1>' +
          '<p class="admin-sub">Staff notifications and language publishing. More settings arrive with later phases.</p>' +
          '<div class="admin-panel"><h2>Staff notifications</h2><form class="admin-form" id="settings-form">' +
          '<div class="full"><label for="s-emails">Notification emails (one per line)</label>' +
          '<textarea id="s-emails" rows="3">' + esc((s["notify.emails"] || []).join("\n")) + "</textarea></div>" +
          '<div><label for="s-wa">WhatsApp number (with country code)</label>' +
          '<input id="s-wa" maxlength="32" value="' + esc(s["notify.whatsapp"] || "") + '"></div>' +
          '<div><label for="s-lang">Published languages</label><select id="s-lang">' +
          '<option value="en"' + (langs.indexOf("ar") === -1 ? " selected" : "") + ">English only</option>" +
          '<option value="en,ar"' + (langs.indexOf("ar") !== -1 ? " selected" : "") + ">English + Arabic</option>" +
          "</select></div>" +
          '<div class="full admin-actions"><button class="btn btn--primary btn--small" type="submit">Save settings</button>' +
          '<span class="admin-inline-note">Arabic content entry opens in the Pages phase; this switch controls what publishes.</span></div>' +
          "</form></div>";
        document.getElementById("settings-form").addEventListener("submit", function (e) {
          e.preventDefault();
          var emails = document.getElementById("s-emails").value.split("\n")
            .map(function (x) { return x.trim(); }).filter(Boolean).slice(0, 20);
          api("/api/admin/settings", { values: {
            "notify.emails": emails,
            "notify.whatsapp": document.getElementById("s-wa").value.trim(),
            "site.languages": document.getElementById("s-lang").value.split(","),
            "site.defaultLanguage": "en"
          } }).then(function (r2) { r2.ok ? toast("Settings saved.") : apiErr(r2); });
        });
      });
    },

    security: function () {
      api("/api/admin/sessions").then(function (r) {
        if (!r.ok) return apiErr(r);
        main.innerHTML =
          '<h1 class="admin-h1">My security</h1>' +
          '<p class="admin-sub">Signed in as ' + esc(me.email) + " · role " + esc(me.role) + "</p>" +
          '<div class="admin-panel"><h2>Active sessions</h2><div class="table-scroll"><table class="admin-table"><thead>' +
          "<tr><th></th><th>Signed in</th><th>Expires</th><th>Browser</th></tr></thead><tbody>" +
          (r.data.sessions || []).map(function (s) {
            return "<tr><td>" + (s.current ? '<span class="badge-ok">this device</span>' : "") +
              "</td><td class=\"muted\">" + esc(when(s.createdAt)) + "</td><td class=\"muted\">" + esc(when(s.expiresAt)) +
              "</td><td class=\"muted\">" + esc(s.userAgent) + "</td></tr>";
          }).join("") + "</tbody></table></div>" +
          '<div class="admin-actions"><button class="btn btn--ghost btn--small" id="revoke-others">Sign out other devices</button></div></div>';
        document.getElementById("revoke-others").addEventListener("click", function () {
          api("/api/admin/sessions/revoke-others", {}).then(function (r2) {
            r2.ok ? (toast("Signed out " + r2.data.revoked + " other session(s)."), views.security()) : apiErr(r2);
          });
        });
      });
    }
  };

  /* ---------- routing ---------- */
  function route() {
    var hash = (location.hash || "#dashboard").slice(1);
    var name = hash.split("/")[0];
    var param = hash.indexOf("/") !== -1 ? hash.slice(name.length + 1) : "";
    if (!views[name]) { name = "dashboard"; param = ""; }
    var link = document.querySelector('.admin-nav a[data-view="' + name + '"]');
    if (link && link.hidden) { name = "dashboard"; param = ""; }
    document.querySelectorAll(".admin-nav a").forEach(function (a) {
      a.classList.toggle("is-active", a.getAttribute("data-view") === name);
    });
    main.innerHTML = '<div class="admin-loading">Loading…</div>';
    views[name](param);
  }
  window.addEventListener("hashchange", route);

  document.getElementById("logout-btn").addEventListener("click", function () {
    api("/api/admin/logout", {}).then(function () { location.replace("/admin"); });
  });

  /* theme toggle (mirrors the public site behaviour) */
  document.querySelector(".theme-toggle").addEventListener("click", function () {
    var next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("em-theme", next); } catch (e) { /* private mode */ }
  });

  /* ---------- boot ---------- */
  api("/api/admin/me").then(function (r) {
    if (!r.ok) { location.replace("/admin"); return; }
    me = r.data;
    document.getElementById("me-name").textContent = me.name;
    document.getElementById("me-role").textContent = me.role;
    document.querySelectorAll(".admin-nav a[data-perm]").forEach(function (a) {
      if (!can(a.getAttribute("data-perm"))) a.hidden = true;
    });
    route();
  });
})();
