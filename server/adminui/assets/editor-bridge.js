/* Elite Marcom visual editor — bridge v2 injected into the iframed preview.
   Element selection with stable paths, live style/attr/animation/section
   application, text updates. Same-origin postMessage only. */
(function () {
  "use strict";
  if (window.top === window) return;

  /* ---------- editor chrome inside the page ---------- */
  var style = document.createElement("style");
  style.textContent =
    "[data-em]{outline:1px dashed rgba(237,108,38,.45);outline-offset:2px;}" +
    "body.em-outlines-off [data-em]{outline:none;}" +
    ".em-hover{outline:2px solid rgba(116,103,199,.85) !important;cursor:pointer;}" +
    ".em-selected{outline:2px solid #ed6c26 !important;box-shadow:0 0 0 4px rgba(237,108,38,.18) !important;}";
  document.head.appendChild(style);
  var liveCss = document.createElement("style");
  liveCss.id = "em-live";
  document.head.appendChild(liveCss);

  var selected = null;
  var origAttrs = {};   // path -> {name: original|null}
  var clones = [];      // preview section duplicates

  function post(msg) { window.parent.postMessage(msg, location.origin); }

  /* ---------- stable paths ---------- */
  function nthOfType(el) {
    var i = 1, sib = el;
    while ((sib = sib.previousElementSibling)) {
      if (sib.tagName === el.tagName) i++;
    }
    return i;
  }
  function pathFor(el) {
    var chain = [];
    var node = el;
    while (node && node !== document.body) {
      var tag = node.tagName.toLowerCase();
      if (node.hasAttribute && node.hasAttribute("data-em-sec")) {
        chain.unshift("[data-em-sec=" + node.getAttribute("data-em-sec") + "]");
        return chain.join(">");
      }
      if (tag === "header" && node.classList.contains("site-header")) {
        chain.unshift("header.site-header");
        return chain.join(">");
      }
      if (tag === "footer" && node.classList.contains("site-footer")) {
        chain.unshift("footer.site-footer");
        return chain.join(">");
      }
      if (tag === "main") {
        chain.unshift("main");
        return chain.join(">");
      }
      chain.unshift(tag + ":nth-of-type(" + nthOfType(node) + ")");
      node = node.parentElement;
    }
    chain.unshift("body");
    return chain.join(">");
  }

  /* An element's text can be replaced wholesale only when nothing structural
     lives inside it — otherwise editing a wrapper would silently delete the
     cards, images or columns it contains. */
  var INLINE_OK = { STRONG: 1, EM: 1, B: 1, I: 1, U: 1, BR: 1, A: 1, SPAN: 1,
                    SMALL: 1, SUP: 1, SUB: 1 };
  function textEditable(el) {
    if (!(el.textContent || "").trim()) return false;
    if (el.hasAttribute("data-em")) return false;      // keyed regions use the content model
    var tag = el.tagName;
    if (tag === "IMG" || tag === "SVG" || tag === "SCRIPT" || tag === "STYLE" ||
        tag === "CANVAS" || tag === "IFRAME" || tag === "VIDEO" || tag === "SELECT" ||
        tag === "INPUT" || tag === "TEXTAREA") return false;
    if (el.hasAttribute("data-em-sec") || el.closest("form")) return false;
    for (var i = 0; i < el.children.length; i++) {
      var child = el.children[i];
      if (!INLINE_OK[child.tagName]) return false;
      if (child.querySelector("*:not(strong):not(em):not(b):not(i):not(u):not(br):not(a):not(span)")) {
        return false;
      }
    }
    return el.children.length <= 4;
  }

  function innerFor(el) {
    var html = el.innerHTML
      .replace(/<!--[\s\S]*?-->/g, "")
      .replace(/\s*(class|style|data-[\w-]+|aria-[\w-]+|id|width|height|loading|target|rel)="[^"]*"/g, "");
    return html.replace(/\s+/g, " ").trim();
  }

  function metaFor(el) {
    var cs = getComputedStyle(el);
    var secEl = el.closest("[data-em-sec]");
    return {
      textEditable: textEditable(el),
      textHtml: textEditable(el) ? innerFor(el) : "",
      type: "em-select",
      path: pathFor(el),
      tag: el.tagName.toLowerCase(),
      emKey: el.getAttribute("data-em"),
      sectionId: secEl ? secEl.getAttribute("data-em-sec") : null,
      isSection: el.hasAttribute("data-em-sec"),
      isImg: el.tagName === "IMG",
      isLink: el.tagName === "A",
      hasBg: cs.backgroundImage !== "none",
      hasText: !!(el.textContent || "").trim() && el.children.length < 6,
      attrs: {
        src: el.getAttribute("src") || "",
        alt: el.getAttribute("alt") || "",
        href: el.getAttribute("href") || "",
        reveal: el.getAttribute("data-reveal") || "",
        revealDelay: el.getAttribute("data-reveal-delay") || "",
        hasRevealClass: el.classList.contains("reveal")
      },
      computed: {
        fontSize: cs.fontSize, fontWeight: cs.fontWeight, lineHeight: cs.lineHeight,
        letterSpacing: cs.letterSpacing, textAlign: cs.textAlign,
        textTransform: cs.textTransform, color: cs.color,
        backgroundColor: cs.backgroundColor, backgroundImage: cs.backgroundImage,
        padding: cs.padding, margin: cs.margin, width: cs.width, height: cs.height,
        maxWidth: cs.maxWidth, borderRadius: cs.borderRadius,
        borderWidth: cs.borderWidth, borderStyle: cs.borderStyle,
        borderColor: cs.borderColor, boxShadow: cs.boxShadow, opacity: cs.opacity
      }
    };
  }

  function select(el) {
    if (selected) selected.classList.remove("em-selected");
    selected = el;
    if (el) {
      el.classList.add("em-selected");
      post(metaFor(el));
    }
  }

  /* ---------- pointer interaction ---------- */
  var hoverEl = null;
  document.addEventListener("mouseover", function (e) {
    var el = e.target;
    if (el === document.body || el === document.documentElement) return;
    if (hoverEl) hoverEl.classList.remove("em-hover");
    hoverEl = el;
    el.classList.add("em-hover");
  });
  document.addEventListener("mouseout", function () {
    if (hoverEl) { hoverEl.classList.remove("em-hover"); hoverEl = null; }
  });
  document.addEventListener("click", function (e) {
    var el = e.target;
    if (el === document.body || el === document.documentElement) return;
    e.preventDefault();
    e.stopPropagation();
    var em = el.closest("[data-em]");
    select(em || el);
  }, true);

  /* ---------- live application ---------- */
  function rememberAttr(el, path, name) {
    var bucket = (origAttrs[path] = origAttrs[path] || {});
    if (!(name in bucket)) bucket[name] = el.hasAttribute(name) ? el.getAttribute(name) : null;
  }
  function applyAttr(el, path, name, value) {
    rememberAttr(el, path, name);
    if (value === null || value === undefined || value === "") {
      var orig = origAttrs[path][name];
      if (orig === null) el.removeAttribute(name); else el.setAttribute(name, orig);
    } else {
      el.setAttribute(name, value);
    }
  }
  function applyAnim(el, path, anim) {
    rememberAttr(el, path, "data-reveal");
    rememberAttr(el, path, "data-reveal-delay");
    rememberAttr(el, path, "class");
    if (!anim || anim.type === "keep") {
      var o = origAttrs[path];
      ["data-reveal", "data-reveal-delay", "class"].forEach(function (name) {
        if (o[name] === null) el.removeAttribute(name); else el.setAttribute(name, o[name]);
      });
      el.classList.add("is-visible");
      return;
    }
    if (anim.type === "none") {
      el.removeAttribute("data-reveal");
      el.removeAttribute("data-reveal-delay");
      el.classList.remove("reveal");
      return;
    }
    el.classList.add("reveal");
    el.setAttribute("data-reveal", anim.type);
    if (anim.delay) el.setAttribute("data-reveal-delay", String(anim.delay));
    else el.removeAttribute("data-reveal-delay");
    el.classList.add("is-visible"); // keep visible while editing
  }

  /* ---------- text replaced by path (elements with no data-em key) ---------- */
  var origHtml = {};    // path -> innerHTML as the page was baked
  function applyPathText(path, html) {
    var el = document.querySelector(path);
    if (!el) return;
    if (!(path in origHtml)) origHtml[path] = el.innerHTML;
    el.innerHTML = (html === null || html === undefined || html === "") ? origHtml[path] : html;
  }

  /* ---------- sections added from the block library ---------- */
  var addedEls = {};    // id -> the element inserted into the preview
  function syncAdded(added) {
    var wanted = {};
    (added || []).forEach(function (item) {
      wanted[item.id] = true;
      // after a save the frame reloads with the block already baked in — it is
      // a real section now, and inserting the preview copy would double it
      if (addedEls[item.id] || document.querySelector('[data-em-sec="' + item.id + '"]')) return;
      var host = document.createElement("div");
      host.innerHTML = item.html;
      var el = host.firstElementChild;
      if (!el) return;
      el.setAttribute("data-em-sec", item.id);
      // reveal animations only fire on scroll; a block dropped in mid-edit
      // has to be visible straight away or it reads as a failed insert
      el.querySelectorAll(".reveal").forEach(function (n) { n.classList.add("is-visible"); });
      addedEls[item.id] = el;
    });
    Object.keys(addedEls).forEach(function (id) {
      if (!wanted[id]) {
        addedEls[id].remove();
        delete addedEls[id];
      }
    });
  }

  var pristineSections = null;
  function capturedSections() {
    if (!pristineSections) {
      var main = document.querySelector("main");
      pristineSections = main
        ? Array.prototype.slice.call(main.querySelectorAll(":scope > section[data-em-sec]"))
        : [];
    }
    return pristineSections;
  }
  function sectionInfo() {
    return capturedSections().map(function (s) {
      var h = s.querySelector("h1,h2,h3");
      return { id: s.getAttribute("data-em-sec"),
               label: (h ? h.textContent.trim().replace(/\s+/g, " ").slice(0, 44) : "")
                      || s.getAttribute("aria-label") || s.className.split(" ")[0] || "section" };
    });
  }
  function applySections(spec) {
    var sections = capturedSections();
    if (!sections.length) return;
    var main = sections[0].parentElement;
    clones.forEach(function (c) { c.remove(); });
    clones = [];
    syncAdded(spec.added);
    var byId = {};
    sections.forEach(function (s) { byId[s.getAttribute("data-em-sec")] = s; });
    Object.keys(addedEls).forEach(function (id) { byId[id] = addedEls[id]; });
    var order = (spec.order || Object.keys(byId)).filter(function (id) { return byId[id]; });
    Object.keys(byId).forEach(function (id) {
      if (order.indexOf(id) === -1) order.push(id);
    });
    var removed = spec.removed || [];
    var anchor = sections[0].previousSibling;
    order.forEach(function (id) {
      var el = byId[id];
      el.style.display = removed.indexOf(id) !== -1 ? "none" : "";
      main.appendChild(el);
      if ((spec.duplicated || []).indexOf(id) !== -1 && removed.indexOf(id) === -1) {
        var clone = el.cloneNode(true);
        clone.removeAttribute("data-em-sec");
        clone.querySelectorAll("[data-em]").forEach(function (n) { n.removeAttribute("data-em"); });
        clone.querySelectorAll(".em-selected,.em-hover").forEach(function (n) {
          n.classList.remove("em-selected", "em-hover");
        });
        clone.querySelectorAll(".reveal").forEach(function (n) { n.classList.add("is-visible"); });
        clones.push(clone);
        main.appendChild(clone);
      }
    });
    void anchor; // sections re-appended in order after any leading content
  }

  window.addEventListener("message", function (ev) {
    if (ev.origin !== location.origin || !ev.data || typeof ev.data !== "object") return;
    var d = ev.data;
    if (d.type === "em-update" && typeof d.key === "string") {
      document.querySelectorAll('[data-em="' + CSS.escape(d.key) + '"]').forEach(function (el) {
        el.innerHTML = d.html;
      });
    } else if (d.type === "em-apply") {
      if (typeof d.css === "string") liveCss.textContent = d.css;
      (d.attrs || []).forEach(function (op) {
        var el = document.querySelector(op.path);
        if (!el) return;
        Object.keys(op.set || {}).forEach(function (name) {
          applyAttr(el, op.path, name, op.set[name]);
        });
      });
      (d.anims || []).forEach(function (op) {
        var el = document.querySelector(op.path);
        if (el) applyAnim(el, op.path, op);
      });
      if (d.sections) applySections(d.sections);
      (d.texts || []).forEach(function (t) {
        document.querySelectorAll('[data-em="' + CSS.escape(t.key) + '"]').forEach(function (el) {
          el.innerHTML = t.html;
        });
      });
      (d.pathTexts || []).forEach(function (t) { applyPathText(t.path, t.html); });
    } else if (d.type === "em-outlines") {
      document.body.classList.toggle("em-outlines-off", !d.on);
    } else if (d.type === "em-select-parent") {
      if (selected && selected.parentElement && selected.parentElement !== document.documentElement &&
          selected.parentElement !== document.body) {
        select(selected.parentElement);
      }
    } else if (d.type === "em-play-anim" && typeof d.path === "string") {
      var el = document.querySelector(d.path);
      if (el) {
        el.classList.remove("is-visible");
        void el.offsetWidth; // reflow so the transition restarts
        setTimeout(function () { el.classList.add("is-visible"); }, 60);
      }
    } else if (d.type === "em-focus" && typeof d.path === "string") {
      var target = document.querySelector(d.path);
      if (target) {
        select(target);
        target.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }
  });

  post({ type: "em-ready", sections: sectionInfo(),
         keys: Array.prototype.map.call(document.querySelectorAll("[data-em]"), function (el) {
           return el.getAttribute("data-em");
         }) });
})();
