/* ============================================================
   ELITE MARCOM — one job page: application form, copy link
   The posting itself is server-rendered; this only wires the
   parts that need a hand — the form, and the share buttons.
   ============================================================ */
(function () {
  "use strict";
  var EM = window.EM;

  /* ---------- copy link ---------- */
  document.querySelectorAll("[data-copy-link]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var url = btn.getAttribute("data-copy-link");
      (navigator.clipboard ? navigator.clipboard.writeText(url) : Promise.reject())
        .then(function () { EM.toast("Job link copied", "ok"); },
              function () { window.prompt("Copy this link:", url); });
    });
  });

  /* ---------- application form (only on an open job) ---------- */
  var form = document.getElementById("application-form");
  if (!form) return;
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
        if (f.type !== "application/pdf" && !/\.pdf$/i.test(f.name)) return "The CV must be a PDF file.";
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
      /* the role is this page's job — fixed, never a choice the visitor
         could get wrong */
      fd.append("roleId", form.getAttribute("data-job-id"));
      fd.append("portfolioUrl", form.portfolioUrl.value.trim());
      fd.append("introduction", form.introduction.value.trim());
      fd.append("consent", form.consent.checked ? "yes" : "");
      if (cvInput && cvInput.files && cvInput.files.length) fd.append("cv", cvInput.files[0]);
    }
  });
})();
