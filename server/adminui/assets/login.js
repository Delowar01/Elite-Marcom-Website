/* Elite Marcom admin — sign-in flow: bootstrap → password → TOTP setup/verify */
(function () {
  "use strict";
  var stage = document.getElementById("login-stage");
  var statusEl = document.getElementById("login-status");
  var card = document.getElementById("login-card");

  function esc(s) {
    var d = document.createElement("div");
    d.textContent = String(s == null ? "" : s);
    return d.innerHTML;
  }
  function setStatus(msg, isErr) {
    statusEl.textContent = msg || "";
    statusEl.className = "form-status " + (msg ? (isErr ? "is-err" : "is-ok") : "");
  }
  function api(path, body) {
    return fetch(path, {
      method: body ? "POST" : "GET",
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        return { ok: res.ok, data: data };
      });
    });
  }
  function fail(r) {
    setStatus((r.data && r.data.detail) || "Something went wrong — try again.", true);
  }

  function bootstrapForm(codeRequired) {
    stage.innerHTML =
      '<p class="login-hint">Welcome! Create the first Owner account to finish setting up the admin panel.</p>' +
      '<form id="f"><div class="form-field"><label for="b-name">Your name</label><input id="b-name" required minlength="2" maxlength="120" autocomplete="name"></div>' +
      '<div class="form-field"><label for="b-email">Email</label><input id="b-email" type="email" required maxlength="200" autocomplete="username"></div>' +
      '<div class="form-field"><label for="b-pass">Password (12+ characters)</label><input id="b-pass" type="password" required minlength="12" maxlength="200" autocomplete="new-password"></div>' +
      (codeRequired ? '<div class="form-field"><label for="b-code">Setup code</label><input id="b-code" required maxlength="120"></div>' : "") +
      '<button class="btn btn--primary" type="submit">Create Owner account</button></form>';
    document.getElementById("f").addEventListener("submit", function (e) {
      e.preventDefault();
      setStatus("");
      api("/api/admin/bootstrap", {
        name: document.getElementById("b-name").value.trim(),
        email: document.getElementById("b-email").value.trim(),
        password: document.getElementById("b-pass").value,
        setupCode: codeRequired ? document.getElementById("b-code").value.trim() : ""
      }).then(function (r) {
        if (!r.ok) return fail(r);
        setStatus("Account created — sign in to continue.", false);
        passwordForm();
      });
    });
  }

  function passwordForm() {
    stage.innerHTML =
      '<form id="f"><div class="form-field"><label for="l-email">Email</label><input id="l-email" type="email" required maxlength="200" autocomplete="username" autofocus></div>' +
      '<div class="form-field"><label for="l-pass">Password</label><input id="l-pass" type="password" required maxlength="200" autocomplete="current-password"></div>' +
      '<button class="btn btn--primary" type="submit">Sign in</button></form>';
    document.getElementById("f").addEventListener("submit", function (e) {
      e.preventDefault();
      setStatus("");
      api("/api/admin/login", {
        email: document.getElementById("l-email").value.trim(),
        password: document.getElementById("l-pass").value
      }).then(function (r) {
        if (!r.ok) return fail(r);
        if (r.data.stage === "setup") setupForm(r.data);
        else totpForm(r.data.pending);
      });
    });
  }

  function codeField(formId) {
    return '<div class="form-field"><label for="c-code">6-digit code</label>' +
      '<input id="c-code" inputmode="numeric" pattern="[0-9]{6}" required maxlength="6" autocomplete="one-time-code" autofocus></div>';
  }

  function verify(pending) {
    api("/api/admin/2fa/verify", {
      pending: pending,
      code: document.getElementById("c-code").value.trim()
    }).then(function (r) {
      if (!r.ok) return fail(r);
      location.replace("/admin");
    });
  }

  function setupForm(data) {
    stage.innerHTML =
      '<p class="login-hint">Two-factor authentication is required. Scan this code with Google Authenticator, 1Password or any authenticator app, then enter the 6-digit code.</p>' +
      '<div class="qr-box">' +
        (data.qr ? '<img src="' + esc(data.qr) + '" alt="Scan this QR code with your authenticator app">' : "") +
        "<div><code>" + esc(data.secret) + "</code><p class=\"admin-inline-note\" style=\"margin:8px 0 0;\">Manual entry key</p></div>" +
      "</div>" +
      '<form id="f">' + codeField() + '<button class="btn btn--primary" type="submit">Enable &amp; sign in</button></form>';
    document.getElementById("f").addEventListener("submit", function (e) {
      e.preventDefault();
      setStatus("");
      verify(data.pending);
    });
  }

  function totpForm(pending) {
    stage.innerHTML =
      '<p class="login-hint">Enter the 6-digit code from your authenticator app.</p>' +
      '<form id="f">' + codeField() + '<button class="btn btn--primary" type="submit">Verify</button></form>';
    document.getElementById("f").addEventListener("submit", function (e) {
      e.preventDefault();
      setStatus("");
      verify(pending);
    });
  }

  api("/api/admin/state").then(function (r) {
    card.removeAttribute("aria-busy");
    if (r.ok && r.data.needsBootstrap) bootstrapForm(r.data.setupCodeRequired);
    else passwordForm();
  });
})();
