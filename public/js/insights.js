/* ============================================================
   ELITE MARCOM — first-party insights beacon
   No cookies. No third-party calls unless GA4 is configured by an
   admin. Sends a small batch of events over the site's own API.
   ============================================================ */
(function () {
  "use strict";
  var doc = document;
  var queue = [];
  var config = null;
  var sent = {};

  /* session id: sessionStorage only — cleared when the tab closes, never a cookie */
  var session = "";
  try {
    session = sessionStorage.getItem("em-s") || "";
    if (!session) {
      session = (Math.random().toString(36) + Math.random().toString(36)).replace(/[^a-z0-9]/g, "").slice(0, 16);
      sessionStorage.setItem("em-s", session);
    }
  } catch (e) { /* private mode: events still count, sessions do not */ }

  function path() {
    return location.pathname.replace(/index\.html$/, "") || "/";
  }
  function push(kind, extra) {
    var ev = { kind: kind, path: path(), session: session };
    if (extra) {
      if (extra.meta) ev.meta = String(extra.meta).slice(0, 120);
      if (extra.metric) ev.metric = extra.metric;
      if (typeof extra.value === "number") ev.value = extra.value;
      if (extra.referrer) ev.referrer = extra.referrer;
    }
    queue.push(ev);
    if (queue.length >= 8) flush();
    else schedule();
  }
  var timer = null;
  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(flush, 2500);
  }
  function flush(useBeacon) {
    if (!queue.length || !config || !config.enabled) return;
    var payload = JSON.stringify({ events: queue.splice(0, 20) });
    clearTimeout(timer);
    try {
      if (useBeacon && navigator.sendBeacon) {
        navigator.sendBeacon("/api/insights/collect", new Blob([payload], { type: "application/json" }));
        return;
      }
      fetch("/api/insights/collect", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: payload, keepalive: true
      }).catch(function () { /* measurement must never disturb the visit */ });
    } catch (e) { /* ignore */ }
  }

  /* ---------- optional GA4 (only when an admin sets a measurement id) ---------- */
  function loadGa4(id) {
    if (!/^G-[A-Z0-9]{4,16}$/.test(id)) return;
    var s = doc.createElement("script");
    s.async = true;
    s.src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(id);
    doc.head.appendChild(s);
    window.dataLayer = window.dataLayer || [];
    window.gtag = function () { window.dataLayer.push(arguments); };
    window.gtag("js", new Date());
    window.gtag("config", id, { anonymize_ip: true });
  }
  function ga4(name, params) {
    if (window.gtag) window.gtag("event", name, params || {});
  }

  /* ---------- page + interaction events ---------- */
  function trackPageview() {
    push("pageview", { referrer: doc.referrer || "" });
    var id = new URLSearchParams(location.search).get("id");
    if (/product\.html$/.test(location.pathname) && id) {
      var name = (doc.getElementById("pdp-title") || {}).textContent || "";
      push("product_view", { meta: (name || "").trim().slice(0, 80) || ("id " + id) });
      ga4("view_item", { item_id: id });
    }
    if (/rental-item\.html$/.test(location.pathname) && id) {
      var rname = (doc.getElementById("rip-title") || {}).textContent || "";
      push("product_view", { meta: "Rental — " + ((rname || id).trim().slice(0, 70)) });
    }
  }

  function watchSearch(id, label) {
    var input = doc.getElementById(id);
    if (!input) return;
    var t = null;
    input.addEventListener("input", function () {
      clearTimeout(t);
      t = setTimeout(function () {
        var term = input.value.trim().toLowerCase().slice(0, 60);
        if (term.length < 3 || sent["s:" + term]) return;
        sent["s:" + term] = 1;
        push("catalog_search", { meta: label + ": " + term });
        ga4("search", { search_term: term });
      }, 1200);
    });
  }

  doc.addEventListener("click", function (e) {
    var add = e.target.closest && e.target.closest("[data-add]");
    if (add) {
      var card = add.closest("[data-id]") || add.closest("article") || doc.body;
      var title = card.querySelector ? card.querySelector("h2,h3,#pdp-title,#rip-title") : null;
      push("add_to_request", { meta: (title ? title.textContent : "").trim().slice(0, 80) });
      ga4("add_to_cart", {});
      return;
    }
    var manual = e.target.closest && e.target.closest('[data-manual], a[href*="/api/giveaways/manual"]');
    if (manual) {
      push("manual_download", { meta: (doc.getElementById("pdp-title") || {}).textContent || "" });
      ga4("file_download", {});
      return;
    }
    var link = e.target.closest && e.target.closest('a[href^="http"]');
    if (link && link.hostname && link.hostname !== location.hostname) {
      push("outbound", { meta: link.hostname.slice(0, 60) });
    }
  }, true);

  doc.addEventListener("change", function (e) {
    var el = e.target;
    if (!el || !el.name) return;
    if (el.matches('select[name], input[type="radio"][name]') &&
        el.closest(".filters, [data-filters], form.filters")) {
      push("filter_use", { meta: (el.name + ": " + el.value).slice(0, 60) });
    }
  }, true);

  /* forms that fail visibly are worth knowing about */
  doc.addEventListener("em:form-error", function (e) {
    push("form_error", { meta: (e.detail && e.detail.form) || "" });
  });

  /* ---------- Core Web Vitals from real visitors ---------- */
  function vitals() {
    if (!("PerformanceObserver" in window)) return;
    function report(metric, value) {
      queue.push({ kind: "vital", metric: metric, value: Math.round(value * 1000) / 1000, path: path() });
      schedule();
    }
    try {
      var lcp = 0;
      new PerformanceObserver(function (list) {
        var entries = list.getEntries();
        lcp = entries[entries.length - 1].startTime;
      }).observe({ type: "largest-contentful-paint", buffered: true });
      var cls = 0;
      new PerformanceObserver(function (list) {
        list.getEntries().forEach(function (entry) {
          if (!entry.hadRecentInput) cls += entry.value;
        });
      }).observe({ type: "layout-shift", buffered: true });
      var inp = 0;
      new PerformanceObserver(function (list) {
        list.getEntries().forEach(function (entry) {
          inp = Math.max(inp, entry.duration || 0);
        });
      }).observe({ type: "event", buffered: true, durationThreshold: 40 });
      new PerformanceObserver(function (list) {
        list.getEntries().forEach(function (entry) {
          if (entry.name === "first-contentful-paint") report("FCP", entry.startTime);
        });
      }).observe({ type: "paint", buffered: true });
      var nav = performance.getEntriesByType("navigation")[0];
      if (nav && nav.responseStart) report("TTFB", nav.responseStart);
      doc.addEventListener("visibilitychange", function () {
        if (doc.visibilityState !== "hidden") return;
        if (lcp) { report("LCP", lcp); lcp = 0; }
        if (cls) { report("CLS", cls); cls = 0; }
        if (inp) { report("INP", inp); inp = 0; }
        flush(true);
      });
    } catch (e) { /* unsupported browser: skip vitals */ }
  }

  window.addEventListener("pagehide", function () { flush(true); });

  fetch("/api/site/insights-config").then(function (r) { return r.json(); }).then(function (cfg) {
    config = cfg;
    if (!cfg || !cfg.enabled) return;
    if (cfg.ga4Id) loadGa4(cfg.ga4Id);
    trackPageview();
    watchSearch("give-search", "gifts");
    watchSearch("rent-search", "rental");
    vitals();
    flush();
  }).catch(function () { /* offline or blocked: site works exactly the same */ });
})();
