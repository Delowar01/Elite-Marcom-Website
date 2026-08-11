/* ============================================================
   ELITE MARCOM — rental: availability + request workflow
   No prices · no booking · request → private confirmation
   ============================================================ */
(function () {
  "use strict";
  var EM = window.EM;

  var MARKET_KEY = "em-rental-market";
  var REQUEST_KEY = "em-rental-request"; /* { ksa: [...], uae: [...] } */
  var MAX_ITEMS = 50;
  var REFRESH_MS = 5 * 60 * 1000;

  var grid = document.getElementById("rent-grid");
  if (!grid) return;

  var els = {
    state: document.getElementById("rent-data-state"),
    count: document.getElementById("rent-count"),
    empty: document.getElementById("rent-empty"),
    search: document.getElementById("rent-search"),
    category: document.getElementById("rent-category"),
    sort: document.getElementById("rent-sort"),
    clear: document.getElementById("rent-clear"),
    fabCount: document.getElementById("rent-fab-count")
  };

  var market = EM.store.get(MARKET_KEY, "ksa");
  if (market !== "ksa" && market !== "uae") market = "ksa";
  var items = [];
  var itemById = {};
  var flags = {};
  var isFallback = false;

  /* ---------- request lists (separate per market) ---------- */
  function loadRequests() {
    var all = EM.store.get(REQUEST_KEY, {});
    if (!all || typeof all !== "object") all = {};
    ["ksa", "uae"].forEach(function (m) {
      if (!Array.isArray(all[m])) all[m] = [];
      all[m] = all[m].filter(function (it) {
        return it && typeof it.id === "string" && typeof it.qty === "number" && it.qty >= 1 && it.market === m;
      }).slice(0, MAX_ITEMS).map(function (it) {
        return { id: String(it.id).slice(0, 80), code: String(it.code || "").slice(0, 80),
                 name: String(it.name || "").slice(0, 200), image: String(it.image || "").slice(0, 500),
                 market: m, qty: Math.min(1000, Math.floor(it.qty)) };
      });
    });
    return all;
  }
  var requests = loadRequests();
  function saveRequests() { EM.store.set(REQUEST_KEY, requests); updateFab(); }
  function marketList() { return requests[market]; }
  function findRequest(id) {
    var out = null;
    marketList().forEach(function (it) { if (it.id === id) out = it; });
    return out;
  }
  function updateFab() {
    var n = marketList().length;
    document.querySelectorAll(".request-fab").forEach(function (fab) { fab.hidden = n === 0; });
    if (els.fabCount) els.fabCount.textContent = String(n);
  }

  function stockFor(p) {
    var s = (p.stockByMarket && p.stockByMarket[market]);
    return typeof s === "number" ? s : 0;
  }

  function reconcile() {
    var changed = false;
    requests[market] = marketList().filter(function (it) {
      var p = itemById[it.id];
      if (!p) { changed = true; return false; }
      var avail = stockFor(p);
      if (avail <= 0) { changed = true; return false; }
      if (it.qty > avail) { it.qty = avail; changed = true; }
      it.name = p.name; it.code = p.code; it.image = p.image || "";
      return true;
    });
    if (changed) { saveRequests(); EM.toast("Your rental list was updated to match current availability.", ""); }
    updateFab();
  }

  /* ---------- data ---------- */
  function setDataState(state, label) {
    if (!els.state) return;
    els.state.className = "data-state data-state--" + state;
    els.state.textContent = label;
  }

  function loadInventory(silent) {
    if (!silent) {
      setDataState("connecting", "Connecting");
      grid.setAttribute("aria-busy", "true");
      grid.innerHTML = new Array(8).fill(
        '<div class="skeleton-card"><div class="sk sk-media"></div><div class="sk sk-line" style="width:70%;"></div><div class="sk sk-line" style="width:45%;"></div></div>'
      ).join("");
    }
    EM.api("/api/rentals/products").then(function (r) {
      if (r.ok && r.data && Array.isArray(r.data.products)) {
        items = r.data.products;
        isFallback = false;
        setDataState("live", "Live inventory");
        finishLoad();
      } else {
        throw new Error("inventory");
      }
    }).catch(function () {
      /* controlled fallback — never labelled live */
      fetch("/data/rental-products.json").then(function (res) { return res.json(); }).then(function (raw) {
        items = raw.products || [];
        isFallback = true;
        setDataState("cache", "Latest cached data");
        finishLoad();
      }).catch(function () {
        items = [];
        isFallback = true;
        setDataState("cache", "Inventory unavailable");
        finishLoad();
      });
    });
  }

  function finishLoad() {
    itemById = {};
    items.forEach(function (p) { itemById[p.id] = p; });
    buildCategories();
    reconcile();
    render();
  }

  /* silent refresh every five minutes */
  setInterval(function () {
    if (!document.hidden) loadInventory(true);
  }, REFRESH_MS);

  function buildCategories() {
    if (!els.category) return;
    var cats = {};
    items.forEach(function (p) { if (p.category) cats[p.category] = 1; });
    var current = els.category.value;
    els.category.innerHTML = '<option value="">All categories</option>' +
      Object.keys(cats).sort().map(function (c) {
        return '<option value="' + EM.escapeHtml(c) + '">' + EM.escapeHtml(c) + "</option>";
      }).join("");
    els.category.value = current;
    if (els.category.value !== current) els.category.value = "";
  }

  function filtered() {
    var q = (els.search && els.search.value || "").trim().toLowerCase();
    var cat = els.category ? els.category.value : "";
    var out = items.filter(function (p) {
      if (q) {
        var hay = (p.name + " " + p.code + " " + (p.category || "") + " " + (p.description || "") + " " +
                   (p.tags || []).join(" ")).toLowerCase();
        if (hay.indexOf(q) === -1) return false;
      }
      if (cat && p.category !== cat) return false;
      if (flags.available && stockFor(p) <= 0) return false;
      if (flags.featured && !p.featured) return false;
      return true;
    });
    var sort = els.sort ? els.sort.value : "featured";
    if (sort === "name-asc") out.sort(function (a, b) { return a.name.localeCompare(b.name); });
    else if (sort === "name-desc") out.sort(function (a, b) { return b.name.localeCompare(a.name); });
    else if (sort === "stock") out.sort(function (a, b) { return stockFor(b) - stockFor(a); });
    else out.sort(function (a, b) { return (b.featured ? 1 : 0) - (a.featured ? 1 : 0); });
    return out;
  }

  /* ---------- rendering ---------- */
  function availability(p) {
    var s = stockFor(p);
    if (s > 0 && s <= 2) return { cls: "availability--low", label: "Only " + s + " available" };
    if (s > 0) return { cls: "availability--in", label: s + " unit" + (s === 1 ? "" : "s") + " available" };
    return { cls: "availability--out", label: "Currently unavailable" };
  }

  function cardHtml(p) {
    var av = availability(p);
    var inReq = findRequest(p.id);
    var max = stockFor(p);
    var canOrder = max > 0;
    return (
      '<div class="product-card__media">' +
        (p.image ? '<img src="' + EM.escapeHtml(p.image) + '" alt="" loading="lazy" width="400" height="300">' : "") +
        '<div class="product-card__badges">' +
          (p.category ? '<span class="chip">' + EM.escapeHtml(p.category) + "</span>" : "") +
          (p.featured ? '<span class="chip chip--orange">Featured</span>' : "") +
        "</div>" +
      "</div>" +
      '<div class="product-card__body">' +
        '<span class="product-card__code">' + EM.escapeHtml(p.code) + " · " + market.toUpperCase() + "</span>" +
        '<h3 class="product-card__name">' + EM.escapeHtml(p.name) + "</h3>" +
        '<span class="availability ' + av.cls + '">' + EM.escapeHtml(av.label) + "</span>" +
        '<div class="product-card__actions">' +
          (canOrder
            ? '<div class="qty-control" aria-label="Quantity">' +
                '<button type="button" data-qty-minus aria-label="Decrease quantity">−</button>' +
                '<input type="number" inputmode="numeric" value="' + (inReq ? inReq.qty : 1) + '" min="1" max="' + max + '" aria-label="Requested quantity">' +
                '<button type="button" data-qty-plus aria-label="Increase quantity">+</button>' +
              "</div>" +
              '<button class="btn btn--primary btn--small" type="button" data-add>' + (inReq ? "Update request" : "Add to request") + "</button>"
            : '<button class="btn btn--violet btn--small" type="button" data-notify>Notify when available</button>') +
          '<button class="btn btn--ghost btn--small" type="button" data-details>View details</button>' +
        "</div>" +
      "</div>");
  }

  function render() {
    grid.setAttribute("aria-busy", "false");
    var list = filtered();
    grid.innerHTML = "";
    list.forEach(function (p) {
      var card = document.createElement("article");
      card.className = "product-card";
      card.innerHTML = cardHtml(p);
      bindCard(card, p);
      grid.appendChild(card);
    });
    if (els.count) {
      var availCount = items.filter(function (p) { return stockFor(p) > 0; }).length;
      els.count.textContent = items.length + " catalog items · " + availCount + " available now";
    }
    if (els.empty) els.empty.hidden = list.length !== 0;
  }

  function clampQty(input, max) {
    var v = parseInt(input.value, 10);
    if (isNaN(v) || v < 1) v = 1;
    if (v > max) { v = max; EM.toast("Quantity limited to available units (" + max + ").", ""); }
    input.value = String(v);
    return v;
  }

  function bindCard(card, p) {
    var qtyInput = card.querySelector(".qty-control input");
    var max = stockFor(p) || 1;
    card.querySelectorAll("[data-qty-minus]").forEach(function (b) {
      b.addEventListener("click", function () { qtyInput.value = String(Math.max(1, clampQty(qtyInput, max) - 1)); });
    });
    card.querySelectorAll("[data-qty-plus]").forEach(function (b) {
      b.addEventListener("click", function () { qtyInput.value = String(Math.min(max, clampQty(qtyInput, max) + 1)); });
    });
    var addBtn = card.querySelector("[data-add]");
    if (addBtn) addBtn.addEventListener("click", function () {
      addToRequest(p, clampQty(qtyInput, max));
      addBtn.textContent = "Update request";
    });
    var detBtn = card.querySelector("[data-details]");
    if (detBtn) detBtn.addEventListener("click", function () { openDetail(p); });
    var notBtn = card.querySelector("[data-notify]");
    if (notBtn) notBtn.addEventListener("click", function () { openNotify(p); });
  }

  function addToRequest(p, qty) {
    var existing = findRequest(p.id);
    if (existing) {
      existing.qty = qty;
      EM.toast("Rental list updated — " + p.name + " × " + qty, "ok");
    } else {
      if (marketList().length >= MAX_ITEMS) {
        EM.toast("A request can contain up to " + MAX_ITEMS + " items.", "err");
        return;
      }
      requests[market].push({ id: p.id, code: p.code, name: p.name, image: p.image || "", market: market, qty: qty });
      EM.toast("Added to rental list — " + p.name + " × " + qty, "ok");
    }
    saveRequests();
  }

  /* ---------- market switch ---------- */
  document.querySelectorAll(".market-switch [data-market]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var m = btn.getAttribute("data-market");
      if (m === market) return;
      market = m;
      EM.store.set(MARKET_KEY, market);
      document.querySelectorAll(".market-switch [data-market]").forEach(function (b) {
        b.setAttribute("aria-pressed", b.getAttribute("data-market") === market ? "true" : "false");
      });
      reconcile();
      render();
      updateFab();
    });
    btn.setAttribute("aria-pressed", btn.getAttribute("data-market") === market ? "true" : "false");
  });

  /* ---------- controls ---------- */
  var searchTimer = null;
  if (els.search) els.search.addEventListener("input", function () {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(render, 220);
  });
  [els.category, els.sort].forEach(function (sel) {
    if (sel) sel.addEventListener("change", render);
  });
  document.querySelectorAll(".catalog-toolbar [data-flag]").forEach(function (chip) {
    chip.addEventListener("click", function () {
      var key = chip.getAttribute("data-flag");
      flags[key] = !flags[key];
      chip.setAttribute("aria-pressed", flags[key] ? "true" : "false");
      render();
    });
  });
  if (els.clear) els.clear.addEventListener("click", function () {
    if (els.search) els.search.value = "";
    if (els.category) els.category.value = "";
    flags = {};
    document.querySelectorAll(".catalog-toolbar [data-flag]").forEach(function (c) { c.setAttribute("aria-pressed", "false"); });
    render();
  });
  document.querySelectorAll(".view-toggle [data-view]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      grid.classList.toggle("is-list", btn.getAttribute("data-view") === "list");
      document.querySelectorAll(".view-toggle [data-view]").forEach(function (b) {
        b.setAttribute("aria-pressed", b === btn ? "true" : "false");
      });
    });
  });

  /* ---------- detail drawer ---------- */
  var detailDrawer = EM.drawer(document.getElementById("rent-detail-drawer"), document.getElementById("rent-detail-scrim"));
  var detailBody = document.getElementById("rent-detail-body");

  function openDetail(p) {
    var av = availability(p);
    var imgs = (p.images && p.images.length ? p.images : (p.image ? [p.image] : []));
    var gallery = imgs.map(function (src, i) {
      return '<figure class="media-frame" style="aspect-ratio:4/3;margin-bottom:10px;"><img src="' + EM.escapeHtml(src) + '" alt="' + EM.escapeHtml(p.name) + ' — image ' + (i + 1) + '" loading="lazy"></figure>';
    }).join("");
    var specs = (p.specs || []).map(function (s) { return "<li>" + EM.escapeHtml(s) + "</li>"; }).join("");
    var inReq = findRequest(p.id);
    var max = stockFor(p);
    detailBody.innerHTML =
      gallery +
      '<span class="product-card__code">' + EM.escapeHtml(p.code) + " · " + market.toUpperCase() + "</span>" +
      "<h3 style=\"margin:6px 0 8px;\">" + EM.escapeHtml(p.name) + "</h3>" +
      (p.category ? '<span class="chip">' + EM.escapeHtml(p.category) + "</span> " : "") +
      ((p.tags || []).slice(0, 6).map(function (t) { return '<span class="chip">' + EM.escapeHtml(t) + "</span>"; }).join(" ")) +
      '<p style="margin-top:12px;"><span class="availability ' + av.cls + '">' + EM.escapeHtml(av.label) + "</span></p>" +
      (p.description ? "<p>" + EM.escapeHtml(p.description) + "</p>" : "") +
      (specs ? "<h4 style=\"margin:14px 0 8px;\">Specifications</h4><ul class=\"service-points\">" + specs + "</ul>" : "") +
      '<div class="product-card__actions" style="margin-top:18px;">' +
        (max > 0
          ? '<div class="qty-control" aria-label="Quantity">' +
              '<button type="button" data-qty-minus aria-label="Decrease quantity">−</button>' +
              '<input type="number" inputmode="numeric" value="' + (inReq ? inReq.qty : 1) + '" min="1" max="' + max + '" aria-label="Requested quantity">' +
              '<button type="button" data-qty-plus aria-label="Increase quantity">+</button>' +
            "</div>" +
            '<button class="btn btn--primary btn--small" type="button" data-add>' + (inReq ? "Update request" : "Add to request") + "</button>"
          : '<button class="btn btn--violet btn--small" type="button" data-notify>Notify when available</button>') +
      "</div>";
    bindCard(detailBody, p);
    detailDrawer.open();
  }

  /* ---------- request drawer ---------- */
  var requestDrawer = EM.drawer(document.getElementById("rent-request-drawer"), document.getElementById("rent-request-scrim"));
  var requestBody = document.getElementById("rent-request-body");

  function renderRequest() {
    var list = marketList();
    if (!list.length) {
      requestBody.innerHTML = '<div class="empty-state"><h3>Your rental list is empty</h3><p>Browse the ' + market.toUpperCase() + ' inventory and add the items your event needs.</p></div>';
      return;
    }
    requestBody.innerHTML =
      '<p class="text-muted" style="font-size:0.85rem;">' + list.length + " item" + (list.length === 1 ? "" : "s") + " · " + market.toUpperCase() + " inventory · no prices shown</p>" +
      list.map(function (it, i) {
        var p = itemById[it.id];
        var max = p ? stockFor(p) : it.qty;
        return '<div class="request-item" data-idx="' + i + '">' +
          (it.image ? '<img src="' + EM.escapeHtml(it.image) + '" alt="" width="64" height="64">' : "") +
          '<div class="request-item__body">' +
            '<p class="request-item__name">' + EM.escapeHtml(it.name) + "</p>" +
            '<p class="request-item__meta">' + EM.escapeHtml(it.code) + " · " + it.market.toUpperCase() + "</p>" +
            '<div class="request-item__row">' +
              '<div class="qty-control"><button type="button" data-r-minus aria-label="Decrease quantity">−</button>' +
              '<input type="number" inputmode="numeric" value="' + it.qty + '" min="1" max="' + max + '" aria-label="Quantity for ' + EM.escapeHtml(it.name) + '">' +
              '<button type="button" data-r-plus aria-label="Increase quantity">+</button></div>' +
              '<button type="button" class="request-item__remove" data-r-remove>Remove</button>' +
            "</div>" +
          "</div></div>";
      }).join("");
    requestBody.querySelectorAll(".request-item").forEach(function (row) {
      var idx = parseInt(row.getAttribute("data-idx"), 10);
      var input = row.querySelector("input");
      var it = marketList()[idx];
      var p = itemById[it.id];
      var max = p ? stockFor(p) : it.qty;
      function commit(v) {
        v = Math.max(1, Math.min(max, Math.floor(v) || 1));
        input.value = String(v);
        it.qty = v;
        saveRequests();
      }
      row.querySelector("[data-r-minus]").addEventListener("click", function () { commit(parseInt(input.value, 10) - 1); });
      row.querySelector("[data-r-plus]").addEventListener("click", function () { commit(parseInt(input.value, 10) + 1); });
      input.addEventListener("change", function () { commit(parseInt(input.value, 10)); });
      row.querySelector("[data-r-remove]").addEventListener("click", function () {
        requests[market].splice(idx, 1);
        saveRequests();
        renderRequest();
        render();
      });
    });
  }

  document.querySelectorAll("[data-open-request]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      reconcile();
      renderRequest();
      requestDrawer.open();
    });
  });

  /* ---------- request form ---------- */
  var enquiryDlg = EM.dialog(document.getElementById("rent-enquiry-dialog"));
  var enquiryForm = document.getElementById("rent-enquiry-form");
  var enquirySummary = document.getElementById("rent-enquiry-summary");

  document.getElementById("rent-request-submit").addEventListener("click", function () {
    reconcile();
    if (!marketList().length) {
      EM.toast("Add at least one item to your rental list first.", "err");
      return;
    }
    requestDrawer.close();
    var list = marketList();
    enquirySummary.textContent = list.length + " item" + (list.length === 1 ? "" : "s") + " · " +
      market.toUpperCase() + " — " + list.map(function (it) { return it.name + " × " + it.qty; }).slice(0, 4).join(", ") +
      (list.length > 4 ? "…" : "");
    enquiryDlg.open();
  });

  EM.bindForm({
    form: enquiryForm,
    formKey: "rental_enquiry",
    endpoint: "/api/rentals/enquiries",
    successMessage: "Rental request received — we will confirm availability and pricing privately.",
    validate: function () {
      var s = enquiryForm.startDate.value, e = enquiryForm.endDate.value;
      if (s && e && e < s) return "The rental end date cannot be before the start date.";
      return true;
    },
    collect: function () {
      return {
        fullName: enquiryForm.fullName.value.trim(),
        company: enquiryForm.company.value.trim(),
        email: enquiryForm.email.value.trim(),
        phone: enquiryForm.phone.value.trim(),
        startDate: enquiryForm.startDate.value,
        endDate: enquiryForm.endDate.value,
        eventCity: enquiryForm.eventCity.value.trim(),
        venue: enquiryForm.venue.value.trim(),
        notes: enquiryForm.notes.value.trim(),
        consent: enquiryForm.consent.checked,
        market: market,
        items: marketList().map(function (it) { return { productId: it.id, quantity: it.qty }; })
      };
    },
    onSuccess: function () {
      /* clear only the successfully submitted market's list */
      requests[market] = [];
      saveRequests();
      render();
      enquiryDlg.close();
    }
  });

  /* ---------- availability notification ---------- */
  var notifyDlg = EM.dialog(document.getElementById("rent-notify-dialog"));
  var notifyForm = document.getElementById("rent-notify-form");
  var notifyProductEl = document.getElementById("rent-notify-product");
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
  updateFab();
  loadInventory(false);
})();
