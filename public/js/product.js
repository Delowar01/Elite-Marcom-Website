/* ============================================================
   ELITE MARCOM — corporate gift product page
   Full gallery slider · branding options · printing manual ·
   add to request (shared localStorage list) · notify workflow
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
    variants: document.getElementById("pdp-variants"),
    description: document.getElementById("pdp-description"),
    descSection: document.getElementById("pdp-desc-section"),
    specs: document.getElementById("pdp-specs"),
    specsSection: document.getElementById("pdp-specs-section"),
    colors: document.getElementById("pdp-colors"),
    colorsSection: document.getElementById("pdp-colors-section"),
    brandingSection: document.getElementById("pdp-branding-section"),
    branding: document.getElementById("pdp-branding"),
    prefArea: document.getElementById("pref-area"),
    prefMethod: document.getElementById("pref-method"),
    prefNote: document.getElementById("pref-note"),
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

  /* current branding preference — attached to the request item on add */
  function collectPreference() {
    function sel(el) {
      return el && el.value && el.value !== "__none" ? String(el.value).slice(0, 120) : "";
    }
    var pref = {
      area: sel(els.prefArea),
      method: sel(els.prefMethod),
      note: els.prefNote ? els.prefNote.value.trim().slice(0, 500) : ""
    };
    return (pref.area || pref.method || pref.note) ? pref : null;
  }

  function populatePreference(brandingList) {
    if (!els.prefArea) return;
    var areas = [], methods = [];
    (brandingList || []).forEach(function (b) {
      if (b.area && areas.indexOf(b.area) === -1) areas.push(b.area);
      (b.method || "").split(",").forEach(function (m) {
        m = m.trim();
        if (m && methods.indexOf(m) === -1) methods.push(m);
      });
    });
    function fill(select, values, otherLabel) {
      var current = select.value;
      select.innerHTML =
        '<option value="__none">No preference — let Elite Marcom recommend</option>' +
        values.map(function (v) {
          return '<option value="' + EM.escapeHtml(v) + '">' + EM.escapeHtml(v) + "</option>";
        }).join("") +
        '<option value="Other — see notes">' + otherLabel + "</option>";
      if (current) select.value = current;
      if (!select.value) select.value = "__none";
    }
    fill(els.prefArea, areas.slice(0, 12), "Other area — describe in notes");
    fill(els.prefMethod, methods.slice(0, 12), "Other method — describe in notes");
  }

  function addToRequest(p, qty) {
    var pref = collectPreference();
    var existing = findRequest(p.id);
    if (existing) {
      existing.qty = qty;
      existing.branding = pref;
      EM.toast("Request updated — " + p.name + " × " + qty, "ok");
    } else {
      if (requests[market].length >= MAX_ITEMS) {
        EM.toast("A request can contain up to " + MAX_ITEMS + " items.", "err");
        return;
      }
      requests[market].push({ id: p.id, code: p.code, name: p.name, image: p.image || "",
                              market: market, qty: qty, branding: pref });
      EM.toast("Added to request — " + p.name + " × " + qty +
               (pref ? " (with branding preference)" : ""), "ok");
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

  /* ---------- size / colour variants (one supplier row per variant) ---------- */
  var group = [];

  function variantAttrMap(v) {
    var out = {};
    EM.variantAttrs(v).forEach(function (r) { out[r[0]] = r[1]; });
    return out;
  }

  function pickVariant(want, changedLabel) {
    var best = null, bestScore = -1;
    group.forEach(function (v) {
      var attrs = variantAttrMap(v);
      if (changedLabel && attrs[changedLabel] !== want[changedLabel]) return;
      var score = 0;
      Object.keys(want).forEach(function (k) { if (attrs[k] === want[k]) score++; });
      if (score > bestScore) { best = v; bestScore = score; }
    });
    return best;
  }

  function renderVariants(p) {
    if (!els.variants) return;
    if (group.length < 2) { els.variants.hidden = true; els.variants.innerHTML = ""; return; }
    var current = variantAttrMap(p);
    var labels = [], values = {};
    group.forEach(function (v) {
      EM.variantAttrs(v).forEach(function (r) {
        if (labels.indexOf(r[0]) === -1) { labels.push(r[0]); values[r[0]] = []; }
        if (values[r[0]].indexOf(r[1]) === -1) values[r[0]].push(r[1]);
      });
    });
    els.variants.innerHTML = labels.map(function (label) {
      return '<div class="variant-field"><label>' + EM.escapeHtml(label) + "</label>" +
        '<select data-variant="' + EM.escapeHtml(label) + '" aria-label="Choose ' + EM.escapeHtml(label) + '">' +
        values[label].map(function (v) {
          return '<option value="' + EM.escapeHtml(v) + '"' + (current[label] === v ? " selected" : "") + ">" +
                 EM.escapeHtml(v) + "</option>";
        }).join("") +
        "</select></div>";
    }).join("");
    els.variants.hidden = false;
    els.variants.querySelectorAll("select").forEach(function (sel) {
      sel.addEventListener("change", function () {
        var want = {};
        els.variants.querySelectorAll("select").forEach(function (s) { want[s.getAttribute("data-variant")] = s.value; });
        var next = pickVariant(want, sel.getAttribute("data-variant"));
        if (next && next.id !== p.id) {
          history.replaceState(null, "", "/product.html?country=" + encodeURIComponent(market) + "&id=" + encodeURIComponent(next.id));
          render(next);
        } else {
          renderVariants(p); /* impossible combination — snap selects back */
        }
      });
    });
  }

  /* ---------- gallery: images, then play-on-click YouTube slides ----------
     Rebuilt from scratch on every call — a variant switch and a video that
     arrives after first paint both land here, so nothing may accumulate. */
  var galleryScrollBound = false;

  function videoThumb(v) {
    return v.thumbnail || ("https://i.ytimg.com/vi/" + encodeURIComponent(v.youtubeId) + "/hqdefault.jpg");
  }

  function playVideo(slide) {
    if (!slide || slide.querySelector("iframe")) return;
    var vid = slide.getAttribute("data-youtube");
    if (!vid) return;
    var frame = document.createElement("iframe");
    frame.src = "https://www.youtube-nocookie.com/embed/" + encodeURIComponent(vid) +
      "?autoplay=1&rel=0&playsinline=1&modestbranding=1";
    frame.title = "Product video";
    /* fullscreen needs both the permission and the legacy attribute; without
       playsinline + autoplay in the policy, iOS refuses to start the video */
    frame.setAttribute("allow",
      "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; fullscreen");
    frame.setAttribute("allowfullscreen", "");
    frame.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
    slide.innerHTML = "";
    slide.appendChild(frame);
  }

  function buildGallery(p, vids) {
    /* re-rendering: drop carousel controls before rebuilding */
    els.carousel.querySelectorAll(".carousel__btn, .carousel__dots").forEach(function (n) { n.remove(); });
    els.carousel.classList.remove("carousel--single");
    els.thumbs.innerHTML = "";

    /* The video's poster arrives in the feed as an ordinary photograph too, so
       without this the same frame appears twice — once playable, once not. The
       server identifies it by supplier record id (/web/image/product.image/N/),
       never by gallery position, and leaves it unset when it cannot be sure;
       an unset poster means every photograph stays. Both the carousel and the
       thumbnail strip are built from imgs, so removing it here removes it from
       both. */
    var drop = {};
    vids.forEach(function (v) {
      if (v.supplierPoster) drop[v.supplierPoster] = 1;
      if (v.thumbnail) drop[v.thumbnail] = 1;
    });
    var dropIds = {};
    vids.forEach(function (v) { if (v.supplierImageId) dropIds[String(v.supplierImageId)] = 1; });
    var imgs = (p.images && p.images.length ? p.images : (p.image ? [p.image] : []))
      .filter(function (src) {
        if (drop[src]) return false;
        var rec = /\/web\/image\/product\.image\/(\d+)/.exec(src);
        if (rec && dropIds[rec[1]]) return false;
        return !vids.some(function (v) { return src.indexOf("/vi/" + v.youtubeId + "/") !== -1; });
      });

    els.track.innerHTML = imgs.map(function (src, i) {
      return '<img src="' + EM.escapeHtml(src) + '" alt="' + EM.escapeHtml(p.name) + ' — image ' + (i + 1) + '"' +
             (i > 0 ? ' loading="lazy"' : "") + ' width="800" height="800">';
    }).join("") + vids.map(function (v) {
      return '<div class="video-slide" data-youtube="' + EM.escapeHtml(v.youtubeId) + '" tabindex="0" role="button" ' +
             'aria-label="' + EM.escapeHtml(p.name) + ' — play product video">' +
             '<img src="' + EM.escapeHtml(videoThumb(v)) + '" alt="' + EM.escapeHtml(p.name) + ' — video" loading="lazy" width="800" height="800">' +
             '<span class="video-slide__play" aria-hidden="true">' +
             '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5.5v13l11-6.5z"/></svg>' +
             "</span></div>";
    }).join("");
    EM.carousel(els.carousel);
    els.track.querySelectorAll(".video-slide").forEach(function (slide) {
      /* the whole poster is the target, not just the small button — a tap
         anywhere on a video slide should start it */
      slide.addEventListener("click", function (e) {
        e.stopPropagation();
        playVideo(slide);
      });
      slide.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); playVideo(slide); }
      });
    });
    lbImages = imgs; /* the fullscreen viewer shows images only */
    els.track.querySelectorAll(":scope > img").forEach(function (img, i) {
      img.classList.add("pdp__zoomable");
      img.addEventListener("click", function () { lbOpen(i); });
    });
    if (imgs.length + vids.length > 1) {
      els.thumbs.innerHTML = imgs.map(function (src, i) {
        return '<button type="button" class="' + (i === 0 ? "is-active" : "") + '" aria-label="Show image ' + (i + 1) + '">' +
               '<img src="' + EM.escapeHtml(src) + '" alt="" loading="lazy" width="72" height="72"></button>';
      }).join("") + vids.map(function (v, i) {
        return '<button type="button" class="is-video" aria-label="Show video ' + (i + 1) + '">' +
               '<img src="' + EM.escapeHtml(videoThumb(v)) + '" alt="" loading="lazy" width="72" height="72"></button>';
      }).join("");
      els.thumbs.querySelectorAll("button").forEach(function (btn, i) {
        btn.addEventListener("click", function () {
          els.track.scrollTo({ left: i * els.track.clientWidth, behavior: EM.reducedMotion() ? "auto" : "smooth" });
        });
      });
      /* bound once: the buttons are re-read on every scroll, so a rebuilt
         strip is followed without stacking another listener each time */
      if (!galleryScrollBound) {
        galleryScrollBound = true;
        els.track.addEventListener("scroll", function () {
          var idx = Math.round(els.track.scrollLeft / Math.max(1, els.track.clientWidth));
          els.thumbs.querySelectorAll("button").forEach(function (b, i) {
            b.classList.toggle("is-active", i === idx);
          });
        }, { passive: true });
      }
    }
  }

  /* Videos the Product API did not carry are discovered from the supplier's
     public product page, server-side and cached. It is asked for only after
     the page has rendered, and only for the product actually being looked at —
     the catalogue never asks, so browsing never becomes a crawl. */
  function enrichVideos(p) {
    if ((p.videos || []).some(function (v) { return v && v.youtubeId; })) return;
    if (!p.parentId) return;
    EM.api("/api/giveaways/video?country=" + encodeURIComponent(market) +
           "&product_id=" + encodeURIComponent(p.id)).then(function (r) {
      var vids = (r.ok && r.data && r.data.videos) || [];
      vids = vids.filter(function (v) { return v && v.youtubeId; });
      if (!vids.length || currentProductId !== p.id) return;
      p.videos = vids;
      buildGallery(p, vids);
    }).catch(function () { /* a missing video is never an error the customer sees */ });
  }

  var currentProductId = null;

  function render(p) {
    currentProductId = p.id;
    els.loading.hidden = true;
    els.loading.style.display = "none";
    els.pdp.hidden = false;
    seoMeta({
      title: p.name + " — Corporate Gifts | Elite Marcom",
      description: (p.description || ("Branded " + p.name + " from Elite Marcom — corporate gifts and "
        + "merchandise for Saudi Arabia and the UAE.")).replace(/\s+/g, " ").slice(0, 300),
      url: location.origin + location.pathname + location.search,
      image: (p.images && p.images[0]) || p.image || ""
    });

    buildGallery(p, (p.videos || []).filter(function (v) { return v && v.youtubeId; }));
    enrichVideos(p);

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
    renderVariants(p);
    /* description straight from the supplier API — shown whenever it exists */
    if (p.description) {
      els.description.textContent = p.description;
      els.descSection.hidden = false;
    } else {
      els.descSection.hidden = true;
    }

    /* alternative colours — sibling products resolved server-side */
    if (p.colorOptions && p.colorOptions.length) {
      els.colors.innerHTML = p.colorOptions.map(function (o) {
        return '<a class="pdp__color" href="/product.html?country=' + encodeURIComponent(market) +
               "&id=" + encodeURIComponent(o.id) + '" title="' + EM.escapeHtml(o.name) + '">' +
               (o.image ? '<img src="' + EM.escapeHtml(o.image) + '" alt="' + EM.escapeHtml(o.name) + '" loading="lazy" width="64" height="64">' : "") +
               (o.color ? "<span>" + EM.escapeHtml(o.color) + "</span>" : "") +
               "</a>";
      }).join("");
      els.colorsSection.hidden = false;
    } else {
      els.colorsSection.hidden = true;
    }

    /* specifications — grouped like the supplier's spec sheet */
    function specRows(rows) {
      return rows.map(function (f) {
        return '<div class="spec-table__row"><span class="spec-table__label">' + EM.escapeHtml(String(f[0])) +
               '</span><span class="spec-table__value">' + EM.escapeHtml(String(f[1])) + "</span></div>";
      }).join("");
    }
    var productRows = [];
    if (p.brand) productRows.push(["Brand", p.brand]);
    if (p.color) productRows.push(["Colour", p.color]);
    /* merge repeated option labels: "Size: S", "Size: M" → one "Size" row */
    var optValues = {}, optOrder = [];
    (p.options || []).forEach(function (o) {
      var m = /^([^:]{1,40}):\s*(.+)$/.exec(String(o));
      var label = m ? m[1].trim() : "Option";
      var value = m ? m[2].trim() : String(o);
      if (!optValues[label]) { optValues[label] = []; optOrder.push(label); }
      if (optValues[label].indexOf(value) === -1) optValues[label].push(value);
    });
    optOrder.forEach(function (label) { productRows.push([label, optValues[label].join(", ")]); });
    if (p.hsCode) productRows.push(["HS / Commodity code", p.hsCode]);
    if (p.categories && p.categories.length > 1) productRows.push(["Categories", p.categories.join(", ")]);
    var packRows = [];
    if (p.cartonDimensions) packRows.push(["Carton dimensions", p.cartonDimensions + (/[a-z]/i.test(p.cartonDimensions) ? "" : " cm")]);
    if (p.unitsPerCarton) packRows.push(["Qty per carton", p.unitsPerCarton + " pcs / carton"]);
    if (p.cartonWeight) packRows.push(["Carton gross weight", p.cartonWeight + (/[a-z]/i.test(p.cartonWeight) ? "" : " kgs / carton")]);
    if (p.cartonVolume) packRows.push(["Carton volume", p.cartonVolume + (/[a-z³]/i.test(p.cartonVolume) ? "" : " m³")]);
    var specsHtml = "";
    if (productRows.length) specsHtml += '<div class="spec-table__group">Product</div>' + specRows(productRows);
    if (packRows.length) specsHtml += '<div class="spec-table__group">Packing</div>' + specRows(packRows);
    els.specs.innerHTML = specsHtml;
    els.specsSection.hidden = !specsHtml;

    /* actions: qty + add, or notify */
    var canOrder = p.stock && p.stock.available > 0;
    var inReq = findRequest(p.id);
    els.actions.innerHTML =
      (canOrder
        ? '<div class="qty-control" aria-label="Quantity">' +
            '<button type="button" data-qty-minus aria-label="Decrease quantity">−</button>' +
            '<input type="number" inputmode="numeric" value="' + (inReq ? Math.max(1, parseInt(inReq.qty, 10) || 1) : 1) + '" min="1" max="' + p.stock.available + '" aria-label="Requested quantity">' +
            '<button type="button" data-qty-plus aria-label="Increase quantity">+</button>' +
          "</div>" +
          '<button class="btn btn--primary" type="button" data-add>' + (inReq ? "Update request" : "Add to request") + "</button>"
        : '<button class="btn btn--violet" type="button" data-notify>Notify when available</button>');

    /* printing manual — validated server-side and served from our own domain;
       the button appears only when a genuine PDF exists for this product */
    (function (renderedFor) {
      EM.api("/api/giveaways/manual/status?country=" + encodeURIComponent(market) +
             "&product_id=" + encodeURIComponent(p.id)).then(function (r) {
        if (!(r.ok && r.data && r.data.available)) return;
        /* a variant switch may have re-rendered the page meanwhile */
        if (currentProductId !== renderedFor || els.actions.querySelector(".btn--manual")) return;
        var a = document.createElement("a");
        a.className = "btn btn--ghost btn--manual";
        a.href = "/api/giveaways/manual?country=" + encodeURIComponent(market) +
                 "&product_id=" + encodeURIComponent(p.id);
        a.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 3v12m0 0 4-4m-4 4-4-4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/></svg>Download Printing Manual';
        els.actions.appendChild(a);
      }).catch(function () { /* no manual — nothing to show */ });
    })(p.id);

    var qtyInput = els.actions.querySelector(".qty-control input");
    var max = (p.stock && p.stock.available) || 1;
    function clamp() {
      var v = parseInt(qtyInput.value, 10);
      if (isNaN(v) || v < 1) v = 1;
      if (v > max) { v = max; EM.toast("Quantity limited to available stock (" + max + ").", ""); }
      qtyInput.value = String(v);
      return v;
    }
    if (qtyInput) qtyInput.addEventListener("change", clamp);
    var minus = els.actions.querySelector("[data-qty-minus]");
    var plus = els.actions.querySelector("[data-qty-plus]");
    if (minus) minus.addEventListener("click", function () { qtyInput.value = String(Math.max(1, clamp() - 1)); });
    if (plus) plus.addEventListener("click", function () { qtyInput.value = String(Math.min(max, clamp() + 1)); });
    var addBtn = els.actions.querySelector("[data-add]");
    if (addBtn) addBtn.addEventListener("click", function () { addToRequest(p, clamp()); });
    var notifyBtn = els.actions.querySelector("[data-notify]");
    if (notifyBtn) notifyBtn.addEventListener("click", function () { openNotify(p); });

    /* branding options — resolved server-side for known products only */
    populatePreference([]);
    var stored = inReq && inReq.branding;
    if (stored) {
      if (els.prefNote) els.prefNote.value = stored.note || "";
    } else if (els.prefNote) {
      els.prefNote.value = "";
    }
    EM.api("/api/giveaways/branding?country=" + market + "&product_id=" + encodeURIComponent(p.id)).then(function (r) {
      if (r.ok && r.data && Array.isArray(r.data.branding) && r.data.branding.length) {
        els.branding.innerHTML = r.data.branding.map(function (b) {
          var bits = [b.area, b.method, b.dimensions].filter(Boolean).map(String).map(EM.escapeHtml);
          return "<li>" + bits.join(" · ") + "</li>";
        }).join("");
        els.brandingSection.hidden = false;
        populatePreference(r.data.branding);
      }
      if (stored) {
        if (stored.area && els.prefArea) els.prefArea.value = stored.area;
        if (stored.method && els.prefMethod) els.prefMethod.value = stored.method;
        if (els.prefArea && !els.prefArea.value) els.prefArea.value = "__none";
        if (els.prefMethod && !els.prefMethod.value) els.prefMethod.value = "__none";
      }
    }).catch(function () { /* branding advice arrives with the proposal */ });
  }

  function showMissing() {
    els.loading.hidden = true;
    els.loading.style.display = "none";
    els.missing.hidden = false;
  }

  /* ---------- fullscreen viewer: swipe, thumbnails, zoom ---------- */
  var lbImages = [];
  var lb = {
    root: document.getElementById("pdp-lightbox"),
    track: document.getElementById("pdp-lightbox-track"),
    count: document.getElementById("pdp-lightbox-count"),
    close: document.querySelector("#pdp-lightbox .lightbox__close"),
    prev: document.querySelector("#pdp-lightbox .lightbox__nav--prev"),
    next: document.querySelector("#pdp-lightbox .lightbox__nav--next"),
    zoom: document.querySelector("#pdp-lightbox .lightbox__zoom")
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
      return '<div class="lightbox__slide"><img src="' + EM.escapeHtml(src) + '" alt="Product image ' + (k + 1) + '" draggable="false"></div>';
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
  /* "Back" returns to the exact catalog position when the visitor came from it */
  document.querySelectorAll(".pdp__back").forEach(function (back) {
    back.addEventListener("click", function (e) {
      var cameFromCatalog = false;
      try {
        cameFromCatalog = document.referrer &&
          new URL(document.referrer).pathname === "/giveaways.html" && history.length > 1;
      } catch (err) { cameFromCatalog = false; }
      if (cameFromCatalog) {
        e.preventDefault();
        history.back();
      }
    });
  });

  updateFab();
  if (!productId) {
    showMissing();
  } else {
    loadCatalog().then(function (products) {
      var all = products || [];
      var p = null;
      all.forEach(function (x) { if (x.id === productId) p = x; });
      if (p) {
        var key = EM.giftKey(p);
        group = all.filter(function (x) { return EM.giftKey(x) === key; });
        render(p);
      } else {
        showMissing();
      }
    }).catch(showMissing);
  }
})();
