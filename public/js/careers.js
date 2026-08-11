/* ============================================================
   ELITE MARCOM — careers: jobs list, role detail, application
   ============================================================ */
(function () {
  "use strict";
  var EM = window.EM;

  var listEl = document.getElementById("role-list");
  var countEl = document.getElementById("role-count");
  var emptyEl = document.getElementById("role-empty");
  var filterWrap = document.getElementById("role-filters");
  var roleSelect = document.getElementById("app-role");
  var dialogScrim = document.getElementById("role-dialog");
  var dlg = dialogScrim ? EM.dialog(dialogScrim) : null;
  var dlgContent = document.getElementById("role-dialog-content");

  var jobs = [];
  var activeFilter = "all";

  function render() {
    if (!listEl) return;
    listEl.setAttribute("aria-busy", "false");
    listEl.innerHTML = "";
    var shown = jobs.filter(function (j) { return activeFilter === "all" || j.track === activeFilter; });
    shown.forEach(function (job) {
      var card = document.createElement("button");
      card.type = "button";
      card.className = "role-card";
      card.setAttribute("aria-label", job.title + " — " + job.department + ". View role details.");
      card.innerHTML =
        "<div>" +
          '<span class="role-card__dept">' + EM.escapeHtml(job.department) + "</span>" +
          "<h3>" + EM.escapeHtml(job.title) + "</h3>" +
          '<p class="role-card__sum">' + EM.escapeHtml(job.summary) + "</p>" +
          '<span class="role-card__meta">' +
            '<span class="chip">' + EM.escapeHtml(job.location) + "</span>" +
            '<span class="chip chip--violet">' + EM.escapeHtml(job.employmentType) + "</span>" +
          "</span>" +
        "</div>" +
        '<span class="role-card__go" aria-hidden="true">Details →</span>';
      card.addEventListener("click", function () { openRole(job); });
      listEl.appendChild(card);
    });
    if (countEl) countEl.textContent = shown.length + " open role" + (shown.length === 1 ? "" : "s");
    if (emptyEl) emptyEl.hidden = shown.length !== 0;
  }

  function openRole(job) {
    if (!dlg) return;
    var reqs = (job.requirements || []).map(function (r) {
      return "<li>" + EM.escapeHtml(r) + "</li>";
    }).join("");
    dlgContent.innerHTML =
      '<div class="career-dialog__grid">' +
        '<img src="' + job.poster + '" alt="" width="640" height="800">' +
        "<div>" +
          '<span class="role-card__dept">' + EM.escapeHtml(job.department) + "</span>" +
          '<h2 id="role-dialog-title" style="margin-top:6px;">' + EM.escapeHtml(job.title) + "</h2>" +
          "<p>" + EM.escapeHtml(job.summary) + "</p>" +
          '<p class="role-card__meta" style="display:flex;gap:8px;flex-wrap:wrap;">' +
            '<span class="chip">' + EM.escapeHtml(job.location) + "</span>" +
            '<span class="chip chip--violet">' + EM.escapeHtml(job.employmentType) + "</span></p>" +
          (reqs ? "<h3 style=\"margin-top:20px;\">What you'll bring</h3><ul class=\"service-points\">" + reqs + "</ul>" : "") +
          '<button class="btn btn--primary" type="button" data-apply-role="' + EM.escapeHtml(job.id) + '" style="margin-top:22px;">Apply for this role</button>' +
        "</div>" +
      "</div>";
    dlgContent.querySelector("[data-apply-role]").addEventListener("click", function () {
      dlg.close();
      if (roleSelect) roleSelect.value = job.id;
      var heading = document.getElementById("apply-h");
      if (heading) {
        heading.setAttribute("tabindex", "-1");
        heading.scrollIntoView({ behavior: EM.reducedMotion() ? "auto" : "smooth", block: "start" });
        heading.focus({ preventScroll: true });
      }
    });
    dlg.open();
  }

  if (filterWrap) {
    filterWrap.addEventListener("click", function (e) {
      var chip = e.target.closest("[data-role-filter]");
      if (!chip) return;
      activeFilter = chip.getAttribute("data-role-filter");
      filterWrap.querySelectorAll(".filter-chip").forEach(function (c) {
        c.setAttribute("aria-pressed", c === chip ? "true" : "false");
      });
      render();
    });
  }

  /* load jobs — no stale browser caching */
  EM.api("/api/careers/jobs?ts=" + Date.now()).then(function (r) {
    if (r.ok && r.data && Array.isArray(r.data.jobs)) {
      jobs = r.data.jobs;
    } else {
      jobs = [];
    }
    if (roleSelect) {
      jobs.forEach(function (job) {
        var opt = document.createElement("option");
        opt.value = job.id;
        opt.textContent = job.title + " — " + job.department;
        roleSelect.insertBefore(opt, roleSelect.firstChild);
      });
      roleSelect.value = "general";
    }
    render();
  }).catch(function () {
    jobs = [];
    render();
  });

  /* ---------- application form ---------- */
  var form = document.getElementById("application-form");
  if (form) {
    var cvInput = document.getElementById("app-cv");
    EM.bindForm({
      form: form,
      formKey: "career",
      endpoint: "/api/careers/applications",
      multipart: true,
      successMessage: "Application received — thank you. Our team reviews every submission personally.",
      validate: function () {
        if (cvInput && cvInput.files && cvInput.files.length) {
          var f = cvInput.files[0];
          if (f.type !== "application/pdf" && !/\.pdf$/i.test(f.name)) {
            return "The CV must be a PDF file.";
          }
          if (f.size > 5 * 1024 * 1024) return "The CV must be 5 MB or smaller.";
          if (f.size < 100) return "The CV file appears to be empty.";
        }
        return true;
      },
      collect: function (fd) {
        fd.append("fullName", form.fullName.value.trim());
        fd.append("email", form.email.value.trim());
        fd.append("phone", form.phone.value.trim());
        fd.append("location", form.location.value.trim());
        fd.append("roleId", form.roleId.value);
        fd.append("portfolioUrl", form.portfolioUrl.value.trim());
        fd.append("introduction", form.introduction.value.trim());
        fd.append("consent", form.consent.checked ? "yes" : "");
        if (cvInput && cvInput.files && cvInput.files.length) fd.append("cv", cvInput.files[0]);
      }
    });
  }
})();
