/* ============================================================
   ELITE MARCOM — shared site behaviour
   theme · header · menu · cursor · reveals · marquee · helpers
   ============================================================ */
(function () {
  "use strict";

  var doc = document;
  var root = doc.documentElement;
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  var finePointer = window.matchMedia("(hover: hover) and (pointer: fine)");

  /* ---------- namespace ---------- */
  var EM = (window.EM = window.EM || {});
  EM.reducedMotion = function () { return reduceMotion.matches; };
  EM.finePointer = function () { return finePointer.matches; };

  /* ---------- theme ---------- */
  var THEME_KEY = "em-theme";
  function setTheme(theme, persist) {
    root.setAttribute("data-theme", theme);
    if (persist) {
      try { localStorage.setItem(THEME_KEY, theme); } catch (e) { /* private mode */ }
    }
    doc.querySelectorAll(".theme-toggle").forEach(function (btn) {
      btn.setAttribute("aria-label", theme === "dark" ? "Switch to light theme" : "Switch to dark theme");
    });
  }
  doc.addEventListener("click", function (e) {
    var btn = e.target.closest(".theme-toggle");
    if (!btn) return;
    var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    setTheme(next, true);
  });
  setTheme(root.getAttribute("data-theme") || "dark", false);

  /* ---------- header scroll state + scroll progress ---------- */
  var header = doc.querySelector(".site-header");
  var progress = doc.querySelector(".scroll-progress");
  var scrollScheduled = false;
  function onScroll() {
    if (scrollScheduled) return;
    scrollScheduled = true;
    requestAnimationFrame(function () {
      scrollScheduled = false;
      var y = window.scrollY;
      if (header) header.classList.toggle("is-scrolled", y > 24);
      if (progress) {
        var max = doc.documentElement.scrollHeight - window.innerHeight;
        progress.style.transform = "scaleX(" + (max > 0 ? Math.min(1, y / max) : 0) + ")";
      }
    });
  }
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  /* ---------- focus trap helper ---------- */
  var FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
  EM.trapFocus = function (container, e) {
    var items = Array.prototype.filter.call(container.querySelectorAll(FOCUSABLE), function (el) {
      return el.offsetParent !== null || el === doc.activeElement;
    });
    if (!items.length) return;
    var first = items[0];
    var last = items[items.length - 1];
    if (e.shiftKey && doc.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && doc.activeElement === last) { e.preventDefault(); first.focus(); }
  };

  /* ---------- expanded menu panel ---------- */
  var menuPanel = doc.querySelector(".menu-panel");
  var menuScrim = doc.querySelector(".menu-scrim");
  var menuTrigger = doc.querySelector(".menu-trigger");
  var menuOpen = false;
  var menuReturnFocus = null;

  function openMenu() {
    if (!menuPanel) return;
    menuOpen = true;
    menuReturnFocus = doc.activeElement;
    doc.body.classList.add("menu-open", "scroll-locked");
    menuPanel.setAttribute("aria-hidden", "false");
    if (menuTrigger) menuTrigger.setAttribute("aria-expanded", "true");
    var closeBtn = menuPanel.querySelector(".menu-close");
    if (closeBtn) closeBtn.focus();
  }
  function closeMenu() {
    if (!menuPanel || !menuOpen) return;
    menuOpen = false;
    doc.body.classList.remove("menu-open", "scroll-locked");
    menuPanel.setAttribute("aria-hidden", "true");
    if (menuTrigger) menuTrigger.setAttribute("aria-expanded", "false");
    if (menuReturnFocus && menuReturnFocus.focus) menuReturnFocus.focus();
  }
  if (menuTrigger) menuTrigger.addEventListener("click", function () { menuOpen ? closeMenu() : openMenu(); });
  if (menuScrim) menuScrim.addEventListener("click", closeMenu);
  if (menuPanel) {
    menuPanel.addEventListener("click", function (e) {
      if (e.target.closest(".menu-close") || e.target.closest("a")) closeMenu();
    });
    menuPanel.addEventListener("keydown", function (e) {
      if (e.key === "Tab") EM.trapFocus(menuPanel, e);
    });
  }
  doc.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && menuOpen) closeMenu();
  });

  /* ---------- custom cursor ---------- */
  (function initCursor() {
    if (!finePointer.matches || reduceMotion.matches) return;
    var dot = doc.createElement("div");
    var ring = doc.createElement("div");
    dot.className = "cursor-dot";
    ring.className = "cursor-ring";
    dot.setAttribute("aria-hidden", "true");
    ring.setAttribute("aria-hidden", "true");
    doc.body.appendChild(dot);
    doc.body.appendChild(ring);
    doc.body.classList.add("has-cursor");

    var tx = -100, ty = -100, rx = -100, ry = -100, raf = null;
    function frame() {
      rx += (tx - rx) * 0.18;
      ry += (ty - ry) * 0.18;
      dot.style.transform = "translate3d(" + tx + "px," + ty + "px,0)";
      ring.style.transform = "translate3d(" + rx + "px," + ry + "px,0)";
      if (Math.abs(tx - rx) > 0.3 || Math.abs(ty - ry) > 0.3) raf = requestAnimationFrame(frame);
      else raf = null;
    }
    doc.addEventListener("pointermove", function (e) {
      if (e.pointerType !== "mouse") return;
      tx = e.clientX; ty = e.clientY;
      if (!raf) raf = requestAnimationFrame(frame);
    }, { passive: true });
    doc.addEventListener("pointerover", function (e) {
      var interactive = e.target.closest("a, button, [role=\"button\"], .product-card, .project-card, [data-cursor]");
      ring.classList.toggle("is-active", !!interactive);
      ring.classList.toggle("is-drag", !!(interactive && interactive.getAttribute && interactive.getAttribute("data-cursor") === "drag"));
    });
    doc.addEventListener("pointerleave", function () {
      tx = ty = -100;
      if (!raf) raf = requestAnimationFrame(frame);
    });
  })();

  /* ---------- scroll reveals ---------- */
  (function initReveals() {
    var items = doc.querySelectorAll(".reveal");
    if (!items.length) return;
    if (reduceMotion.matches || !("IntersectionObserver" in window)) {
      root.classList.add("reveals-off");
      items.forEach(function (el) { el.classList.add("is-visible"); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        var el = entry.target;
        var delay = Math.min(parseInt(el.getAttribute("data-reveal-delay") || "0", 10), 420);
        el.style.setProperty("--reveal-delay", delay + "ms");
        el.classList.add("is-visible");
        io.unobserve(el);
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
    items.forEach(function (el) { io.observe(el); });
    /* fail-safe: never leave content invisible */
    setTimeout(function () {
      doc.querySelectorAll(".reveal:not(.is-visible)").forEach(function (el) {
        var r = el.getBoundingClientRect();
        if (r.top < window.innerHeight && r.bottom > 0) el.classList.add("is-visible");
      });
    }, 2200);
    setTimeout(function () {
      doc.querySelectorAll(".reveal:not(.is-visible)").forEach(function (el) { el.classList.add("is-visible"); });
    }, 6000);
    EM.observeReveal = function (el) { io.observe(el); };
  })();

  /* process line reveal */
  (function () {
    var procs = doc.querySelectorAll(".process");
    if (!procs.length) return;
    if (reduceMotion.matches || !("IntersectionObserver" in window)) {
      procs.forEach(function (p) { p.classList.add("is-visible"); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add("is-visible"); io.unobserve(en.target); }
      });
    }, { threshold: 0.25 });
    procs.forEach(function (p) { io.observe(p); });
  })();

  /* ---------- marquee: duplicate track for seamless loop ---------- */
  doc.querySelectorAll(".marquee").forEach(function (mq) {
    var track = mq.querySelector(".marquee__track");
    var group = mq.querySelector(".marquee__group");
    if (!track || !group || reduceMotion.matches) return;
    var clone = group.cloneNode(true);
    clone.setAttribute("aria-hidden", "true");
    track.appendChild(clone);
    var speed = parseFloat(mq.getAttribute("data-speed") || "70"); /* px per second */
    requestAnimationFrame(function () {
      var w = group.scrollWidth;
      if (w > 0) track.style.setProperty("--marquee-dur", (w / speed).toFixed(2) + "s");
    });
    /* pause offscreen */
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          track.style.animationPlayState = en.isIntersecting ? "running" : "paused";
        });
      }).observe(mq);
    }
  });

  /* ---------- magnetic buttons ---------- */
  if (finePointer.matches && !reduceMotion.matches) {
    doc.querySelectorAll("[data-magnetic]").forEach(function (el) {
      var raf = null, mx = 0, my = 0;
      el.addEventListener("pointermove", function (e) {
        var r = el.getBoundingClientRect();
        mx = (e.clientX - r.left - r.width / 2) * 0.18;
        my = (e.clientY - r.top - r.height / 2) * 0.22;
        if (!raf) raf = requestAnimationFrame(function () {
          raf = null;
          el.style.transform = "translate(" + mx.toFixed(1) + "px," + my.toFixed(1) + "px)";
        });
      });
      el.addEventListener("pointerleave", function () {
        if (raf) cancelAnimationFrame(raf);
        raf = null;
        el.style.transform = "";
      });
    });
  }

  /* ---------- count-up ---------- */
  (function () {
    var nums = doc.querySelectorAll("[data-countup]");
    if (!nums.length) return;
    if (reduceMotion.matches || !("IntersectionObserver" in window)) return;
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        io.unobserve(en.target);
        var el = en.target;
        var target = parseFloat(el.getAttribute("data-countup"));
        if (isNaN(target)) return;
        var suffix = el.getAttribute("data-countup-suffix") || "";
        var start = null;
        var durMs = 1200;
        function step(ts) {
          if (!start) start = ts;
          var p = Math.min(1, (ts - start) / durMs);
          var eased = 1 - Math.pow(1 - p, 3);
          el.textContent = Math.round(target * eased) + suffix;
          if (p < 1) requestAnimationFrame(step);
        }
        requestAnimationFrame(step);
      });
    }, { threshold: 0.6 });
    nums.forEach(function (el) { io.observe(el); });
  })();

  /* ---------- scroll-linked parallax (light) ---------- */
  (function () {
    if (reduceMotion.matches) return;
    var els = doc.querySelectorAll("[data-parallax]");
    if (!els.length) return;
    var ticking = false;
    function update() {
      ticking = false;
      var vh = window.innerHeight;
      els.forEach(function (el) {
        var r = el.getBoundingClientRect();
        if (r.bottom < -100 || r.top > vh + 100) return;
        var f = parseFloat(el.getAttribute("data-parallax") || "0.1");
        var center = r.top + r.height / 2 - vh / 2;
        el.style.transform = "translate3d(0," + (-center * f).toFixed(1) + "px,0)";
      });
    }
    window.addEventListener("scroll", function () {
      if (!ticking) { ticking = true; requestAnimationFrame(update); }
    }, { passive: true });
    update();
  })();

  /* ---------- footer year ---------- */
  doc.querySelectorAll("[data-year]").forEach(function (el) {
    el.textContent = String(new Date().getFullYear());
  });

  /* ---------- toast ---------- */
  var toastRegion = null;
  EM.toast = function (message, kind) {
    if (!toastRegion) {
      toastRegion = doc.createElement("div");
      toastRegion.className = "toast-region";
      toastRegion.setAttribute("role", "status");
      toastRegion.setAttribute("aria-live", "polite");
      doc.body.appendChild(toastRegion);
    }
    var t = doc.createElement("div");
    t.className = "toast" + (kind === "ok" ? " toast--ok" : kind === "err" ? " toast--err" : "");
    t.textContent = message;
    toastRegion.appendChild(t);
    setTimeout(function () {
      t.style.opacity = "0";
      t.style.transition = "opacity 0.4s linear";
      setTimeout(function () { t.remove(); }, 450);
    }, 4200);
  };

  /* ---------- dialog helper ---------- */
  EM.dialog = function (scrimEl) {
    var lastFocus = null;
    var dialogEl = scrimEl.querySelector(".dialog");
    function open() {
      lastFocus = doc.activeElement;
      scrimEl.classList.add("is-open");
      doc.body.classList.add("scroll-locked");
      var target = dialogEl.querySelector("[data-autofocus]") || dialogEl.querySelector(".dialog__close") || dialogEl;
      if (target && target.focus) target.focus();
    }
    function close() {
      scrimEl.classList.remove("is-open");
      doc.body.classList.remove("scroll-locked");
      if (lastFocus && lastFocus.focus) lastFocus.focus();
    }
    scrimEl.addEventListener("mousedown", function (e) { if (e.target === scrimEl) close(); });
    scrimEl.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { e.stopPropagation(); close(); }
      if (e.key === "Tab") EM.trapFocus(dialogEl, e);
    });
    scrimEl.querySelectorAll(".dialog__close, [data-dialog-close]").forEach(function (b) {
      b.addEventListener("click", close);
    });
    return { open: open, close: close, el: dialogEl, isOpen: function () { return scrimEl.classList.contains("is-open"); } };
  };

  /* ---------- drawer helper ---------- */
  EM.drawer = function (drawerEl, scrimEl) {
    var lastFocus = null;
    function open() {
      lastFocus = doc.activeElement;
      drawerEl.classList.add("is-open");
      if (scrimEl) scrimEl.classList.add("is-open");
      doc.body.classList.add("scroll-locked");
      var target = drawerEl.querySelector("[data-autofocus]") || drawerEl.querySelector("button, a, input");
      if (target) target.focus();
    }
    function close() {
      drawerEl.classList.remove("is-open");
      if (scrimEl) scrimEl.classList.remove("is-open");
      doc.body.classList.remove("scroll-locked");
      if (lastFocus && lastFocus.focus) lastFocus.focus();
    }
    if (scrimEl) scrimEl.addEventListener("click", close);
    drawerEl.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { e.stopPropagation(); close(); }
      if (e.key === "Tab") EM.trapFocus(drawerEl, e);
    });
    drawerEl.querySelectorAll("[data-drawer-close]").forEach(function (b) { b.addEventListener("click", close); });
    return { open: open, close: close, el: drawerEl, isOpen: function () { return drawerEl.classList.contains("is-open"); } };
  };

  /* ---------- API helpers ---------- */
  EM.api = function (path, options) {
    options = options || {};
    var init = {
      method: options.method || "GET",
      headers: Object.assign({ "Accept": "application/json" }, options.headers || {}),
      credentials: "same-origin"
    };
    if (options.json) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(options.json);
    } else if (options.body) {
      init.body = options.body;
    }
    return fetch(path, init).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        return { ok: res.ok, status: res.status, data: data };
      });
    });
  };

  /* one-time signed form challenge */
  EM.getChallenge = function (form) {
    return EM.api("/api/security/challenge?form=" + encodeURIComponent(form)).then(function (r) {
      if (!r.ok || !r.data || !r.data.challenge) throw new Error("challenge");
      return r.data.challenge;
    });
  };

  /* security config (consent version, turnstile site key) — cached */
  var secConfig = null;
  EM.securityConfig = function () {
    if (secConfig) return Promise.resolve(secConfig);
    return EM.api("/api/security/config").then(function (r) {
      secConfig = (r.ok && r.data) ? r.data : { consentVersion: "2026-01", turnstileSiteKey: null };
      return secConfig;
    }).catch(function () {
      secConfig = { consentVersion: "2026-01", turnstileSiteKey: null };
      return secConfig;
    });
  };

  /* ---------- localStorage helpers ---------- */
  EM.store = {
    get: function (key, fallback) {
      try {
        var raw = localStorage.getItem(key);
        return raw === null ? fallback : JSON.parse(raw);
      } catch (e) { return fallback; }
    },
    set: function (key, value) {
      try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* full/private */ }
    },
    remove: function (key) {
      try { localStorage.removeItem(key); } catch (e) { /* noop */ }
    }
  };

  EM.escapeHtml = function (s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  };

  EM.formatQty = function (n) { return String(Math.max(0, Math.floor(n))); };

  /* ---------- image carousel (catalog cards + product page) ----------
     markup: .carousel > .carousel__track > img*, buttons/dots injected here.
     Buttons auto-hide: visible only on hover/focus, and never for 1 image. */
  EM.carousel = function (root) {
    var track = root.querySelector(".carousel__track");
    if (!track) return;
    var slides = track.children.length;
    if (slides <= 1) { root.classList.add("carousel--single"); return; }

    var prev = doc.createElement("button");
    prev.type = "button";
    prev.className = "carousel__btn carousel__btn--prev";
    prev.setAttribute("aria-label", "Previous image");
    prev.innerHTML = "&#8249;";
    var next = doc.createElement("button");
    next.type = "button";
    next.className = "carousel__btn carousel__btn--next";
    next.setAttribute("aria-label", "Next image");
    next.innerHTML = "&#8250;";
    var dots = doc.createElement("div");
    dots.className = "carousel__dots";
    dots.setAttribute("aria-hidden", "true");
    for (var i = 0; i < slides; i++) {
      var d = doc.createElement("span");
      d.className = "carousel__dot" + (i === 0 ? " is-active" : "");
      dots.appendChild(d);
    }
    root.appendChild(prev);
    root.appendChild(next);
    root.appendChild(dots);

    function index() {
      return Math.round(track.scrollLeft / Math.max(1, track.clientWidth));
    }
    function go(delta, e) {
      if (e) { e.stopPropagation(); e.preventDefault(); }
      var target = Math.min(slides - 1, Math.max(0, index() + delta));
      track.scrollTo({ left: target * track.clientWidth, behavior: EM.reducedMotion() ? "auto" : "smooth" });
    }
    prev.addEventListener("click", function (e) { go(-1, e); });
    next.addEventListener("click", function (e) { go(1, e); });

    var scrollTimer = null;
    track.addEventListener("scroll", function () {
      clearTimeout(scrollTimer);
      scrollTimer = setTimeout(function () {
        var idx = index();
        dots.querySelectorAll(".carousel__dot").forEach(function (d, i) {
          d.classList.toggle("is-active", i === idx);
        });
      }, 80);
    }, { passive: true });
  };

  /* ---------- corporate gifts: variant grouping ----------
     The supplier lists every size/colour variant as its own product row.
     Rows sharing a template id (or, failing that, name + brand) are one
     product with selectable attributes. */
  EM.giftKey = function (p) {
    if (p.templateId) return "t:" + p.templateId;
    return "n:" + (String(p.name || "") + "|" + String(p.brand || "")).toLowerCase();
  };

  EM.giftGroups = function (products) {
    var map = {}, order = [];
    (products || []).forEach(function (p) {
      var k = EM.giftKey(p);
      if (!map[k]) { map[k] = []; order.push(k); }
      map[k].push(p);
    });
    return order.map(function (k) { return map[k]; });
  };

  /* Ordered attribute map for one variant: [["Size","Small"],["Color","Black"]].
     Built from "Label: value" options; the plain colour field fills in when no
     Color attribute exists. */
  EM.variantAttrs = function (p) {
    var rows = [], seen = {};
    (p.options || []).forEach(function (o) {
      var m = /^([^:]{1,40}):\s*(.+)$/.exec(String(o));
      if (m) {
        var label = m[1].trim();
        if (!seen[label]) { seen[label] = true; rows.push([label, m[2].trim()]); }
      }
    });
    if (!seen.Color && !seen.Colour && p.color) rows.push(["Color", p.color]);
    return rows;
  };
})();
