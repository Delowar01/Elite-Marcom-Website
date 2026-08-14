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
  /* Shared Media Library picker. The visual editor has its own inline copy
     bound to its overlay; this one builds its overlay on demand so any screen
     can offer "choose an existing image" without duplicating the markup. */
  function mediaPicker(onPick) {
    var overlay = document.getElementById("shared-picker");
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.className = "picker-overlay";
      overlay.id = "shared-picker";
      overlay.innerHTML = '<div class="picker-box"><div class="picker-head">' +
        "<h2>Choose an image</h2>" +
        '<button class="btn btn--ghost btn--small" type="button" data-close>Close</button></div>' +
        '<div class="picker-grid"></div></div>';
      document.body.appendChild(overlay);
      overlay.addEventListener("click", function (e) {
        if (e.target === overlay || e.target.hasAttribute("data-close")) overlay.hidden = true;
      });
    }
    var grid = overlay.querySelector(".picker-grid");
    grid.innerHTML = '<p class="admin-inline-note">Loading…</p>';
    overlay.hidden = false;
    api("/api/admin/media").then(function (r) {
      if (!r.ok) { overlay.hidden = true; return apiErr(r); }
      var lib = (r.data.library || []).map(function (m) {
        return { url: "/media/" + m.file, label: m.name || m.file };
      });
      var assets = (r.data.siteAssets || []).filter(function (a) {
        return a.ext !== "glb" && a.ext !== "svg";
      }).map(function (a) { return { url: "/" + a.path, label: a.path.replace("assets/", "") }; });
      var items = lib.concat(assets);
      grid.innerHTML = items.length
        ? items.map(function (it) {
            return '<button type="button" class="picker-item" data-url="' + esc(it.url) + '">' +
              '<img src="' + esc(it.url) + '" alt="" loading="lazy"><span>' + esc(it.label) + "</span></button>";
          }).join("")
        : '<p class="admin-inline-note">Nothing in the library yet — upload an image above or on the Media screen.</p>';
      grid.querySelectorAll(".picker-item").forEach(function (btn) {
        btn.addEventListener("click", function () {
          overlay.hidden = true;
          onPick(btn.getAttribute("data-url"));
        });
      });
    });
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

  /* ---------- visual editor state + iframe messages ---------- */
  var edState = {
    page: "index", lang: "en", vw: "desktop", outlines: true,
    changedText: {}, fields: {},
    pageDoc: { elements: {}, sections: {} },
    globalDoc: { elements: {}, sections: {} },
    docTouched: { page: false, global: false },
    touchedAttrPaths: {}, touchedAnimPaths: {},
    sections: [], sel: null,
    undo: [], redo: [],
    onSelect: null, onReady: null, postFrame: null
  };
  window.addEventListener("message", function (ev) {
    if (ev.origin !== location.origin || !ev.data || typeof ev.data !== "object") return;
    if (!document.getElementById("ed-frame")) return; // editor not on screen
    if (ev.data.type === "em-select" && edState.onSelect) {
      edState.onSelect(ev.data);
    } else if (ev.data.type === "em-ready" && edState.onReady) {
      edState.onReady(ev.data);
    }
  });

  /* client-side mirror of the server's limited rich-text policy */
  function richHtml(text) {
    var d = document.createElement("div");
    d.textContent = String(text == null ? "" : text);
    var out = d.innerHTML
      .replace(/&lt;(\/?)(strong|em|b|i|u|ul|ol|li)&gt;/g, "<$1$2>")
      .replace(/&lt;br&gt;/g, "<br>")
      .replace(/&lt;a href="([^"<>\s]+)"&gt;/g, function (m, href) {
        return /^(https?:\/\/|mailto:|tel:|\/|#)/.test(href) ? '<a href="' + href + '">' : m;
      })
      .replace(/&lt;\/a&gt;/g, "</a>");
    return out.replace(/\n/g, "<br>");
  }

  /* ---------- page editor ---------- */
  var pageLang = "en";
  var edInsightRange = { days: 30, start: '', end: '' };
  var emailForm = "";

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
        var tot = d.requestTotals || {};
        var sup = d.supplier || {};
        var mk = sup.markets || {};
        var mail = d.mail || {};
        var series = d.requestSeries || [];
        var MARKET_LIST = [["ksa", "Saudi Arabia", "Riyadh (UTC+3)"],
                           ["uae", "United Arab Emirates", "Dubai (UTC+4)"]];
        var LABELS = { giveaway_enquiry: "Gift requests", giveaway_notification: "Stock alerts",
                       rental_enquiry: "Rental requests", rental_notification: "Availability alerts",
                       contact: "Contact messages", career: "Applications" };

        function delta(now, prev) {
          if (!prev && !now) return '<span class="stat-delta stat-delta--flat">no change</span>';
          if (!prev) return '<span class="stat-delta stat-delta--up">new</span>';
          var pc = Math.round(((now - prev) / prev) * 100);
          var cls = pc > 0 ? "up" : (pc < 0 ? "down" : "flat");
          return '<span class="stat-delta stat-delta--' + cls + '">' +
                 (pc > 0 ? "▲ +" : pc < 0 ? "▼ " : "= ") + esc(pc) + "% vs previous 30 days</span>";
        }
        /* 14-day trend, drawn inline — no chart library, no external request */
        function sparkline(vals) {
          if (!vals.length) return "";
          var max = Math.max.apply(null, vals.concat([1]));
          var w = 100, h = 30;
          var pts = vals.map(function (v, i) {
            return [(i / Math.max(1, vals.length - 1)) * w, h - (v / max) * (h - 3) - 1.5];
          });
          var line = pts.map(function (p, i) { return (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1); }).join(" ");
          return '<svg class="stat-spark" viewBox="0 0 ' + w + " " + h + '" preserveAspectRatio="none" aria-hidden="true">' +
            '<path d="' + line + " L" + w + " " + h + " L0 " + h + ' Z" fill="var(--orange)" opacity="0.13"/>' +
            '<path d="' + line + '" fill="none" stroke="var(--orange-2)" stroke-width="1.6" ' +
            'stroke-linejoin="round" stroke-linecap="round" vector-effect="non-scaling-stroke"/></svg>';
        }
        function areaChart(rows) {
          if (!rows.length) return '<p class="admin-inline-note">No submissions in the last 14 days.</p>';
          var w = 560, h = 150, pad = 22;
          var max = Math.max.apply(null, rows.map(function (x) { return x.enquiries + x.notifications; }).concat([1]));
          var step = (w - pad * 2) / Math.max(1, rows.length - 1);
          function path(key, stack) {
            return rows.map(function (x, i) {
              var v = stack ? x.enquiries + x.notifications : x[key];
              var y = h - pad - (v / max) * (h - pad * 2);
              return (i ? "L" : "M") + (pad + i * step).toFixed(1) + " " + y.toFixed(1);
            }).join(" ");
          }
          var base = " L" + (pad + (rows.length - 1) * step).toFixed(1) + " " + (h - pad) + " L" + pad + " " + (h - pad) + " Z";
          return '<svg class="chart" viewBox="0 0 ' + w + " " + h + '" role="img" aria-label="Submissions over the last 14 days">' +
            '<line x1="' + pad + '" y1="' + (h - pad) + '" x2="' + (w - pad) + '" y2="' + (h - pad) +
            '" stroke="var(--adm-line-strong)" stroke-width="1"/>' +
            '<path d="' + path("x", true) + base + '" fill="var(--violet)" opacity="0.16"/>' +
            '<path d="' + path("x", true) + '" fill="none" stroke="var(--violet-2)" stroke-width="2"/>' +
            '<path d="' + path("enquiries") + base + '" fill="var(--orange)" opacity="0.18"/>' +
            '<path d="' + path("enquiries") + '" fill="none" stroke="var(--orange-2)" stroke-width="2"/>' +
            '<text x="' + pad + '" y="' + (h - 5) + '" font-size="9" fill="var(--text-muted)">' +
            esc(dayLabel(rows[0].day)) + "</text>" +
            '<text x="' + (w - pad) + '" y="' + (h - 5) + '" font-size="9" fill="var(--text-muted)" text-anchor="end">' +
            esc(dayLabel(rows[rows.length - 1].day)) + "</text>" +
            '<text x="' + pad + '" y="12" font-size="9" fill="var(--text-muted)">peak ' + esc(max) + "/day</text></svg>";
        }
        function dayLabel(ts) {
          var dt = new Date(ts * 1000);
          return dt.toLocaleDateString(undefined, { day: "numeric", month: "short" });
        }
        /* status mix as a donut — one ring segment per status, real counts only */
        function donut(counts) {
          var order = ["new", "in_progress", "quoted", "won", "lost", "closed"];
          var colors = { new: "var(--orange-2)", in_progress: "var(--adm-info)", quoted: "var(--violet-2)",
                         won: "var(--adm-ok)", lost: "var(--adm-bad)", closed: "var(--text-muted)" };
          var total = order.reduce(function (s, k) { return s + (counts[k] || 0); }, 0);
          if (!total) return '<p class="admin-inline-note">No requests yet.</p>';
          var C = 2 * Math.PI * 42, at = 0;
          var ring = order.map(function (k) {
            var v = counts[k] || 0;
            if (!v) return "";
            var len = (v / total) * C;
            var seg = '<circle cx="60" cy="60" r="42" fill="none" stroke="' + colors[k] +
              '" stroke-width="15" stroke-dasharray="' + len.toFixed(2) + " " + (C - len).toFixed(2) +
              '" stroke-dashoffset="' + (-at).toFixed(2) + '" transform="rotate(-90 60 60)"><title>' +
              esc(STATUS_LABELS[k] || k) + ": " + esc(v) + "</title></circle>";
            at += len;
            return seg;
          }).join("");
          return '<div class="donut-wrap"><svg class="donut" viewBox="0 0 120 120" role="img" aria-label="Requests by status">' +
            '<circle cx="60" cy="60" r="42" fill="none" stroke="var(--adm-inset)" stroke-width="15"/>' + ring +
            '<text class="donut-mid" x="60" y="60" text-anchor="middle" dominant-baseline="central">' + esc(total) + "</text>" +
            '<text class="donut-sub" x="60" y="78" text-anchor="middle">total</text></svg>' +
            '<div class="bar-list" style="flex:1;min-width:180px">' + order.map(function (k) {
              var v = counts[k] || 0;
              return '<div class="bar-row"><span class="bar-label">' + esc(STATUS_LABELS[k] || k) + "</span>" +
                '<span class="bar-track"><i class="bar-fill" style="width:' + Math.round((v / total) * 100) +
                "%;background:" + colors[k] + '"></i></span><span class="bar-num">' + esc(v) + "</span></div>";
            }).join("") + "</div></div>";
        }
        function marketPanel(key, label) {
          var m = mk[key] || {};
          var a = m.lastAttempt;
          var enq = (d.marketCounts || {})[key] || 0;
          return '<div class="admin-panel"><div class="panel-head"><h2>' + esc(label) +
            '</h2><span class="jz-flag">' + esc(key.toUpperCase()) + "</span></div>" +
            '<div class="stat-row stat-row--tight">' +
            '<div class="stat-card"><b>' + esc(m.products || 0) + "</b><span>Products cached</span></div>" +
            '<div class="stat-card' + (m.cached && !m.inStock ? " stat-card--warn" : "") + '"><b>' +
            esc(m.inStock || 0) + "</b><span>In stock</span></div>" +
            '<div class="stat-card"><b>' + esc(enq) + "</b><span>Requests</span></div></div>" +
            (m.cached
              ? '<p class="admin-inline-note">Products synced ' + esc(when(m.fetchedAt)) +
                (m.productsFresh ? ' <span class="badge-ok">fresh</span>' : ' <span class="badge-bad">due</span>') +
                (m.nextProductsAt ? " · next due " + esc(when(m.nextProductsAt)) : "") +
                "<br>Stock synced " + esc(when(m.stockAt)) +
                (m.stockFresh ? ' <span class="badge-ok">fresh</span>' : ' <span class="badge-bad">due</span>') +
                (m.nextStockAt ? " · next due " + esc(when(m.nextStockAt)) : "") + "</p>"
              : '<p class="admin-inline-note">Nothing cached for this market yet.</p>') +
            (a && !a.ok
              ? '<p class="ins-alert ins-alert--warn">Last sync failed (' + esc(a.what) + ", " +
                esc(when(a.ts)) + "): " + esc(a.reason) + "</p>"
              : a ? '<p class="admin-inline-note">Last sync ' + esc(when(a.ts)) +
                    ' <span class="badge-ok">reached</span></p>' : "");
        }
        function svc(state, name, detail) {
          return '<div class="svc-row svc-row--' + state + '"><i class="svc-dot"></i><b>' +
                 esc(name) + "</b><small>" + esc(detail) + "</small></div>";
        }
        var mailState = !mail.configured ? "warn" : (mail.failed ? "bad" : "ok");
        var totalRequests = Object.keys(d.requests || {}).reduce(function (s, k) { return s + d.requests[k]; }, 0);

        main.innerHTML =
          '<h1 class="admin-h1">Welcome back, ' + esc(d.user.name) + "</h1>" +
          '<p class="admin-sub">Live figures from the site — enquiries, supplier catalogue and delivery. ' +
          "Everything here reads the real system state.</p>" +

          '<div class="stat-row">' +
          '<div class="stat-card stat-card--click" data-go="requests"><b>' + esc(totalRequests) +
          "</b><span>Requests all time</span>" + delta(tot.last30 || 0, tot.prev30 || 0) +
          sparkline(series.map(function (x) { return x.enquiries + x.notifications; })) + "</div>" +
          '<div class="stat-card stat-card--click" data-go="requests"><b>' + esc((d.statusCounts || {}).new || 0) +
          "</b><span>Awaiting a first reply</span></div>" +
          '<div class="stat-card"><b>' + esc(tot.last7 || 0) + "</b><span>Last 7 days</span></div>" +
          '<div class="stat-card' + (mail.failed ? " stat-card--bad" : "") + '"><b>' + esc(mail.sent || 0) +
          "</b><span>Emails delivered</span>" +
          (mail.failed ? '<span class="stat-delta stat-delta--down">' + esc(mail.failed) + " failed</span>" : "") + "</div>" +
          '<div class="stat-card"><b>' + esc((d.rentals || {}).count || 0) + "</b><span>Rental items</span></div>" +
          "</div>" +

          '<div class="dash-grid">' +
          '<div class="admin-panel dash-wide"><div class="panel-head"><h2>Submissions · last 14 days</h2>' +
          '<span class="legend"><span><i class="key key--orange"></i> Enquiries</span>' +
          '<span><i class="key key--violet"></i> Including alerts</span></span></div>' +
          areaChart(series) + "</div>" +

          '<div class="admin-panel"><h2>Where requests stand</h2>' + donut(d.statusCounts || {}) + "</div>" +

          '<div class="admin-panel"><h2>What people ask for</h2><div class="bar-list">' +
          (function () {
            var keys = Object.keys(d.requests || {});
            var max = Math.max.apply(null, keys.map(function (k) { return d.requests[k]; }).concat([1]));
            return keys.map(function (k) {
              return '<div class="bar-row"><span class="bar-label">' + esc(LABELS[k] || k) + "</span>" +
                '<span class="bar-track"><i class="bar-fill' + (k.indexOf("notification") !== -1 ? " bar-fill--violet" : "") +
                '" style="width:' + Math.round((d.requests[k] / max) * 100) + '%"></i></span>' +
                '<span class="bar-num">' + esc(d.requests[k]) + "</span></div>";
            }).join("");
          }()) + "</div></div>" +
          "</div>" +

          MARKET_LIST.map(function (m) {
            var b = (sup.budgets || {})[m[0]] || {};
            var rh = Math.floor((b.resetInSeconds || 0) / 3600);
            var rm = Math.floor(((b.resetInSeconds || 0) % 3600) / 60);
            var pct = b.limit ? Math.min(100, Math.round((b.used / b.limit) * 100)) : 0;
            return '<div class="admin-panel"><div class="panel-head"><h2>Jasani — ' + esc(m[1]) +
              '</h2><span class="admin-inline-note">' + esc(b.used || 0) + " of " + esc(b.limit || 0) +
              " calls used · " + esc(b.remaining || 0) + " left · resets in " + rh + "h " + rm +
              "m · " + esc(m[2]) + "</span></div>" +
              '<div class="gauge gauge--split"><div class="gauge__fill' +
              (b.autoRemaining === 0 ? " gauge__fill--max" : "") + '" style="width:' + pct + '%"></div>' +
              (b.reserved ? '<i class="gauge__reserve" style="width:' +
                Math.round((b.reserved / Math.max(1, b.limit)) * 100) + '%"></i>' : "") + "</div>" +
              ((sup.tokensConfigured || {})[m[0]] ? "" :
                '<p class="ins-alert ins-alert--warn">No API token for this market — set ' +
                esc(m[0] === "uae" ? "JASANI_API_TOKEN_UAE" : "JASANI_API_TOKEN") +
                " on the server.</p>") + "</div>";
          }).join("") +
          '<div class="jz-grid">' + marketPanel("ksa", "Saudi Arabia — giftsksa.com") +
          marketPanel("uae", "United Arab Emirates — jasani.ae") + "</div>" +

          '<div class="dash-grid">' +
          '<div class="admin-panel"><h2>Service status</h2><div class="svc-list">' +
          MARKET_LIST.map(function (m) {
            var b = (sup.budgets || {})[m[0]] || {};
            var ok = (sup.tokensConfigured || {})[m[0]];
            return svc(!ok ? "bad" : (b.autoRemaining === 0 ? "warn" : "ok"),
                       "Jasani " + m[0].toUpperCase(),
                       !ok ? "no token" : (b.remaining || 0) + " of " + (b.limit || 0) + " calls left");
          }).join("") +
          svc(mailState, "Transactional email",
              !mail.configured ? "no API key set" :
              (mail.pending ? mail.pending + " queued" : "queue clear") +
              (mail.failed ? ", " + mail.failed + " failed" : "")) +
          svc("ok", "Rental catalogue", ((d.rentals || {}).count || 0) + " items · " + esc((d.rentals || {}).source || "")) +
          svc("ok", "Admin accounts", d.adminUsers + " with access") +
          "</div></div>" +
          '<div class="admin-panel"><h2>Recent activity</h2><div class="act-list">' +
          ((d.audit || []).map(function (a) {
            return '<div class="act-item"><time>' + esc(when(a.ts)) + "</time><b>" + esc(a.action) +
              "</b><span>" + esc(a.user_email || "system") + "</span></div>";
          }).join("") || '<p class="admin-inline-note">Nothing yet.</p>') + "</div></div>" +
          "</div>";

        main.querySelectorAll("[data-go]").forEach(function (el) {
          el.addEventListener("click", function () { location.hash = "#" + el.getAttribute("data-go"); });
        });
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
          '<div class="admin-panel"><h2>Find a request</h2><div class="req-filters">' +
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
        var budgets = d.budgets || {};
        var tokens = d.tokensConfigured || {};
        var MARKETS = [["ksa", "Saudi Arabia — giftsksa.com", "Riyadh (UTC+3)"],
                       ["uae", "United Arab Emirates — jasani.ae", "Dubai (UTC+4)"]];

        function hhmm(h) { return (h < 10 ? "0" + h : h) + ":00"; }
        function budgetBlock(key, zone) {
          var b = budgets[key] || {};
          var pct = b.limit ? Math.min(100, Math.round((b.used / b.limit) * 100)) : 0;
          var resetH = Math.floor((b.resetInSeconds || 0) / 3600);
          var resetM = Math.floor(((b.resetInSeconds || 0) % 3600) / 60);
          var done = b.slotsDone || [];
          var next = b.nextSlot || {};
          return '<div class="gauge gauge--split"><div class="gauge__fill' +
            (b.autoRemaining === 0 ? " gauge__fill--max" : "") + '" style="width:' + pct + '%"></div>' +
            (b.reserved ? '<i class="gauge__reserve" style="width:' +
              Math.round((b.reserved / Math.max(1, b.limit)) * 100) + '%"></i>' : "") + "</div>" +
            '<p class="admin-inline-note">' + esc(b.used || 0) + " of " + esc(b.limit || 0) +
            " calls used · " + esc(b.remaining || 0) + " left · resets in " + resetH + "h " + resetM +
            "m · " + esc(zone) + " day " + esc(b.day || "—") + "<br>" +
            "Automatic syncs stop after " + esc(b.autoLimit || 0) + "; the last " +
            esc(b.reserved || 0) + " is reserved for a manual sync by an owner or admin.</p>" +
            '<div class="slot-row">' + (b.schedule || []).map(function (s) {
              var ran = done.indexOf(s.hour) !== -1;
              return '<span class="slot' + (ran ? " slot--done" : "") +
                (!ran && next.hour === s.hour ? (next.due ? " slot--due" : " slot--next") : "") + '">' +
                esc(hhmm(s.hour)) + "<em>" + esc(s.what) + "</em></span>";
            }).join("") + "</div>";
        }

        function marketCard(key, label, zone) {
          var m = (d.markets || {})[key] || {};
          var a = m.lastAttempt;
          return '<div class="admin-panel jz-market"><div class="panel-head"><h2>' + esc(label) +
            '</h2><span class="jz-flag">' + esc(key.toUpperCase()) + "</span></div>" +
            (tokens[key] ? "" :
              '<p class="ins-alert ins-alert--warn">No API token for this market — set ' +
              esc(key === "uae" ? "JASANI_API_TOKEN_UAE" : "JASANI_API_TOKEN") +
              " on the server. Nothing is called and the cached snapshot keeps serving.</p>") +
            budgetBlock(key, zone) +
            (m.cached
              ? '<div class="stat-row stat-row--tight">' +
                '<div class="stat-card"><b>' + esc(m.products) + "</b><span>Products cached</span></div>" +
                '<div class="stat-card"><b>' + esc(m.inStock) + "</b><span>In stock</span></div>" +
                '<div class="stat-card"><b>' + esc(m.withPrice) + "</b><span>With a price</span></div></div>" +
                '<p class="admin-inline-note">Products: ' + esc(when(m.fetchedAt)) +
                (m.productsFresh ? ' <span class="badge-ok">fresh</span>' : ' <span class="badge-bad">due</span>') +
                "<br>Prices: " + (m.priceAt ? esc(when(m.priceAt)) +
                    (m.pricesFresh ? ' <span class="badge-ok">fresh</span>' : ' <span class="badge-bad">due</span>') +
                    (m.currencies && m.currencies.length ? " · " + esc(m.currencies.join(", ")) : "")
                  : '<span class="badge-bad">never synced</span>') +
                "<br>Stock: " + esc(when(m.stockAt)) +
                (m.stockFresh ? ' <span class="badge-ok">fresh</span>' : ' <span class="badge-bad">due</span>') + "</p>" +
                (m.withPrice === 0 && m.products
                  ? '<p class="ins-alert ins-alert--warn">No product carries a price. Prices come from ' +
                    "the supplier's own Price API — a products sync does not fetch them. Run " +
                    "<b>Prices</b> below, or wait for the scheduled price call.</p>" : "")
              : '<p class="admin-inline-note">Nothing cached yet for this market.</p>') +
            (function () {
              if (!a) return "";
              return a.ok
                ? '<p class="admin-inline-note">Last supplier call: ' + esc(when(a.ts)) +
                  ' <span class="badge-ok">reached</span> · ' + esc(a.reason) + "</p>"
                : '<p class="ins-alert ins-alert--warn">Last supplier call failed — ' +
                  esc(a.what) + ", " + esc(when(a.ts)) + ": " + esc(a.reason) + "</p>";
            }()) +
            (can("jasani.refresh")
              ? '<div class="admin-actions">' +
                '<button class="btn btn--primary btn--small" data-refresh="full" data-market="' + key + '">Full sync (3 calls)</button>' +
                '<button class="btn btn--ghost btn--small" data-refresh="products" data-market="' + key + '">Products (1 call)</button>' +
                '<button class="btn btn--ghost btn--small" data-refresh="prices" data-market="' + key + '">Prices (1 call)</button>' +
                '<button class="btn btn--ghost btn--small" data-refresh="stock" data-market="' + key + '">Stock (1 call)</button></div>'
              : "") + "</div>";
        }

        main.innerHTML =
          '<h1 class="admin-h1">Jasani console</h1>' +
          '<p class="admin-sub">Each market has its own supplier account, its own five calls a day and ' +
          "its own local clock. The website always serves the cached snapshot — a page load never waits " +
          "on the supplier.</p>" +
          '<div class="jz-grid">' + MARKETS.map(function (m) {
            return marketCard(m[0], m[1], m[2]);
          }).join("") + "</div>" +
          '<div class="admin-panel"><h2>Printing manuals cache</h2><p class="admin-inline-note">' +
          esc(d.manuals.cachedPdfs) + " PDF(s) cached (" + (d.manuals.bytes / (1024 * 1024)).toFixed(1) + " MB) · " +
          esc(d.manuals.validVerdicts) + " valid · " + esc(d.manuals.failedVerdicts) + " marked unavailable</p></div>" +
          '<div class="admin-panel" id="jz-visibility"><p class="admin-inline-note">Loading…</p></div>' +
          '<div class="admin-panel"><h2>Search the cached catalog</h2>' +
          '<p class="admin-inline-note" style="margin-bottom:10px;">A quick look-up. The full table, ' +
          'with filters, prices and exports, is on <a href="#items">Jasani items</a>.</p>' +
          '<div class="req-filters">' +
          '<select id="jz-market"><option value="ksa">Saudi Arabia</option><option value="uae">UAE</option></select>' +
          '<input id="jz-q" placeholder="Name, SKU or id" maxlength="80">' +
          '<button class="btn btn--ghost btn--small" id="jz-search">Search</button></div>' +
          '<div id="jz-results"></div></div>';

        /* what the public Corporate Gifts pages are allowed to show */
        var visMarket = "ksa", visSearch = "";
        function loadVisibility() {
          var box = document.getElementById("jz-visibility");
          if (!box) return;
          api("/api/admin/jasani/visibility?market=" + visMarket).then(function (rv) {
            if (!rv.ok) { box.innerHTML = '<p class="admin-inline-note">Could not load.</p>'; return; }
            var v = rv.data, canVis = can("jasani.visibility");
            var needle = visSearch.trim().toLowerCase();
            box.innerHTML =
              '<div class="panel-head"><h2>What the website shows</h2>' +
              '<span class="admin-inline-note">Applies to the public Corporate Gifts pages</span></div>' +
              '<div class="jz-head" style="margin-bottom:14px;"><span class="jz-head__spacer"></span>' +
              '<div class="jz-seg" role="group" aria-label="Market">' +
              ["ksa", "uae"].map(function (m) {
                return '<button type="button" data-vismarket="' + m + '" aria-pressed="' +
                  (visMarket === m) + '">' + (m === "ksa" ? "Saudi Arabia" : "UAE") + "</button>";
              }).join("") + "</div></div>" +
              '<label class="jz-rule-card" style="margin-bottom:14px;">' +
                '<input type="checkbox" id="jz-zero-rule"' + (v.hideZeroStock ? " checked" : "") +
                (canVis ? "" : " disabled") + ">" +
                "<span><b>Hide items with no available stock</b><span>Applies to " +
                esc(visMarket.toUpperCase()) + ", where " + v.zeroStockCount + " item" +
                (v.zeroStockCount === 1 ? " has" : "s have") + " zero available stock right now. " +
                "With this on they leave the catalogue and search, and they come back on their own " +
                "at the next stock sync — nobody has to remember to switch them back." +
                (canVis ? "" : " Only an owner or admin can change this.") + "</span></span></label>" +
              '<h3 style="font-size:0.95rem;margin:18px 0 8px;">Hide one item</h3>' +
              '<div class="req-filters"><input id="jz-hide-q" placeholder="Search a SKU, name or brand" ' +
                'maxlength="80" value="' + esc(visSearch) + '"></div>' +
              '<div id="jz-hide-results"></div>' +
              '<h3 style="font-size:0.95rem;margin:22px 0 8px;">Hidden right now</h3>' +
              ((v.hiddenItems || []).length
                ? '<div class="jz-hidden-list">' + v.hiddenItems.map(function (h) {
                    return '<div class="jz-hidden-item"><b>' + esc(h.code || h.product_id) + "</b>" +
                      "<span>" + esc(h.name) + "</span>" +
                      '<span class="jz-hidden-item__spacer"></span>' +
                      '<span class="jz-hidden-why">hidden by hand · ' + esc(when(h.hidden_at)) + "</span>" +
                      (canVis ? '<button class="btn btn--ghost btn--small" data-unhide="' +
                        esc(h.product_id) + '">Show on website</button>' : "") + "</div>";
                  }).join("") + "</div>"
                : '<p class="admin-inline-note">Nothing is hidden by hand in ' +
                  esc(visMarket.toUpperCase()) + ".</p>") +
              '<p class="admin-inline-note" style="margin-top:10px;">Only items switched off by hand ' +
              "are listed here. Items the zero-stock rule is holding back are not — they return by " +
              'themselves, and you can see which ones on <a href="#items">Jasani items</a> under ' +
              "Website → Not on the website.</p>";

            box.querySelectorAll("[data-vismarket]").forEach(function (b) {
              b.addEventListener("click", function () {
                visMarket = b.getAttribute("data-vismarket");
                visSearch = "";
                loadVisibility();
              });
            });
            var rule = document.getElementById("jz-zero-rule");
            if (rule && canVis) rule.addEventListener("change", function () {
              api("/api/admin/jasani/zero-stock-rule", { market: visMarket, on: rule.checked })
                .then(function (r2) {
                  if (!r2.ok) return apiErr(r2);
                  toast(rule.checked ? "Zero-stock items are now hidden from the website."
                                     : "Zero-stock items are shown on the website again.");
                  loadVisibility();
                });
            });
            var hq = document.getElementById("jz-hide-q");
            var hTimer = null;
            hq.addEventListener("input", function () {
              visSearch = hq.value;
              clearTimeout(hTimer);
              hTimer = setTimeout(searchToHide, 300);
            });
            if (needle) searchToHide();
            box.querySelectorAll("[data-unhide]").forEach(function (b) {
              b.addEventListener("click", function () {
                api("/api/admin/jasani/visibility",
                    { market: visMarket, productId: b.getAttribute("data-unhide"), hidden: false })
                  .then(function (r2) {
                    r2.ok ? (toast("Shown on the website again."), loadVisibility()) : apiErr(r2);
                  });
              });
            });
          });
        }
        function searchToHide() {
          var out = document.getElementById("jz-hide-results");
          if (!out) return;
          var term = (document.getElementById("jz-hide-q") || {}).value || "";
          if (!term.trim()) { out.innerHTML = ""; return; }
          api("/api/admin/jasani/items?market=" + visMarket + "&q=" +
              encodeURIComponent(term) + "&perPage=10").then(function (r2) {
            if (!r2.ok) return apiErr(r2);
            var rows = r2.data.items || [];
            var canVis = can("jasani.visibility");
            out.innerHTML = rows.length
              ? '<div class="jz-hidden-list">' + rows.map(function (it) {
                  return '<div class="jz-hidden-item">' +
                    (it.image ? '<img class="jz-img" style="width:30px;height:30px;" src="' +
                      esc(it.image) + '" alt="">' : "") +
                    "<b>" + esc(it.code) + "</b><span>" + esc(it.name) + "</span>" +
                    '<span class="jz-hidden-item__spacer"></span>' +
                    '<span class="jz-hidden-why">' + jzNum(it.available) + " available</span>" +
                    (canVis ? '<button class="btn btn--ghost btn--small" data-hidetoggle="' +
                      esc(it.id) + '" data-on="' + (it.hidden ? "1" : "0") + '">' +
                      (it.hidden ? "Show on website" : "Hide from website") + "</button>" : "") +
                    "</div>";
                }).join("") + "</div>"
              : '<p class="admin-inline-note">Nothing matches “' + esc(term) + "”.</p>";
            out.querySelectorAll("[data-hidetoggle]").forEach(function (b) {
              b.addEventListener("click", function () {
                api("/api/admin/jasani/visibility", {
                  market: visMarket, productId: b.getAttribute("data-hidetoggle"),
                  hidden: b.getAttribute("data-on") !== "1"
                }).then(function (r3) {
                  if (!r3.ok) return apiErr(r3);
                  toast("Saved.");
                  loadVisibility();
                });
              });
            });
          });
        }
        loadVisibility();

        main.querySelectorAll("[data-refresh]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var what = btn.getAttribute("data-refresh"), market = btn.getAttribute("data-market");
            var b = budgets[market] || {};
            var cost = (d.refreshCost || {})[what] || 1;
            var reserve = b.autoRemaining < cost && b.remaining >= cost;
            if (!confirm("This uses " + cost + " of " + market.toUpperCase() + "'s " + b.limit +
                         " daily supplier calls (" + b.remaining + " remaining)." +
                         (reserve ? " It will use the call reserved for manual syncs." : "") +
                         " Continue?")) return;
            btn.disabled = true;
            api("/api/admin/jasani/refresh", { market: market, what: what }).then(function (r2) {
              btn.disabled = false;
              if (!r2.ok) return apiErr(r2);
              toast(what === "full"
                ? "Full sync done for " + market.toUpperCase() + " — " +
                  jzNum(r2.data.priced || 0) + " products priced."
                : "Refreshed " + what + " for " + market.toUpperCase() + ".");
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
          '<p class="admin-sub">Add pages, edit text and SEO per page, preview privately, then publish the whole site in one click. The original design always stays safe in the code.</p>' +
          '<div class="admin-panel" id="hidden-panel"><div class="panel-head"><h2>Hidden on the site</h2>' +
          '<span class="admin-inline-note">Anything switched off in the visual editor, in one place</span></div>' +
          '<div id="hidden-list"><p class="admin-inline-note">Loading…</p></div></div>' +
          '<div class="admin-panel"><h2>Publishing</h2>' +
          (d.staleBuild ? '<p class="ins-alert ins-alert--warn">The site code was updated after your last publish — press <b>Publish site</b> once so the live pages pick up the newest version.</p>' : "") +
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
          '<div class="admin-panel"><h2>Pages</h2>' +
          '<div class="admin-actions" style="margin-bottom:14px;">' +
          '<button class="btn btn--primary btn--small" id="page-new">+ New page</button></div>' +
          '<form id="page-new-form" class="admin-form" hidden style="margin-bottom:18px;">' +
          '<div class="form-row"><label>Page name (shown in the menu)<input id="np-label" maxlength="60" required placeholder="Our team"></label>' +
          '<label>Web address<span class="np-slug-wrap">/<input id="np-slug" maxlength="40" required placeholder="our-team">.html</span></label></div>' +
          '<label>Browser &amp; search title<input id="np-title" maxlength="200" placeholder="Our team — Elite Marcom"></label>' +
          '<label>Meta description<textarea id="np-desc" rows="2" maxlength="300" placeholder="One or two sentences describing the page for search results."></textarea></label>' +
          '<label class="ed-check"><input type="checkbox" id="np-nav" checked> Show this page in the site menus</label>' +
          '<div class="admin-actions"><button class="btn btn--primary btn--small" type="submit">Create page</button>' +
          '<button class="btn btn--ghost btn--small" type="button" id="np-cancel">Cancel</button></div>' +
          '<p class="admin-inline-note">The new page starts with the same header, footer and styling as the rest of the site. ' +
          "Open it in the <b>Visual editor</b> to write it, then press <b>Publish site</b>.</p></form>" +
          '<div class="table-scroll"><table class="admin-table"><thead>' +
          "<tr><th>Page</th><th>Text fields</th><th>State</th><th></th></tr></thead><tbody>" +
          (d.pages || []).map(function (p) {
            return "<tr><td>" + esc(p.label) +
              (p.custom ? ' <span class="status-pill">added</span>' : "") +
              ' <span class="muted">(' + esc(p.file) + ")</span>" +
              (p.custom && !p.nav ? '<br><span class="admin-inline-note">not in the menus</span>' : "") + "</td>" +
              '<td class="muted">' + (p.regions ? p.regions + " + SEO" : "SEO only") + "</td>" +
              "<td>" + (p.dirty ? '<span class="badge-bad">unpublished edits</span>' : '<span class="muted">up to date</span>') + "</td>" +
              '<td class="cell-actions"><a class="btn btn--ghost btn--small" href="#editor/' + esc(p.page) + '">Visual editor</a> ' +
              '<a class="btn btn--ghost btn--small" href="#pages/' + esc(p.page) + '">Text &amp; SEO</a> ' +
              '<a class="btn btn--ghost btn--small" href="/admin/preview/' + esc(p.page) + '" target="_blank" rel="noopener">Preview</a>' +
              (p.custom ? ' <button class="btn btn--ghost btn--small" data-page-nav="' + esc(p.page) + '" data-on="' +
                (p.nav ? "1" : "0") + '">' + (p.nav ? "Remove from menus" : "Add to menus") + "</button>" +
                ' <button class="btn btn--ghost btn--small" data-page-del="' + esc(p.page) + '">Delete</button>' : "") +
              "</td></tr>";
          }).join("") + "</tbody></table></div></div>";
        /* what is currently hidden anywhere on the site, and how to put it back */
        function loadHidden() {
          var box = document.getElementById("hidden-list");
          if (!box) return;
          api("/api/admin/design-hidden").then(function (r2) {
            if (!r2.ok) { box.innerHTML = '<p class="admin-inline-note">Could not load.</p>'; return; }
            var rows = r2.data.hidden || [];
            var LABELS = { base: "desktop", tablet: "tablet", mobile: "mobile" };
            box.innerHTML = rows.length
              ? '<div class="table-scroll"><table class="admin-table"><thead><tr>' +
                "<th>What</th><th>Page</th><th>Hidden on</th><th></th></tr></thead><tbody>" +
                rows.map(function (h) {
                  return "<tr><td><b>" + esc(h.label) + "</b><br>" +
                    '<span class="admin-inline-note">' + esc(h.kind) + " · " + esc(h.path) + "</span></td>" +
                    '<td class="muted">' + esc(h.page === "_global" ? "every page" : h.page) + "</td>" +
                    "<td>" + h.breakpoints.map(function (b2) {
                      return '<span class="status-pill">' + esc(LABELS[b2] || b2) + "</span>";
                    }).join(" ") + "</td>" +
                    '<td class="cell-actions"><button class="btn btn--ghost btn--small" data-unhide="' +
                    esc(h.page) + "|" + esc(h.kind) + "|" + esc(h.path) + '">Show again</button></td></tr>';
                }).join("") + "</tbody></table></div>"
              : '<p class="admin-inline-note">Nothing is hidden — every section and element is visible. ' +
                "To hide something, open the <b>Visual editor</b>, click it, and use Visibility " +
                "(or the eye button in the Sections list for a whole section).</p>";
            box.querySelectorAll("[data-unhide]").forEach(function (btn) {
              btn.addEventListener("click", function () {
                var parts = btn.getAttribute("data-unhide").split("|");
                btn.disabled = true;
                api("/api/admin/design-hidden/restore",
                    { page: parts[0], kind: parts[1], path: parts[2] }).then(function (r3) {
                  btn.disabled = false;
                  if (!r3.ok) return apiErr(r3);
                  toast("Shown again — publish to put it live.");
                  loadHidden();
                });
              });
            });
          });
        }
        loadHidden();

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
        (function () {
          var form = document.getElementById("page-new-form");
          var label = document.getElementById("np-label");
          var slug = document.getElementById("np-slug");
          var slugTouched = false;
          document.getElementById("page-new").addEventListener("click", function () {
            form.hidden = !form.hidden;
            if (!form.hidden) label.focus();
          });
          document.getElementById("np-cancel").addEventListener("click", function () {
            form.hidden = true;
          });
          slug.addEventListener("input", function () { slugTouched = true; });
          label.addEventListener("input", function () {
            if (slugTouched) return;
            slug.value = label.value.toLowerCase().replace(/[^a-z0-9]+/g, "-")
              .replace(/^-+|-+$/g, "").slice(0, 40);
          });
          form.addEventListener("submit", function (e) {
            e.preventDefault();
            api("/api/admin/pages-new", {
              slug: slug.value.trim(), label: label.value.trim(),
              title: document.getElementById("np-title").value.trim(),
              description: document.getElementById("np-desc").value.trim(),
              nav: document.getElementById("np-nav").checked
            }).then(function (r2) {
              if (!r2.ok) return apiErr(r2);
              toast("Page created — opening the visual editor.");
              location.hash = "#editor/" + r2.data.page.slug;
            });
          });
        }());
        main.querySelectorAll("[data-page-del]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var page = btn.getAttribute("data-page-del");
            if (!confirm("Delete the page “" + page + "” with everything written on it? This cannot be undone.")) return;
            api("/api/admin/pages-delete/" + encodeURIComponent(page), {}).then(function (r2) {
              r2.ok ? (toast("Page deleted."), views.pages()) : apiErr(r2);
            });
          });
        });
        main.querySelectorAll("[data-page-nav]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var page = btn.getAttribute("data-page-nav");
            api("/api/admin/pages-meta/" + encodeURIComponent(page),
                { nav: btn.getAttribute("data-on") !== "1" }).then(function (r2) {
              r2.ok ? (toast("Menus updated — publish to put it live."), views.pages()) : apiErr(r2);
            });
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
          '<div class="full"><label>Images</label>' +
          '<div class="up-drop" id="rf-drop" tabindex="0" role="button">' +
          '<b>Drop images here, or click to choose from your computer</b>' +
          '<span class="field-help">JPG, PNG or WebP · up to 8 MB each · converted and stored in the Media Library. ' +
          'The first image is the one shown on the rental card.</span>' +
          '<input type="file" id="rf-file" accept="image/*" multiple hidden></div>' +
          '<div class="admin-actions" style="margin-top:10px">' +
          '<button class="btn btn--ghost btn--small" type="button" id="rf-pick">Choose from Media Library</button>' +
          '<span class="admin-inline-note" id="rf-upstatus"></span></div>' +
          '<div class="up-bar" id="rf-bar" hidden><span style="width:0%"></span></div>' +
          '<div class="gal-grid" id="rf-gallery"></div></div>' +
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

        /* ---- image gallery: upload, pick, reorder, set primary, remove ---- */
        var galleryImages = [];
        function renderGallery() {
          var grid = document.getElementById("rf-gallery");
          if (!grid) return;
          grid.innerHTML = galleryImages.length
            ? galleryImages.map(function (src, i) {
                return '<figure class="gal-item' + (i === 0 ? " is-primary" : "") + '">' +
                  (i === 0 ? '<span class="gal-tag">Card image</span>' : "") +
                  '<img src="' + esc(src) + '" alt="" loading="lazy">' +
                  '<figcaption class="gal-btns">' +
                  '<button type="button" data-gal-left="' + i + '" title="Move earlier"' +
                  (i === 0 ? " disabled" : "") + ">←</button>" +
                  '<button type="button" data-gal-right="' + i + '" title="Move later"' +
                  (i === galleryImages.length - 1 ? " disabled" : "") + ">→</button>" +
                  '<button type="button" data-gal-primary="' + i + '" title="Use as the card image"' +
                  (i === 0 ? " disabled" : "") + ">★</button>" +
                  '<button type="button" data-gal-del="' + i + '" title="Remove">✕</button>' +
                  "</figcaption></figure>";
              }).join("")
            : '<p class="admin-inline-note">No images yet — upload one or choose from the Media Library.</p>';
          grid.querySelectorAll("[data-gal-left]").forEach(function (b) {
            b.addEventListener("click", function () {
              var i = +b.getAttribute("data-gal-left");
              galleryImages.splice(i - 1, 0, galleryImages.splice(i, 1)[0]);
              renderGallery();
            });
          });
          grid.querySelectorAll("[data-gal-right]").forEach(function (b) {
            b.addEventListener("click", function () {
              var i = +b.getAttribute("data-gal-right");
              galleryImages.splice(i + 1, 0, galleryImages.splice(i, 1)[0]);
              renderGallery();
            });
          });
          grid.querySelectorAll("[data-gal-primary]").forEach(function (b) {
            b.addEventListener("click", function () {
              var i = +b.getAttribute("data-gal-primary");
              galleryImages.unshift(galleryImages.splice(i, 1)[0]);
              renderGallery();
            });
          });
          grid.querySelectorAll("[data-gal-del]").forEach(function (b) {
            b.addEventListener("click", function () {
              galleryImages.splice(+b.getAttribute("data-gal-del"), 1);
              renderGallery();
            });
          });
        }
        function addImage(src) {
          if (src && galleryImages.indexOf(src) === -1 && galleryImages.length < 10) {
            galleryImages.push(src);
            renderGallery();
          }
        }
        function uploadFiles(files) {
          var list = Array.prototype.slice.call(files || []).filter(function (f) {
            return /^image\//.test(f.type);
          });
          if (!list.length) return;
          var bar = document.getElementById("rf-bar");
          var fill = bar.querySelector("span");
          var status = document.getElementById("rf-upstatus");
          bar.hidden = false;
          var done = 0;
          function step() {
            if (!list.length) {
              bar.hidden = true;
              fill.style.width = "0%";
              status.textContent = done ? done + " image(s) added." : "";
              return;
            }
            var file = list.shift();
            status.textContent = "Uploading " + file.name + "…";
            var fd = new FormData();
            fd.append("file", file);
            fd.append("alt", file.name.replace(/\.[^.]+$/, "").slice(0, 120));
            apiUpload("/api/admin/media/upload", fd).then(function (r2) {
              if (r2.ok) { addImage("/media/" + r2.data.item.file); done++; }
              else { status.textContent = (r2.data && r2.data.detail) || "That file was rejected."; }
              fill.style.width = Math.round((done / (done + list.length)) * 100) + "%";
              step();
            });
          }
          step();
        }

        function openForm(p) {
          document.getElementById("rent-form-panel").hidden = false;
          document.getElementById("rent-form-title").textContent = p ? "Edit — " + p.name : "Add new item";
          document.getElementById("rf-id").value = p ? p.id : "";
          document.getElementById("rf-id").readOnly = !!p;
          document.getElementById("rf-code").value = p ? p.code || "" : "";
          document.getElementById("rf-name").value = p ? p.name : "";
          document.getElementById("rf-category").value = p ? p.category : "";
          galleryImages = p ? (p.images || []).slice() : [];
          if (p && p.image && galleryImages.indexOf(p.image) === -1) galleryImages.unshift(p.image);
          renderGallery();
          document.getElementById("rf-desc").value = p ? p.description || "" : "";
          document.getElementById("rf-specs").value = p ? (p.specs || []).join("\n") : "";
          document.getElementById("rf-tags").value = p ? (p.tags || []).join(", ") : "";
          document.getElementById("rf-featured").value = p && p.featured ? "yes" : "no";
          document.getElementById("rf-ksa").value = p ? p.stockByMarket.ksa : 0;
          document.getElementById("rf-uae").value = p ? p.stockByMarket.uae : 0;
          document.getElementById("rent-form-panel").scrollIntoView({ behavior: "smooth", block: "start" });
        }
        (function wireGallery() {
          var drop = document.getElementById("rf-drop");
          var input = document.getElementById("rf-file");
          if (!drop || !input) return;
          drop.addEventListener("click", function () { input.click(); });
          drop.addEventListener("keydown", function (e) {
            if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); }
          });
          input.addEventListener("change", function () { uploadFiles(input.files); input.value = ""; });
          ["dragenter", "dragover"].forEach(function (ev) {
            drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add("is-over"); });
          });
          ["dragleave", "drop"].forEach(function (ev) {
            drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.remove("is-over"); });
          });
          drop.addEventListener("drop", function (e) { uploadFiles(e.dataTransfer.files); });
          document.getElementById("rf-pick").addEventListener("click", function () {
            mediaPicker(function (url) { addImage(url); });
          });
        }());
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
          var images = galleryImages.slice(0, 10);
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
          '<div class="full"><label for="hc-size">Model size — ' +
          '<output id="hc-size-out">' + Math.round((hero.size != null ? hero.size : 1) * 100) + "%</output></label>" +
          '<input type="range" id="hc-size" step="0.05" min="' + d.heroRanges.size[0] + '" max="' +
          d.heroRanges.size[1] + '" value="' + esc(hero.size != null ? hero.size : 1) + '">' +
          '<span class="field-help">How much of the hero area the model fills. ' +
          "<b>100% is the largest the model can be and still never touch an edge at any rotation</b>, " +
          "whatever model is uploaded. Above that it keeps growing in proportion — 130% draws it about " +
          "a third larger — but the safe headroom depends on the shape of the model, so raise it a step " +
          'at a time and drag the hero right around to check.<span id="hc-size-warn"></span></span></div>' +
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
        (function () {
          var range = document.getElementById("hc-size");
          var out = document.getElementById("hc-size-out");
          if (range && out) {
            var warn = document.getElementById("hc-size-warn");
            function show() {
              var v = parseFloat(range.value);
              out.textContent = Math.round(v * 100) + "%";
              warn.innerHTML = v > 1
                ? '<br><b style="color:var(--adm-warn)">Above the guaranteed size</b> — ' +
                  "check the homepage at this setting, including on a phone, before leaving it."
                : "";
            }
            range.addEventListener("input", show);
            show();
          }
        }());
        document.getElementById("hero-form").addEventListener("submit", function (e) {
          e.preventDefault();
          api("/api/admin/hero", { values: {
            size: parseFloat(document.getElementById("hc-size").value),
            camz: document.getElementById("hc-camz").value,
            camy: document.getElementById("hc-camy").value,
            fov: document.getElementById("hc-fov").value
          } }).then(function (r2) {
            r2.ok ? toast("Camera saved — reload the homepage to see it.") : apiErr(r2);
          });
        });
      });
    },

    editor: function (param) {
      if (param) edState.page = param;
      var VIEWPORTS = { desktop: 1440, tablet: 834, mobile: 390 };
      var SHADOWS = { soft: "0 8px 30px rgba(8,10,18,0.35)", strong: "0 20px 60px rgba(8,10,18,0.5)",
                      glow: "0 0 34px rgba(237,108,38,0.45)", none: "none" };
      var ANIMS = ["fade-up", "fade-in", "slide-left", "slide-right", "zoom", "zoom-up",
                   "mask-title", "blur-in", "rise"];
      var st = edState;
      function bp() { return st.vw === "desktop" ? "base" : st.vw; }
      function isGlobalPath(path) {
        return path.indexOf("header.site-header") === 0 || path.indexOf("footer.site-footer") === 0;
      }
      function docFor(path, forceScope) {
        var scope = forceScope || (isGlobalPath(path) && !st.pageScopeOnly ? "global" : "page");
        return scope === "global" ? st.globalDoc : st.pageDoc;
      }
      function specOf(doc, path, create) {
        if (!doc.elements[path] && create) doc.elements[path] = {};
        return doc.elements[path] || {};
      }
      function markTouched(doc) {
        if (doc === st.globalDoc) st.docTouched.global = true; else st.docTouched.page = true;
      }
      function mergedElements() {
        var out = {};
        [st.globalDoc, st.pageDoc].forEach(function (doc) {
          Object.keys(doc.elements).forEach(function (path) {
            var spec = doc.elements[path];
            var t = (out[path] = out[path] || {});
            Object.keys(spec.styles || {}).forEach(function (b) {
              t.styles = t.styles || {};
              t.styles[b] = Object.assign({}, t.styles[b] || {}, spec.styles[b]);
            });
            if (spec.attrs) t.attrs = Object.assign({}, t.attrs || {}, spec.attrs);
            if (spec.text) t.text = spec.text;
            if (spec.hidden) t.hidden = Object.assign({}, t.hidden || {}, spec.hidden);
            if (spec.anim) t.anim = spec.anim;
          });
        });
        return out;
      }
      function buildCss(elements) {
        var media = { tablet: "@media (max-width: 1024px)", mobile: "@media (max-width: 640px)" };
        var hideMedia = { base: "@media (min-width: 1025px)",
                          tablet: "@media (min-width: 641px) and (max-width: 1024px)",
                          mobile: "@media (max-width: 640px)" };
        var buckets = { base: [], tablet: [], mobile: [] };
        var hides = { base: [], tablet: [], mobile: [] };
        Object.keys(elements).forEach(function (path) {
          var spec = elements[path];
          Object.keys(spec.styles || {}).forEach(function (b) {
            var props = spec.styles[b];
            var decls = "";
            Object.keys(props).forEach(function (prop) {
              if (!props[prop]) return;
              decls += prop === "background-image"
                ? "background-image:url('" + props[prop] + "') !important;"
                : prop + ":" + props[prop] + " !important;";
            });
            if (decls) buckets[b].push(path + "{" + decls + "}");
          });
          Object.keys(spec.hidden || {}).forEach(function (b) {
            if (spec.hidden[b]) hides[b].push(path + "{display:none !important;}");
          });
        });
        var css = buckets.base.join("\n");
        ["tablet", "mobile"].forEach(function (b) {
          if (buckets[b].length) css += "\n" + media[b] + "{\n" + buckets[b].join("\n") + "\n}";
        });
        ["base", "tablet", "mobile"].forEach(function (b) {
          if (hides[b].length) css += "\n" + hideMedia[b] + "{\n" + hides[b].join("\n") + "\n}";
        });
        return css;
      }
      function applyLive() {
        if (!st.postFrame) return;
        var elements = mergedElements();
        var attrs = [];
        Object.keys(st.touchedAttrPaths).forEach(function (path) {
          var current = (elements[path] || {}).attrs || {};
          var set = {};
          Object.keys(st.touchedAttrPaths[path]).forEach(function (name) {
            set[name] = current[name] || null;
          });
          attrs.push({ path: path, set: set });
        });
        var anims = [];
        Object.keys(st.touchedAnimPaths).forEach(function (path) {
          var a = (elements[path] || {}).anim;
          anims.push(a ? { path: path, type: a.type, delay: a.delay || 0 }
                       : { path: path, type: "keep" });
        });
        var texts = Object.keys(st.changedText).map(function (key) {
          var f = st.fields[key] || {};
          return { key: key, html: richHtml(st.changedText[key] || f.original || "") };
        });
        var pathTexts = Object.keys(st.touchedTextPaths).map(function (path) {
          return { path: path, html: (elements[path] || {}).text || "" };
        });
        var sections = Object.assign({}, st.pageDoc.sections || {});
        sections.added = (sections.added || []).map(function (item) {
          return { id: item.id, template: item.template,
                   html: (st.blockHtml[item.template] || "").replace(/__ID__/g, item.id) };
        });
        st.postFrame({ type: "em-apply", css: buildCss(elements), attrs: attrs,
                       anims: anims, sections: sections, texts: texts, pathTexts: pathTexts });
        refreshDirty();
      }
      function snapshot() {
        return JSON.stringify({ t: st.changedText, p: st.pageDoc, g: st.globalDoc,
                                d: st.docTouched, a: st.touchedAttrPaths, n: st.touchedAnimPaths,
                                x: st.touchedTextPaths });
      }
      function restore(snap) {
        var s = JSON.parse(snap);
        st.changedText = s.t; st.pageDoc = s.p; st.globalDoc = s.g;
        st.docTouched = s.d; st.touchedAttrPaths = s.a; st.touchedAnimPaths = s.n;
        st.touchedTextPaths = s.x || {};
        reloadFrame();
      }
      function pushUndo() {
        st.undo.push(snapshot());
        if (st.undo.length > 60) st.undo.shift();
        st.redo = [];
        refreshDirty();
      }
      function reloadFrame() {
        var frame = document.getElementById("ed-frame");
        if (frame) frame.src = "/admin/visual/" + encodeURIComponent(st.page) + "?lang=" + st.lang +
          "&t=" + Date.now();
      }
      function dirtyCount() {
        return Object.keys(st.changedText).length +
          (st.docTouched.page ? 1 : 0) + (st.docTouched.global ? 1 : 0);
      }
      function refreshDirty() {
        var el = document.getElementById("ed-dirty");
        if (!el) return;
        var n = dirtyCount();
        el.textContent = n ? "Unsaved changes" : "";
        document.getElementById("ed-save").disabled = !n;
        document.getElementById("ed-undo").disabled = !st.undo.length;
        document.getElementById("ed-redo").disabled = !st.redo.length;
      }

      Promise.all([
        api("/api/admin/pages/" + st.page + "?lang=" + st.lang),
        api("/api/admin/pages/_global?lang=" + st.lang),
        api("/api/admin/pages"),
        api("/api/admin/design/" + st.page),
        api("/api/admin/blocks")
      ]).then(function (rs) {
        var bad = rs.find(function (r) { return !r.ok; });
        if (bad) return apiErr(bad);
        st.fields = {};
        rs[0].data.regions.concat(rs[0].data.seo).forEach(function (f) {
          st.fields[f.key] = { label: f.label, kind: f.kind, original: f.original,
                               value: f.value, scope: st.page };
        });
        rs[1].data.regions.forEach(function (f) {
          st.fields[f.key] = { label: f.label, kind: f.kind, original: f.original,
                               value: f.value, scope: "_global" };
        });
        st.pageDoc = rs[3].data.doc && rs[3].data.doc.elements
          ? rs[3].data.doc : { elements: {}, sections: {} };
        if (!st.pageDoc.sections) st.pageDoc.sections = {};
        st.globalDoc = rs[3].data.globalDoc && rs[3].data.globalDoc.elements
          ? rs[3].data.globalDoc : { elements: {}, sections: {} };
        st.docTouched = { page: false, global: false };
        st.touchedAttrPaths = {}; st.touchedAnimPaths = {}; st.touchedTextPaths = {};
        st.changedText = {}; st.undo = []; st.redo = []; st.sel = null;
        st.blocks = (rs[4].data && rs[4].data.blocks) || [];
        st.maxBlocks = (rs[4].data && rs[4].data.max) || 30;
        st.blockHtml = {}; st.blockLabel = {};
        st.blocks.forEach(function (b) {
          st.blockHtml[b.id] = b.html;
          st.blockLabel[b.id] = b.label;
        });

        st.pageList = rs[2].data.pages;
        var pageOpts = rs[2].data.pages
          .map(function (p) {
            return '<option value="' + esc(p.page) + '"' + (p.page === st.page ? " selected" : "") + ">" +
                   esc(p.label) + "</option>";
          }).join("");
        main.innerHTML =
          '<div class="ed-toolbar">' +
          '<select id="ed-page">' + pageOpts + "</select>" +
          '<span class="ed-group">' +
          '<button class="btn btn--small ' + (st.lang === "en" ? "btn--primary" : "btn--ghost") + '" data-edlang="en">EN</button>' +
          '<button class="btn btn--small ' + (st.lang === "ar" ? "btn--primary" : "btn--ghost") + '" data-edlang="ar">AR</button></span>' +
          '<span class="ed-group">' + Object.keys(VIEWPORTS).map(function (v) {
            var labels = { desktop: "🖥 Desktop", tablet: "📱 Tablet", mobile: "📱 Mobile" };
            return '<button class="btn btn--small ' + (st.vw === v ? "btn--primary" : "btn--ghost") + '" data-edvw="' + v + '">' + labels[v] + "</button>";
          }).join("") + "</span>" +
          '<label class="ed-outline-toggle"><input type="checkbox" id="ed-outlines"' + (st.outlines ? " checked" : "") + "> Outlines</label>" +
          '<button class="btn btn--ghost btn--small" id="ed-sections-btn">Sections</button>' +
          '<span class="ed-group"><button class="btn btn--ghost btn--small" id="ed-undo" disabled title="Undo (Ctrl+Z)">↺</button>' +
          '<button class="btn btn--ghost btn--small" id="ed-redo" disabled title="Redo (Ctrl+Shift+Z)">↻</button></span>' +
          '<span class="admin-inline-note" id="ed-dirty"></span>' +
          '<span class="ed-spacer"></span>' +
          '<span class="admin-inline-note" id="ed-bp-note">Styling: ' + esc(st.vw) + "</span>" +
          '<button class="btn btn--ghost btn--small" id="ed-save" disabled>Save draft</button>' +
          '<button class="btn btn--primary btn--small" id="ed-publish">Publish site</button>' +
          "</div>" +
          '<div class="ed-body"><div class="ed-canvas" id="ed-canvas"><div class="ed-frame-wrap" id="ed-wrap">' +
          '<iframe id="ed-frame" src="/admin/visual/' + esc(st.page) + "?lang=" + st.lang + '" title="Page preview"></iframe>' +
          "</div></div>" +
          '<aside class="ed-panel" id="ed-panel"><p class="admin-inline-note">Click anything in the page to edit it — any heading, paragraph, button label, card title or caption, plus images, colours, spacing and animation. <b>Sections</b> adds new blocks and reorders, hides or deletes the ones already there.</p></aside></div>' +
          '<div class="picker-overlay" id="ed-picker" hidden><div class="picker-box">' +
          '<div class="picker-head"><h2>Choose an image</h2><button class="btn btn--ghost btn--small" id="picker-close">Close</button></div>' +
          '<div class="picker-grid" id="picker-grid"></div></div></div>';

        var frame = document.getElementById("ed-frame");
        var wrap = document.getElementById("ed-wrap");
        var canvas = document.getElementById("ed-canvas");
        st.postFrame = function (msg) {
          if (frame.contentWindow) frame.contentWindow.postMessage(msg, location.origin);
        };

        function fit() {
          var w = VIEWPORTS[st.vw];
          var k = Math.min(1, (canvas.clientWidth - 20) / w);
          frame.style.width = w + "px";
          frame.style.height = Math.max(400, (canvas.clientHeight - 20) / k) + "px";
          wrap.style.transform = "scale(" + k + ")";
          wrap.style.width = w + "px";
        }
        fit();
        window.addEventListener("resize", fit);

        st.onReady = function (data) {
          st.sections = data.sections || [];
          st.postFrame({ type: "em-outlines", on: st.outlines });
          applyLive();
          if (st.sel) st.postFrame({ type: "em-focus", path: st.sel.path });
        };

        /* ---------- media picker ---------- */
        function openPicker(cb) {
          var overlay = document.getElementById("ed-picker");
          var grid = document.getElementById("picker-grid");
          grid.innerHTML = '<p class="admin-inline-note">Loading…</p>';
          overlay.hidden = false;
          api("/api/admin/media").then(function (r) {
            if (!r.ok) return apiErr(r);
            var lib = (r.data.library || []).map(function (m) {
              return { url: "/media/" + m.file, label: m.name };
            });
            var assets = (r.data.siteAssets || []).filter(function (a) {
              return a.ext !== "glb" && a.ext !== "svg";
            }).map(function (a) { return { url: "/" + a.path, label: a.path.replace("assets/", "") }; });
            grid.innerHTML = lib.concat(assets).map(function (it) {
              return '<button class="picker-item" data-url="' + esc(it.url) + '">' +
                '<img src="' + esc(it.url) + '" alt="" loading="lazy"><span>' + esc(it.label) + "</span></button>";
            }).join("") || '<p class="admin-inline-note">No images yet — upload in Media.</p>';
            grid.querySelectorAll(".picker-item").forEach(function (btn) {
              btn.addEventListener("click", function () {
                overlay.hidden = true;
                cb(btn.getAttribute("data-url"));
              });
            });
          });
        }
        document.getElementById("picker-close").addEventListener("click", function () {
          document.getElementById("ed-picker").hidden = true;
        });

        /* ---------- selection panel ---------- */
        function rgbToHex(c) {
          var m = /rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(c || "");
          if (!m) return "#000000";
          return "#" + [m[1], m[2], m[3]].map(function (x) {
            return ("0" + parseInt(x, 10).toString(16)).slice(-2);
          }).join("");
        }
        function styleVal(path, prop) {
          var spec = specOf(docFor(path), path, false);
          return spec.styles && spec.styles[bp()] ? spec.styles[bp()][prop] || "" : "";
        }
        function setStyle(path, prop, value) {
          pushUndo();
          var doc = docFor(path);
          var spec = specOf(doc, path, true);
          spec.styles = spec.styles || {};
          spec.styles[bp()] = spec.styles[bp()] || {};
          if (value) spec.styles[bp()][prop] = value;
          else delete spec.styles[bp()][prop];
          markTouched(doc);
          applyLive();
        }
        function setAttr(path, name, value) {
          pushUndo();
          var doc = docFor(path);
          var spec = specOf(doc, path, true);
          spec.attrs = spec.attrs || {};
          if (value) spec.attrs[name] = value; else delete spec.attrs[name];
          (st.touchedAttrPaths[path] = st.touchedAttrPaths[path] || {})[name] = true;
          markTouched(doc);
          applyLive();
        }
        function setAnim(path, type, delay) {
          pushUndo();
          var doc = docFor(path);
          var spec = specOf(doc, path, true);
          if (!type) delete spec.anim;
          else spec.anim = { type: type, delay: delay | 0 };
          st.touchedAnimPaths[path] = true;
          markTouched(doc);
          applyLive();
        }
        function setText(path, html) {
          pushUndo();
          var doc = docFor(path);
          var spec = specOf(doc, path, true);
          if (html) spec.text = html; else delete spec.text;
          st.touchedTextPaths[path] = true;
          markTouched(doc);
          applyLive();
        }
        function setHidden(path, b, on) {
          pushUndo();
          var doc = docFor(path);
          var spec = specOf(doc, path, true);
          spec.hidden = spec.hidden || {};
          if (on) spec.hidden[b] = true; else delete spec.hidden[b];
          markTouched(doc);
          applyLive();
        }

        function textInput(id, value, placeholder) {
          return '<input id="' + id + '" value="' + esc(value) + '" placeholder="' + esc(placeholder || "") + '">';
        }
        function selectInput(id, options, current) {
          return '<select id="' + id + '">' + options.map(function (o) {
            return '<option value="' + esc(o[0]) + '"' + (o[0] === current ? " selected" : "") + ">" + esc(o[1]) + "</option>";
          }).join("") + "</select>";
        }
        function group(title, inner, open) {
          return "<details" + (open ? " open" : "") + "><summary>" + esc(title) + "</summary>" +
                 '<div class="ed-fields">' + inner + "</div></details>";
        }
        function bindStyle(id, path, prop, transform) {
          var el = document.getElementById(id);
          if (!el) return;
          el.addEventListener("change", function () {
            setStyle(path, prop, transform ? transform(el.value) : el.value.trim());
          });
        }

        st.onSelect = function (meta) {
          st.sel = meta;
          var path = meta.path;
          var c = meta.computed;
          var panel = document.getElementById("ed-panel");
          var globalEl = isGlobalPath(path);
          st.pageScopeOnly = false;
          var spec = specOf(docFor(path), path, false);
          var attrs = spec.attrs || {};
          var anim = spec.anim || null;
          var hidden = (specOf(st.pageDoc, path, false).hidden || {});
          if (globalEl) hidden = Object.assign({}, specOf(st.globalDoc, path, false).hidden || {}, hidden);
          var f = meta.emKey ? st.fields[meta.emKey] : null;

          var content = "";
          if (!f && meta.textEditable) {
            var pathText = spec.text || "";
            content = group("Content — " + meta.tag,
              '<div class="rich-bar" data-rich="path">' +
              '<button type="button" data-rt="strong" title="Bold"><b>B</b></button>' +
              '<button type="button" data-rt="em" title="Italic"><i>I</i></button>' +
              '<button type="button" data-rt="a" title="Link">🔗</button>' +
              '<button type="button" data-rt="br" title="Line break">↵</button></div>' +
              '<textarea id="ed-ptext" rows="4" maxlength="2000">' +
              esc(pathText || meta.textHtml) + "</textarea>" +
              '<span class="admin-inline-note">Type over the words to change them. ' +
              "Empty puts the original text back.</span>" +
              '<div class="admin-actions"><button class="btn btn--ghost btn--small" id="ed-ptext-revert">Use original</button></div>',
              true);
          }
          if (f) {
            var currentText = meta.emKey in st.changedText ? st.changedText[meta.emKey] : (f.value || f.original);
            content = group("Content — " + f.label,
              '<div class="rich-bar">' +
              '<button type="button" data-rt="strong" title="Bold"><b>B</b></button>' +
              '<button type="button" data-rt="em" title="Italic"><i>I</i></button>' +
              '<button type="button" data-rt="a" title="Link">🔗</button>' +
              '<button type="button" data-rt="li" title="List item">• List</button>' +
              '<button type="button" data-rt="br" title="Line break">↵</button></div>' +
              '<textarea id="ed-text" rows="4" maxlength="2000">' + esc(currentText) + "</textarea>" +
              '<span class="admin-inline-note">Original: ' + esc(f.original || "—") + "</span>" +
              '<div class="admin-actions"><button class="btn btn--ghost btn--small" id="ed-text-revert">Use original</button></div>', true);
          }
          var media = "";
          if (meta.isImg) {
            media = group("Image",
              '<img class="ed-thumb" src="' + esc(attrs.src || meta.attrs.src) + '" alt="">' +
              '<div class="admin-actions"><button class="btn btn--ghost btn--small" id="ed-img-replace">Replace…</button>' +
              (attrs.src ? '<button class="btn btn--ghost btn--small" id="ed-img-reset">Reset</button>' : "") + "</div>" +
              "<label>Alt text</label>" + textInput("ed-alt", attrs.alt || meta.attrs.alt, "describe the image"), true);
          } else if (meta.hasBg) {
            media = group("Background image",
              '<span class="admin-inline-note">' + esc((styleVal(path, "background-image") || c.backgroundImage).slice(0, 60)) + "</span>" +
              '<div class="admin-actions"><button class="btn btn--ghost btn--small" id="ed-bg-replace">Replace…</button>' +
              (styleVal(path, "background-image") ? '<button class="btn btn--ghost btn--small" id="ed-bg-reset">Reset</button>' : "") + "</div>");
          }
          var link = meta.isLink
            ? group("Link", "<label>Target (URL or /page.html)</label>" +
                textInput("ed-href", attrs.href || meta.attrs.href, "/contact.html"))
            : "";
          var currentAnim = anim ? anim.type : "";
          var animGroup = group("Animation",
            "<label>Effect</label>" +
            selectInput("ed-anim",
              [["", meta.attrs.reveal ? "Keep original (" + meta.attrs.reveal + ")" : "Keep original (none)"],
               ["none", "No animation"]].concat(ANIMS.map(function (a) { return [a, a]; })),
              currentAnim) +
            "<label>Delay (ms, 0–420)</label>" +
            textInput("ed-anim-delay", anim && anim.delay ? String(anim.delay) : "", meta.attrs.revealDelay || "0") +
            '<div class="admin-actions"><button class="btn btn--ghost btn--small" id="ed-anim-play">▶ Play</button></div>');
          var typo = group("Typography",
            "<label>Size</label>" + textInput("ed-fs", styleVal(path, "font-size"), c.fontSize) +
            "<label>Weight</label>" + selectInput("ed-fw",
              [["", "Default (" + c.fontWeight + ")"], ["300", "300"], ["400", "400"], ["500", "500"],
               ["600", "600"], ["700", "700"], ["800", "800"]], styleVal(path, "font-weight")) +
            "<label>Align</label>" + selectInput("ed-ta",
              [["", "Default"], ["left", "Left"], ["center", "Center"], ["right", "Right"]],
              styleVal(path, "text-align")) +
            "<label>Transform</label>" + selectInput("ed-tt",
              [["", "Default"], ["none", "none"], ["uppercase", "UPPERCASE"], ["capitalize", "Capitalize"]],
              styleVal(path, "text-transform")) +
            '<label>Text colour</label><span class="ed-color"><input type="color" id="ed-color" value="' +
            esc(styleVal(path, "color") || rgbToHex(c.color)) + '">' +
            '<button class="btn btn--ghost btn--small" id="ed-color-clear">Clear</button></span>');
          var box = group("Background & border",
            '<label>Background colour</label><span class="ed-color"><input type="color" id="ed-bgc" value="' +
            esc(styleVal(path, "background-color") || rgbToHex(c.backgroundColor)) + '">' +
            '<button class="btn btn--ghost btn--small" id="ed-bgc-clear">Clear</button></span>' +
            "<label>Border width</label>" + textInput("ed-bw", styleVal(path, "border-width"), c.borderWidth) +
            "<label>Border style</label>" + selectInput("ed-bs",
              [["", "Default"], ["none", "none"], ["solid", "solid"], ["dashed", "dashed"]],
              styleVal(path, "border-style")) +
            '<label>Border colour</label><span class="ed-color"><input type="color" id="ed-bc" value="' +
            esc(styleVal(path, "border-color") || rgbToHex(c.borderColor)) + '">' +
            '<button class="btn btn--ghost btn--small" id="ed-bc-clear">Clear</button></span>' +
            "<label>Corner radius</label>" + textInput("ed-br", styleVal(path, "border-radius"), c.borderRadius) +
            "<label>Shadow</label>" + selectInput("ed-sh",
              [["", "Default"], ["none", "None"], [SHADOWS.soft, "Soft"], [SHADOWS.strong, "Strong"],
               [SHADOWS.glow, "Orange glow"]], styleVal(path, "box-shadow")) +
            "<label>Opacity (0–1)</label>" + textInput("ed-op", styleVal(path, "opacity"), c.opacity));
          var space = group("Spacing & size",
            "<label>Margin (e.g. 10px or 10px 20px)</label>" + textInput("ed-mg", styleVal(path, "margin"), c.margin) +
            "<label>Padding</label>" + textInput("ed-pd", styleVal(path, "padding"), c.padding) +
            "<label>Width</label>" + textInput("ed-w", styleVal(path, "width"), c.width) +
            "<label>Max width</label>" + textInput("ed-mw", styleVal(path, "max-width"), c.maxWidth) +
            "<label>Height</label>" + textInput("ed-h", styleVal(path, "height"), c.height));
          var vis = group("Visibility",
            ["base", "tablet", "mobile"].map(function (b) {
              var labels = { base: "Hide on desktop", tablet: "Hide on tablet", mobile: "Hide on mobile" };
              return '<label class="ed-check"><input type="checkbox" data-hide="' + b + '"' +
                (hidden[b] ? " checked" : "") + "> " + labels[b] + "</label>";
            }).join(""));
          panel.innerHTML =
            '<div class="ed-sel-head"><span class="chip">' + esc(meta.tag) + "</span>" +
            (globalEl ? '<span class="chip chip--violet">site-wide</span>' : "") +
            '<button class="btn btn--ghost btn--small" id="ed-parent">Select parent</button></div>' +
            (globalEl ? '<label class="ed-check" style="margin-bottom:10px;"><input type="checkbox" id="ed-scope-page"> Apply changes to this page only</label>' : "") +
            content + media + link + typo + box + space + animGroup + vis +
            '<div class="admin-actions" style="margin-top:14px;"><button class="btn btn--ghost btn--small" id="ed-el-reset">Reset this element</button></div>' +
            '<p class="admin-inline-note" style="margin-top:8px;">Style edits apply to the <b>' + esc(st.vw) + "</b> view" +
            (st.vw === "desktop" ? " (and smaller screens unless they override)" : "") + ".</p>";

          document.getElementById("ed-parent").addEventListener("click", function () {
            st.postFrame({ type: "em-select-parent" });
          });
          var scopeCb = document.getElementById("ed-scope-page");
          if (scopeCb) scopeCb.addEventListener("change", function () {
            st.pageScopeOnly = scopeCb.checked;
          });
          if (f) {
            var ta = document.getElementById("ed-text");
            function pushText() {
              st.changedText[meta.emKey] = ta.value;
              st.postFrame({ type: "em-update", key: meta.emKey,
                             html: richHtml(ta.value || f.original) });
              refreshDirty();
            }
            ta.addEventListener("input", pushText);
            panel.querySelectorAll("[data-rt]").forEach(function (btn) {
              btn.addEventListener("click", function () {
                var tag = btn.getAttribute("data-rt");
                var s = ta.selectionStart, e = ta.selectionEnd;
                var sel = ta.value.slice(s, e);
                var ins;
                if (tag === "br") ins = "<br>";
                else if (tag === "a") {
                  var url = prompt("Link to (URL or /page.html):", "https://");
                  if (!url) return;
                  ins = '<a href="' + url.trim() + '">' + (sel || "link text") + "</a>";
                } else if (tag === "li") ins = "<ul><li>" + (sel || "item") + "</li></ul>";
                else ins = "<" + tag + ">" + (sel || "text") + "</" + tag + ">";
                ta.setRangeText(ins, s, e, "end");
                ta.focus();
                pushText();
              });
            });
            document.getElementById("ed-text-revert").addEventListener("click", function () {
              ta.value = "";
              st.changedText[meta.emKey] = "";
              st.postFrame({ type: "em-update", key: meta.emKey, html: richHtml(f.original) });
              refreshDirty();
            });
          }
          var pta = document.getElementById("ed-ptext");
          if (pta) {
            var ptTimer = null;
            function pushPathText() {
              clearTimeout(ptTimer);
              ptTimer = setTimeout(function () { setText(path, pta.value.trim()); }, 300);
              st.postFrame({ type: "em-apply", pathTexts: [{ path: path, html: pta.value.trim() }] });
            }
            pta.addEventListener("input", pushPathText);
            panel.querySelectorAll('[data-rich="path"] [data-rt]').forEach(function (btn) {
              btn.addEventListener("click", function () {
                var tag = btn.getAttribute("data-rt");
                var a = pta.selectionStart, b = pta.selectionEnd, sel = pta.value.slice(a, b);
                var ins;
                if (tag === "br") ins = "<br>";
                else if (tag === "a") {
                  var url = prompt("Link to (URL or /page.html):", "https://");
                  if (!url) return;
                  ins = '<a href="' + url.trim() + '">' + (sel || "link text") + "</a>";
                } else ins = "<" + tag + ">" + (sel || "text") + "</" + tag + ">";
                pta.setRangeText(ins, a, b, "end");
                pta.focus();
                pushPathText();
              });
            });
            document.getElementById("ed-ptext-revert").addEventListener("click", function () {
              pta.value = "";
              setText(path, "");
            });
          }
          if (meta.isImg) {
            document.getElementById("ed-img-replace").addEventListener("click", function () {
              openPicker(function (url) { setAttr(path, "src", url); st.onSelect(meta); });
            });
            var imgReset = document.getElementById("ed-img-reset");
            if (imgReset) imgReset.addEventListener("click", function () {
              setAttr(path, "src", ""); st.onSelect(meta);
            });
            document.getElementById("ed-alt").addEventListener("change", function () {
              setAttr(path, "alt", this.value.trim());
            });
          }
          if (!meta.isImg && meta.hasBg) {
            document.getElementById("ed-bg-replace").addEventListener("click", function () {
              openPicker(function (url) { setStyle(path, "background-image", url); st.onSelect(meta); });
            });
            var bgReset = document.getElementById("ed-bg-reset");
            if (bgReset) bgReset.addEventListener("click", function () {
              setStyle(path, "background-image", ""); st.onSelect(meta);
            });
          }
          if (meta.isLink) {
            document.getElementById("ed-href").addEventListener("change", function () {
              setAttr(path, "href", this.value.trim());
            });
          }
          document.getElementById("ed-anim").addEventListener("change", function () {
            var delay = parseInt(document.getElementById("ed-anim-delay").value, 10) || 0;
            setAnim(path, this.value, delay);
          });
          document.getElementById("ed-anim-delay").addEventListener("change", function () {
            var type = document.getElementById("ed-anim").value;
            if (type) setAnim(path, type, parseInt(this.value, 10) || 0);
          });
          document.getElementById("ed-anim-play").addEventListener("click", function () {
            st.postFrame({ type: "em-play-anim", path: path });
          });
          bindStyle("ed-fs", path, "font-size");
          bindStyle("ed-fw", path, "font-weight");
          bindStyle("ed-ta", path, "text-align");
          bindStyle("ed-tt", path, "text-transform");
          bindStyle("ed-bw", path, "border-width");
          bindStyle("ed-bs", path, "border-style");
          bindStyle("ed-br", path, "border-radius");
          bindStyle("ed-sh", path, "box-shadow");
          bindStyle("ed-op", path, "opacity");
          bindStyle("ed-mg", path, "margin");
          bindStyle("ed-pd", path, "padding");
          bindStyle("ed-w", path, "width");
          bindStyle("ed-mw", path, "max-width");
          bindStyle("ed-h", path, "height");
          document.getElementById("ed-color").addEventListener("change", function () {
            setStyle(path, "color", this.value);
          });
          document.getElementById("ed-color-clear").addEventListener("click", function () {
            setStyle(path, "color", "");
          });
          document.getElementById("ed-bgc").addEventListener("change", function () {
            setStyle(path, "background-color", this.value);
          });
          document.getElementById("ed-bgc-clear").addEventListener("click", function () {
            setStyle(path, "background-color", "");
          });
          document.getElementById("ed-bc").addEventListener("change", function () {
            setStyle(path, "border-color", this.value);
          });
          document.getElementById("ed-bc-clear").addEventListener("click", function () {
            setStyle(path, "border-color", "");
          });
          panel.querySelectorAll("[data-hide]").forEach(function (cb) {
            cb.addEventListener("change", function () {
              setHidden(path, cb.getAttribute("data-hide"), cb.checked);
            });
          });
          document.getElementById("ed-el-reset").addEventListener("click", function () {
            pushUndo();
            delete st.pageDoc.elements[path];
            delete st.globalDoc.elements[path];
            st.docTouched = { page: true, global: true };
            reloadFrame();
            toast("Element reset — will apply after saving.");
          });
        };

        /* ---------- sections manager ---------- */
        function renderSections() {
          var panel = document.getElementById("ed-panel");
          var spec = st.pageDoc.sections || {};
          var added = spec.added || [];
          var known = st.sections.map(function (s) { return s.id; })
            .concat(added.map(function (a) { return a.id; }));
          var order = (spec.order && spec.order.length ? spec.order : known)
            .filter(function (id) { return known.indexOf(id) !== -1; });
          known.forEach(function (id) {
            if (order.indexOf(id) === -1) order.push(id);
          });
          var removed = spec.removed || [];
          var duplicated = spec.duplicated || [];
          var labels = {};
          st.sections.forEach(function (s) { labels[s.id] = s.label; });
          added.forEach(function (a) {
            labels[a.id] = (st.blockLabel[a.template] || "Block") + " (added)";
          });
          panel.innerHTML =
            "<h2>Page sections</h2>" +
            '<p class="admin-inline-note">Reorder, hide, duplicate or delete the big blocks of this page — and add new ones.</p>' +
            '<div class="sec-list">' + order.map(function (id, i) {
              var off = removed.indexOf(id) !== -1;
              var isAdded = added.some(function (a) { return a.id === id; });
              return '<div class="sec-item' + (off ? " sec-item--off" : "") + '" data-sec="' + esc(id) + '">' +
                "<span>" + esc(labels[id] || id) + "</span><span class=\"sec-btns\">" +
                '<button title="Move up" data-sec-up' + (i === 0 ? " disabled" : "") + ">↑</button>" +
                '<button title="Move down" data-sec-down' + (i === order.length - 1 ? " disabled" : "") + ">↓</button>" +
                '<button title="' + (off ? "Show" : "Hide") + '" data-sec-hide>' + (off ? "🚫" : "👁") + "</button>" +
                '<button title="Duplicate" data-sec-dup' + (duplicated.indexOf(id) !== -1 ? ' class="is-on"' : "") + ">⧉</button>" +
                (isAdded ? '<button title="Delete this added block" data-sec-del>🗑</button>' : "") +
                "</span></div>";
            }).join("") + "</div>" +
            '<div class="admin-actions" style="margin-top:12px;">' +
            '<button class="btn btn--primary btn--small" id="sec-add">+ Add section</button>' +
            '<button class="btn btn--ghost btn--small" id="sec-reset">Reset section layout</button></div>' +
            '<div id="sec-picker" hidden><h3 style="margin-top:18px;">Choose a block</h3>' +
            '<div class="block-list">' + st.blocks.map(function (b) {
              return '<button class="block-item" data-block="' + esc(b.id) + '">' +
                "<b>" + esc(b.label) + "</b><span>" + esc(b.hint) + "</span></button>";
            }).join("") + "</div></div>";
          function mutate(fn) {
            pushUndo();
            var s = st.pageDoc.sections = st.pageDoc.sections || {};
            s.order = order.slice();
            fn(s);
            st.docTouched.page = true;
            applyLive();
            renderSections();
          }
          panel.querySelectorAll(".sec-item").forEach(function (row) {
            var id = row.getAttribute("data-sec");
            row.querySelector("[data-sec-up]").addEventListener("click", function () {
              mutate(function (s) {
                var i = s.order.indexOf(id);
                if (i > 0) { s.order.splice(i, 1); s.order.splice(i - 1, 0, id); }
              });
            });
            row.querySelector("[data-sec-down]").addEventListener("click", function () {
              mutate(function (s) {
                var i = s.order.indexOf(id);
                if (i < s.order.length - 1) { s.order.splice(i, 1); s.order.splice(i + 1, 0, id); }
              });
            });
            row.querySelector("[data-sec-hide]").addEventListener("click", function () {
              mutate(function (s) {
                s.removed = s.removed || [];
                var i = s.removed.indexOf(id);
                if (i === -1) s.removed.push(id); else s.removed.splice(i, 1);
              });
            });
            row.querySelector("[data-sec-dup]").addEventListener("click", function () {
              mutate(function (s) {
                s.duplicated = s.duplicated || [];
                var i = s.duplicated.indexOf(id);
                if (i === -1) s.duplicated.push(id); else s.duplicated.splice(i, 1);
              });
            });
            var del = row.querySelector("[data-sec-del]");
            if (del) del.addEventListener("click", function () {
              if (!confirm("Delete this added block and everything written in it?")) return;
              mutate(function (s) {
                s.added = (s.added || []).filter(function (a) { return a.id !== id; });
                s.order = s.order.filter(function (x) { return x !== id; });
                s.removed = (s.removed || []).filter(function (x) { return x !== id; });
                s.duplicated = (s.duplicated || []).filter(function (x) { return x !== id; });
                // drop styles and text written into the block that is going away
                Object.keys(st.pageDoc.elements).forEach(function (path) {
                  if (path.indexOf("[data-em-sec=" + id + "]") === 0) delete st.pageDoc.elements[path];
                });
              });
            });
          });
          document.getElementById("sec-add").addEventListener("click", function () {
            var picker = document.getElementById("sec-picker");
            picker.hidden = !picker.hidden;
          });
          panel.querySelectorAll("[data-block]").forEach(function (btn) {
            btn.addEventListener("click", function () {
              var current = (st.pageDoc.sections || {}).added || [];
              if (current.length >= st.maxBlocks) {
                toast("That is the most blocks one page can hold.", true);
                return;
              }
              var used = current.map(function (a) { return parseInt(a.id.slice(1), 10); });
              var next = 1;
              while (used.indexOf(next) !== -1) next++;
              mutate(function (s) {
                s.added = current.concat([{ id: "a" + next, template: btn.getAttribute("data-block") }]);
                s.order = s.order.concat(["a" + next]);
              });
              toast("Block added at the bottom — use ↑ to move it.");
            });
          });
          document.getElementById("sec-reset").addEventListener("click", function () {
            pushUndo();
            st.pageDoc.sections = {};
            st.docTouched.page = true;
            applyLive();
            renderSections();
          });
        }
        document.getElementById("ed-sections-btn").addEventListener("click", renderSections);

        /* ---------- toolbar ---------- */
        function guardedSwitch(fn) {
          if (dirtyCount() && !confirm("You have unsaved changes — discard them?")) return;
          fn();
          views.editor();
        }
        document.getElementById("ed-page").addEventListener("change", function () {
          var v = this.value;
          guardedSwitch(function () { st.page = v; });
        });
        main.querySelectorAll("[data-edlang]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var v = btn.getAttribute("data-edlang");
            if (v !== st.lang) guardedSwitch(function () { st.lang = v; });
          });
        });
        main.querySelectorAll("[data-edvw]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            st.vw = btn.getAttribute("data-edvw");
            main.querySelectorAll("[data-edvw]").forEach(function (b) {
              b.className = "btn btn--small " + (b === btn ? "btn--primary" : "btn--ghost");
            });
            document.getElementById("ed-bp-note").textContent = "Styling: " + st.vw;
            fit();
            if (st.sel) st.onSelect(st.sel); // re-render panel for the new breakpoint
          });
        });
        document.getElementById("ed-outlines").addEventListener("change", function () {
          st.outlines = this.checked;
          st.postFrame({ type: "em-outlines", on: st.outlines });
        });
        document.getElementById("ed-undo").addEventListener("click", function () {
          if (!st.undo.length) return;
          st.redo.push(snapshot());
          restore(st.undo.pop());
        });
        document.getElementById("ed-redo").addEventListener("click", function () {
          if (!st.redo.length) return;
          st.undo.push(snapshot());
          restore(st.redo.pop());
        });
        document.addEventListener("keydown", function (e) {
          if (!document.getElementById("ed-frame")) return;
          if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
            e.preventDefault();
            document.getElementById(e.shiftKey ? "ed-redo" : "ed-undo").click();
          }
        });
        document.getElementById("ed-save").addEventListener("click", function () {
          var calls = [];
          var byScope = {};
          Object.keys(st.changedText).forEach(function (key) {
            var scope = st.fields[key] ? st.fields[key].scope : st.page;
            (byScope[scope] = byScope[scope] || {})[key] = st.changedText[key];
          });
          Object.keys(byScope).forEach(function (scope) {
            calls.push(api("/api/admin/pages/" + encodeURIComponent(scope),
                           { lang: st.lang, values: byScope[scope] }));
          });
          if (st.docTouched.page) {
            calls.push(api("/api/admin/design/" + encodeURIComponent(st.page), { doc: st.pageDoc }));
          }
          if (st.docTouched.global) {
            calls.push(api("/api/admin/design/_global", { doc: st.globalDoc }));
          }
          if (!calls.length) return;
          Promise.all(calls).then(function (results) {
            var bad = results.find(function (r) { return !r.ok; });
            if (bad) return apiErr(bad);
            Object.keys(st.changedText).forEach(function (key) {
              if (st.fields[key]) st.fields[key].value = st.changedText[key];
            });
            st.changedText = {};
            st.docTouched = { page: false, global: false };
            refreshDirty();
            toast("Draft saved — publish when you are ready.");
          });
        });
        document.getElementById("ed-publish").addEventListener("click", function () {
          if (dirtyCount()) { toast("Save your draft first.", true); return; }
          if (!confirm("Publish all pages to the live site now?")) return;
          api("/api/admin/pages-publish", {}).then(function (r2) {
            r2.ok ? toast("Published " + r2.data.pages + " pages — live now.") : apiErr(r2);
          });
        });
        refreshDirty();
      });
    },

    insights: function () {
      var rng = edInsightRange;
      var days = rng.days;
      function rangeQs() {
        return rng.start && rng.end
          ? "start=" + encodeURIComponent(rng.start) + "&end=" + encodeURIComponent(rng.end)
          : "days=" + rng.days;
      }
      api("/api/admin/insights?" + rangeQs()).then(function (r) {
        if (!r.ok) return apiErr(r);
        var d = r.data;
        var t = d.totals || {};
        var s = d.settings || {};

        function delta(v) {
          if (v === null || v === undefined) return "";
          var cls = v >= 0 ? "badge-ok" : "badge-bad";
          return ' <span class="' + cls + '" style="font-size:0.72rem;">' +
                 (v >= 0 ? "+" : "") + esc(v) + "%</span>";
        }
        function sparkline(series) {
          if (!series.length) return "";
          var w = 720, h = 150, pad = 4;
          var max = Math.max.apply(null, series.map(function (p) { return p.views; })) || 1;
          var step = series.length > 1 ? (w - pad * 2) / (series.length - 1) : 0;
          function pts(key) {
            return series.map(function (p, i) {
              var x = pad + i * step;
              var y = h - pad - (p[key] / max) * (h - pad * 2);
              return x.toFixed(1) + "," + y.toFixed(1);
            }).join(" ");
          }
          var line = pts("views");
          var area = line + " " + (pad + (series.length - 1) * step).toFixed(1) + "," + (h - pad) +
                     " " + pad + "," + (h - pad);
          return '<svg class="chart" viewBox="0 0 ' + w + " " + h + '" preserveAspectRatio="none" role="img" aria-label="Daily pageviews">' +
            '<defs><linearGradient id="cg" x1="0" y1="0" x2="0" y2="1">' +
            '<stop offset="0%" stop-color="var(--orange)" stop-opacity="0.45"/>' +
            '<stop offset="100%" stop-color="var(--orange)" stop-opacity="0.02"/></linearGradient></defs>' +
            '<polygon points="' + area + '" fill="url(#cg)"></polygon>' +
            '<polyline points="' + line + '" fill="none" stroke="var(--orange-2)" stroke-width="2.5" ' +
            'stroke-linejoin="round" stroke-linecap="round"></polyline>' +
            '<polyline points="' + pts("visitors") + '" fill="none" stroke="var(--violet-2)" ' +
            'stroke-width="2" stroke-dasharray="5 4"></polyline></svg>';
        }
        function barList(rows, empty, suffix) {
          if (!rows || !rows.length) return '<p class="admin-inline-note">' + esc(empty) + "</p>";
          var max = Math.max.apply(null, rows.map(function (x) { return x.count; })) || 1;
          return '<div class="bar-list">' + rows.map(function (x) {
            return '<div class="bar-row"><span class="bar-label" title="' + esc(x.label) + '">' +
              esc(x.label) + '</span><span class="bar-track"><span class="bar-fill" style="width:' +
              Math.max(2, Math.round(x.count / max * 100)) + '%"></span></span>' +
              '<span class="bar-num">' + esc(x.count) + esc(suffix || "") + "</span></div>";
          }).join("") + "</div>";
        }

        main.innerHTML =
          '<h1 class="admin-h1">Site Insights</h1>' +
          '<p class="admin-sub">Your own measurement — no cookies, no visitor profiles. Visitor counts use a key that changes every day, so nobody can be followed across days or identified.</p>' +
          '<div class="ins-toolbar">' +
          [7, 30, 90, 365].map(function (n) {
            var on = !rng.start && n === days;
            return '<button class="btn btn--small ' + (on ? "btn--primary" : "btn--ghost") +
              '" data-days="' + n + '">' + (n === 365 ? "12 months" : n + " days") + "</button>";
          }).join("") +
          '<span class="date-range"><label for="ins-from">From</label>' +
          '<input type="date" id="ins-from" value="' + esc(rng.start || d.start) + '" max="' + esc(d.end) + '">' +
          '<label for="ins-to">to</label>' +
          '<input type="date" id="ins-to" value="' + esc(rng.end || d.end) + '" max="' + esc(d.end) + '">' +
          '<button class="btn btn--ghost btn--small" id="ins-apply">Apply</button>' +
          (rng.start ? '<button class="btn btn--ghost btn--small" id="ins-clear">Clear</button>' : "") +
          "</span>" +
          '<span class="ed-spacer"></span>' +
          (s.enabled ? "" : '<span class="badge-bad">measurement is off</span> ') +
          '<button class="btn btn--ghost btn--small" id="ins-export">Download report ▾</button></div>' +
          ((d.alerts || []).length
            ? '<div class="admin-panel">' + d.alerts.map(function (a) {
                return '<p class="ins-alert ins-alert--' + esc(a.level) + '">' + esc(a.text) + "</p>";
              }).join("") + "</div>" : "") +
          '<div class="stat-row">' +
          '<div class="stat-card"><b>' + esc(t.views || 0) + delta(t.viewsChange) + "</b><span>Pageviews</span></div>" +
          '<div class="stat-card"><b>' + esc(t.visitors || 0) + delta(t.visitorsChange) + "</b><span>Visitors</span></div>" +
          '<div class="stat-card"><b>' + esc(t.sessions || 0) + "</b><span>Visits</span></div>" +
          '<div class="stat-card"><b>' + esc((d.funnel && d.funnel[2] ? d.funnel[2].count : 0)) + "</b><span>Enquiries sent</span></div>" +
          '<div class="stat-card"><b>' + esc(d.manualDownloads || 0) + "</b><span>Manuals downloaded</span></div></div>" +
          '<div class="admin-panel"><h2>Traffic</h2>' +
          (t.views ? sparkline(d.series || []) : '<p class="admin-inline-note">No visits recorded yet — the beacon starts counting as soon as people browse the site.</p>') +
          '<p class="admin-inline-note"><span class="key key--orange"></span> Pageviews &nbsp; <span class="key key--violet"></span> Visitors &nbsp;·&nbsp; ' +
          esc(d.start) + " → " + esc(d.end) + "</p></div>" +
          '<div class="ins-grid">' +
          '<div class="admin-panel"><h2>Top pages</h2>' + barList(d.topPages, "No pageviews yet.") + "</div>" +
          '<div class="admin-panel"><h2>Where visitors come from</h2>' + barList(d.referrers, "All visits are direct or unreferred so far.") + "</div>" +
          '<div class="admin-panel"><h2>Countries</h2>' + barList(d.countries, "Country data appears once the site runs behind Cloudflare.") + "</div>" +
          '<div class="admin-panel"><h2>Devices</h2>' + barList(d.devices, "No device data yet.") + "</div>" +
          '<div class="admin-panel"><h2>Landing pages</h2>' + barList(d.entryPages, "No sessions yet.") + "</div>" +
          '<div class="admin-panel"><h2>Last page seen</h2>' + barList(d.exitPages, "No sessions yet.") + "</div>" +
          "</div>" +
          '<div class="admin-panel"><h2>Catalog interest</h2><div class="ins-grid ins-grid--tight">' +
          "<div><h3 class=\"ins-h3\">Most viewed products</h3>" + barList(d.products, "No product pages viewed yet.") + "</div>" +
          "<div><h3 class=\"ins-h3\">What people searched for</h3>" + barList(d.searches, "No catalog searches yet.") + "</div>" +
          "<div><h3 class=\"ins-h3\">Filters used</h3>" + barList(d.filters, "No filters used yet.") + "</div>" +
          "</div></div>" +
          '<div class="admin-panel"><h2>From browsing to enquiry</h2><div class="funnel">' +
          (d.funnel || []).map(function (f, i) {
            var base = d.funnel[0].count;
            var rate = !base ? "—" : (i === 0 ? "starting point" : f.rate + "% of viewers");
            return '<div class="funnel-step"><b>' + esc(f.count) + "</b><span>" + esc(f.step) +
              '</span><span class="funnel-rate">' + esc(rate) + "</span></div>";
          }).join('<span class="funnel-arrow">→</span>') + "</div></div>" +
          '<div class="admin-panel"><h2>Speed experienced by real visitors</h2>' +
          ((d.vitals || []).length
            ? '<div class="stat-row">' + d.vitals.map(function (v) {
                var good = { LCP: 2500, CLS: 0.1, INP: 200, FCP: 1800, TTFB: 800 }[v.metric];
                var label = { LCP: "Main content shown", CLS: "Layout stability",
                              INP: "Response to taps", FCP: "First paint", TTFB: "Server response" }[v.metric];
                var value = v.metric === "CLS" ? v.p75 : Math.round(v.p75) + " ms";
                return '<div class="stat-card"><b>' + esc(value) +
                  (v.p75 <= good ? ' <span class="badge-ok" style="font-size:0.7rem;">good</span>'
                                 : ' <span class="badge-bad" style="font-size:0.7rem;">slow</span>') +
                  "</b><span>" + esc(label) + " (" + esc(v.metric) + ")</span></div>";
              }).join("") + "</div>" +
              (d.slowPages && d.slowPages.length
                ? "<h3 class=\"ins-h3\">Slowest pages (average main-content time)</h3>" +
                  barList(d.slowPages, "", " ms") : "")
            : '<p class="admin-inline-note">Speed data appears after a few real visits.</p>') + "</div>" +
          (d.canManage
            ? '<div class="admin-panel"><h2>Measurement settings</h2><form class="admin-form" id="ins-settings">' +
              '<div><label for="ins-enabled">First-party measurement</label><select id="ins-enabled">' +
              '<option value="on"' + (s.enabled ? " selected" : "") + ">On</option>" +
              '<option value="off"' + (s.enabled ? "" : " selected") + ">Off — collect nothing</option></select></div>" +
              '<div><label for="ins-ga4">Google Analytics 4 measurement id (optional)</label>' +
              '<input id="ins-ga4" maxlength="24" placeholder="G-XXXXXXXXXX" value="' + esc(s.ga4Id || "") + '"></div>' +
              '<div><label for="ins-retention">Keep raw events for (days)</label>' +
              '<input id="ins-retention" type="number" min="30" max="1000" value="' + esc(s.retentionDays || 400) + '"></div>' +
              '<div class="full admin-actions"><button class="btn btn--primary btn--small" type="submit">Save settings</button>' +
              '<span class="admin-inline-note">GA4 only loads for visitors when an id is set. ' +
              esc(d.totalEvents) + " events stored in total.</span></div></form></div>"
            : "");

        main.querySelectorAll("[data-days]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            edInsightRange = { days: parseInt(btn.getAttribute("data-days"), 10), start: "", end: "" };
            views.insights();
          });
        });
        document.getElementById("ins-apply").addEventListener("click", function () {
          var from = document.getElementById("ins-from").value;
          var to = document.getElementById("ins-to").value;
          if (!from || !to) { toast("Pick both dates.", true); return; }
          if (from > to) { var swap = from; from = to; to = swap; }
          edInsightRange = { days: rng.days, start: from, end: to };
          views.insights();
        });
        var clearBtn = document.getElementById("ins-clear");
        if (clearBtn) clearBtn.addEventListener("click", function () {
          edInsightRange = { days: 30, start: "", end: "" };
          views.insights();
        });
        document.getElementById("ins-export").addEventListener("click", function (e) {
          e.stopPropagation();
          showMenu(this, [
            { label: "PDF report (branded)", action: function () {
              location.href = "/api/admin/insights/export?format=pdf&" + rangeQs(); } },
            { label: "HTML report (share or print)", action: function () {
              location.href = "/api/admin/insights/export?format=html&" + rangeQs(); } },
            { label: "CSV (daily traffic)", action: function () {
              location.href = "/api/admin/insights/export?format=csv&" + rangeQs(); } }
          ]);
        });
        var form = document.getElementById("ins-settings");
        if (form) form.addEventListener("submit", function (e) {
          e.preventDefault();
          api("/api/admin/settings", { values: {
            "analytics.enabled": document.getElementById("ins-enabled").value === "on",
            "analytics.ga4Id": document.getElementById("ins-ga4").value.trim(),
            "analytics.retentionDays": parseInt(document.getElementById("ins-retention").value, 10) || 400
          } }).then(function (r2) {
            r2.ok ? (toast("Measurement settings saved."), views.insights()) : apiErr(r2);
          });
        });
      });
    },

    operations: function () {
      api("/api/admin/operations").then(function (r) {
        if (!r.ok) return apiErr(r);
        var d = r.data;
        var a = d.announcement || {};
        function localInput(ts) {
          if (!ts) return "";
          var dt = new Date(ts * 1000);
          var pad = function (n) { return (n < 10 ? "0" : "") + n; };
          return dt.getFullYear() + "-" + pad(dt.getMonth() + 1) + "-" + pad(dt.getDate()) +
                 "T" + pad(dt.getHours()) + ":" + pad(dt.getMinutes());
        }
        function toTs(value) {
          if (!value) return 0;
          var ms = new Date(value).getTime();
          return isNaN(ms) ? 0 : Math.round(ms / 1000);
        }
        main.innerHTML =
          '<h1 class="admin-h1">Operations</h1>' +
          '<p class="admin-sub">Backups, scheduled publishing, the announcement bar and a health check of the whole site.</p>' +
          '<div class="admin-panel"><h2>Security centre <span class="ops-score">' +
          esc(d.score) + "/" + esc(d.total) + " security checks passing" +
          (d.advisories ? " · " + esc(d.advisories) + " suggestion(s)" : "") + "</span></h2>" +
          '<div class="ops-checks">' + (d.checks || []).map(function (c) {
            return '<div class="ops-check ops-check--' + (c.ok ? "ok" : (c.weight === "info" ? "info" : "bad")) + '">' +
              '<span class="ops-dot">' + (c.ok ? "✓" : (c.weight === "info" ? "i" : "!")) + "</span>" +
              "<div><b>" + esc(c.label) + "</b><span>" + esc(c.detail) + "</span></div></div>";
          }).join("") + "</div>" +
          '<div class="stat-row" style="margin-top:18px;">' +
          '<div class="stat-card"><b>' + esc(d.users.active) + "</b><span>Active accounts</span></div>" +
          '<div class="stat-card"><b>' + esc(d.sessions) + "</b><span>Open sessions</span></div>" +
          '<div class="stat-card"><b>' + esc((d.failedLogins || []).length) + "</b><span>Failed sign-ins (7 days)</span></div>" +
          '<div class="stat-card"><b>' + esc(d.retention.submissions) + "</b><span>Days requests are kept</span></div></div>" +
          ((d.failedLogins || []).length
            ? '<div class="table-scroll"><table class="admin-table"><thead><tr><th>When</th><th>Account</th><th>Reason</th></tr></thead><tbody>' +
              d.failedLogins.map(function (f) {
                return '<tr><td class="muted">' + esc(when(f.ts)) + "</td><td>" + esc(f.email) +
                  '</td><td class="muted">' + esc(f.detail) + "</td></tr>";
              }).join("") + "</tbody></table></div>" : "") + "</div>" +

          '<div class="admin-panel"><h2>Backups</h2>' +
          '<p class="admin-inline-note" style="margin-bottom:12px;">A backup holds all page content, design changes, settings, rental items and media files. ' +
          'Customer submissions are deliberately excluded — they are encrypted personal data with their own retention rules. ' +
          (d.lastBackup ? "Last download: " + esc(when(d.lastBackup)) + "." : "No backup downloaded yet.") + "</p>" +
          '<div class="admin-actions" style="margin-top:0;"><a class="btn btn--primary btn--small" href="/api/admin/backup">Download backup</a></div>' +
          '<h3 class="ins-h3" style="margin-top:20px;">Restore from a backup</h3>' +
          '<form class="admin-form" id="restore-form">' +
          '<div><label for="rs-file">Backup file (.zip)</label><input type="file" id="rs-file" accept=".zip" required></div>' +
          '<div><label for="rs-confirm">Type RESTORE to confirm</label><input id="rs-confirm" placeholder="RESTORE" maxlength="10"></div>' +
          '<div class="full" id="rs-preview"></div>' +
          '<div class="full admin-actions"><button class="btn btn--ghost btn--small" type="button" id="rs-check">Check file</button>' +
          '<button class="btn btn--ghost btn--small" type="submit">Restore</button>' +
          '<span class="admin-inline-note">Restoring replaces current content, design and settings. Admin accounts and customer requests are untouched.</span></div></form></div>' +

          '<div class="admin-panel"><h2>Scheduled publishing</h2>' +
          '<p class="admin-inline-note" style="margin-bottom:12px;">' +
          (d.schedule && d.schedule.at
            ? "Publishing automatically on <b>" + esc(when(d.schedule.at)) + "</b> (set by " + esc(d.schedule.by) + ")."
            : "Nothing scheduled — publishing happens only when someone presses Publish.") +
          (d.lastPublish ? " Last publish: " + esc(when(d.lastPublish.ts)) + "." : "") + "</p>" +
          '<form class="admin-form" id="sched-form">' +
          '<div><label for="sc-at">Publish at</label><input type="datetime-local" id="sc-at" value="' +
          esc(localInput(d.schedule ? d.schedule.at : 0)) + '"></div>' +
          '<div class="full admin-actions"><button class="btn btn--primary btn--small" type="submit">Schedule publish</button>' +
          (d.schedule && d.schedule.at ? '<button class="btn btn--ghost btn--small" type="button" id="sc-clear">Cancel schedule</button>' : "") +
          '<span class="admin-inline-note">Your saved drafts go live at that moment — nothing publishes on its own otherwise.</span></div></form></div>' +

          '<div class="admin-panel"><h2>Announcement bar</h2>' +
          '<p class="admin-inline-note" style="margin-bottom:12px;">A dismissible strip at the top of every page — for Ramadan collections, event presence or opening hours.</p>' +
          '<form class="admin-form" id="ann-form">' +
          '<div><label for="an-enabled">Show the bar</label><select id="an-enabled">' +
          '<option value="off"' + (a["announce.enabled"] ? "" : " selected") + ">Off</option>" +
          '<option value="on"' + (a["announce.enabled"] ? " selected" : "") + ">On</option></select></div>" +
          '<div><label for="an-style">Style</label><select id="an-style">' +
          '<option value="brand"' + (a["announce.style"] === "quiet" ? "" : " selected") + ">Brand gradient</option>" +
          '<option value="quiet"' + (a["announce.style"] === "quiet" ? " selected" : "") + ">Quiet</option></select></div>" +
          '<div class="full"><label for="an-text">Message</label><input id="an-text" maxlength="200" value="' +
          esc(a["announce.text"] || "") + '" placeholder="Visit us at Cityscape, stand B21"></div>' +
          '<div><label for="an-link">Link (optional)</label><input id="an-link" maxlength="200" value="' +
          esc(a["announce.link"] || "") + '" placeholder="/contact.html"></div>' +
          '<div><label for="an-label">Link label</label><input id="an-label" maxlength="60" value="' +
          esc(a["announce.linkLabel"] || "") + '" placeholder="Book a meeting"></div>' +
          '<div><label for="an-from">Show from (optional)</label><input type="datetime-local" id="an-from" value="' +
          esc(localInput(a["announce.startsAt"])) + '"></div>' +
          '<div><label for="an-to">Show until (optional)</label><input type="datetime-local" id="an-to" value="' +
          esc(localInput(a["announce.endsAt"])) + '"></div>' +
          '<div class="full admin-actions"><button class="btn btn--primary btn--small" type="submit">Save announcement</button>' +
          '<a class="btn btn--ghost btn--small" href="/" target="_blank" rel="noopener">View site</a></div></form></div>' +

          '<div class="admin-panel"><h2>Languages</h2>' +
          '<p class="admin-inline-note" style="margin-bottom:12px;">English is always published. Turning Arabic on publishes a right-to-left Arabic edition at /ar/ and adds a language switch to the header — fill the Arabic text in Pages or the Visual editor first.</p>' +
          '<form class="admin-form" id="lang-form"><div><label for="lg-mode">Published languages</label>' +
          '<select id="lg-mode"><option value="en"' + (d.languages.indexOf("ar") === -1 ? " selected" : "") + ">English only</option>" +
          '<option value="en,ar"' + (d.languages.indexOf("ar") !== -1 ? " selected" : "") + ">English + Arabic</option></select></div>" +
          '<div class="full admin-actions"><button class="btn btn--primary btn--small" type="submit">Save languages</button>' +
          '<span class="admin-inline-note">Press Publish afterwards for the change to reach the live site.</span></div></form></div>';

        document.getElementById("rs-check").addEventListener("click", function () {
          var f = document.getElementById("rs-file").files[0];
          if (!f) { toast("Choose a backup file first.", true); return; }
          var fd = new FormData();
          fd.append("file", f);
          apiUpload("/api/admin/backup/inspect", fd).then(function (r2) {
            if (!r2.ok) return apiErr(r2);
            var c = r2.data.counts;
            document.getElementById("rs-preview").innerHTML =
              '<p class="admin-inline-note">Backup from <b>' + esc(r2.data.manifest.createdAtHuman) +
              "</b> — " + esc(c.content) + " content entries, " + esc(c.designs) + " design records, " +
              esc(c.rentals) + " rental items, " + esc(c.media) + " media files.</p>";
          });
        });
        document.getElementById("restore-form").addEventListener("submit", function (e) {
          e.preventDefault();
          var f = document.getElementById("rs-file").files[0];
          if (!f) { toast("Choose a backup file first.", true); return; }
          if (!confirm("Restore this backup? Current content, design and settings will be replaced.")) return;
          var fd = new FormData();
          fd.append("file", f);
          fd.append("confirm", document.getElementById("rs-confirm").value.trim());
          apiUpload("/api/admin/backup/restore", fd).then(function (r2) {
            r2.ok ? (toast("Backup restored — review the pages, then publish."), views.operations()) : apiErr(r2);
          });
        });
        document.getElementById("sched-form").addEventListener("submit", function (e) {
          e.preventDefault();
          var at = toTs(document.getElementById("sc-at").value);
          if (!at) { toast("Pick a date and time.", true); return; }
          api("/api/admin/schedule-publish", { at: at }).then(function (r2) {
            r2.ok ? (toast("Publishing scheduled."), views.operations()) : apiErr(r2);
          });
        });
        var scClear = document.getElementById("sc-clear");
        if (scClear) scClear.addEventListener("click", function () {
          api("/api/admin/schedule-publish", { at: 0 }).then(function (r2) {
            r2.ok ? (toast("Schedule cancelled."), views.operations()) : apiErr(r2);
          });
        });
        document.getElementById("ann-form").addEventListener("submit", function (e) {
          e.preventDefault();
          api("/api/admin/settings", { values: {
            "announce.enabled": document.getElementById("an-enabled").value === "on",
            "announce.text": document.getElementById("an-text").value.trim(),
            "announce.link": document.getElementById("an-link").value.trim(),
            "announce.linkLabel": document.getElementById("an-label").value.trim(),
            "announce.style": document.getElementById("an-style").value,
            "announce.startsAt": toTs(document.getElementById("an-from").value),
            "announce.endsAt": toTs(document.getElementById("an-to").value)
          } }).then(function (r2) {
            r2.ok ? (toast("Announcement saved."), views.operations()) : apiErr(r2);
          });
        });
        document.getElementById("lang-form").addEventListener("submit", function (e) {
          e.preventDefault();
          api("/api/admin/settings", { values: {
            "site.languages": document.getElementById("lg-mode").value.split(","),
            "site.defaultLanguage": "en"
          } }).then(function (r2) {
            r2.ok ? (toast("Languages saved — publish to apply."), views.operations()) : apiErr(r2);
          });
        });
      });
    },

    email: function () {
      api("/api/admin/email").then(function (r) {
        if (!r.ok) return apiErr(r);
        var d = r.data;
        var g = d.general || {};
        var forms = d.forms || [];
        if (!emailForm || !forms.some(function (f) { return f.key === emailForm; })) {
          emailForm = forms.length ? forms[0].key : "";
        }
        var current = forms.filter(function (f) { return f.key === emailForm; })[0] || {};
        var stats = d.stats || {};
        var pending = stats.pending || 0;
        var sending = stats.sending || 0;
        var failed = stats.failed || 0;
        function vars(list) {
          return (list || []).map(function (v) {
            return '<button type="button" class="var-chip" data-var="{{' + esc(v) + '}}">{{' + esc(v) + "}}</button>";
          }).join("");
        }
        main.innerHTML =
          '<h1 class="admin-h1">Email</h1>' +
          '<p class="admin-sub">Sender identity, where each form is delivered, and the confirmation your customers receive. ' +
          "The email service key lives on the server only — it is never shown or stored here.</p>" +
          (d.configured ? "" :
            '<p class="ins-alert ins-alert--warn">No email service key is configured on the server yet ' +
            "(RESEND_API_KEY). Settings can be prepared now; sending starts once the key is in place.</p>") +
          '<div class="stat-row stat-row--tight">' +
          '<div class="stat-card' + (pending ? " stat-card--warn" : "") + '"><b>' + esc(pending) +
          "</b><span>Pending</span></div>" +
          '<div class="stat-card"><b>' + esc(sending) + "</b><span>Sending</span></div>" +
          '<div class="stat-card"><b>' + esc(stats.sent || 0) + "</b><span>Sent</span></div>" +
          '<div class="stat-card' + (failed ? " stat-card--bad" : "") + '"><b>' + esc(failed) +
          "</b><span>Failed</span></div>" +
          '<div class="stat-card"><b>' + esc(stats.total || 0) + "</b><span>Total deliveries</span></div></div>" +
          (failed
            ? '<p class="ins-alert ins-alert--warn mail-health">\u26a0 <b>Email delivery attention required</b> — ' +
              esc(failed) + " email deliver" + (failed === 1 ? "y" : "ies") + " failed and require review" +
              (pending ? ", " + esc(pending) + " still waiting to send" : "") +
              ". Retry them under Recent deliveries below.</p>"
            : pending
              ? '<p class="ins-alert mail-health">' + esc(pending) + " email" + (pending === 1 ? " is" : "s are") +
                " waiting in the queue — the server sends them automatically.</p>"
              : '<p class="ins-alert ins-alert--good mail-health">\u2713 Email delivery is healthy.</p>') +

          '<div class="admin-panel"><h2>Sender &amp; branding</h2>' +
          '<form class="admin-form" id="em-general">' +
          '<div><label for="eg-name">From name</label><input id="eg-name" maxlength="80" value="' + esc(g.fromName || "") + '"></div>' +
          '<div><label for="eg-from">From email</label><input id="eg-from" maxlength="120" value="' + esc(g.fromEmail || "") + '">' +
          '<span class="admin-inline-note">Only verified domains are accepted: ' + esc((d.senderDomains || []).join(", ")) + "</span></div>" +
          '<div><label for="eg-reply">Reply-to email</label><input id="eg-reply" maxlength="120" value="' + esc(g.replyTo || "") + '"></div>' +
          '<div><label for="eg-contact">Contact email (shown in the footer)</label><input id="eg-contact" maxlength="120" value="' + esc(g.contactEmail || "") + '"></div>' +
          '<div><label for="eg-site">Website URL</label><input id="eg-site" maxlength="160" value="' + esc(g.websiteUrl || "") + '"></div>' +
          '<div class="full"><label for="eg-footer">Footer text</label><textarea id="eg-footer" rows="2" maxlength="300">' + esc(g.footerText || "") + "</textarea></div>" +
          '<div class="full admin-actions"><button class="btn btn--primary btn--small" type="submit">Save sender settings</button></div>' +
          "</form></div>" +

          '<div class="admin-panel"><h2>Forms &amp; routing</h2>' +
          '<div class="table-scroll"><table class="admin-table"><thead><tr><th>Form</th><th>Internal recipient</th>' +
          "<th>Notify team</th><th>Auto reply</th><th></th></tr></thead><tbody>" +
          forms.map(function (f) {
            return '<tr' + (f.key === emailForm ? ' class="is-current"' : "") + '><td><b>' + esc(f.label) + "</b></td>" +
              '<td class="muted">' + esc(f.recipient) + "</td>" +
              "<td>" + (f.internalOn ? '<span class="badge-ok">on</span>' : '<span class="muted">off</span>') + "</td>" +
              "<td>" + (f.customerOn ? '<span class="badge-ok">on</span>' : '<span class="muted">off</span>') + "</td>" +
              '<td class="cell-actions"><button class="btn btn--ghost btn--small" data-pick="' + esc(f.key) + '">Edit</button></td></tr>';
          }).join("") + "</tbody></table></div></div>" +

          '<div class="admin-panel"><h2>' + esc(current.label || "") + " — notification &amp; template</h2>" +
          '<form class="admin-form" id="em-form">' +
          '<div><label for="ef-recipient">Internal recipient</label><input id="ef-recipient" maxlength="120" value="' + esc(current.recipient || "") + '"></div>' +
          '<div><label for="ef-internal-on">Internal notification</label><select id="ef-internal-on">' +
          '<option value="on"' + (current.internalOn ? " selected" : "") + ">On</option>" +
          '<option value="off"' + (current.internalOn ? "" : " selected") + ">Off</option></select></div>" +
          '<div class="full"><label for="ef-internal-subject">Internal email subject</label>' +
          '<input id="ef-internal-subject" maxlength="200" value="' + esc(current.internalSubject || "") + '"></div>' +
          '<div><label for="ef-customer-on">Customer auto reply</label><select id="ef-customer-on">' +
          '<option value="on"' + (current.customerOn ? " selected" : "") + ">On</option>" +
          '<option value="off"' + (current.customerOn ? "" : " selected") + ">Off</option></select></div>" +
          '<div><label for="ef-button-text">Button text (optional)</label><input id="ef-button-text" maxlength="60" value="' + esc(current.buttonText || "") + '"></div>' +
          '<div class="full"><label for="ef-customer-subject">Customer email subject</label>' +
          '<input id="ef-customer-subject" maxlength="200" value="' + esc(current.customerSubject || "") + '"></div>' +
          '<div class="full"><label for="ef-heading">Heading</label><input id="ef-heading" maxlength="160" value="' + esc(current.heading || "") + '"></div>' +
          '<div class="full"><label for="ef-body">Main message</label><textarea id="ef-body" rows="8" maxlength="4000">' + esc(current.body || "") + "</textarea>" +
          '<span class="admin-inline-note">Available for this form — click to insert: </span><span class="var-list">' + vars(current.variables) + "</span></div>" +
          '<div class="full"><label for="ef-closing">Closing message</label><textarea id="ef-closing" rows="2" maxlength="600">' + esc(current.closing || "") + "</textarea></div>" +
          '<div class="full"><label for="ef-button-url">Button link (optional)</label><input id="ef-button-url" maxlength="300" value="' + esc(current.buttonUrl || "") + '"></div>' +
          '<div class="full admin-actions"><button class="btn btn--primary btn--small" type="submit">Save this form</button>' +
          '<button class="btn btn--ghost btn--small" type="button" data-preview="customer">Preview customer email</button>' +
          '<button class="btn btn--ghost btn--small" type="button" data-preview="internal">Preview internal email</button></div>' +
          "</form></div>" +

          '<div class="admin-panel"><h2>Send a test email</h2>' +
          '<form class="admin-form" id="em-test">' +
          '<div><label for="et-to">Send to</label><input id="et-to" type="email" maxlength="200" placeholder="you@elitemarcom.com" required></div>' +
          '<div class="full admin-actions"><button class="btn btn--primary btn--small" type="submit">Send test email</button>' +
          '<span class="admin-inline-note" id="et-result"></span></div></form></div>' +

          '<div class="admin-panel"><h2>Recent deliveries</h2>' +
          '<p class="admin-inline-note" style="margin-bottom:12px;">Every email is queued when the ' +
          "form is submitted and sent by the server, so a temporary email outage never loses a " +
          "message — failed deliveries stay here and can be retried without resending the form." +
          (failed ? ' <button class="btn btn--ghost btn--small" id="em-retry-all">Retry all failed</button>' : "") +
          "</p>" +
          ((d.log || []).length
            ? '<div class="table-scroll"><table class="admin-table"><thead><tr><th>When</th><th>Form</th><th>Type</th>' +
              "<th>To</th><th>Status</th></tr></thead><tbody>" +
              d.log.map(function (l) {
                var cls = l.status === "sent" ? "badge-ok" : (l.status === "failed" ? "badge-bad" : "muted");
                return '<tr><td class="muted">' + esc(when(l.ts)) + "</td><td>" + esc(l.form) +
                  '</td><td class="muted">' + esc(l.kind) + '</td><td class="muted">' + esc(l.recipient) +
                  '</td><td><span class="' + cls + '">' + esc(l.status) + "</span>" +
                  (l.attempts > 1 ? ' <span class="admin-inline-note">(' + esc(l.attempts) + " attempts)</span>" : "") +
                  (l.detail ? '<br><span class="admin-inline-note">' + esc(l.detail) + "</span>" : "") +
                  (l.status === "failed" && l.reference
                    ? ' <button class="btn btn--ghost btn--small" data-retry="' + esc(l.reference) + '">Retry</button>'
                    : "") + "</td></tr>";
              }).join("") + "</tbody></table></div>"
            : '<p class="admin-inline-note">Nothing sent yet.</p>') + "</div>" +
          '<div class="picker-overlay" id="em-preview" hidden><div class="picker-box">' +
          '<div class="picker-head"><div><h2 id="pv-subject">Preview</h2>' +
          '<p class="admin-inline-note" id="pv-meta"></p></div>' +
          '<button class="btn btn--ghost btn--small" id="pv-close">Close</button></div>' +
          '<iframe id="pv-frame" title="Email preview" class="pv-frame"></iframe></div></div>';

        main.querySelectorAll("[data-pick]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            emailForm = btn.getAttribute("data-pick");
            views.email();
          });
        });
        main.querySelectorAll(".var-chip").forEach(function (chip) {
          chip.addEventListener("click", function () {
            var ta = document.getElementById("ef-body");
            ta.setRangeText(chip.getAttribute("data-var"), ta.selectionStart, ta.selectionEnd, "end");
            ta.focus();
          });
        });
        document.getElementById("em-general").addEventListener("submit", function (e) {
          e.preventDefault();
          api("/api/admin/email/general", { values: {
            fromName: document.getElementById("eg-name").value.trim(),
            fromEmail: document.getElementById("eg-from").value.trim(),
            replyTo: document.getElementById("eg-reply").value.trim(),
            contactEmail: document.getElementById("eg-contact").value.trim(),
            websiteUrl: document.getElementById("eg-site").value.trim(),
            footerText: document.getElementById("eg-footer").value.trim()
          } }).then(function (r2) {
            r2.ok ? (toast("Sender settings saved."), views.email()) : apiErr(r2);
          });
        });
        function formValues() {
          return {
            recipient: document.getElementById("ef-recipient").value.trim(),
            internalOn: document.getElementById("ef-internal-on").value === "on",
            customerOn: document.getElementById("ef-customer-on").value === "on",
            internalSubject: document.getElementById("ef-internal-subject").value,
            customerSubject: document.getElementById("ef-customer-subject").value,
            heading: document.getElementById("ef-heading").value,
            body: document.getElementById("ef-body").value,
            closing: document.getElementById("ef-closing").value,
            buttonText: document.getElementById("ef-button-text").value,
            buttonUrl: document.getElementById("ef-button-url").value.trim()
          };
        }
        document.getElementById("em-form").addEventListener("submit", function (e) {
          e.preventDefault();
          api("/api/admin/email/form/" + encodeURIComponent(emailForm), { values: formValues() })
            .then(function (r2) {
              r2.ok ? (toast("Saved — new submissions use it immediately."), views.email()) : apiErr(r2);
            });
        });
        main.querySelectorAll("[data-preview]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            api("/api/admin/email/preview", { form: emailForm, values: formValues(),
                                              audience: btn.getAttribute("data-preview") })
              .then(function (r2) {
                if (!r2.ok) return apiErr(r2);
                document.getElementById("pv-subject").textContent = r2.data.subject;
                document.getElementById("pv-meta").textContent =
                  "From " + r2.data.from + " · reply-to " + r2.data.replyTo;
                document.getElementById("pv-frame").srcdoc = r2.data.html;
                document.getElementById("em-preview").hidden = false;
              });
          });
        });
        document.getElementById("pv-close").addEventListener("click", function () {
          document.getElementById("em-preview").hidden = true;
        });
        var retryAll = document.getElementById("em-retry-all");
        if (retryAll) retryAll.addEventListener("click", function () {
          api("/api/admin/email/retry", { all: true }).then(function (r2) {
            r2.ok ? (toast("Requeued " + r2.data.requeued + " delivery(ies)."), views.email()) : apiErr(r2);
          });
        });
        main.querySelectorAll("[data-retry]").forEach(function (btn) {
          btn.addEventListener("click", function () {
            api("/api/admin/email/retry", { reference: btn.getAttribute("data-retry") })
              .then(function (r2) {
                r2.ok ? (toast("Requeued — the server will try again shortly."), views.email()) : apiErr(r2);
              });
          });
        });
        document.getElementById("em-test").addEventListener("submit", function (e) {
          e.preventDefault();
          var out = document.getElementById("et-result");
          out.textContent = "Sending…";
          out.className = "admin-inline-note";
          api("/api/admin/email/test", { to: document.getElementById("et-to").value.trim() })
            .then(function (r2) {
              if (r2.ok) {
                out.textContent = "✓ Sent successfully to " +
                  document.getElementById("et-to").value.trim() + ".";
                out.className = "badge-ok";
                toast("Test email sent.");
              } else {
                out.textContent = "✗ Failed — " + ((r2.data && r2.data.detail) || "please check the settings.");
                out.className = "badge-bad";
              }
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
          '<div class="admin-panel"><h2>Recorded actions</h2>' +
          '<div class="table-scroll"><table class="admin-table"><thead>' +
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
        var smtp = !!s["notify.smtpConfigured"];
        var SOCIAL = (s.socialNetworks || []).map(function (n) {
          return [n.key, n.label, n.placeholder];
        });

        function help(text) { return '<span class="field-help">' + text + "</span>"; }
        function elsewhere(title, view, what) {
          return '<div class="svc-row"><i class="svc-dot"></i><b>' + esc(title) + "</b><small>" +
            esc(what) + '</small><button class="btn btn--ghost btn--small" data-goto="' + view +
            '">Open</button></div>';
        }

        main.innerHTML =
          '<h1 class="admin-h1">Settings</h1>' +
          '<p class="admin-sub">Everything the site reads from configuration, and where each one shows up. ' +
          "Settings that live on their own screen are listed at the bottom with a link.</p>" +

          '<div class="admin-panel"><h2>Staff notifications</h2>' +
          '<p class="admin-inline-note" style="margin-bottom:14px;">Internal alerts about new submissions. ' +
          "These are separate from the customer emails, which are configured on the Email screen.</p>" +
          '<form class="admin-form" id="settings-form">' +

          '<div class="full"><label for="s-emails">Alert recipients (one email per line)</label>' +
          '<textarea id="s-emails" rows="3">' + esc((s["notify.emails"] || []).join("\n")) + "</textarea>" +
          help("Who gets a heads-up the moment any of the six forms is submitted. The alert carries " +
               "the reference and the kind of request only — never a name, address or message — so a " +
               "compromised team mailbox leaks nothing about a customer. Maximum 20 addresses. " +
               "Delivery uses the same durable queue as every other email, so an alert survives a " +
               "restart, is retried on failure and appears in the Email screen's delivery log. " +
               (smtp ? "The legacy SMTP route is also configured and is used if the mail service is not."
                     : "")) + "</div>" +

          '<div><label for="s-lang">Published languages</label><select id="s-lang">' +
          '<option value="en"' + (langs.indexOf("ar") === -1 ? " selected" : "") + ">English only</option>" +
          '<option value="en,ar"' + (langs.indexOf("ar") !== -1 ? " selected" : "") + ">English + Arabic</option>" +
          "</select>" +
          help("Choosing English + Arabic makes <b>Publish site</b> bake a second, right-to-left edition " +
               "under /ar/ alongside the English pages. Arabic wording is entered per field on Pages &amp; " +
               "SEO; this switch only decides whether that edition is published.") + "</div>" +

          '<div><label for="s-default-lang">Language shown by default</label><select id="s-default-lang"' +
          (langs.indexOf("ar") === -1 ? " disabled" : "") + ">" +
          '<option value="en"' + (s["site.defaultLanguage"] === "ar" ? "" : " selected") + ">English</option>" +
          '<option value="ar"' + (s["site.defaultLanguage"] === "ar" ? " selected" : "") + ">Arabic</option>" +
          "</select>" +
          help("Which edition a visitor gets at elitemarcom.com without a language in the address. " +
               "/ar/ keeps working either way. " +
               (langs.indexOf("ar") === -1
                 ? "<b>Publish Arabic first to enable this.</b>"
                 : "Only a published language can be the default, so this cannot leave the site " +
                   "serving nothing.")) + "</div>" +

          '<div class="full admin-actions"><button class="btn btn--primary btn--small" type="submit">Save settings</button>' +
          '<span class="admin-inline-note">Saved immediately; language changes reach the public site at the next publish.</span></div>' +
          "</form></div>" +

          '<div class="admin-panel"><h2>Social media links</h2>' +
          '<p class="admin-inline-note" style="margin-bottom:14px;">Paste the full address of each profile you ' +
          "want in the footer. Leave a field empty and that icon is not shown at all — the row only ever " +
          "contains accounts you have filled in. Icons appear on every page after the next " +
          "<b>Publish site</b>.</p>" +
          '<form class="admin-form" id="social-form">' +
          SOCIAL.map(function (n) {
            return '<div><label for="soc-' + n[0] + '">' + esc(n[1]) + "</label>" +
              '<input id="soc-' + n[0] + '" type="url" maxlength="300" placeholder="' + esc(n[2]) +
              '" value="' + esc(s["social." + n[0]] || "") + '"></div>';
          }).join("") +
          '<div class="full admin-actions"><button class="btn btn--primary btn--small" type="submit">Save social links</button>' +
          '<span class="admin-inline-note">Must start with https://</span></div></form></div>' +

          '<div class="admin-panel"><h2>Configured on other screens</h2>' +
          '<p class="admin-inline-note" style="margin-bottom:14px;">These are real settings, kept where the ' +
          "work happens rather than duplicated here.</p><div class=\"svc-list\">" +
          elsewhere("Logo, colours, fonts and the 3D hero", "brand",
                    "Website & Brand — brand tokens and hero camera") +
          elsewhere("Page text, SEO and share images", "pages",
                    "Pages & SEO — titles, descriptions, canonical and social cards") +
          elsewhere("Sender address, routing and templates", "email",
                    "Email — six notification types, delivery log and queue health") +
          elsewhere("Visitor analytics and GA4", "insights",
                    "Site Insights — tracking on/off, GA4 id, retention in days") +
          elsewhere("Site-wide announcement bar", "operations",
                    "Operations — text, link, style and the dates it shows between") +
          elsewhere("Backups, restore and scheduled publishing", "operations",
                    "Operations — download a backup, restore one, schedule a publish") +
          elsewhere("Supplier catalogue and call budget", "jasani",
                    "Jasani — cache state per market, refresh, daily call budget") +
          "</div></div>" +

          '<div class="admin-panel"><h2>Server configuration</h2>' +
          '<p class="admin-inline-note">Set as environment variables on the server, never in this panel: ' +
          "the Resend API key, the Jasani supplier token, the encryption and session secrets, Turnstile " +
          "keys, retention periods and the supplier call budget. They are deliberately not editable here — " +
          "a secret that can be read back from a browser is a secret you have to rotate.</p></div>";

        main.querySelectorAll("[data-goto]").forEach(function (btn) {
          btn.addEventListener("click", function () { location.hash = "#" + btn.getAttribute("data-goto"); });
        });
        document.getElementById("settings-form").addEventListener("submit", function (e) {
          e.preventDefault();
          var emails = document.getElementById("s-emails").value.split("\n")
            .map(function (x) { return x.trim(); }).filter(Boolean).slice(0, 20);
          api("/api/admin/settings", { values: {
            "notify.emails": emails,
            "site.languages": document.getElementById("s-lang").value.split(","),
            "site.defaultLanguage": document.getElementById("s-default-lang").value
          } }).then(function (r2) { r2.ok ? toast("Settings saved.") : apiErr(r2); });
        });
        document.getElementById("social-form").addEventListener("submit", function (e) {
          e.preventDefault();
          var values = {};
          SOCIAL.forEach(function (n) {
            values["social." + n[0]] = document.getElementById("soc-" + n[0]).value.trim();
          });
          api("/api/admin/settings", { values: values }).then(function (r2) {
            r2.ok ? toast("Social links saved — publish the site to show them.") : apiErr(r2);
          });
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

  /* ---------------- Jasani items ---------------- */

  var jzState = {
    market: "ksa", terms: [], field: "all", stock: "", brand: "", colour: "",
    category: "", visibility: "", sort: "featured", hideZero: false,
    priceMin: "", priceMax: "",
    page: 1, perPage: 25, listScroll: 0, gallery: 0, data: null
  };

  function jzQuery(extra) {
    var s = jzState;
    var q = {
      market: s.market, q: s.terms.join(","), field: s.field, stock: s.stock,
      brand: s.brand, colour: s.colour, category: s.category,
      visibility: s.visibility, hideZero: s.hideZero ? "true" : "false",
      priceMin: s.priceMin, priceMax: s.priceMax,
      sort: s.sort, page: s.page, perPage: s.perPage
    };
    Object.keys(extra || {}).forEach(function (k) { q[k] = extra[k]; });
    return Object.keys(q).filter(function (k) { return q[k] !== "" && q[k] != null; })
      .map(function (k) { return k + "=" + encodeURIComponent(q[k]); }).join("&");
  }

  function jzMoney(v) {
    return v == null ? "—" : Number(v).toLocaleString("en-GB",
      { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  function jzNum(v) { return Number(v || 0).toLocaleString("en-GB"); }
  /* the chip has room for an age, not a full timestamp */
  function jzAgo(ts) {
    if (!ts) return "never";
    var mins = Math.max(0, Math.round((Date.now() / 1000 - ts) / 60));
    if (mins < 2) return "just now";
    if (mins < 60) return mins + " min ago";
    var hours = Math.round(mins / 60);
    if (hours < 24) return hours + (hours === 1 ? " hour ago" : " hours ago");
    var days = Math.round(hours / 24);
    return days + (days === 1 ? " day ago" : " days ago");
  }

  var JZ_EYE_ON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 12s3.5-7 9-7 9 7 9 7-3.5 7-9 7-9-7-9-7z"/><circle cx="12" cy="12" r="2.6"/></svg>';
  var JZ_EYE_OFF = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 3l18 18"/><path d="M10.6 5.1A9.7 9.7 0 0112 5c5 0 9 4.5 9 7a11 11 0 01-2.2 3.2M6.2 6.7C3.9 8.2 3 10.4 3 12c0 2.5 4 7 9 7a9.6 9.6 0 004.3-1"/></svg>';

  function jzVisBadge(it) {
    var live = it.live;
    var label = it.hidden ? "Hidden" : (it.hiddenByRule ? "Hidden by rule" : "Live");
    var why = it.hidden ? "hidden by hand"
      : it.hiddenByRule ? "no available stock" : "shown on the website";
    return '<span class="jz-vis' + (live ? "" : " jz-vis--off") + '" title="' + esc(why) + '">' +
      (live ? JZ_EYE_ON : JZ_EYE_OFF) + esc(label) + "</span>";
  }

  function jzExportChildren(scope) {
    return ["pdf", "xlsx", "csv"].map(function (fmt) {
      var names = { pdf: "PDF (branded)", xlsx: "Excel (.xlsx)", csv: "CSV (spreadsheet)" };
      return { label: names[fmt], action: function () {
        location.href = "/api/admin/jasani/items-export?" + jzQuery({ format: fmt, scope: scope });
      } };
    });
  }

  function jzSetHidden(it, hidden, after) {
    api("/api/admin/jasani/visibility",
        { market: jzState.market, productId: it.id, hidden: hidden }).then(function (r) {
      if (!r.ok) return apiErr(r);
      toast(hidden ? it.code + " hidden from the website."
                   : it.code + " is shown on the website again.");
      after && after();
    });
  }

  function jzRowMenu(btn, it, canVis, after) {
    var entries = [
      { label: "View details", action: function () { location.hash = "#items/" + jzState.market + "/" + encodeURIComponent(it.id); } },
      { label: "Open on the website", disabled: !it.live,
        title: "This item is not on the website right now",
        action: function () { window.open("/product.html?country=" + jzState.market + "&id=" + encodeURIComponent(it.id), "_blank", "noopener"); } },
      { label: "Download printing manual",
        action: function () { location.href = "/api/giveaways/manual?country=" + jzState.market + "&product_id=" + encodeURIComponent(it.id); } },
      { label: "Copy SKU", action: function () { jzCopy(it.code); } },
      { label: "Copy supplier product id", action: function () { jzCopy(it.id); } }
    ];
    if (canVis) {
      entries.push({ label: it.hidden ? "Show on website" : "Hide from website",
                     danger: !it.hidden,
                     action: function () { jzSetHidden(it, !it.hidden, after); } });
    }
    entries.push({ label: "Export as PDF", action: function () {
      location.href = "/api/admin/jasani/items/" + jzState.market + "/" +
        encodeURIComponent(it.id) + "/sheet";
    } });
    showMenu(btn, entries);
  }

  function jzCopy(text) {
    try {
      navigator.clipboard.writeText(text);
      toast("Copied " + text + ".");
    } catch (e) {
      toast("Could not copy — " + text, true);
    }
  }

  views.items = function (param) {
    if (param) {
      var bits = param.split("/");
      return jzDetail(bits[0], decodeURIComponent(bits.slice(1).join("/")));
    }
    api("/api/admin/jasani/items?" + jzQuery()).then(function (r) {
      if (!r.ok) return apiErr(r);
      var d = jzState.data = r.data;
      var prices = d.canSeePrices, canVis = d.canChangeVisibility;
      var cur = d.currency;
      var t = d.totals;

      function sel(id, label, value, options) {
        return '<select id="' + id + '" aria-label="' + esc(label) + '">' +
          '<option value="">' + esc(label) + "</option>" +
          options.map(function (o) {
            var v = Array.isArray(o) ? o[0] : o, txt = Array.isArray(o) ? o[1] : o;
            return '<option value="' + esc(v) + '"' + (value === v ? " selected" : "") + ">" +
              esc(txt) + "</option>";
          }).join("") + "</select>";
      }
      var STOCK_LABEL = { in: "In stock", low: "Low stock", out: "Out of stock",
                          incoming: "Incoming expected", booked: "Has booked stock" };
      var chips = [];
      if (jzState.stock) chips.push(["stock", "Stock: " + STOCK_LABEL[jzState.stock]]);
      if (jzState.brand) chips.push(["brand", "Brand: " + jzState.brand]);
      if (jzState.colour) chips.push(["colour", "Colour: " + jzState.colour]);
      if (jzState.category) chips.push(["category", "Category: " + jzState.category]);
      if (jzState.visibility) chips.push(["visibility", "Website: " +
        ({ visible: "Live", hidden: "Not live", byhand: "Hidden by hand" }[jzState.visibility])]);
      if (jzState.hideZero) chips.push(["hideZero", "Zero stock hidden"]);
      if (jzState.priceMin !== "" || jzState.priceMax !== "") {
        chips.push(["price", "Price " + (jzState.priceMin || "0") + "–" +
          (jzState.priceMax || "any") + " " + cur]);
      }

      var cards = [["", jzNum(t.all), "Items in the snapshot", "all"],
                   ["ok", jzNum(t.in), "In stock", "in"],
                   ["warn", jzNum(t.low), "Low stock (≤ " + d.lowThreshold + ")", "low"],
                   ["bad", jzNum(t.out), "Out of stock", "out"],
                   ["", jzNum(t.hidden), "Hidden from the website", "hidden"]];
      var snap = d.snapshot || {};

      main.innerHTML =
        '<div class="jz-head"><div>' +
          '<h1 class="admin-h1">Jasani items</h1>' +
          '<p class="admin-sub">Every product in the cached supplier snapshot, per market. ' +
          "Reading this page never calls Jasani — it costs none of the day's five calls.</p></div>" +
          '<span class="jz-head__spacer"></span>' +
          '<div class="jz-head__tools">' +
            '<span class="jz-snap' + (snap.stockFresh ? "" : " jz-snap--due") + '"><i></i>' +
            (snap.cached ? "Products " + esc(jzAgo(snap.fetchedAt)) + " · stock " + esc(jzAgo(snap.stockAt))
                         : "Nothing cached yet") + "</span>" +
            '<div class="jz-seg" role="group" aria-label="Market">' +
              ["ksa", "uae"].map(function (m) {
                var labels = { ksa: "Saudi Arabia", uae: "UAE" };
                return '<button type="button" data-jzmarket="' + m + '" aria-pressed="' +
                  (jzState.market === m) + '">' + labels[m] +
                  ' <span class="jz-seg__n">' + jzNum((d.markets || {})[m] || 0) + "</span></button>";
              }).join("") + "</div>" +
          "</div></div>" +

        '<div class="stat-row stat-row--tight">' + cards.map(function (c) {
          return '<button type="button" class="stat-card stat-card--click' +
            (c[0] ? " stat-card--" + c[0] : "") + '" data-jzstat="' + c[3] + '"><b>' + c[1] +
            "</b><span>" + esc(c[2]) + "</span></button>";
        }).join("") + "</div>" +

        '<div class="admin-panel">' +
          '<div class="jz-search">' +
            '<span class="jz-search__icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg></span>' +
            jzState.terms.map(function (term, i) {
              return '<span class="jz-chip">' + esc(term) +
                '<button type="button" data-jzterm="' + i + '" aria-label="Remove ' + esc(term) + '">✕</button></span>';
            }).join("") +
            '<input id="jz-q" autocomplete="off" placeholder="' +
            (jzState.terms.length ? "Add another term…" : "Search name, SKU, brand, colour or category…") + '">' +
            '<select id="jz-field" aria-label="Search in">' +
            [["all", "All fields"], ["name", "Name only"], ["sku", "SKU only"],
             ["brand", "Brand only"], ["colour", "Colour only"], ["category", "Category only"]]
              .map(function (o) {
                return '<option value="' + o[0] + '"' + (jzState.field === o[0] ? " selected" : "") +
                  ">" + o[1] + "</option>";
              }).join("") + "</select>" +
            (jzState.terms.length ? '<button class="btn btn--ghost btn--small" id="jz-clear">Clear all</button>' : "") +
          "</div>" +
          '<p class="jz-search__hint">Press <b>Enter</b> or type a <b>comma</b> to add another term — ' +
          "results match any of them. Paste a column of SKUs and each line becomes its own term.</p>" +
          '<div class="jz-filters">' +
            sel("jz-sort", "Sort", jzState.sort,
                [["featured", "Featured (website order)"], ["name", "Name A–Z"],
                 ["sku", "SKU A–Z"], ["stockDesc", "Stock high → low"],
                 ["stockAsc", "Stock low → high"]].concat(prices
                   ? [["priceAsc", "Price low → high"], ["priceDesc", "Price high → low"]] : [])
                 .concat([["brand", "Brand"]])) +
            sel("jz-stock", "Stock status", jzState.stock,
                [["in", "In stock"], ["low", "Low stock (≤ " + d.lowThreshold + ")"],
                 ["out", "Out of stock"], ["incoming", "Incoming expected"]]
                .concat(prices ? [["booked", "Has booked stock"]] : [])) +
            sel("jz-brand", "Brand", jzState.brand, d.facets.brands) +
            sel("jz-colour", "Colour", jzState.colour, d.facets.colours) +
            sel("jz-category", "Category", jzState.category, d.facets.categories) +
            sel("jz-vis", "Website", jzState.visibility,
                [["visible", "Live on the website"], ["hidden", "Not on the website"],
                 ["byhand", "Hidden by hand"]]) +
            '<label class="jz-toggle"><input type="checkbox" id="jz-zero"' +
              (jzState.hideZero ? " checked" : "") + "> Hide zero-stock items</label>" +
            (prices ? '<span class="jz-price-filter"><label for="jz-pmin">Price</label>' +
              '<input id="jz-pmin" type="number" min="0" step="0.01" placeholder="Min" aria-label="Minimum price" value="' + esc(jzState.priceMin) + '">' +
              '<i aria-hidden="true">–</i>' +
              '<input id="jz-pmax" type="number" min="0" step="0.01" placeholder="Max" aria-label="Maximum price" value="' + esc(jzState.priceMax) + '">' +
              "<em>" + esc(cur) + " ex VAT</em></span>" : "") +
            '<button class="btn btn--primary btn--small jz-export" id="jz-export">Export ▾</button>' +
          "</div>" +
          (chips.length ? '<div class="jz-applied"><span class="muted">Filters:</span>' +
            chips.map(function (c) {
              return '<span class="jz-chip">' + esc(c[1]) +
                '<button type="button" data-jzclear="' + c[0] + '" aria-label="Remove filter">✕</button></span>';
            }).join("") +
            '<button class="btn btn--ghost btn--small" data-jzclear="all">Reset all</button></div>' : "") +
        "</div>" +

        '<div class="admin-panel">' +
          '<div class="panel-head"><h2>' + jzNum(d.matched) + " item" + (d.matched === 1 ? "" : "s") +
          (d.matched !== t.all ? " of " + jzNum(t.all) : "") + "</h2>" +
          '<span class="admin-inline-note">' +
          (prices ? "Prices are " + esc(cur) + ", excluding VAT. " : "") +
          "Available is the supplier's guaranteed-sellable quantity; incoming dates are estimates." +
          (prices ? " Prices and booked stock are internal — they never reach the website." : "") +
          "</span></div>" +
          // the snapshot on disk predates the internal store: prices and booked
          // stock exist only in the supplier's payload, so they arrive with the
          // next sync rather than being invented here
          (d.pricesPending
            ? '<div class="jz-pending"><b>No prices in this snapshot yet.</b> ' +
              "The price comes from the supplier's own Price API, which is a call " +
              "of its own — a products sync does not fetch them. The scheduled price call " +
              "fills them, or press <b>Prices</b> on the " +
              '<a href="#jasani">Jasani console</a> to do it now. Booked stock arrives with ' +
              "the next stock call.</div>"
            : "") +
          '<div class="table-scroll"><table class="jz-table"><thead><tr>' +
            "<th>SN</th><th></th><th>SKU</th><th>Name</th><th>Brand</th><th>Colour</th>" +
            (prices ? '<th class="jz-num">Price</th>' : "") +
            '<th class="jz-num">Available</th><th class="jz-num">Incoming</th>' +
            (prices ? '<th class="jz-num">Booked</th>' : "") +
            "<th>Website</th><th></th></tr></thead><tbody>" +
            (d.items.length ? d.items.map(function (it, i) {
              var cls = it.available === 0 ? " jz-stock--out"
                : (it.available <= d.lowThreshold ? " jz-stock--low" : "");
              return '<tr' + (it.live ? "" : ' class="is-hidden"') + ' data-jzid="' + esc(it.id) + '">' +
                '<td class="jz-sn">' + ((d.page - 1) * d.perPage + i + 1) + "</td>" +
                '<td class="jz-cell-img"><span class="jz-img">' + (it.image
                  ? '<img src="' + esc(it.image) + '" alt="" loading="lazy">' : "") +
                  "</span></td>" +
                '<td class="jz-sku">' + esc(it.code) + "</td>" +
                '<td class="jz-name"><b>' + esc(it.name) + '</b><span class="jz-cat">' +
                  esc(it.category) + '</span><span class="jz-meta">' +
                  esc([it.brand, it.color, it.category].filter(Boolean).join(" · ")) + "</span></td>" +
                '<td class="jz-brand">' + esc(it.brand || "—") + "</td>" +
                '<td class="jz-colour">' + esc(it.color || "—") + "</td>" +
                (prices ? '<td class="jz-num jz-price" data-l="Price"><b>' +
                    jzMoney(it.price) + "</b>" + JZ_INT + "</td>" : "") +
                '<td class="jz-num jz-stock' + cls + '" data-l="Available">' +
                  '<span class="jz-stock-label">Available</span><b>' + jzNum(it.available) + "</b>" +
                  '<span class="jz-sub">' + (it.available === 0 ? "out of stock"
                    : it.available <= d.lowThreshold ? "low" : "available") + "</span></td>" +
                '<td class="jz-num" data-l="Incoming">' + (it.incoming
                  ? "<b>" + jzNum(it.incoming) + "</b>" + (it.incomingDate
                      ? '<span class="jz-sub">est. ' + esc(it.incomingDate) + "</span>" : "")
                  : '<span class="muted">—</span>') + "</td>" +
                (prices ? '<td class="jz-num jz-booked" data-l="Booked">' +
                  (it.booked ? jzNum(it.booked) : '<span class="muted">—</span>') + JZ_INT + "</td>" : "") +
                '<td class="jz-cell-vis">' + jzVisBadge(it) + "</td>" +
                '<td class="jz-cell-actions cell-actions"><button class="dots-btn" data-jzrow="' +
                  esc(it.id) + '" aria-label="Actions for ' + esc(it.code) + '">⋮</button></td></tr>';
            }).join("")
              : '<tr><td colspan="12"><div class="jz-empty"><b>Nothing matches.</b><br>' +
                '<span class="admin-inline-note">Try removing a filter, or search a different SKU.</span></div></td></tr>') +
          "</tbody></table></div>" +
          '<div class="jz-foot"><span>Showing ' +
            (d.matched ? jzNum((d.page - 1) * d.perPage + 1) + "–" +
              jzNum(Math.min(d.page * d.perPage, d.matched)) : "0") + " of " + jzNum(d.matched) + "</span>" +
            '<span class="jz-foot__spacer"></span>' +
            '<label style="display:flex;gap:7px;align-items:center;">Per page<select id="jz-per">' +
            [25, 50, 100].map(function (v) {
              return '<option value="' + v + '"' + (d.perPage === v ? " selected" : "") + ">" + v + "</option>";
            }).join("") + "</select></label>" +
            '<span class="jz-pager">' +
              '<button type="button" data-jzpage="prev"' + (d.page === 1 ? " disabled" : "") + ">‹</button>" +
              jzPageButtons(d.page, d.pages) +
              '<button type="button" data-jzpage="next"' + (d.page === d.pages ? " disabled" : "") + ">›</button>" +
            "</span></div>" +
        "</div>";

      jzWireList(d);
      if (jzState.listScroll) {
        var y = jzState.listScroll;
        jzState.listScroll = 0;
        requestAnimationFrame(function () { window.scrollTo(0, y); });
      }
    });
  };

  var JZ_INT = '<span class="jz-note-internal jz-card-only">internal</span>';

  function jzPageButtons(page, pages) {
    // a long catalogue would otherwise render hundreds of page buttons
    var out = [], seen = {};
    [1, 2, page - 1, page, page + 1, pages - 1, pages].forEach(function (n) {
      if (n >= 1 && n <= pages && !seen[n]) { seen[n] = 1; out.push(n); }
    });
    out.sort(function (a, b) { return a - b; });
    var html = "", last = 0;
    out.forEach(function (n) {
      if (last && n > last + 1) html += '<span class="jz-pager__gap">…</span>';
      html += '<button type="button" data-jzpage="' + n + '" aria-current="' + (n === page) + '">' + n + "</button>";
      last = n;
    });
    return html;
  }

  function jzReload(resetPage) {
    if (resetPage !== false) jzState.page = 1;
    views.items();
  }

  function jzWireList(d) {
    main.querySelectorAll("[data-jzmarket]").forEach(function (b) {
      b.addEventListener("click", function () {
        jzState.market = b.getAttribute("data-jzmarket");
        jzState.brand = jzState.colour = jzState.category = "";
        jzState.priceMin = jzState.priceMax = "";   // the band was another currency
        jzReload();
      });
    });
    main.querySelectorAll("[data-jzstat]").forEach(function (c) {
      c.addEventListener("click", function () {
        var k = c.getAttribute("data-jzstat");
        if (k === "all") { jzState.stock = ""; jzState.visibility = ""; jzState.hideZero = false; }
        else if (k === "hidden") { jzState.stock = ""; jzState.visibility = "hidden"; }
        else { jzState.stock = k; jzState.visibility = ""; }
        jzReload();
      });
    });
    var q = document.getElementById("jz-q");
    function addTerms(raw) {
      var dropped = 0;
      raw.split(/[,\n\t]/).map(function (t) { return t.trim(); }).filter(Boolean).forEach(function (t) {
        if (jzState.terms.indexOf(t) !== -1) return;
        if (jzState.terms.length >= 20) { dropped++; return; }
        jzState.terms.push(t);
      });
      if (dropped) toast("20 search terms is the maximum — " + dropped + " were not added.", true);
      jzReload();
      var again = document.getElementById("jz-q");
      if (again) again.focus();
    }
    q.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && q.value.trim()) { e.preventDefault(); addTerms(q.value); }
      else if (e.key === "Backspace" && !q.value && jzState.terms.length) {
        jzState.terms.pop();
        jzReload();
        var again = document.getElementById("jz-q");
        if (again) again.focus();
      }
    });
    q.addEventListener("input", function () { if (q.value.indexOf(",") !== -1) addTerms(q.value); });
    q.addEventListener("paste", function (e) {
      var text = (e.clipboardData || window.clipboardData).getData("text");
      if (/[,\n\t]/.test(text)) { e.preventDefault(); addTerms(text); }
    });
    main.querySelectorAll("[data-jzterm]").forEach(function (b) {
      b.addEventListener("click", function () {
        jzState.terms.splice(parseInt(b.getAttribute("data-jzterm"), 10), 1);
        jzReload();
      });
    });
    var clear = document.getElementById("jz-clear");
    if (clear) clear.addEventListener("click", function () { jzState.terms = []; jzReload(); });

    var binds = { "jz-field": "field", "jz-sort": "sort", "jz-stock": "stock",
                  "jz-brand": "brand", "jz-colour": "colour", "jz-category": "category",
                  "jz-vis": "visibility" };
    Object.keys(binds).forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.addEventListener("change", function () {
        jzState[binds[id]] = this.value;
        jzReload();
      });
    });
    document.getElementById("jz-zero").addEventListener("change", function () {
      jzState.hideZero = this.checked;
      jzReload();
    });
    ["jz-pmin", "jz-pmax"].forEach(function (id) {
      var el = document.getElementById(id);
      if (!el) return;
      var key = id === "jz-pmin" ? "priceMin" : "priceMax", timer = null;
      el.addEventListener("input", function () {
        clearTimeout(timer);
        var v = el.value;
        timer = setTimeout(function () {
          jzState[key] = v;
          jzReload();
          var again = document.getElementById(id);
          if (again) again.focus();
        }, 400);
      });
    });
    main.querySelectorAll("[data-jzclear]").forEach(function (b) {
      b.addEventListener("click", function () {
        var k = b.getAttribute("data-jzclear");
        if (k === "all") {
          jzState.stock = jzState.brand = jzState.colour = jzState.category = jzState.visibility = "";
          jzState.hideZero = false;
          jzState.priceMin = jzState.priceMax = "";
        } else if (k === "hideZero") jzState.hideZero = false;
        else if (k === "price") jzState.priceMin = jzState.priceMax = "";
        else jzState[k] = "";
        jzReload();
      });
    });
    document.getElementById("jz-per").addEventListener("change", function () {
      jzState.perPage = parseInt(this.value, 10);
      jzReload();
    });
    main.querySelectorAll("[data-jzpage]").forEach(function (b) {
      b.addEventListener("click", function () {
        var v = b.getAttribute("data-jzpage");
        jzState.page = v === "prev" ? Math.max(1, d.page - 1)
          : v === "next" ? Math.min(d.pages, d.page + 1) : parseInt(v, 10);
        jzReload(false);
      });
    });
    document.getElementById("jz-export").addEventListener("click", function (e) {
      e.stopPropagation();
      showMenu(this, [
        { heading: "Export" },
        { label: "These " + jzNum(d.matched) + " item" + (d.matched === 1 ? "" : "s"),
          children: jzExportChildren("filtered") },
        { label: "Whole " + jzState.market.toUpperCase() + " snapshot (" + jzNum(d.totals.all) + ")",
          children: jzExportChildren("all") }
      ]);
    });
    var byId = {};
    d.items.forEach(function (it) { byId[it.id] = it; });
    main.querySelectorAll("[data-jzrow]").forEach(function (b) {
      b.addEventListener("click", function (e) {
        e.stopPropagation();
        jzRowMenu(b, byId[b.getAttribute("data-jzrow")], d.canChangeVisibility,
                  function () { jzReload(false); });
      });
    });
    main.querySelectorAll("tbody tr[data-jzid]").forEach(function (tr) {
      tr.addEventListener("click", function (e) {
        if (e.target.closest(".dots-btn")) return;
        jzState.listScroll = window.scrollY;
        location.hash = "#items/" + jzState.market + "/" +
          encodeURIComponent(tr.getAttribute("data-jzid"));
      });
    });
  }

  /* ---------------- one item, on its own page ---------------- */

  function jzDetail(market, productId) {
    api("/api/admin/jasani/items/" + encodeURIComponent(market) + "/" +
        encodeURIComponent(productId)).then(function (r) {
      if (!r.ok) return apiErr(r);
      var it = r.data.item, low = r.data.lowThreshold, cur = r.data.currency;
      var prices = it.price !== undefined;
      var images = (it.images && it.images.length) ? it.images : (it.image ? [it.image] : []);
      if (jzState.gallery >= images.length) jzState.gallery = 0;
      var cls = it.available === 0 ? "bad" : (it.available <= low ? "warn" : "ok");
      var label = it.available === 0 ? "Out of stock" : (it.available <= low ? "Low stock" : "In stock");

      var specs = [
        ["Supplier code", it.code], ["Supplier product id", it.id],
        ["Brand", it.brand], ["Colour", it.color],
        ["Category", (it.categories || []).join(", ")],
        ["Options", (it.options || []).join(", ")],
        ["Barcode", it.barcode], ["HS code", it.hsCode],
        ["Units per carton", it.unitsPerCarton],
        ["Carton size", it.cartonDimensions],
        ["Carton weight", it.cartonWeight ? it.cartonWeight + " kg" : ""],
        ["Carton volume", it.cartonVolume ? it.cartonVolume + " m³" : ""],
        ["Tags", (it.tags || []).join(", ")]
      ].filter(function (s) { return s[1] !== "" && s[1] != null; });

      function fact(label2, value, sub) {
        return "<div><dt>" + esc(label2) + "</dt><dd>" + value +
          (sub ? "<span>" + esc(sub) + "</span>" : "") + "</dd></div>";
      }

      main.innerHTML =
        '<button class="jz-back" id="jz-back">← All Jasani items</button>' +
        '<div class="jz-pdp">' +
          '<div class="jz-pdp__media">' +
            (images.length ? '<div class="jz-gal">' +
              '<button class="jz-pdp__main" id="jz-zoom" aria-label="Open the image full size">' +
                '<img src="' + esc(images[jzState.gallery]) + '" alt="' + esc(it.name) + '">' +
                '<span class="jz-zoom-hint">Click to zoom</span></button>' +
              (images.length > 1
                ? '<button class="jz-gal__btn jz-gal__btn--prev" data-jzslide="-1" aria-label="Previous image">‹</button>' +
                  '<button class="jz-gal__btn jz-gal__btn--next" data-jzslide="1" aria-label="Next image">›</button>' +
                  '<div class="jz-gal__dots">' + images.map(function (_, i) {
                    return '<button class="jz-gal__dot' + (i === jzState.gallery ? " is-on" : "") +
                      '" data-jzg="' + i + '" aria-label="Image ' + (i + 1) + '"' +
                      (i === jzState.gallery ? ' aria-current="true"' : "") + "></button>";
                  }).join("") + "</div>" +
                  '<span class="jz-gal__count">' + (jzState.gallery + 1) + " / " + images.length + "</span>"
                : "") +
            "</div>" : '<div class="jz-pdp__main jz-pdp__main--empty">No image in the snapshot</div>') +
            (images.length > 1 ? '<div class="jz-pdp__thumbs" role="group" aria-label="Product images">' +
              images.map(function (g, i) {
                return '<button class="jz-thumb-btn' + (i === jzState.gallery ? " is-on" : "") +
                  '" data-jzg="' + i + '" aria-label="Image ' + (i + 1) + '"><img src="' +
                  esc(g) + '" alt="" loading="lazy"></button>';
              }).join("") + "</div>" : "") +
          "</div>" +
          '<div class="jz-pdp__info">' +
            '<p class="jz-pdp__eyebrow">' +
              esc([it.brand, (it.categories || [])[0]].filter(Boolean).join(" · ")) + "</p>" +
            "<h1>" + esc(it.name) + "</h1>" +
            '<p class="jz-pdp__sku">' + esc(it.code) + '<span class="jz-pdp__market">' +
              esc(market.toUpperCase()) + "</span></p>" +
            '<div class="jz-pdp__pills"><span class="status-pill status-pill--' + cls + '">' +
              label + "</span>" + jzVisBadge(it) + "</div>" +
            '<dl class="jz-pdp__facts">' +
              fact("Available", jzNum(it.available)) +
              fact("Incoming", it.incoming ? jzNum(it.incoming) : "—",
                   it.incoming && it.incomingDate ? "est. " + it.incomingDate : "") +
              (prices ? fact("Booked", it.booked ? jzNum(it.booked) : "—") : "") +
              (prices ? fact("Price", jzMoney(it.price), cur + " ex VAT") : "") +
            "</dl>" +
            (prices ? '<p class="admin-inline-note">Prices and booked stock are internal — they are ' +
              "never shown on the website, in a public API response or in a customer document.</p>" : "") +
            '<div class="jz-pdp__actions">' +
              '<button class="btn btn--primary btn--small" id="jz-sheet">Export as PDF</button>' +
              '<button class="btn btn--ghost btn--small" id="jz-manual">Download printing manual</button>' +
              (r.data.canChangeVisibility
                ? '<button class="btn btn--ghost btn--small" id="jz-hide">' +
                  (it.hidden ? "Show on website" : "Hide from website") + "</button>" : "") +
            "</div>" +
          "</div>" +
        "</div>" +
        (it.description ? '<div class="admin-panel"><h2>Description</h2><p class="jz-prose">' +
          esc(it.description) + "</p></div>" : "") +
        (specs.length ? '<div class="admin-panel"><h2>Specifications</h2><dl class="jz-specs">' +
          specs.map(function (s) {
            return "<div><dt>" + esc(s[0]) + "</dt><dd>" + esc(s[1]) + "</dd></div>";
          }).join("") + "</dl></div>" : "");

      document.getElementById("jz-back").addEventListener("click", function () {
        location.hash = "#items";
      });
      main.querySelectorAll("[data-jzg]").forEach(function (b) {
        b.addEventListener("click", function () {
          jzState.gallery = parseInt(b.getAttribute("data-jzg"), 10);
          jzDetail(market, productId);
        });
      });
      main.querySelectorAll("[data-jzslide]").forEach(function (b) {
        b.addEventListener("click", function () {
          var step = parseInt(b.getAttribute("data-jzslide"), 10);
          jzState.gallery = (jzState.gallery + step + images.length) % images.length;
          jzDetail(market, productId);
          setTimeout(function () {
            var again = document.querySelector('[data-jzslide="' + step + '"]');
            if (again) again.focus();
          }, 30);
        });
      });
      var gal = document.querySelector(".jz-gal");
      if (gal) gal.addEventListener("keydown", function (e) {
        if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
        e.preventDefault();
        jzState.gallery = (jzState.gallery + (e.key === "ArrowRight" ? 1 : -1) + images.length) % images.length;
        jzDetail(market, productId);
      });
      var zoom = document.getElementById("jz-zoom");
      if (zoom) zoom.addEventListener("click", function () { jzLightbox(it, images); });
      document.getElementById("jz-sheet").addEventListener("click", function () {
        location.href = "/api/admin/jasani/items/" + encodeURIComponent(market) + "/" +
          encodeURIComponent(it.id) + "/sheet";
      });
      document.getElementById("jz-manual").addEventListener("click", function () {
        location.href = "/api/giveaways/manual?country=" + encodeURIComponent(market) +
          "&product_id=" + encodeURIComponent(it.id);
      });
      var hide = document.getElementById("jz-hide");
      if (hide) hide.addEventListener("click", function () {
        jzSetHidden(it, !it.hidden, function () { jzDetail(market, productId); });
      });
      window.scrollTo(0, 0);
    });
  }

  /* the site's lightbox behaviour: slide, zoom, dots, keyboard, click-out */
  function jzLightbox(item, images) {
    var i = jzState.gallery, zoomed = false;
    var box = document.createElement("div");
    box.className = "jz-lightbox";
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-label", item.name + " images");
    function draw() {
      box.innerHTML =
        '<div class="jz-lightbox__bar"><span>' + esc(item.name) + " — " + (i + 1) + " of " +
          images.length + "</span>" +
          '<button class="jz-lb-btn" data-lb="zoom">' + (zoomed ? "Fit" : "Zoom") + "</button>" +
          '<button class="jz-lb-btn" data-lb="close" aria-label="Close">✕</button></div>' +
        (images.length > 1 ? '<button class="jz-lb-nav jz-lb-nav--prev" data-lb="prev" aria-label="Previous image">‹</button>' : "") +
        '<div class="jz-lightbox__stage' + (zoomed ? " is-zoomed" : "") + '">' +
          '<img src="' + esc(images[i]) + '" alt="' + esc(item.name) + '"></div>' +
        (images.length > 1 ? '<button class="jz-lb-nav jz-lb-nav--next" data-lb="next" aria-label="Next image">›</button>' : "") +
        '<div class="jz-lightbox__dots">' + images.map(function (_, k) {
          return '<button class="jz-lb-dot' + (k === i ? " is-on" : "") +
            '" data-lb="go" data-i="' + k + '" aria-label="Image ' + (k + 1) + '"></button>';
        }).join("") + "</div>";
      box.querySelectorAll("[data-lb]").forEach(function (b) {
        b.addEventListener("click", function (e) {
          e.stopPropagation();
          var a = b.getAttribute("data-lb");
          if (a === "close") return close();
          if (a === "prev") i = (i - 1 + images.length) % images.length;
          else if (a === "next") i = (i + 1) % images.length;
          else if (a === "go") i = parseInt(b.getAttribute("data-i"), 10);
          else if (a === "zoom") zoomed = !zoomed;
          draw();
        });
      });
      var x = box.querySelector('[data-lb="close"]');
      if (x) x.focus();
    }
    function close() {
      box.remove();
      document.removeEventListener("keydown", key);
      jzState.gallery = i;
      var hash = (location.hash || "").slice(1).split("/");
      if (hash[0] === "items" && hash.length > 2) jzDetail(hash[1], decodeURIComponent(hash.slice(2).join("/")));
    }
    function key(e) {
      if (e.key === "Escape") close();
      else if (e.key === "ArrowLeft") { i = (i - 1 + images.length) % images.length; draw(); }
      else if (e.key === "ArrowRight") { i = (i + 1) % images.length; draw(); }
    }
    box.addEventListener("click", function (e) { if (e.target === box) close(); });
    document.addEventListener("keydown", key);
    draw();
    document.body.appendChild(box);
  }

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
    main.classList.toggle("admin-main--wide", name === "editor");
    main.innerHTML = '<div class="admin-loading">Loading…</div>';
    views[name](param);
  }
  window.addEventListener("hashchange", route);

  /* mobile drawer: the sidebar is off-canvas under 1024px */
  (function () {
    var side = document.getElementById("admin-side");
    var burger = document.getElementById("admin-burger");
    var scrim = document.getElementById("admin-scrim");
    if (!side || !burger || !scrim) return;
    function setOpen(open) {
      side.classList.toggle("is-open", open);
      scrim.hidden = !open;
      burger.setAttribute("aria-expanded", open ? "true" : "false");
    }
    burger.addEventListener("click", function () { setOpen(!side.classList.contains("is-open")); });
    scrim.addEventListener("click", function () { setOpen(false); });
    side.addEventListener("click", function (e) {
      if (e.target.closest("a[data-view]")) setOpen(false);   // navigating closes it
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") setOpen(false);
    });
  }());

  /* an empty section heading means every link under it is permission-hidden */
  function tidyNavGroups() {
    var nav = document.getElementById("admin-nav");
    if (!nav) return;
    var heading = null, shown = 0;
    Array.prototype.forEach.call(nav.children, function (el) {
      if (el.tagName === "B") {
        if (heading) heading.hidden = shown === 0;
        heading = el; shown = 0;
      } else if (!el.hidden) { shown++; }
    });
    if (heading) heading.hidden = shown === 0;
  }

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
    document.getElementById("me-initials").textContent =
      (me.name || "?").trim().split(/\s+/).slice(0, 2).map(function (w) { return w[0]; }).join("").toUpperCase();
    document.querySelectorAll(".admin-nav a[data-perm]").forEach(function (a) {
      if (!can(a.getAttribute("data-perm"))) a.hidden = true;
    });
    tidyNavGroups();
    route();
  });
})();
