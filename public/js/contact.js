/* ============================================================
   ELITE MARCOM — contact enquiry form
   ============================================================ */
(function () {
  "use strict";
  var EM = window.EM;
  var form = document.getElementById("contact-form");
  if (!form) return;

  EM.bindForm({
    form: form,
    formKey: "contact",
    endpoint: "/api/contact/enquiries",
    successMessage: "Enquiry received — we will come back to you personally.",
    collect: function () {
      return {
        enquiryType: form.enquiryType.value,
        fullName: form.fullName.value.trim(),
        company: form.company.value.trim(),
        email: form.email.value.trim(),
        phone: form.phone.value.trim(),
        market: form.market.value,
        service: form.service.value,
        projectDate: form.projectDate.value || null,
        projectCity: form.projectCity.value.trim(),
        message: form.message.value.trim(),
        consent: form.consent.checked
      };
    }
  });
})();
