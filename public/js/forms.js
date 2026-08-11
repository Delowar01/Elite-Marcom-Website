/* ============================================================
   ELITE MARCOM — shared secure form submission helper
   challenge token · honeypot · consent version · validation UI
   ============================================================ */
(function () {
  "use strict";
  var EM = window.EM;

  /* Lazy Cloudflare Turnstile — script loads only when the server is configured with a site key. */
  var turnstileReady = null;
  EM.turnstileToken = function (siteKey) {
    if (!turnstileReady) {
      turnstileReady = new Promise(function (resolve, reject) {
        if (window.turnstile) return resolve(window.turnstile);
        var s = document.createElement("script");
        s.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
        s.async = true;
        s.onload = function () { resolve(window.turnstile); };
        s.onerror = function () { reject(new Error("turnstile-load")); };
        document.head.appendChild(s);
      });
    }
    return turnstileReady.then(function (ts) {
      return new Promise(function (resolve, reject) {
        var host = document.createElement("div");
        host.style.position = "fixed";
        host.style.bottom = "8px";
        host.style.left = "8px";
        host.style.zIndex = "500";
        document.body.appendChild(host);
        var timer = setTimeout(function () { host.remove(); reject(new Error("turnstile-timeout")); }, 30000);
        try {
          ts.render(host, {
            sitekey: siteKey,
            callback: function (token) { clearTimeout(timer); host.remove(); resolve(token); },
            "error-callback": function () { clearTimeout(timer); host.remove(); reject(new Error("turnstile-error")); }
          });
        } catch (e) { clearTimeout(timer); host.remove(); reject(e); }
      });
    });
  };

  /* Attach standard behaviour to a form:
     opts = {
       form: HTMLFormElement,
       formKey: server form id ("contact" | "career" | "giveaway_enquiry" | ...),
       endpoint: POST url,
       multipart: bool,
       collect: fn(formData|object) -> payload object (json mode) or FormData mutation,
       validate: fn() -> true | errorMessage,
       onSuccess: fn(responseData)
     } */
  EM.bindForm = function (opts) {
    var form = opts.form;
    if (!form) return;
    var statusEl = form.querySelector(".form-status");
    var submitBtn = form.querySelector('[type="submit"]');

    function setStatus(kind, msg) {
      if (!statusEl) return;
      statusEl.className = "form-status " + (kind === "ok" ? "is-ok" : "is-err");
      statusEl.textContent = msg;
      statusEl.setAttribute("tabindex", "-1");
      statusEl.focus();
    }
    function clearStatus() {
      if (statusEl) { statusEl.className = "form-status"; statusEl.textContent = ""; }
    }

    function fieldError(input, msg) {
      var field = input.closest(".form-field");
      if (!field) return;
      field.classList.toggle("has-error", !!msg);
      var err = field.querySelector(".field-error");
      if (err && msg) err.textContent = msg;
    }

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      clearStatus();

      /* native validity first */
      var invalid = null;
      form.querySelectorAll("input, select, textarea").forEach(function (input) {
        if (input.closest(".hp-field")) return;
        var ok = input.checkValidity();
        fieldError(input, ok ? "" : (input.validationMessage || "Please check this field."));
        if (!ok && !invalid) invalid = input;
      });
      if (invalid) {
        invalid.focus();
        setStatus("err", "Please correct the highlighted fields and try again.");
        return;
      }
      if (opts.validate) {
        var v = opts.validate();
        if (v !== true) { setStatus("err", v); return; }
      }

      if (submitBtn) { submitBtn.disabled = true; submitBtn.setAttribute("aria-disabled", "true"); }
      var restore = function () {
        if (submitBtn) { submitBtn.disabled = false; submitBtn.removeAttribute("aria-disabled"); }
      };

      Promise.all([EM.getChallenge(opts.formKey), EM.securityConfig()]).then(function (res) {
        var challenge = res[0];
        var config = res[1];
        /* Cloudflare Turnstile (loaded only when the server provides a site key) */
        if (config.turnstileSiteKey) {
          return EM.turnstileToken(config.turnstileSiteKey).then(function (token) {
            return { challenge: challenge, config: config, turnstile: token };
          });
        }
        return { challenge: challenge, config: config, turnstile: null };
      }).then(function (ctx) {
        var challenge = ctx.challenge;
        var config = ctx.config;
        var hp = form.querySelector('[name="website"]');

        if (opts.multipart) {
          var fd = new FormData();
          if (opts.collect) opts.collect(fd);
          fd.append("challenge", challenge);
          fd.append("consentVersion", config.consentVersion || "2026-01");
          fd.append("website", hp ? hp.value : "");
          fd.append("sourcePage", location.pathname);
          if (ctx.turnstile) fd.append("turnstileToken", ctx.turnstile);
          return EM.api(opts.endpoint, { method: "POST", body: fd });
        }
        var payload = opts.collect ? opts.collect() : {};
        payload.challenge = challenge;
        payload.consentVersion = config.consentVersion || "2026-01";
        payload.website = hp ? hp.value : "";
        payload.sourcePage = location.pathname;
        if (ctx.turnstile) payload.turnstileToken = ctx.turnstile;
        return EM.api(opts.endpoint, { method: "POST", json: payload });
      }).then(function (r) {
        restore();
        if (r.ok && r.data && r.data.reference) {
          if (opts.onSuccess) opts.onSuccess(r.data);
          setStatus("ok", (opts.successMessage || "Thank you — your submission was received.") +
            " Reference: " + r.data.reference);
          /* keep the visitor's data only on failure; on success reset */
          form.reset();
          form.querySelectorAll(".has-error").forEach(function (f) { f.classList.remove("has-error"); });
        } else {
          var msg = (r.data && r.data.detail && typeof r.data.detail === "string")
            ? r.data.detail
            : "We could not send this right now. Your details are still in the form — please try again in a moment.";
          setStatus("err", msg);
        }
      }).catch(function () {
        restore();
        setStatus("err", "Connection problem. Your details are still in the form — please try again.");
      });
    });
  };
})();
