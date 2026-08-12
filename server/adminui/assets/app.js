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
          '<p class="admin-sub">Everything on the public site is running. Requests and Jasani controls arrive in Phase 1.</p>' +
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
    var name = (location.hash || "#dashboard").slice(1);
    if (!views[name]) name = "dashboard";
    var link = document.querySelector('.admin-nav a[data-view="' + name + '"]');
    if (link && link.hidden) name = "dashboard";
    document.querySelectorAll(".admin-nav a").forEach(function (a) {
      a.classList.toggle("is-active", a.getAttribute("data-view") === name);
    });
    main.innerHTML = '<div class="admin-loading">Loading…</div>';
    views[name]();
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
