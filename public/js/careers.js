/* ============================================================
   ELITE MARCOM — careers: open roles, filters, application
   Every role is a page of its own (/careers/<slug>); a card is
   the way in. The filters are built from the roles that exist,
   never from a fixed list that would go stale.
   ============================================================ */
(function () {
  "use strict";
  var EM = window.EM;

  var listEl = document.getElementById("role-list");
  var countEl = document.getElementById("role-count");
  var emptyEl = document.getElementById("role-empty");
  var filterWrap = document.getElementById("role-filters");
  var selectWrap = document.getElementById("role-selects");
  var roleSelect = document.getElementById("app-role");

  var jobs = [];
  var filter = { department: "all", location: "", type: "" };

  function distinct(key) {
    var seen = {};
    return jobs.map(function (j) { return j[key] || ""; })
      .filter(function (v) { return v && !seen[v] && (seen[v] = true); });
  }

  function matches(j) {
    return (filter.department === "all" || j.department === filter.department) &&
      (!filter.location || j.location === filter.location) &&
      (!filter.type || j.employmentType === filter.type);
  }

  function render() {
    if (!listEl) return;
    listEl.setAttribute("aria-busy", "false");
    listEl.innerHTML = "";
    var shown = jobs.filter(matches);
    shown.forEach(function (job) {
      var card = document.createElement("a");
      card.className = "role-card" + (job.featured ? " role-card--featured" : "");
      card.href = "/careers/" + encodeURIComponent(job.slug);
      card.setAttribute("aria-label", job.title + " — " + job.department + ". View the role.");
      if (job.featuredImage) card.classList.add("role-card--has-image");
      card.innerHTML =
        (job.featuredImage
          ? '<span class="role-card__image"><img src="' + EM.escapeHtml(job.featuredImage) + '" alt="' +
            EM.escapeHtml(job.featuredImageAlt || "") + '" loading="lazy" width="320" height="200"></span>' : "") +
        "<div>" +
          '<span class="role-card__dept">' + EM.escapeHtml(job.department || "Elite Marcom") +
          (job.featured ? ' <span class="chip chip--featured">Featured</span>' : "") + "</span>" +
          "<h3>" + EM.escapeHtml(job.title) + "</h3>" +
          '<p class="role-card__sum">' + EM.escapeHtml(job.summary || "") + "</p>" +
          '<span class="role-card__meta">' +
            '<span class="chip">' + EM.escapeHtml(job.location) + "</span>" +
            '<span class="chip chip--violet">' + EM.escapeHtml(job.employmentType) + "</span>" +
            (job.workplaceType && job.workplaceType !== "Onsite"
              ? '<span class="chip">' + EM.escapeHtml(job.workplaceType) + "</span>" : "") +
            (job.closingDate ? '<span class="chip chip--soft">Closes ' + EM.escapeHtml(job.closingDate) + "</span>" : "") +
          "</span>" +
        "</div>" +
        '<span class="role-card__go" aria-hidden="true">View job →</span>';
      listEl.appendChild(card);
    });
    if (countEl) countEl.textContent = shown.length + " open role" + (shown.length === 1 ? "" : "s");
    if (emptyEl) emptyEl.hidden = shown.length !== 0;
  }

  function buildFilters() {
    if (filterWrap) {
      var depts = distinct("department");
      filterWrap.innerHTML =
        '<button type="button" class="filter-chip" aria-pressed="true" data-role-filter="all">All roles</button>' +
        depts.map(function (d) {
          return '<button type="button" class="filter-chip" aria-pressed="false" data-role-filter="' +
            EM.escapeHtml(d) + '">' + EM.escapeHtml(d) + "</button>";
        }).join("");
      filterWrap.hidden = depts.length < 2;
    }
    if (selectWrap) {
      var locs = distinct("location"), types = distinct("employmentType");
      function sel(id, label, values) {
        if (values.length < 2) return "";
        return '<label class="role-select"><span>' + label + '</span><select id="' + id + '">' +
          '<option value="">All</option>' +
          values.map(function (v) { return '<option value="' + EM.escapeHtml(v) + '">' + EM.escapeHtml(v) + "</option>"; }).join("") +
          "</select></label>";
      }
      selectWrap.innerHTML = sel("role-loc", "Location", locs) + sel("role-type", "Type", types);
      selectWrap.hidden = !selectWrap.innerHTML;
      var loc = document.getElementById("role-loc"), type = document.getElementById("role-type");
      if (loc) loc.addEventListener("change", function () { filter.location = loc.value; render(); });
      if (type) type.addEventListener("change", function () { filter.type = type.value; render(); });
    }
  }

  if (filterWrap) {
    filterWrap.addEventListener("click", function (e) {
      var chip = e.target.closest("[data-role-filter]");
      if (!chip) return;
      filter.department = chip.getAttribute("data-role-filter");
      filterWrap.querySelectorAll(".filter-chip").forEach(function (c) {
        c.setAttribute("aria-pressed", c === chip ? "true" : "false");
      });
      render();
    });
  }

  /* load jobs — no stale browser caching */
  EM.api("/api/careers/jobs?ts=" + Date.now()).then(function (r) {
    jobs = (r.ok && r.data && Array.isArray(r.data.jobs)) ? r.data.jobs : [];
    if (roleSelect) {
      jobs.forEach(function (job) {
        var opt = document.createElement("option");
        opt.value = job.id;
        opt.textContent = job.title + " — " + job.department;
        roleSelect.insertBefore(opt, roleSelect.firstChild);
      });
      /* a job page may send someone here with the role already chosen */
      var wanted = new URLSearchParams(location.search).get("role");
      roleSelect.value = wanted && jobs.some(function (j) { return j.id === wanted; }) ? wanted : "general";
    }
    buildFilters();
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
