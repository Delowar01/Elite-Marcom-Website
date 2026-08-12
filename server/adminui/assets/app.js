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

  var reqState = { kind: "", q: "", offset: 0 };

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
      var kind = reqState.kind ? "&kind=" + encodeURIComponent(reqState.kind) : "";
      var q = reqState.q ? "&q=" + encodeURIComponent(reqState.q) : "";
      api("/api/admin/requests?limit=30&offset=" + reqState.offset + kind + q).then(function (r) {
        if (!r.ok) return apiErr(r);
        var d = r.data;
        var counts = d.statusCounts || {};
        var kindOpts = Object.keys(KIND_LABELS).map(function (k) {
          return '<option value="' + k + '"' + (reqState.kind === k ? " selected" : "") + ">" +
                 esc(KIND_LABELS[k]) + "</option>";
        }).join("");
        main.innerHTML =
          '<h1 class="admin-h1">Requests inbox</h1>' +
          '<p class="admin-sub">Customer submissions decrypt on view — every view is recorded in the activity log.</p>' +
          '<div class="stat-row">' + (d.statuses || []).map(function (s) {
            return '<div class="stat-card"><b>' + esc(counts[s] || 0) + "</b><span>" + esc(STATUS_LABELS[s] || s) + "</span></div>";
          }).join("") + "</div>" +
          '<div class="admin-panel"><div class="req-filters">' +
          '<select id="rq-kind"><option value="">All types</option>' + kindOpts + "</select>" +
          '<input id="rq-q" placeholder="Search reference (e.g. GV-XXXX)" maxlength="20" value="' + esc(reqState.q) + '">' +
          '<span class="admin-inline-note">' + esc(d.total) + " request(s)</span></div>" +
          '<div class="table-scroll"><table class="admin-table"><thead>' +
          "<tr><th>Received</th><th>Reference</th><th>Type</th><th>From</th><th>Status</th><th>Notes</th><th></th></tr></thead><tbody>" +
          (d.requests || []).map(function (x) {
            var who = [x.summary.fullName, x.summary.company].filter(Boolean).join(" · ");
            return '<tr><td class="muted">' + esc(when(x.createdAt)) + "</td>" +
              "<td><strong>" + esc(x.reference) + "</strong>" + (x.hasFile ? " 📎" : "") + "</td>" +
              '<td>' + esc(KIND_LABELS[x.kind] || x.kind) + (x.summary.items ? ' <span class="muted">(' + x.summary.items + " items)</span>" : "") + "</td>" +
              "<td>" + esc(who || "—") + "</td>" +
              "<td>" + statusPill(x.status) + "</td>" +
              '<td class="muted">' + (x.noteCount || 0) + "</td>" +
              '<td><a class="btn btn--ghost btn--small" href="#requests/' + esc(x.reference) + '">Open</a></td></tr>';
          }).join("") + "</tbody></table></div>" +
          '<div class="admin-actions">' +
          (reqState.offset > 0 ? '<button class="btn btn--ghost btn--small" id="rq-prev">Newer</button>' : "") +
          (reqState.offset + 30 < d.total ? '<button class="btn btn--ghost btn--small" id="rq-next">Older</button>' : "") +
          "</div></div>";
        document.getElementById("rq-kind").addEventListener("change", function () {
          reqState.kind = this.value; reqState.offset = 0; views.requests();
        });
        document.getElementById("rq-q").addEventListener("change", function () {
          reqState.q = this.value.trim(); reqState.offset = 0; views.requests();
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
