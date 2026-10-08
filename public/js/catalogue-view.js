/* Shared web catalogue — the viewer.
 *
 * Three rules this file keeps.
 *
 * Nothing is built from a string of markup. Every product name, code,
 * specification and category arrives as data and is put on the page with
 * `textContent`, so no supplier text can ever be read as HTML. Setting
 * markup from a string is forbidden here, and a test reads this file to say
 * so — which is why the forbidden property is not named in this comment.
 *
 * The catalogue is loaded in two stages. `index.json` is one small record per
 * product — name, code, the first picture, availability, categories — which
 * is what the grid, the search box and the filters need; the specifications
 * and the description are the bulk of a catalogue and are fetched one product
 * at a time, when somebody actually opens one. On a five-hundred product
 * catalogue that is tens of kilobytes instead of half a megabyte before the
 * first card appears.
 *
 * The link is the credential, so it only ever travels in the path this page
 * was opened at. Nothing here reads or writes a cookie, and there is no
 * analytics: a client looking at a catalogue is not something to measure
 * beyond the one count the server keeps.
 */
(function () {
  "use strict";

  var body = document.body;
  if (!body || body.getAttribute("data-state") !== "ok") return;

  /* /catalogue/<token> — and nothing else is read out of the address. */
  var match = /^\/catalogue\/([A-Za-z0-9_-]{8,120})\/?$/.exec(location.pathname);
  var token = match ? match[1] : "";
  var base = "/catalogue/" + encodeURIComponent(token);

  var PAGE = 24;                         // cards added per step
  var state = { items: [], shown: 0, filter: "", cat: "", lowStock: 20,
                cache: {}, meta: null, opener: null };

  var el = {
    title: document.getElementById("cv-title"),
    market: document.getElementById("cv-market"),
    q: document.getElementById("cv-q"),
    count: document.getElementById("cv-count"),
    chips: document.getElementById("cv-chips"),
    grid: document.getElementById("cv-grid"),
    empty: document.getElementById("cv-empty"),
    more: document.getElementById("cv-more"),
    sentinel: document.getElementById("cv-sentinel"),
    fail: document.getElementById("cv-fail"),
    stock: document.getElementById("cv-stock"),
    meta: document.getElementById("cv-meta"),
    pdf: document.getElementById("cv-pdf"),
    detail: document.getElementById("cv-detail"),
    detailBody: document.getElementById("cv-detail-body"),
    close: document.getElementById("cv-close")
  };

  /* ---------------- small helpers ---------------- */

  function node(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = String(text);
    return n;
  }

  function imageUrl(hash) {
    return /^[0-9a-f]{64}$/.test(String(hash || ""))
      ? base + "/i/" + hash + ".webp" : "";
  }

  function num(n) {
    return typeof n === "number" && isFinite(n)
      ? n.toLocaleString("en-US") : "";
  }

  function dateText(ts) {
    if (!ts) return "";
    try {
      return new Date(ts * 1000).toLocaleDateString("en-GB",
        { day: "numeric", month: "long", year: "numeric" });
    } catch (e) { return ""; }
  }

  function get(path) {
    return fetch(base + path, { credentials: "omit", headers: { Accept: "application/json" } })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); });
  }

  /* ---------------- the grid ---------------- */

  function matches(item) {
    if (state.cat && (item.cats || []).indexOf(state.cat) < 0) return false;
    if (!state.filter) return true;
    var hay = ((item.name || "") + " " + (item.code || "") + " " +
               (item.cats || []).join(" ")).toLowerCase();
    return state.filter.split(/\s+/).every(function (term) {
      return !term || hay.indexOf(term) >= 0;
    });
  }

  function filtered() {
    return state.items.filter(matches);
  }

  function card(item) {
    var btn = node("button", "cv-card");
    btn.type = "button";
    var shot = node("div", "cv-card__shot");
    var url = imageUrl(item.img);
    if (url) {
      var img = node("img");
      img.src = url;
      img.alt = item.name || "Product";
      img.loading = "lazy";
      img.decoding = "async";
      /* No width/height attributes: the picture's real shape is whatever the
         supplier shot, and the tile already reserves its own square, so
         there is no layout shift to prevent and no aspect ratio to guess
         wrong. */
      shot.appendChild(img);
    } else {
      shot.appendChild(node("span", "cv-card__none", "No photograph"));
    }
    btn.appendChild(shot);
    var text = node("div", "cv-card__text");
    if (item.code) text.appendChild(node("span", "cv-card__code", item.code));
    text.appendChild(node("span", "cv-card__name", item.name || "Product"));
    if (item.stockText) {
      var low = item.known && typeof item.qty === "number" &&
                item.qty > 0 && item.qty <= state.lowStock;
      var line = node("span", "cv-card__stock" + (low ? " is-low" : ""));
      var qty = node("b", null, item.stockText);
      line.appendChild(qty);
      if (low) line.appendChild(node("span", null, " · low stock"));
      text.appendChild(line);
    }
    btn.appendChild(text);
    btn.addEventListener("click", function () { openDetail(item.i, btn); });
    return btn;
  }

  function render(reset) {
    var rows = filtered();
    if (reset) {
      el.grid.textContent = "";
      state.shown = 0;
    }
    var frag = document.createDocumentFragment();
    var upto = Math.min(rows.length, state.shown + PAGE);
    for (var n = state.shown; n < upto; n++) frag.appendChild(card(rows[n]));
    el.grid.appendChild(frag);
    state.shown = upto;
    el.more.hidden = state.shown >= rows.length;
    el.empty.hidden = rows.length > 0;
    el.count.textContent = rows.length === state.items.length
      ? num(rows.length) + (rows.length === 1 ? " product" : " products")
      : num(rows.length) + " of " + num(state.items.length);
  }

  function refilter() {
    render(true);
  }

  /* ---------------- categories ---------------- */

  function chips() {
    var seen = {};
    state.items.forEach(function (item) {
      (item.cats || []).forEach(function (c) { seen[c] = (seen[c] || 0) + 1; });
    });
    var names = Object.keys(seen).sort(function (a, b) { return seen[b] - seen[a]; });
    if (names.length < 2) return;
    el.chips.hidden = false;
    var all = node("button", "cv-chip", "All");
    all.type = "button";
    all.setAttribute("aria-pressed", "true");
    var buttons = [all];
    names.slice(0, 18).forEach(function (name) {
      var b = node("button", "cv-chip", name);
      b.type = "button";
      b.setAttribute("aria-pressed", "false");
      b.setAttribute("data-cat", name);
      buttons.push(b);
    });
    buttons.forEach(function (b) {
      el.chips.appendChild(b);
      b.addEventListener("click", function () {
        state.cat = b.getAttribute("data-cat") || "";
        buttons.forEach(function (other) {
          other.setAttribute("aria-pressed", other === b ? "true" : "false");
        });
        refilter();
      });
    });
  }

  /* ---------------- one product ---------------- */

  function gallery(item) {
    var wrap = node("div");
    var hashes = (item.img || []).filter(function (h) { return imageUrl(h); });
    var main = node("div", "cv-d-main");
    var img = null;
    if (hashes.length) {
      img = node("img");
      img.src = imageUrl(hashes[0]);
      img.alt = item.name || "Product";
      img.decoding = "async";
      main.appendChild(img);
    } else {
      main.appendChild(node("span", "cv-card__none", "No photograph"));
    }
    wrap.appendChild(main);
    if (hashes.length > 1) {
      var strip = node("div", "cv-d-thumbs");
      var thumbs = [];
      hashes.forEach(function (hash, n) {
        var t = node("button", "cv-d-thumb");
        t.type = "button";
        t.setAttribute("aria-pressed", n === 0 ? "true" : "false");
        t.setAttribute("aria-label", "View picture " + (n + 1));
        var ti = node("img");
        ti.src = imageUrl(hash);
        ti.alt = "";
        ti.loading = "lazy";
        t.appendChild(ti);
        t.addEventListener("click", function () {
          if (img) img.src = imageUrl(hash);
          thumbs.forEach(function (other) {
            other.setAttribute("aria-pressed", other === t ? "true" : "false");
          });
        });
        thumbs.push(t);
        strip.appendChild(t);
      });
      wrap.appendChild(strip);
    }
    return wrap;
  }

  function detailBody(item) {
    var grid = node("div", "cv-d-grid");
    grid.appendChild(gallery(item));
    var side = node("div");
    if (item.code) side.appendChild(node("p", "cv-d-eyebrow", item.code));
    side.appendChild(node("h2", "cv-d-name", item.name || "Product"));
    if (item.stockText) {
      var box = node("div", "cv-d-stock");
      box.appendChild(node("strong", null, item.stockText));
      box.appendChild(node("span", null, "available"));
      side.appendChild(box);
    }
    if (item.desc) side.appendChild(node("p", "cv-d-desc", item.desc));
    if ((item.specs || []).length) {
      var table = node("table", "cv-d-specs");
      table.appendChild(node("caption", null, "Specifications"));
      var tbody = node("tbody");
      item.specs.forEach(function (row) {
        var tr = node("tr");
        tr.appendChild(node("th", null, row[0]));
        tr.appendChild(node("td", null, row[1]));
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      side.appendChild(table);
    }
    if ((item.cats || []).length) {
      var list = node("ul", "cv-d-cats");
      item.cats.forEach(function (c) { list.appendChild(node("li", null, c)); });
      side.appendChild(list);
    }
    side.appendChild(node("p", "cv-d-price",
      "Price on request — branding, quantities and lead times quoted per order."));
    grid.appendChild(side);
    return grid;
  }

  function show(item) {
    el.detailBody.textContent = "";
    el.detailBody.appendChild(detailBody(item));
    if (typeof el.detail.showModal === "function") {
      if (!el.detail.open) el.detail.showModal();
    } else {
      el.detail.setAttribute("open", "open");
    }
    el.close.focus();
  }

  function openDetail(index, from) {
    /* where the keyboard came from, so closing puts it back rather than
       dropping focus to the top of a page of four hundred cards */
    state.opener = from || null;
    if (state.cache[index]) { show(state.cache[index]); return; }
    get("/p/" + encodeURIComponent(index) + ".json").then(function (data) {
      state.cache[index] = data.product;
      show(data.product);
    }).catch(function () {
      /* a product that will not load is not a broken catalogue: the grid
         keeps working and the one card says so */
      show({ name: "This product could not be loaded.", specs: [], img: [] });
    });
  }

  function closeDetail() {
    if (typeof el.detail.close === "function" && el.detail.open) el.detail.close();
    else el.detail.removeAttribute("open");
    if (state.opener && state.opener.isConnected) state.opener.focus();
    state.opener = null;
  }

  /* ---------------- start ---------------- */

  function start(data) {
    state.items = data.items || [];
    state.lowStock = data.lowStock || 20;
    state.meta = data;
    var title = data.title || "Product Catalogue";
    el.title.textContent = title.replace(/\s*\n\s*/g, " — ");
    document.title = el.title.textContent + " — Elite Marcom";
    if (data.market) {
      el.market.textContent = "Corporate gifts · " + String(data.market).toUpperCase();
    }
    if (data.allowPdf) {
      el.pdf.href = base + "/pdf";
      el.pdf.hidden = false;
    }
    var stamp = dateText(data.stockAt);
    el.stock.textContent = stamp
      ? "Availability as of " + stamp + ". Figures are indicative and not a reservation."
      : "Availability is indicative and not a reservation.";
    var bits = [];
    if (data.sharedAt) bits.push("Shared " + dateText(data.sharedAt));
    bits.push(data.expiresAt ? "link valid until " + dateText(data.expiresAt)
                             : "this link does not expire");
    el.meta.textContent = bits.join(" · ") + ".";
    chips();
    render(true);
  }

  el.q.addEventListener("input", function () {
    state.filter = el.q.value.trim().toLowerCase();
    refilter();
  });
  el.more.addEventListener("click", function () { render(false); });
  el.close.addEventListener("click", closeDetail);
  el.detail.addEventListener("click", function (ev) {
    if (ev.target === el.detail) closeDetail();   // the backdrop
  });
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape") closeDetail();
  });

  if ("IntersectionObserver" in window) {
    new IntersectionObserver(function (entries) {
      if (entries.some(function (e) { return e.isIntersecting; }) && !el.more.hidden) {
        render(false);
      }
    }, { rootMargin: "400px" }).observe(el.sentinel);
  }

  if (!token) {
    el.fail.hidden = false;
    return;
  }
  get("/index.json").then(start).catch(function () {
    el.fail.hidden = false;
    el.count.textContent = "";
  });
})();
