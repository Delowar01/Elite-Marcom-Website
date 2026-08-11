/* ============================================================
   ELITE MARCOM — giveaways: live B2B catalog + request workflow
   No public prices · no payment · request → private proposal
   ============================================================ */
(function () {
  "use strict";
  var EM = window.EM;

  var MARKET_KEY = "em-giveaway-market";
  var REQUEST_KEY = "em-giveaway-request"; /* { ksa: [...], uae: [...] } */
  var BATCH = 24;
  var MAX_ITEMS = 50;

  var grid = document.getElementById("give-grid");
  if (!grid) return;

  var els = {
    state: document.getElementById("give-data-state"),
    count: document.getElementById("give-count"),
    empty: document.getElementById("give-empty"),
    more: document.getElementById("give-more"),
    search: document.getElementById("give-search"),
    category: document.getElementById("give-category"),
    brand: document.getElementById("give-brand"),
    color: document.getElementById("give-color"),
    minstock: document.getElementById("give-minstock"),
    sort: document.getElementById("give-sort"),
    flags: document.getElementById("give-flags"),
    activeFilters: document.getElementById("give-active-filters"),
    clear: document.getElementById("give-clear"),
    fabCount: document.getElementById("give-fab-count")
  };

  var market = EM.store.get(MARKET_KEY, "ksa");
  if (market !== "ksa" && market !== "uae") market = "ksa";
  var products = [];
  var productById = {};
  var dataState = "connecting";
  var visibleLimit = BATCH;
  var flags = {};
  var refreshTimer = null;

  /* ---------- request list (localStorage, sanitized) ---------- */
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
                 market: m, qty: Math.min(100000, Math.floor(it.qty)) };
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
    document.querySelectorAll(".request-fab").forEach(function (fab) {
      fab.hidden = n === 0;
    });
    if (els.fabCount) els.fabCount.textContent = String(n);
  }

  /* reconcile stored items against fresh server catalog */
  function reconcile() {
    var changed = false;
    requests[market] = marketList().filter(function (it) {
      var p = productById[it.id];
      if (!p) { changed = true; return false; }
      var avail = p.stock ? p.stock.available : 0;
      if (avail <= 0) { changed = true; return false; }
      if (it.qty > avail) { it.qty = avail; changed = true; }
      it.name = p.name; it.code = p.code; it.image = p.image || "";
      return true;
    });
    if (changed) { saveRequests(); EM.toast("Your request list was updated to match current availability.", ""); }
    updateFab();
  }

  /* ---------- data loading ---------- */
  function setDataState(state, label) {
    dataState = state;
    if (!els.state) return;
    els.state.className = "data-state data-state--" + state;
    els.state.textContent = label;
  }

  function normalizePreview(raw) {
    return (raw.products || []).filter(function (p) { return p && p.market === market; });
  }

  function loadCatalog(fromRefresh) {
    if (!fromRefresh) {
      setDataState("connecting", "Connecting");
      grid.setAttribute("aria-busy", "true");
      grid.innerHTML = new Array(8).fill(
        '<div class="skeleton-card"><div class="sk sk-media"></div><div class="sk sk-line" style="width:70%;"></div><div class="sk sk-line" style="width:45%;"></div></div>'
      ).join("");
    } else {
      setDataState(dataState, "Refreshing");
    }
    EM.api("/api/giveaways/products?country=" + market).then(function (r) {
      if (r.ok && r.data && Array.isArray(r.data.products)) {
        products = r.data.products;
        var st = r.data.state === "live" ? "live" : "cache";
        setDataState(st, r.data.state === "live" ? "Live data" : "Latest cached data");
        finishLoad();
      } else if (r.status === 503) {
        /* controlled fallback to local preview catalog */
        return fetch("/data/giveaway-preview-products.json").then(function (res) { return res.json(); }).then(function (raw) {
          products = normalizePreview(raw);
          setDataState("preview", "Preview data");
          finishLoad();
        });
      } else {
        throw new Error("catalog");
      }
    }).catch(function () {
      fetch("/data/giveaway-preview-products.json").then(function (res) { return res.json(); }).then(function (raw) {
        products = normalizePreview(raw);
        setDataState("preview", "Preview data");
        finishLoad();
      }).catch(function () {
        products = [];
        setDataState("preview", "Catalog unavailable");
        finishLoad();
      });
    });
  }

  function finishLoad() {
    productById = {};
    products.forEach(function (p) { productById[p.id] = p; });
    buildFilterOptions();
    reconcile();
    visibleLimit = BATCH;
    render();
    /* hourly browser refresh without multiplying supplier traffic (server caches) */
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = setInterval(function () {
      if (!document.hidden) loadCatalog(true);
    }, 60 * 60 * 1000);
  }

  /* ---------- filters ---------- */
  function buildFilterOptions() {
    var cats = {}, brands = {}, colors = {};
    products.forEach(function (p) {
      (p.categories || []).forEach(function (c) { cats[c] = 1; });
      if (p.brand) brands[p.brand] = 1;
      if (p.color) colors[p.color] = 1;
    });
    function fill(select, values, label) {
      if (!select) return;
      var current = select.value;
      select.innerHTML = '<option value="">' + label + "</option>" +
        Object.keys(values).sort().map(function (v) {
          return '<option value="' + EM.escapeHtml(v) + '">' + EM.escapeHtml(v) + "</option>";
        }).join("");
      select.value = current;
      if (select.value !== current) select.value = "";
    }
    fill(els.category, cats, "All categories");
    fill(els.brand, brands, "All brands");
    fill(els.color, colors, "All colours");
  }

  function filtered() {
    var q = (els.search && els.search.value || "").trim().toLowerCase();
    var cat = els.category ? els.category.value : "";
    var brand = els.brand ? els.brand.value : "";
    var color = els.color ? els.color.value : "";
    var minStock = els.minstock ? Math.max(0, parseInt(els.minstock.value, 10) || 0) : 0;
    var out = products.filter(function (p) {
      if (q) {
        var hay = (p.name + " " + p.code + " " + (p.brand || "") + " " + (p.description || "") + " " +
                   (p.categories || []).join(" ") + " " + (p.tags || []).join(" ")).toLowerCase();
        if (hay.indexOf(q) === -1) return false;
      }
      if (cat && (p.categories || []).indexOf(cat) === -1) return false;
      if (brand && p.brand !== brand) return false;
      if (color && p.color !== color) return false;
      if (flags.sustainable && !p.sustainable) return false;
      if (flags.new && !p.isNew) return false;
      if (flags.luxury && !p.luxury) return false;
      if (flags.ramadan && !p.ramadan) return false;
      if (flags["in-stock"] && !(p.stock && p.stock.available > 0)) return false;
      if (minStock > 0 && !(p.stock && p.stock.available >= minStock)) return false;
      if (flags.incoming && !(p.stock && p.stock.incoming > 0)) return false;
      return true;
    });
    var sort = els.sort ? els.sort.value : "featured";
    /* Featured mirrors the supplier's site: lowest website_sequence first */
    if (sort === "featured") out.sort(function (a, b) { return (a.sequence || 1e9) - (b.sequence || 1e9); });
    else if (sort === "newest") out.sort(function (a, b) {
      return (b.isNew ? 1 : 0) - (a.isNew ? 1 : 0) || (a.sequence || 1e9) - (b.sequence || 1e9);
    });
    else if (sort === "name-asc") out.sort(function (a, b) { return a.name.localeCompare(b.name); });
    else if (sort === "name-desc") out.sort(function (a, b) { return b.name.localeCompare(a.name); });
    else if (sort === "stock") out.sort(function (a, b) { return ((b.stock && b.stock.available) || 0) - ((a.stock && a.stock.available) || 0); });
    return out;
  }

  function activeFilterCount() {
    var n = 0;
    if (els.search && els.search.value.trim()) n++;
    if (els.category && els.category.value) n++;
    if (els.brand && els.brand.value) n++;
    if (els.color && els.color.value) n++;
    if (els.minstock && parseInt(els.minstock.value, 10) > 0) n++;
    Object.keys(flags).forEach(function (k) { if (flags[k]) n++; });
    return n;
  }

  /* ---------- rendering ---------- */
  function availability(p) {
    var s = p.stock || {};
    if (s.available > 0 && s.available <= 20) return { cls: "availability--low", label: "Low stock — " + s.available + " left" };
    if (s.available > 0) return { cls: "availability--in", label: s.available + " in stock" };
    if (s.incoming > 0) return { cls: "availability--incoming", label: "Incoming" + (s.incomingDate ? " — " + s.incomingDate : "") };
    return { cls: "availability--out", label: "Out of stock" };
  }

  function productUrl(p) {
    return "/product.html?country=" + encodeURIComponent(market) + "&id=" + encodeURIComponent(p.id);
  }

  function cardHtml(p) {
    var av = availability(p);
    var inReq = findRequest(p.id);
    var canOrder = p.stock && p.stock.available > 0;
    var badges = "";
    if (p.categories && p.categories.length) badges += '<span class="chip">' + EM.escapeHtml(p.categories[0]) + "</span>";
    if (p.isNew) badges += '<span class="chip chip--violet">New</span>';
    if (p.sustainable) badges += '<span class="chip chip--orange">Sustainable</span>';
    /* the card shows the primary image; the full gallery lives on the product page */
    return (
      '<div class="product-card__media">' +
        (p.image ? '<img src="' + EM.escapeHtml(p.image) + '" alt="" loading="lazy" width="480" height="480">' : "") +
        '<div class="product-card__badges">' + badges + "</div>" +
      "</div>" +
      '<div class="product-card__body">' +
        '<span class="product-card__code"><span>' + EM.escapeHtml(p.code) + "</span><span>" + market.toUpperCase() + "</span></span>" +
        '<h3 class="product-card__name">' + EM.escapeHtml(p.name) + "</h3>" +
        '<span class="product-card__meta">' + EM.escapeHtml([p.brand, p.color].filter(Boolean).join(" · ")) + "</span>" +
        '<span class="availability ' + av.cls + '">' + EM.escapeHtml(av.label) + "</span>" +
        '<div class="product-card__actions">' +
          (canOrder
            ? '<div class="qty-control" aria-label="Quantity">' +
                '<button type="button" data-qty-minus aria-label="Decrease quantity">−</button>' +
                '<input type="number" inputmode="numeric" value="' + (inReq ? inReq.qty : 1) + '" min="1" max="' + p.stock.available + '" aria-label="Requested quantity">' +
                '<button type="button" data-qty-plus aria-label="Increase quantity">+</button>' +
              "</div>" +
              '<button class="btn btn--primary btn--small" type="button" data-add>' + (inReq ? "Update request" : "Add request") + "</button>"
            : '<button class="btn btn--violet btn--small" type="button" data-notify>Notify when available</button>') +
        "</div>" +
      "</div>");
  }

  function render() {
    grid.setAttribute("aria-busy", "false");
    var list = filtered();
    var slice = list.slice(0, visibleLimit);
    grid.innerHTML = "";
    slice.forEach(function (p) {
      var card = document.createElement("article");
      card.className = "product-card";
      card.setAttribute("data-id", p.id);
      card.setAttribute("role", "link");
      card.setAttribute("tabindex", "0");
      card.setAttribute("aria-label", p.name + " — open product page");
      card.innerHTML = cardHtml(p);
      bindCard(card, p);
      /* the whole card opens the product page — except its own controls */
      card.addEventListener("click", function (e) {
        if (e.target.closest("button, input, a, .qty-control")) return;
        location.href = productUrl(p);
      });
      card.addEventListener("keydown", function (e) {
        if ((e.key === "Enter" || e.key === " ") && e.target === card) {
          e.preventDefault();
          location.href = productUrl(p);
        }
      });
      grid.appendChild(card);
    });
    if (els.count) els.count.textContent = list.length + " product" + (list.length === 1 ? "" : "s");
    if (els.empty) els.empty.hidden = list.length !== 0;
    if (els.more) {
      els.more.hidden = list.length <= visibleLimit;
      els.more.textContent = "Load more products (" + Math.max(0, list.length - visibleLimit) + " remaining)";
    }
    if (els.activeFilters) {
      var n = activeFilterCount();
      els.activeFilters.textContent = n ? n + " filter" + (n === 1 ? "" : "s") + " active" : "";
    }
  }

  function clampQty(input, max) {
    var v = parseInt(input.value, 10);
    if (isNaN(v) || v < 1) v = 1;
    if (v > max) { v = max; EM.toast("Quantity limited to available stock (" + max + ").", ""); }
    input.value = String(v);
    return v;
  }

  function bindCard(card, p) {
    var qtyInput = card.querySelector(".qty-control input");
    var max = (p.stock && p.stock.available) || 1;
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
    var notBtn = card.querySelector("[data-notify]");
    if (notBtn) notBtn.addEventListener("click", function () { openNotify(p); });
  }

  function addToRequest(p, qty) {
    var existing = findRequest(p.id);
    if (existing) {
      existing.qty = qty;
      EM.toast("Request updated — " + p.name + " × " + qty, "ok");
    } else {
      if (marketList().length >= MAX_ITEMS) {
        EM.toast("A request can contain up to " + MAX_ITEMS + " items.", "err");
        return;
      }
      requests[market].push({ id: p.id, code: p.code, name: p.name, image: p.image || "", market: market, qty: qty });
      EM.toast("Added to request — " + p.name + " × " + qty, "ok");
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
      updateFab();
      loadCatalog(false);
    });
    btn.setAttribute("aria-pressed", btn.getAttribute("data-market") === market ? "true" : "false");
  });

  /* ---------- controls ---------- */
  var searchTimer = null;
  if (els.search) els.search.addEventListener("input", function () {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(function () { visibleLimit = BATCH; render(); }, 220);
  });
  if (els.minstock) els.minstock.addEventListener("input", function () {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(function () { visibleLimit = BATCH; render(); }, 220);
  });
  [els.category, els.brand, els.color, els.sort].forEach(function (sel) {
    if (sel) sel.addEventListener("change", function () { visibleLimit = BATCH; render(); });
  });
  if (els.flags) els.flags.addEventListener("click", function (e) {
    var chip = e.target.closest("[data-flag]");
    if (!chip) return;
    var key = chip.getAttribute("data-flag");
    flags[key] = !flags[key];
    chip.setAttribute("aria-pressed", flags[key] ? "true" : "false");
    visibleLimit = BATCH;
    render();
  });
  if (els.clear) els.clear.addEventListener("click", function () {
    if (els.search) els.search.value = "";
    [els.category, els.brand, els.color].forEach(function (s) { if (s) s.value = ""; });
    if (els.minstock) els.minstock.value = "";
    flags = {};
    if (els.flags) els.flags.querySelectorAll("[data-flag]").forEach(function (c) { c.setAttribute("aria-pressed", "false"); });
    visibleLimit = BATCH;
    render();
  });
  if (els.more) els.more.addEventListener("click", function () { visibleLimit += BATCH; render(); });
  document.querySelectorAll(".view-toggle [data-view]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      grid.classList.toggle("is-list", btn.getAttribute("data-view") === "list");
      document.querySelectorAll(".view-toggle [data-view]").forEach(function (b) {
        b.setAttribute("aria-pressed", b === btn ? "true" : "false");
      });
    });
  });

  /* ---------- request drawer ---------- */
  var requestDrawer = EM.drawer(document.getElementById("give-request-drawer"), document.getElementById("give-request-scrim"));
  var requestBody = document.getElementById("give-request-body");

  function renderRequest() {
    var list = marketList();
    if (!list.length) {
      requestBody.innerHTML = '<div class="empty-state"><h3>Your request is empty</h3><p>Browse the ' + market.toUpperCase() + ' catalog and add products — we will price the whole list privately.</p></div>';
      return;
    }
    requestBody.innerHTML =
      '<p class="text-muted" style="font-size:0.85rem;">' + list.length + " item" + (list.length === 1 ? "" : "s") + " · " + market.toUpperCase() + " market · no prices shown</p>" +
      list.map(function (it, i) {
        var p = productById[it.id];
        var max = p && p.stock ? p.stock.available : it.qty;
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
      var p = productById[it.id];
      var max = p && p.stock ? p.stock.available : it.qty;
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

  /* ---------- enquiry dialog ---------- */
  var enquiryDlg = EM.dialog(document.getElementById("give-enquiry-dialog"));
  var enquiryForm = document.getElementById("give-enquiry-form");
  var enquirySummary = document.getElementById("give-enquiry-summary");

  document.getElementById("give-request-submit").addEventListener("click", function () {
    reconcile();
    if (!marketList().length) {
      EM.toast("Add at least one product to your request first.", "err");
      return;
    }
    requestDrawer.close();
    var list = marketList();
    enquirySummary.textContent = list.length + " item" + (list.length === 1 ? "" : "s") + " from the " +
      market.toUpperCase() + " catalog — " + list.map(function (it) { return it.name + " × " + it.qty; }).slice(0, 4).join(", ") +
      (list.length > 4 ? "…" : "");
    enquiryDlg.open();
  });

  EM.bindForm({
    form: enquiryForm,
    formKey: "giveaway_enquiry",
    endpoint: "/api/giveaways/enquiries",
    successMessage: "Request received — we will prepare one clear proposal.",
    collect: function () {
      return {
        fullName: enquiryForm.fullName.value.trim(),
        company: enquiryForm.company.value.trim(),
        email: enquiryForm.email.value.trim(),
        phone: enquiryForm.phone.value.trim(),
        requiredBy: enquiryForm.requiredBy.value || null,
        deliveryCity: enquiryForm.deliveryCity.value.trim(),
        notes: enquiryForm.notes.value.trim(),
        consent: enquiryForm.consent.checked,
        market: market,
        items: marketList().map(function (it) { return { productId: it.id, quantity: it.qty }; })
      };
    },
    onSuccess: function () {
      requests[market] = [];
      saveRequests();
      render();
    }
  });

  /* ---------- availability notification ---------- */
  var notifyDlg = EM.dialog(document.getElementById("give-notify-dialog"));
  var notifyForm = document.getElementById("give-notify-form");
  var notifyProductEl = document.getElementById("give-notify-product");
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
  loadCatalog(false);
})();
