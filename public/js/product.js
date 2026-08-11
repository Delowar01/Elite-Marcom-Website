/* ============================================================
   ELITE MARCOM — corporate gift product page
   Full gallery slider · branding options · printing manual ·
   add to request (shared localStorage list) · notify workflow
   ============================================================ */
(function () {
  "use strict";
  var EM = window.EM;

  var REQUEST_KEY = "em-giveaway-request";
  var MAX_ITEMS = 50;

  var params = new URLSearchParams(location.search);
  var market = params.get("country") === "uae" ? "uae" : "ksa";
  var productId = String(params.get("id") || "").slice(0, 80);

  var els = {
    loading: document.getElementById("pdp-loading"),
    missing: document.getElementById("pdp-missing"),
    pdp: document.getElementById("pdp"),
    track: document.getElementById("pdp-track"),
    carousel: document.getElementById("pdp-carousel"),
    thumbs: document.getElementById("pdp-thumbs"),
    badges: document.getElementById("pdp-badges"),
    title: document.getElementById("pdp-title"),
    code: document.getElementById("pdp-code"),
    availability: document.getElementById("pdp-availability"),
    description: document.getElementById("pdp-description"),
    facts: document.getElementById("pdp-facts"),
    brandingSection: document.getElementById("pdp-branding-section"),
    branding: document.getElementById("pdp-branding"),
    actions: document.getElementById("pdp-actions"),
    fabCount: document.getElementById("pdp-fab-count")
  };

  /* ---------- shared request list (same storage as the catalog page) ---------- */
  function loadRequests() {
    var all = EM.store.get(REQUEST_KEY, {});
    if (!all || typeof all !== "object") all = {};
    ["ksa", "uae"].forEach(function (m) {
      if (!Array.isArray(all[m])) all[m] = [];
    });
    return all;
  }
  var requests = loadRequests();
  function findRequest(id) {
    var out = null;
    requests[market].forEach(function (it) { if (it.id === id) out = it; });
    return out;
  }
  function updateFab() {
    var n = requests[market].length;
    document.querySelectorAll(".request-fab").forEach(function (fab) { fab.hidden = n === 0; });
    if (els.fabCount) els.fabCount.textContent = String(n);
  }
  function saveRequests() { EM.store.set(REQUEST_KEY, requests); updateFab(); }

  function addToRequest(p, qty) {
    var existing = findRequest(p.id);
    if (existing) {
      existing.qty = qty;
      EM.toast("Request updated — " + p.name + " × " + qty, "ok");
    } else {
      if (requests[market].length >= MAX_ITEMS) {
        EM.toast("A request can contain up to " + MAX_ITEMS + " items.", "err");
        return;
      }
      requests[market].push({ id: p.id, code: p.code, name: p.name, image: p.image || "", market: market, qty: qty });
      EM.toast("Added to request — " + p.name + " × " + qty, "ok");
    }
    saveRequests();
    var addBtn = document.querySelector("[data-add]");
    if (addBtn) addBtn.textContent = "Update request";
  }

  /* ---------- load product ---------- */
  function normalizePreview(raw) {
    return (raw.products || []).filter(function (p) { return p && p.market === market; });
  }

  function loadCatalog() {
    return EM.api("/api/giveaways/products?country=" + market).then(function (r) {
      if (r.ok && r.data && Array.isArray(r.data.products)) return r.data.products;
      throw new Error("catalog");
    }).catch(function () {
      return fetch("/data/giveaway-preview-products.json")
        .then(function (res) { return res.json(); })
        .then(normalizePreview);
    });
  }

  function availability(p) {
    var s = p.stock || {};
    if (s.available > 0 && s.available <= 20) return { cls: "availability--low", label: "Low stock — " + s.available + " left" };
    if (s.available > 0) return { cls: "availability--in", label: s.available + " in stock — " + market.toUpperCase() };
    if (s.incoming > 0) return { cls: "availability--incoming", label: "Incoming" + (s.incomingDate ? " — " + s.incomingDate : "") };
    return { cls: "availability--out", label: "Out of stock" };
  }

  function render(p) {
    els.loading.hidden = true;
    els.loading.style.display = "none";
    els.pdp.hidden = false;
    document.title = p.name + " — Corporate Gifts | Elite Marcom";

    /* gallery: every image from the API, slideable, with auto-hide arrows */
    var imgs = (p.images && p.images.length ? p.images : (p.image ? [p.image] : []));
    els.track.innerHTML = imgs.map(function (src, i) {
      return '<img src="' + EM.escapeHtml(src) + '" alt="' + EM.escapeHtml(p.name) + ' — image ' + (i + 1) + '"' +
             (i > 0 ? ' loading="lazy"' : "") + ' width="800" height="800">';
    }).join("");
    EM.carousel(els.carousel);
    if (imgs.length > 1) {
      els.thumbs.innerHTML = imgs.map(function (src, i) {
        return '<button type="button" class="' + (i === 0 ? "is-active" : "") + '" aria-label="Show image ' + (i + 1) + '">' +
               '<img src="' + EM.escapeHtml(src) + '" alt="" loading="lazy" width="72" height="72"></button>';
      }).join("");
      var thumbBtns = els.thumbs.querySelectorAll("button");
      thumbBtns.forEach(function (btn, i) {
        btn.addEventListener("click", function () {
          els.track.scrollTo({ left: i * els.track.clientWidth, behavior: EM.reducedMotion() ? "auto" : "smooth" });
        });
      });
      els.track.addEventListener("scroll", function () {
        var idx = Math.round(els.track.scrollLeft / Math.max(1, els.track.clientWidth));
        thumbBtns.forEach(function (b, i) { b.classList.toggle("is-active", i === idx); });
      }, { passive: true });
    }

    /* badges + core details */
    var badges = "";
    if (p.categories && p.categories.length) badges += '<span class="chip">' + EM.escapeHtml(p.categories[0]) + "</span>";
    if (p.isNew) badges += '<span class="chip chip--violet">New</span>';
    if (p.sustainable) badges += '<span class="chip chip--orange">Sustainable</span>';
    if (p.luxury) badges += '<span class="chip">Luxury</span>';
    els.badges.innerHTML = badges;
    els.title.textContent = p.name;
    els.code.textContent = p.code + " · " + market.toUpperCase() + (p.brand ? " · " + p.brand : "");
    var av = availability(p);
    els.availability.className = "availability " + av.cls;
    els.availability.textContent = av.label;
    els.description.textContent = p.description || "";

    var facts = [];
    if (p.color) facts.push(["Colour", p.color]);
    if (p.options && p.options.length) facts.push(["Options", p.options.join(", ")]);
    if (p.unitsPerCarton) facts.push(["Units per carton", p.unitsPerCarton]);
    if (p.cartonDimensions) facts.push(["Carton dimensions", p.cartonDimensions]);
    if (p.cartonWeight) facts.push(["Carton weight", p.cartonWeight]);
    if (p.hsCode) facts.push(["HS code", p.hsCode]);
    if (p.categories && p.categories.length > 1) facts.push(["Categories", p.categories.join(", ")]);
    els.facts.innerHTML = facts.map(function (f) {
      return "<div><dt>" + EM.escapeHtml(String(f[0])) + "</dt><dd>" + EM.escapeHtml(String(f[1])) + "</dd></div>";
    }).join("");

    /* actions: qty + add, or notify; printing manual when the supplier provides it */
    var canOrder = p.stock && p.stock.available > 0;
    var inReq = findRequest(p.id);
    var manualBtn = p.printingManual
      ? '<a class="btn btn--ghost btn--manual" href="' + EM.escapeHtml(p.printingManual) + '" target="_blank" rel="noopener">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 3v12m0 0 4-4m-4 4-4-4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/></svg>' +
        "Download Printing Manual</a>"
      : "";
    els.actions.innerHTML =
      (canOrder
        ? '<div class="qty-control" aria-label="Quantity">' +
            '<button type="button" data-qty-minus aria-label="Decrease quantity">−</button>' +
            '<input type="number" inputmode="numeric" value="' + (inReq ? inReq.qty : 1) + '" min="1" max="' + p.stock.available + '" aria-label="Requested quantity">' +
            '<button type="button" data-qty-plus aria-label="Increase quantity">+</button>' +
          "</div>" +
          '<button class="btn btn--primary" type="button" data-add>' + (inReq ? "Update request" : "Add to request") + "</button>"
        : '<button class="btn btn--violet" type="button" data-notify>Notify when available</button>') +
      manualBtn;

    var qtyInput = els.actions.querySelector(".qty-control input");
    var max = (p.stock && p.stock.available) || 1;
    function clamp() {
      var v = parseInt(qtyInput.value, 10);
      if (isNaN(v) || v < 1) v = 1;
      if (v > max) { v = max; EM.toast("Quantity limited to available stock (" + max + ").", ""); }
      qtyInput.value = String(v);
      return v;
    }
    var minus = els.actions.querySelector("[data-qty-minus]");
    var plus = els.actions.querySelector("[data-qty-plus]");
    if (minus) minus.addEventListener("click", function () { qtyInput.value = String(Math.max(1, clamp() - 1)); });
    if (plus) plus.addEventListener("click", function () { qtyInput.value = String(Math.min(max, clamp() + 1)); });
    var addBtn = els.actions.querySelector("[data-add]");
    if (addBtn) addBtn.addEventListener("click", function () { addToRequest(p, clamp()); });
    var notifyBtn = els.actions.querySelector("[data-notify]");
    if (notifyBtn) notifyBtn.addEventListener("click", function () { openNotify(p); });

    /* branding options — resolved server-side for known products only */
    EM.api("/api/giveaways/branding?country=" + market + "&product_id=" + encodeURIComponent(p.id)).then(function (r) {
      if (r.ok && r.data && Array.isArray(r.data.branding) && r.data.branding.length) {
        els.branding.innerHTML = r.data.branding.map(function (b) {
          var bits = [b.area, b.method, b.dimensions].filter(Boolean).map(String).map(EM.escapeHtml);
          return "<li>" + bits.join(" · ") + "</li>";
        }).join("");
        els.brandingSection.hidden = false;
      }
    }).catch(function () { /* branding advice arrives with the proposal */ });
  }

  function showMissing() {
    els.loading.hidden = true;
    els.loading.style.display = "none";
    els.missing.hidden = false;
  }

  /* ---------- availability notification ---------- */
  var notifyDlg = EM.dialog(document.getElementById("pdp-notify-dialog"));
  var notifyForm = document.getElementById("pdp-notify-form");
  var notifyProductEl = document.getElementById("pdp-notify-product");
  var notifyProductId = null;

  function openNotify(p) {
    notifyProductId = p.id;
    notifyProductEl.textContent = p.name + " (" + p.code + ") — " + market.toUpperCase() + " catalog";
    notifyDlg.open();
  }

  EM.bindForm({
    form: notifyForm,
    formKey: "giveaway_notification",
    endpoint: "/api/giveaways/notifications",
    successMessage: "Noted — we will tell you the moment it is available.",
    collect: function () {
      return {
        fullName: notifyForm.fullName.value.trim(),
        company: notifyForm.company.value.trim(),
        email: notifyForm.email.value.trim(),
        phone: notifyForm.phone.value.trim(),
        message: notifyForm.message.value.trim(),
        consent: notifyForm.consent.checked,
        market: market,
        productId: notifyProductId
      };
    }
  });

  /* ---------- boot ---------- */
  updateFab();
  if (!productId) {
    showMissing();
  } else {
    loadCatalog().then(function (products) {
      var p = null;
      (products || []).forEach(function (x) { if (x.id === productId) p = x; });
      if (p) render(p); else showMissing();
    }).catch(showMissing);
  }
})();
