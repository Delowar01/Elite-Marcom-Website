/* ============================================================
   ELITE MARCOM — rental item page
   Gallery slider · lightbox · qty + days · shared rental list
   ============================================================ */
(function () {
  "use strict";
  /* Detail pages are rendered from the catalogue after load, so their share
     metadata has to be written at the same time — otherwise every product
     shares as the generic page. Indexing stays off (see the robots meta); this
     is what makes a shared link show the right product. */
  function seoMeta(opts) {
    function set(sel, attr, value) {
      if (!value) return;
      var el = document.head.querySelector(sel);
      if (!el) {
        el = document.createElement(sel.indexOf("link") === 0 ? "link" : "meta");
        if (sel.indexOf('[property=') !== -1) el.setAttribute("property", sel.split('"')[1]);
        else if (sel.indexOf("[name=") !== -1) el.setAttribute("name", sel.split('"')[1]);
        else if (sel.indexOf("[rel=") !== -1) el.setAttribute("rel", sel.split('"')[1]);
        document.head.appendChild(el);
      }
      el.setAttribute(attr, value);
    }
    document.title = opts.title;
    set('meta[name="description"]', "content", opts.description);
    set('link[rel="canonical"]', "href", opts.url);
    set('meta[property="og:title"]', "content", opts.title);
    set('meta[property="og:description"]', "content", opts.description);
    set('meta[property="og:url"]', "content", opts.url);
    set('meta[property="og:image"]', "content", opts.image);
    set('meta[name="twitter:title"]', "content", opts.title);
    set('meta[name="twitter:description"]', "content", opts.description);
    set('meta[name="twitter:image"]', "content", opts.image);
  }

  var EM = window.EM;

  var REQUEST_KEY = "em-rental-request";
  var MAX_ITEMS = 50;

  var params = new URLSearchParams(location.search);
  var market = params.get("country") === "uae" ? "uae" : "ksa";
  var itemId = String(params.get("id") || "").slice(0, 80);

  var els = {
    loading: document.getElementById("rip-loading"),
    missing: document.getElementById("rip-missing"),
    page: document.getElementById("rip"),
    track: document.getElementById("rip-track"),
    carousel: document.getElementById("rip-carousel"),
    thumbs: document.getElementById("rip-thumbs"),
    badges: document.getElementById("rip-badges"),
    title: document.getElementById("rip-title"),
    code: document.getElementById("rip-code"),
    availability: document.getElementById("rip-availability"),
    description: document.getElementById("rip-description"),
    descSection: document.getElementById("rip-desc-section"),
    specs: document.getElementById("rip-specs"),
    specsSection: document.getElementById("rip-specs-section"),
    actions: document.getElementById("rip-actions"),
    fabCount: document.getElementById("rip-fab-count")
  };

  /* ---------- shared rental list (same storage as the catalog page) ---------- */
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

  function addToRequest(p, qty, days) {
    var existing = findRequest(p.id);
    if (existing) {
      existing.qty = qty;
      existing.days = days;
      EM.toast("Rental list updated — " + p.name + " × " + qty + " for " + days + " day" + (days === 1 ? "" : "s"), "ok");
    } else {
      if (requests[market].length >= MAX_ITEMS) {
        EM.toast("A request can contain up to " + MAX_ITEMS + " items.", "err");
        return;
      }
      requests[market].push({ id: p.id, code: p.code, name: p.name, image: p.image || "",
                              market: market, qty: qty, days: days });
      EM.toast("Added to rental list — " + p.name + " × " + qty + " for " + days + " day" + (days === 1 ? "" : "s"), "ok");
    }
    saveRequests();
    var addBtn = document.querySelector("[data-add]");
    if (addBtn) addBtn.textContent = "Update rental list";
  }

  /* ---------- data ---------- */
  function loadInventory() {
    return EM.api("/api/rentals/products").then(function (r) {
      if (r.ok && r.data && Array.isArray(r.data.products)) return r.data.products;
      throw new Error("inventory");
    }).catch(function () {
      return fetch("/data/rental-products.json")
        .then(function (res) { return res.json(); })
        .then(function (raw) { return raw.products || []; });
    });
  }

  function stockFor(p) {
    var s = (p.stockByMarket && p.stockByMarket[market]);
    return typeof s === "number" ? s : 0;
  }

  function availability(p) {
    var s = stockFor(p);
    if (s > 0 && s <= 2) return { cls: "availability--low", label: "Only " + s + " available — " + market.toUpperCase() };
    if (s > 0) return { cls: "availability--in", label: s + " unit" + (s === 1 ? "" : "s") + " available — " + market.toUpperCase() };
    return { cls: "availability--out", label: "Currently unavailable" };
  }

  /* ---------- render ---------- */
  function render(p) {
    els.loading.hidden = true;
    els.loading.style.display = "none";
    els.page.hidden = false;
    seoMeta({
      title: p.name + " — Rental | Elite Marcom",
      description: (p.description || ("Rent " + p.name + " from Elite Marcom for events and exhibitions "
        + "in Saudi Arabia and the UAE.")).replace(/\s+/g, " ").slice(0, 300),
      url: location.origin + location.pathname + location.search,
      image: p.image || ""
    });

    /* gallery */
    var imgs = (p.images && p.images.length ? p.images : (p.image ? [p.image] : []));
    els.track.innerHTML = imgs.map(function (src, i) {
      return '<img src="' + EM.escapeHtml(src) + '" alt="' + EM.escapeHtml(p.name) + ' — image ' + (i + 1) + '"' +
             (i > 0 ? ' loading="lazy"' : "") + ' width="800" height="800">';
    }).join("");
    EM.carousel(els.carousel);
    lbImages = imgs;
    els.track.querySelectorAll(":scope > img").forEach(function (img, i) {
      img.classList.add("pdp__zoomable");
      img.addEventListener("click", function () { lbOpen(i); });
    });
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

    /* badges + identity */
    var badges = "";
    if (p.category) badges += '<span class="chip chip--violet">' + EM.escapeHtml(p.category) + "</span>";
    if (p.featured) badges += '<span class="chip">Featured</span>';
    badges += '<span class="chip">For rent</span>';
    els.badges.innerHTML = badges;
    els.title.textContent = p.name;
    els.code.textContent = p.code + " · " + market.toUpperCase() + " inventory";
    var av = availability(p);
    els.availability.className = "availability " + av.cls;
    els.availability.textContent = av.label;

    if (p.description) {
      els.description.textContent = p.description;
      els.descSection.hidden = false;
    } else {
      els.descSection.hidden = true;
    }

    var specs = (p.specs || []).map(function (s) { return "<li>" + EM.escapeHtml(String(s)) + "</li>"; }).join("");
    els.specs.innerHTML = specs;
    els.specsSection.hidden = !specs;

    /* actions: qty + days + add, or notify */
    var max = stockFor(p);
    var inReq = findRequest(p.id);
    els.actions.innerHTML = max > 0
      ? '<div class="labeled-control"><span>Quantity</span>' +
          '<div class="qty-control" aria-label="Quantity">' +
            '<button type="button" data-qty-minus aria-label="Decrease quantity">−</button>' +
            '<input type="number" inputmode="numeric" value="' + (inReq ? Math.max(1, parseInt(inReq.qty, 10) || 1) : 1) + '" min="1" max="' + max + '" aria-label="Requested quantity">' +
            '<button type="button" data-qty-plus aria-label="Increase quantity">+</button>' +
          "</div></div>" +
        '<div class="labeled-control"><span>Days needed</span>' +
          '<div class="qty-control" aria-label="Rental days">' +
            '<button type="button" data-days-minus aria-label="Fewer days">−</button>' +
            '<input type="number" inputmode="numeric" data-days value="' + (inReq ? Math.max(1, parseInt(inReq.days, 10) || 1) : 1) + '" min="1" max="365" aria-label="Rental days">' +
            '<button type="button" data-days-plus aria-label="More days">+</button>' +
          "</div></div>" +
        '<button class="btn btn--violet" type="button" data-add>' + (inReq ? "Update rental list" : "Add to rental list") + "</button>"
      : '<button class="btn btn--ghost" type="button" data-notify>Notify when available</button>';

    var qtyInput = els.actions.querySelector("input:not([data-days])");
    var daysInput = els.actions.querySelector("input[data-days]");
    function clampQty() {
      var v = parseInt(qtyInput.value, 10);
      if (isNaN(v) || v < 1) v = 1;
      if (v > max) { v = max; EM.toast("Quantity limited to available units (" + max + ").", ""); }
      qtyInput.value = String(v);
      return v;
    }
    function clampDays() {
      var v = parseInt(daysInput.value, 10);
      if (isNaN(v) || v < 1) v = 1;
      if (v > 365) v = 365;
      daysInput.value = String(v);
      return v;
    }
    if (qtyInput) {
      qtyInput.addEventListener("change", clampQty);
      els.actions.querySelector("[data-qty-minus]").addEventListener("click", function () {
        qtyInput.value = String(Math.max(1, clampQty() - 1));
      });
      els.actions.querySelector("[data-qty-plus]").addEventListener("click", function () {
        qtyInput.value = String(Math.min(max, clampQty() + 1));
      });
    }
    if (daysInput) {
      daysInput.addEventListener("change", clampDays);
      els.actions.querySelector("[data-days-minus]").addEventListener("click", function () {
        daysInput.value = String(Math.max(1, clampDays() - 1));
      });
      els.actions.querySelector("[data-days-plus]").addEventListener("click", function () {
        daysInput.value = String(Math.min(365, clampDays() + 1));
      });
    }
    var addBtn = els.actions.querySelector("[data-add]");
    if (addBtn) addBtn.addEventListener("click", function () { addToRequest(p, clampQty(), clampDays()); });
    var notifyBtn = els.actions.querySelector("[data-notify]");
    if (notifyBtn) notifyBtn.addEventListener("click", function () { openNotify(p); });
  }

  function showMissing() {
    els.loading.hidden = true;
    els.loading.style.display = "none";
    els.missing.hidden = false;
  }

  /* ---------- fullscreen viewer (same behaviour as the gifts page) ---------- */
  var lbImages = [];
  var lb = {
    root: document.getElementById("rip-lightbox"),
    track: document.getElementById("rip-lightbox-track"),
    count: document.getElementById("rip-lightbox-count"),
    close: document.querySelector("#rip-lightbox .lightbox__close"),
    prev: document.querySelector("#rip-lightbox .lightbox__nav--prev"),
    next: document.querySelector("#rip-lightbox .lightbox__nav--next"),
    zoom: document.querySelector("#rip-lightbox .lightbox__zoom")
  };
  function lbIndex() {
    return Math.max(0, Math.min(lbImages.length - 1,
      Math.round(lb.track.scrollLeft / Math.max(1, lb.track.clientWidth))));
  }
  function lbUpdate() {
    if (lb.count) lb.count.textContent = (lbIndex() + 1) + " / " + lbImages.length;
  }
  function lbOpen(i) {
    if (!lb.root || !lbImages.length) return;
    lb.track.innerHTML = lbImages.map(function (src, k) {
      return '<div class="lightbox__slide"><img src="' + EM.escapeHtml(src) + '" alt="Item image ' + (k + 1) + '" draggable="false"></div>';
    }).join("");
    lb.root.hidden = false;
    document.body.style.overflow = "hidden";
    var multi = lbImages.length > 1;
    if (lb.prev) lb.prev.hidden = !multi;
    if (lb.next) lb.next.hidden = !multi;
    lb.track.querySelectorAll("img").forEach(function (img) {
      img.addEventListener("click", function (e) { e.stopPropagation(); img.classList.toggle("is-zoomed"); });
    });
    lb.track.querySelectorAll(".lightbox__slide").forEach(function (slide) {
      slide.addEventListener("click", function (e) { if (e.target === slide) lbClose(); });
    });
    lb.track.scrollTo({ left: i * lb.track.clientWidth, behavior: "auto" });
    lbUpdate();
    if (lb.close) lb.close.focus();
  }
  function lbClose() {
    if (!lb.root || lb.root.hidden) return;
    lb.root.hidden = true;
    document.body.style.overflow = "";
    lb.track.innerHTML = "";
  }
  function lbGo(delta) {
    var i = Math.max(0, Math.min(lbImages.length - 1, lbIndex() + delta));
    lb.track.scrollTo({ left: i * lb.track.clientWidth, behavior: EM.reducedMotion() ? "auto" : "smooth" });
  }
  if (lb.root) {
    lb.close.addEventListener("click", lbClose);
    lb.prev.addEventListener("click", function () { lbGo(-1); });
    lb.next.addEventListener("click", function () { lbGo(1); });
    lb.zoom.addEventListener("click", function () {
      var slide = lb.track.querySelectorAll(".lightbox__slide")[lbIndex()];
      var img = slide && slide.querySelector("img");
      if (img) img.classList.toggle("is-zoomed");
    });
    lb.track.addEventListener("scroll", lbUpdate, { passive: true });
    document.addEventListener("keydown", function (e) {
      if (lb.root.hidden) return;
      if (e.key === "Escape") { e.preventDefault(); lbClose(); }
      else if (e.key === "ArrowLeft") lbGo(-1);
      else if (e.key === "ArrowRight") lbGo(1);
    });
  }

  /* ---------- availability notification ---------- */
  var notifyDlg = EM.dialog(document.getElementById("rip-notify-dialog"));
  var notifyForm = document.getElementById("rip-notify-form");
  var notifyProductEl = document.getElementById("rip-notify-product");
  var notifyProductId = null;

  function openNotify(p) {
    notifyProductId = p.id;
    notifyProductEl.textContent = p.name + " (" + p.code + ") — " + market.toUpperCase() + " inventory";
    notifyDlg.open();
  }

  EM.bindForm({
    form: notifyForm,
    formKey: "rental_notification",
    endpoint: "/api/rentals/notifications",
    successMessage: "Noted — we will tell you the moment it is available.",
    validate: function () {
      var f = notifyForm.requiredFrom.value, u = notifyForm.requiredUntil.value;
      if (f && u && u < f) return "The end date cannot be before the start date.";
      return true;
    },
    collect: function () {
      return {
        fullName: notifyForm.fullName.value.trim(),
        company: notifyForm.company.value.trim(),
        email: notifyForm.email.value.trim(),
        phone: notifyForm.phone.value.trim(),
        requiredFrom: notifyForm.requiredFrom.value || null,
        requiredUntil: notifyForm.requiredUntil.value || null,
        message: notifyForm.message.value.trim(),
        consent: notifyForm.consent.checked,
        market: market,
        productId: notifyProductId
      };
    }
  });

  /* ---------- boot ---------- */
  /* "Back" returns to the exact catalog position when the visitor came from it */
  document.querySelectorAll(".pdp__back").forEach(function (back) {
    back.addEventListener("click", function (e) {
      var cameFromCatalog = false;
      try {
        cameFromCatalog = document.referrer &&
          new URL(document.referrer).pathname === "/rental.html" && history.length > 1;
      } catch (err) { cameFromCatalog = false; }
      if (cameFromCatalog) {
        e.preventDefault();
        history.back();
      }
    });
  });

  updateFab();
  if (!itemId) {
    showMissing();
  } else {
    loadInventory().then(function (products) {
      var p = null;
      (products || []).forEach(function (x) { if (x.id === itemId) p = x; });
      if (p) render(p); else showMissing();
    }).catch(showMissing);
  }
})();
