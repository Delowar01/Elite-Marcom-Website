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
  function safeStoredImage(u) {
    u = String(u || "").slice(0, 500);
    return (u.indexOf("/") === 0 && u.indexOf("//") !== 0) || u.indexOf("https://") === 0 ? u : "";
  }
  function loadRequests() {
    var all = EM.store.get(REQUEST_KEY, {});
    if (!all || typeof all !== "object") all = {};
    ["ksa", "uae"].forEach(function (m) {
      if (!Array.isArray(all[m])) all[m] = [];
      all[m] = all[m].filter(function (it) {
        return it && typeof it.id === "string" && typeof it.qty === "number" && it.qty >= 1 && it.market === m;
      }).slice(0, MAX_ITEMS).map(function (it) {
        var b = it.branding && typeof it.branding === "object" ? {
          area: String(it.branding.area || "").slice(0, 120),
          method: String(it.branding.method || "").slice(0, 120),
          note: String(it.branding.note || "").slice(0, 500)
        } : null;
        if (b && !b.area && !b.method && !b.note) b = null;
        return { id: String(it.id).slice(0, 80), code: String(it.code || "").slice(0, 80),
                 name: String(it.name || "").slice(0, 200), image: safeStoredImage(it.image),
                 market: m, qty: Math.min(100000, Math.floor(it.qty)), branding: b };
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
    restoreReturnState();
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

  /* one card per variant group: representative = in-stock variant with the
     lowest sequence, else just the lowest sequence */
  function groupRep(items) {
    var pool = items.filter(function (p) { return p.stock && p.stock.available > 0; });
    if (!pool.length) pool = items;
    return pool.reduce(function (best, p) {
      return (p.sequence || 1e9) < (best.sequence || 1e9) ? p : best;
    }, pool[0]);
  }
  function groupStock(items) {
    var sum = 0;
    items.forEach(function (p) { sum += (p.stock && p.stock.available) || 0; });
    return sum;
  }

  function matches(p, q, cat, brand, color, minStock) {
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
  }

  /* One entry per card — a variant group — carrying `n`, how many of its
     variants actually match the active filters.

     A card is a family (one product in six colours is one card), but the
     catalogue is 1,778 products in KSA and 2,573 in UAE, which is the figure
     the admin panel shows and the figure a visitor should read. So the cards
     stay grouped and the headline counts variants. `n` rather than
     `items.length` because a group survives when *any* of its variants
     matches: filtering to Black must not count the other five colours. */
  function filtered() {
    var q = (els.search && els.search.value || "").trim().toLowerCase();
    var cat = els.category ? els.category.value : "";
    var brand = els.brand ? els.brand.value : "";
    var color = els.color ? els.color.value : "";
    var minStock = els.minstock ? Math.max(0, parseInt(els.minstock.value, 10) || 0) : 0;
    var out = [];
    EM.giftGroups(products).forEach(function (items) {
      var n = 0;
      items.forEach(function (p) { if (matches(p, q, cat, brand, color, minStock)) n++; });
      if (n) out.push({ items: items, n: n });
    });
    var sort = els.sort ? els.sort.value : "featured";
    function seq(g) { return (groupRep(g.items).sequence || 1e9); }
    /* Featured mirrors the supplier's site: lowest website_sequence first */
    if (sort === "featured") out.sort(function (a, b) { return seq(a) - seq(b); });
    else if (sort === "newest") out.sort(function (a, b) {
      return (groupRep(b.items).isNew ? 1 : 0) - (groupRep(a.items).isNew ? 1 : 0) || seq(a) - seq(b);
    });
    else if (sort === "name-asc") out.sort(function (a, b) { return groupRep(a.items).name.localeCompare(groupRep(b.items).name); });
    else if (sort === "name-desc") out.sort(function (a, b) { return groupRep(b.items).name.localeCompare(groupRep(a.items).name); });
    else if (sort === "stock") out.sort(function (a, b) { return groupStock(b.items) - groupStock(a.items); });
    return out;
  }

  /* how many products, not how many cards */
  function countProducts(entries) {
    return entries.reduce(function (n, g) { return n + g.n; }, 0);
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
  function qty(n) { return Number(n || 0).toLocaleString("en-GB"); }

  function availability(p) {
    var s = p.stock || {};
    if (s.available > 0 && s.available <= 20) return { cls: "availability--low", label: qty(s.available) + " left" };
    if (s.available > 0) return { cls: "availability--in", label: qty(s.available) + " in stock" };
    if (s.incoming > 0) return { cls: "availability--incoming", label: "Incoming" + (s.incomingDate ? " — " + s.incomingDate : "") };
    return { cls: "availability--out", label: "Out of stock" };
  }

  function productUrl(p) {
    return "/product.html?country=" + encodeURIComponent(market) + "&id=" + encodeURIComponent(p.id);
  }

  /* remember scroll position + list depth so "Back" lands where the visitor left */
  var RETURN_KEY = "em-gifts-return";
  function saveReturnState() {
    try {
      sessionStorage.setItem(RETURN_KEY, JSON.stringify({
        y: window.scrollY, limit: visibleLimit, market: market, t: Date.now()
      }));
    } catch (e) { /* storage unavailable — back simply lands at the top */ }
  }
  function restoreReturnState() {
    var raw = null;
    try {
      raw = sessionStorage.getItem(RETURN_KEY);
      sessionStorage.removeItem(RETURN_KEY);
    } catch (e) { return; }
    if (!raw) return;
    var st = null;
    try { st = JSON.parse(raw); } catch (e) { return; }
    if (!st || st.market !== market || Date.now() - (st.t || 0) > 30 * 60 * 1000) return;
    if (st.limit > visibleLimit) { visibleLimit = st.limit; render(); }
    window.scrollTo(0, st.y || 0);
  }

  /* ---------- which layout ---------- */
  /* Cards are the default; the toolbar's toggle switches to the list and the
     choice is remembered, so it survives opening a product and coming back. */
  var VIEW_KEY = "em-gifts-view";
  var view = "grid";
  try {
    var stored = localStorage.getItem(VIEW_KEY);
    if (stored === "grid" || stored === "list") view = stored;
  } catch (e) { /* storage unavailable — cards it is */ }

  function setView(next, redraw) {
    view = next === "list" ? "list" : "grid";
    try { localStorage.setItem(VIEW_KEY, view); } catch (e) { /* not fatal */ }
    /* the class is set from here rather than trusted from the page, so a
       published snapshot baked before this layout existed still lays out */
    grid.className = view === "list" ? "catalog-list" : "catalog-grid catalog-grid--gifts";
    document.querySelectorAll(".view-toggle [data-view]").forEach(function (b) {
      b.setAttribute("aria-pressed", b.getAttribute("data-view") === view ? "true" : "false");
    });
    if (redraw) render();
  }

  var CHEVRON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
    'aria-hidden="true"><path d="M9 5l7 7-7 7"/></svg>';

  function cardHtml(p, group) {
    var multi = group.length > 1;
    var total = groupStock(group);
    /* aggregate availability across the group's variants */
    var av = availability(multi ? { stock: {
      available: total,
      incoming: Math.max.apply(null, group.map(function (g) { return (g.stock && g.stock.incoming) || 0; })),
      incomingDate: (p.stock || {}).incomingDate
    } } : p);
    var inReq = findRequest(p.id);
    var canOrder = p.stock && p.stock.available > 0;
    var badges = "";
    if (p.categories && p.categories.length) badges += '<span class="chip">' + EM.escapeHtml(p.categories[0]) + "</span>";
    if (p.isNew) badges += '<span class="chip chip--violet">New</span>';
    if (p.sustainable) badges += '<span class="chip chip--orange">Sustainable</span>';
    var meta = multi
      ? [p.brand, group.length + " options"].filter(Boolean).join(" · ")
      : [p.brand, p.color].filter(Boolean).join(" · ");
    /* slideable media with auto-hide arrows, right on the card */
    var imgs = (p.images && p.images.length ? p.images : (p.image ? [p.image] : [])).slice(0, 8);
    var slides = imgs.map(function (src, i) {
      return '<img src="' + EM.escapeHtml(src) + '" alt="" loading="lazy" width="480" height="480" draggable="false">';
    }).join("");
    return (
      '<div class="product-card__media carousel">' +
        '<div class="carousel__track">' + slides + "</div>" +
        '<div class="product-card__badges">' + badges + "</div>" +
      "</div>" +
      '<div class="product-card__body">' +
        '<span class="product-card__code"><span>' + EM.escapeHtml(p.code) + "</span><span>" + market.toUpperCase() + "</span></span>" +
        '<h3 class="product-card__name">' + EM.escapeHtml(p.name) + "</h3>" +
        '<span class="product-card__meta">' + EM.escapeHtml(meta) + "</span>" +
        '<span class="availability ' + av.cls + '">' + EM.escapeHtml(av.label) + "</span>" +
        '<div class="product-card__actions">' +
          (multi
            ? '<a class="btn btn--primary btn--small" href="' + productUrl(p) + '">Select options</a>'
            : canOrder
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

  function rowHtml(p, group) {
    var multi = group.length > 1;
    /* a variant group is one row, so its stock is the group's, not the rep's */
    var av = availability(multi ? { stock: {
      available: groupStock(group),
      incoming: Math.max.apply(null, group.map(function (g) { return (g.stock && g.stock.incoming) || 0; })),
      incomingDate: (p.stock || {}).incomingDate
    } } : p);
    var inReq = findRequest(p.id);
    var canOrder = p.stock && p.stock.available > 0;
    var meta = [p.brand, p.color].filter(Boolean).join(" · ");
    return (
      '<span class="c-img">' +
        (p.image
          ? '<img src="' + EM.escapeHtml(p.image) + '" alt="" loading="lazy" width="44" height="44" draggable="false">'
          : "") +
      "</span>" +
      '<span class="c-sku">' + EM.escapeHtml(p.code) + "</span>" +
      /* data-meta carries brand and colour for the narrow layout, where they
         move under the name instead of keeping columns of their own */
      '<span class="c-name" data-meta="' + EM.escapeHtml(meta) + '">' + EM.escapeHtml(p.name) +
        (multi ? '<span class="vtag">' + group.length + " options</span>" : "") + "</span>" +
      '<span class="c-brand">' + EM.escapeHtml(p.brand || "—") + "</span>" +
      '<span class="c-colour">' + EM.escapeHtml(p.color || "—") + "</span>" +
      '<span class="c-stock"><span class="availability ' + av.cls + '">' +
        EM.escapeHtml(av.label) + "</span></span>" +
      '<span class="c-act">' +
        (multi
          ? '<a class="rowbtn rowbtn--ghost" href="' + productUrl(p) + '">' + group.length + " options</a>"
          : canOrder
          ? '<button class="rowbtn" type="button" data-add>' + (inReq ? "Update" : "Add") + "</button>"
          : '<button class="rowbtn rowbtn--violet" type="button" data-notify>Notify me</button>') +
      "</span>" +
      '<span class="c-go" aria-hidden="true">' + CHEVRON + "</span>");
  }

  var LIST_HEAD =
    '<div class="lhead" aria-hidden="true"><span></span><span>SKU</span><span>Product</span>' +
    '<span class="th-brand">Brand</span><span class="th-colour">Colour</span>' +
    "<span>Available</span><span></span><span></span></div>";

  function render() {
    grid.setAttribute("aria-busy", "false");
    var list = filtered();
    var slice = list.slice(0, visibleLimit);
    var isList = view === "list";
    grid.innerHTML = isList && slice.length ? LIST_HEAD : "";
    slice.forEach(function (entry) {
      var group = entry.items;
      var p = groupRep(group);
      var el = document.createElement(isList ? "div" : "article");
      el.className = isList ? "lrow" : "product-card";
      el.setAttribute("data-id", p.id);
      el.setAttribute("role", "link");
      el.setAttribute("tabindex", "0");
      el.setAttribute("aria-label", p.name + " — open product page");
      el.innerHTML = isList ? rowHtml(p, group) : cardHtml(p, group);
      isList ? bindRow(el, p) : bindCard(el, p);
      /* the whole card or row opens the product page — except its own controls */
      el.addEventListener("click", function (e) {
        if (e.target.closest("input, .qty-control, .carousel__btn, .carousel__dots")) return;
        var link = e.target.closest("a");
        if (e.target.closest("button") && !link) return;
        saveReturnState();
        if (link) return;   /* the options anchor navigates on its own */
        location.href = productUrl(p);
      });
      el.addEventListener("keydown", function (e) {
        if ((e.key === "Enter" || e.key === " ") && e.target === el) {
          e.preventDefault();
          saveReturnState();
          location.href = productUrl(p);
        }
      });
      if (!isList) {
        var mediaEl = el.querySelector(".product-card__media");
        if (mediaEl && EM.carousel) EM.carousel(mediaEl);
      }
      grid.appendChild(el);
    });
    var total = countProducts(list);
    if (els.count) els.count.textContent = qty(total) + " product" + (total === 1 ? "" : "s");
    if (els.empty) els.empty.hidden = list.length !== 0;
    if (els.more) {
      /* more *cards* decides whether the button shows; it counts products,
         so the button and the headline are talking about the same thing */
      els.more.hidden = list.length <= visibleLimit;
      els.more.textContent = "Load more products (" +
        qty(Math.max(0, total - countProducts(slice))) + " remaining)";
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
    /* live validation: a typed quantity can never exceed available stock */
    if (qtyInput) qtyInput.addEventListener("change", function () { clampQty(qtyInput, max); });
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

  function bindRow(row, p) {
    /* one product, one press: quantity is set on the product page or in the
       request drawer, both of which clamp it to available stock */
    var addBtn = row.querySelector("[data-add]");
    if (addBtn) addBtn.addEventListener("click", function () {
      var existing = findRequest(p.id);
      addToRequest(p, existing ? existing.qty : 1);
      addBtn.textContent = "Update";
    });
    var notBtn = row.querySelector("[data-notify]");
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
    btn.addEventListener("click", function () { setView(btn.getAttribute("data-view"), true); });
  });
  /* applied before the first paint, so the container never carries the class
     of a layout it is not showing */
  setView(view, false);

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
            (it.branding
              ? '<p class="request-item__pref">Branding: ' +
                EM.escapeHtml([it.branding.area, it.branding.method].filter(Boolean).join(" · ") || "see notes") +
                "</p>"
              : "") +
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
    multipart: true,
    successMessage: "Request received — we will prepare one clear proposal.",
    collect: function (fd) {
      fd.append("fullName", enquiryForm.fullName.value.trim());
      fd.append("company", enquiryForm.company.value.trim());
      fd.append("email", enquiryForm.email.value.trim());
      fd.append("phone", enquiryForm.phone.value.trim());
      fd.append("requiredBy", enquiryForm.requiredBy.value || "");
      fd.append("deliveryCity", enquiryForm.deliveryCity.value.trim());
      fd.append("shippingAddress", enquiryForm.shippingAddress.value.trim());
      fd.append("notes", enquiryForm.notes.value.trim());
      fd.append("consent", enquiryForm.consent.checked ? "yes" : "");
      fd.append("market", market);
      fd.append("items", JSON.stringify(marketList().map(function (it) {
        var entry = { productId: it.id, quantity: it.qty };
        if (it.branding) entry.branding = it.branding;
        return entry;
      })));
      var logo = enquiryForm.querySelector('input[name="logo"]');
      if (logo && logo.files && logo.files[0]) fd.append("logo", logo.files[0]);
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
