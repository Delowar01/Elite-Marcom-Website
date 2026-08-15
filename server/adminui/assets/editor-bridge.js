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
    ".em-selected{outline:2px solid #ed6c26 !important;box-shadow:0 0 0 4px rgba(237,108,38,.18) !important;}" +
    /* the controls that sit on the page itself, so a section is managed where
       it lives rather than only in a list on the right */
    ".em-bar{position:absolute;z-index:2147483000;display:flex;gap:4px;align-items:center;" +
    "padding:5px 6px;border-radius:11px;background:rgba(16,18,26,.94);" +
    "box-shadow:0 10px 30px rgba(0,0,0,.4);font:600 12px/1 system-ui,sans-serif;color:#fff;}" +
    ".em-bar b{font-weight:700;padding:0 8px 0 4px;max-width:190px;overflow:hidden;" +
    "text-overflow:ellipsis;white-space:nowrap;opacity:.85;}" +
    ".em-bar button{all:unset;cursor:pointer;width:26px;height:26px;border-radius:7px;" +
    "display:grid;place-items:center;font-size:13px;color:#fff;}" +
    ".em-bar button:hover{background:rgba(255,255,255,.16);}" +
    ".em-bar button[disabled]{opacity:.3;cursor:default;}" +
    ".em-bar .em-danger:hover{background:rgba(220,66,54,.9);}" +
    ".em-bar .em-grip{cursor:grab;}" +
    /* drag-to-resize on the selected element */
    ".em-handle{position:absolute;z-index:2147483000;background:#ed6c26;border-radius:3px;" +
    "box-shadow:0 0 0 2px rgba(255,255,255,.85);}" +
    ".em-handle--e{width:9px;height:26px;cursor:ew-resize;}" +
    ".em-handle--s{width:26px;height:9px;cursor:ns-resize;}" +
    ".em-handle--se{width:12px;height:12px;cursor:nwse-resize;}" +
    ".em-size{position:absolute;z-index:2147483000;padding:3px 7px;border-radius:7px;" +
    "background:#ed6c26;color:#fff;font:600 11px/1 system-ui,sans-serif;}" +
    /* where a dragged section would land */
    ".em-drop{position:absolute;z-index:2147482999;height:4px;border-radius:2px;background:#ed6c26;" +
    "box-shadow:0 0 12px rgba(237,108,38,.8);}" +
    ".em-dragging{opacity:.45;}" +
    /* A hidden section stays on screen while editing, dimmed and labelled —
       display:none would take its own Show button away with it. The published
       page drops it; the editor keeps it reachable. */
    ".em-off{opacity:.34;filter:grayscale(.55);position:relative;}" +
    ".em-off::after{content:'Hidden — will not be published';position:absolute;" +
    "left:50%;top:10px;transform:translateX(-50%);z-index:5;padding:5px 12px;border-radius:999px;" +
    "background:rgba(16,18,26,.92);color:#fff;font:600 12px/1 system-ui,sans-serif;" +
    "letter-spacing:.02em;pointer-events:none;}";
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
    var sawEl = false;
    while (node && node !== document.body) {
      var tag = node.tagName.toLowerCase();
      if (node.hasAttribute && node.hasAttribute("data-em-sec")) {
        var sec = "[data-em-sec=" + node.getAttribute("data-em-sec") + "]";
        /* A placed element is a DESCENDANT of its section — the blank template
           wraps it in .container > .em-stack. Joining with ">" would produce a
           path that resolves on the server but matches nothing as a CSS
           selector, so a style would look saved and do nothing. */
        if (chain.length && chain[0].indexOf("[data-em-el=") === 0) {
          return sec + " " + chain.join(">");
        }
        chain.unshift(sec);
        return chain.join(">");
      }
      /* An element placed from the library carries its own id. Anchoring on it
         and dropping the tags between it and the section is what keeps a style
         attached when the elements around it are reordered. */
      if (!sawEl && node.hasAttribute && node.hasAttribute("data-em-el")) {
        chain.unshift("[data-em-el=" + node.getAttribute("data-em-el") + "]");
        sawEl = true;
        node = node.parentElement;
        continue;
      }
      if (sawEl) { node = node.parentElement; continue; }
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
    var listEl = el.closest("[data-em-list]");
    var itemEl = null;
    if (listEl && listEl !== el) {
      itemEl = el;
      while (itemEl && itemEl.parentElement !== listEl) itemEl = itemEl.parentElement;
    }
    var elHost = el.closest("[data-em-el]");
    return {
      listName: listEl ? listEl.getAttribute("data-em-list") : null,
      listIndex: itemEl ? Array.prototype.indexOf.call(listEl.children, itemEl) : -1,
      elId: elHost ? elHost.getAttribute("data-em-el") : null,
      elTemplate: elHost ? elHost.getAttribute("data-em-elt") : null,
      blockId: secEl ? secEl.getAttribute("data-em-block") : null,
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
        borderColor: cs.borderColor, boxShadow: cs.boxShadow, opacity: cs.opacity,
        minHeight: cs.minHeight, gap: cs.gap, display: cs.display,
        alignItems: cs.alignItems, justifyContent: cs.justifyContent
      }
    };
  }

  /* ---------- on-page controls: section toolbar, drag-reorder, resize ----------
     A section is managed where it lives. Every button here only reports what
     was asked for; the panel owns the document and sends the result back, so
     the preview never drifts from what will be saved. */

  var bar = null, handles = [], sizeTag = null, dropMark = null;
  var secOrder = [];        // ids in the order the panel currently has them
  var secFlags = {};        // id -> {hidden: bool, added: bool}

  function chrome(cls, tag) {
    var n = document.createElement(tag || "div");
    n.className = cls;
    n.setAttribute("data-em-chrome", "1");
    document.body.appendChild(n);
    return n;
  }
  function clearChrome() {
    if (bar) { bar.remove(); bar = null; }
    handles.forEach(function (h) { h.remove(); });
    handles = [];
    if (sizeTag) { sizeTag.remove(); sizeTag = null; }
  }
  function isChrome(el) { return !!(el.closest && el.closest("[data-em-chrome]")); }

  function sectionOf(el) { return el && el.closest ? el.closest("[data-em-sec]") : null; }

  function place() {
    if (!selected) return;
    var sec = sectionOf(selected);
    if (bar && sec) {
      var r = sec.getBoundingClientRect();
      bar.style.left = Math.max(6, r.left + window.scrollX) + "px";
      bar.style.top = Math.max(6, r.top + window.scrollY - 38) + "px";
    }
    if (handles.length) {
      var b = selected.getBoundingClientRect();
      var x = b.left + window.scrollX, y = b.top + window.scrollY;
      var pos = { e: [x + b.width - 4, y + b.height / 2 - 13],
                  s: [x + b.width / 2 - 13, y + b.height - 4],
                  se: [x + b.width - 6, y + b.height - 6] };
      handles.forEach(function (h) {
        var p = pos[h.getAttribute("data-em-h")];
        h.style.left = p[0] + "px";
        h.style.top = p[1] + "px";
      });
    }
  }

  function labelOf(sec) {
    var h = sec.querySelector("h1,h2,h3");
    return (h ? h.textContent.trim().replace(/\s+/g, " ").slice(0, 40) : "") ||
           sec.getAttribute("aria-label") || "Section";
  }

  function buildBar(sec) {
    var id = sec.getAttribute("data-em-sec");
    var flags = secFlags[id] || {};
    var i = secOrder.indexOf(id);
    bar = chrome("em-bar");
    function btn(action, glyph, title, danger, disabled) {
      var b = document.createElement("button");
      b.type = "button";
      b.textContent = glyph;
      b.title = title;
      if (danger) b.className = "em-danger";
      if (disabled) b.disabled = true;
      b.addEventListener("mousedown", function (e) { e.stopPropagation(); });
      b.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        post({ type: "em-sec-action", action: action, id: id });
      });
      bar.appendChild(b);
      return b;
    }
    var grip = document.createElement("button");
    grip.type = "button";
    grip.className = "em-grip";
    grip.textContent = "⠿";
    grip.title = "Drag to reorder";
    bar.appendChild(grip);
    var name = document.createElement("b");
    name.textContent = labelOf(sec);
    bar.appendChild(name);
    btn("up", "↑", "Move up", false, i <= 0);
    btn("down", "↓", "Move down", false, i === -1 || i === secOrder.length - 1);
    btn("duplicate", "⧉", "Duplicate this section");
    btn("copy", "⎘", "Copy — paste it on any page");
    btn("hide", flags.hidden ? "🚫" : "👁", flags.hidden ? "Show again" : "Hide from the page");
    btn("delete", "🗑", "Delete this section", true);
    dragSection(grip, sec, id);
  }

  /* ---------- drag a section to a new place ---------- */
  function dragSection(grip, sec, id) {
    grip.addEventListener("mousedown", function (down) {
      down.preventDefault();
      down.stopPropagation();
      var sections = Array.prototype.slice.call(
        document.querySelectorAll("main > [data-em-sec]"));
      if (sections.length < 2) return;
      sec.classList.add("em-dragging");
      dropMark = chrome("em-drop");
      var target = null, moved = false;   // "before nothing" is a real target
      function over(move) {
        var y = move.clientY;
        var best = null, bestGap = Infinity, beforeId = null;
        sections.forEach(function (s) {
          if (s === sec) return;
          var r = s.getBoundingClientRect();
          [[r.top, s.getAttribute("data-em-sec")], [r.bottom, null]].forEach(function (edge, k) {
            var gap = Math.abs(edge[0] - y);
            if (gap < bestGap) {
              bestGap = gap;
              best = edge[0];
              beforeId = k === 0 ? edge[1] : nextSectionId(s);
            }
          });
        });
        if (best === null) return;
        if (Math.abs(move.clientY - down.clientY) < 4 &&
            Math.abs(move.clientX - down.clientX) < 4) return;   // click jitter
        target = beforeId;
        moved = true;
        var wide = document.querySelector("main").getBoundingClientRect();
        dropMark.style.left = (wide.left + window.scrollX) + "px";
        dropMark.style.width = wide.width + "px";
        dropMark.style.top = (best + window.scrollY - 2) + "px";
      }
      function nextSectionId(s) {
        var i = sections.indexOf(s);
        var nxt = sections[i + 1];
        return nxt && nxt !== sec ? nxt.getAttribute("data-em-sec")
                                  : (sections[i + 2] ? sections[i + 2].getAttribute("data-em-sec") : null);
      }
      function up() {
        document.removeEventListener("mousemove", over, true);
        document.removeEventListener("mouseup", up, true);
        sec.classList.remove("em-dragging");
        if (dropMark) { dropMark.remove(); dropMark = null; }
        // a press with no travel is someone taking hold of the handle, not a
        // reorder — posting here moved the section to the bottom of the page
        if (moved) post({ type: "em-sec-action", action: "move", id: id, before: target });
      }
      document.addEventListener("mousemove", over, true);
      document.addEventListener("mouseup", up, true);
    });
  }

  /* ---------- drag the selected element's edge to resize it ---------- */
  function buildHandles(el) {
    if (el.hasAttribute("data-em-sec")) return;   // a section spans the page
    ["e", "s", "se"].forEach(function (dir) {
      var h = chrome("em-handle em-handle--" + dir);
      h.setAttribute("data-em-h", dir);
      h.addEventListener("mousedown", function (down) {
        down.preventDefault();
        down.stopPropagation();
        var box = el.getBoundingClientRect();
        var startX = down.clientX, startY = down.clientY;
        var w = Math.round(box.width), ht = Math.round(box.height);
        sizeTag = sizeTag || chrome("em-size");
        function move(m) {
          var nw = Math.max(24, Math.round(w + (m.clientX - startX)));
          var nh = Math.max(16, Math.round(ht + (m.clientY - startY)));
          if (dir !== "s") el.style.width = nw + "px";
          if (dir !== "e") el.style.height = nh + "px";
          sizeTag.textContent = (dir === "s" ? "" : nw + "px") +
            (dir === "se" ? " × " : "") + (dir === "e" ? "" : nh + "px");
          var b2 = el.getBoundingClientRect();
          sizeTag.style.left = (b2.left + window.scrollX) + "px";
          sizeTag.style.top = (b2.top + window.scrollY - 26) + "px";
          place();
        }
        function up() {
          document.removeEventListener("mousemove", move, true);
          document.removeEventListener("mouseup", up, true);
          if (sizeTag) { sizeTag.remove(); sizeTag = null; }
          var out = { type: "em-resize", path: pathFor(el) };
          if (dir !== "s") out.width = el.style.width;
          if (dir !== "e") out.height = el.style.height;
          /* the inline style was only for the drag; the panel writes the real
             value into the document and sends the stylesheet back */
          el.style.width = "";
          el.style.height = "";
          post(out);
        }
        document.addEventListener("mousemove", move, true);
        document.addEventListener("mouseup", up, true);
      });
      handles.push(h);
    });
  }

  function decorate() {
    clearChrome();
    if (!selected) return;
    var sec = sectionOf(selected);
    if (sec) buildBar(sec);
    buildHandles(selected);
    place();
  }

  window.addEventListener("scroll", place, { passive: true });
  window.addEventListener("resize", place);

  function select(el) {
    if (selected) selected.classList.remove("em-selected");
    selected = el;
    if (el) {
      el.classList.add("em-selected");
      post(metaFor(el));
    }
    decorate();
  }

  /* ---------- pointer interaction ---------- */
  var hoverEl = null;
  document.addEventListener("mouseover", function (e) {
    var el = e.target;
    if (el === document.body || el === document.documentElement || isChrome(el)) return;
    if (hoverEl) hoverEl.classList.remove("em-hover");
    hoverEl = el;
    el.classList.add("em-hover");
  });
  document.addEventListener("mouseout", function () {
    if (hoverEl) { hoverEl.classList.remove("em-hover"); hoverEl = null; }
  });
  document.addEventListener("click", function (e) {
    var el = e.target;
    if (el === document.body || el === document.documentElement || isChrome(el)) return;
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
  var addedHtml = {};   // id -> the markup it was built from
  var pendingSelect = null;   // what to re-select after a section is rebuilt
  function syncAdded(added) {
    var wanted = {};
    (added || []).forEach(function (item) {
      wanted[item.id] = true;
      // an element added to or removed from a blank section changes its
      // markup, so a live copy has to be rebuilt rather than left alone
      var reselect = null;
      if (addedEls[item.id] && addedHtml[item.id] !== item.html) {
        if (selected && addedEls[item.id].contains(selected)) {
          // the node about to be removed is the selected one: remember what to
          // select again, or the toolbar and handles measure a detached
          // element and land in the page's top-left corner
          var host = selected.closest("[data-em-el]");
          reselect = host ? host.getAttribute("data-em-el") : true;
        }
        addedEls[item.id].remove();
        delete addedEls[item.id];
      }
      // after a save the frame reloads with the block already baked in — it is
      // a real section now, and inserting the preview copy would double it
      if (addedEls[item.id] || document.querySelector('[data-em-sec="' + item.id + '"]')) return;
      var host = document.createElement("div");
      host.innerHTML = item.html;
      var el = host.firstElementChild;
      if (!el) return;
      addedHtml[item.id] = item.html;
      el.setAttribute("data-em-sec", item.id);
      if (reselect) {
        pendingSelect = reselect === true ? el
          : el.querySelector('[data-em-el="' + reselect + '"]') || el;
      }
      // reveal animations only fire on scroll; a block dropped in mid-edit
      // has to be visible straight away or it reads as a failed insert
      el.querySelectorAll(".reveal").forEach(function (n) { n.classList.add("is-visible"); });
      addedEls[item.id] = el;
    });
    Object.keys(addedEls).forEach(function (id) {
      if (!wanted[id]) {
        addedEls[id].remove();
        delete addedEls[id];
        delete addedHtml[id];
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
    secFlags = {};
    (spec.removed || []).forEach(function (id) {
      secFlags[id] = Object.assign(secFlags[id] || {}, { hidden: true });
    });
    (spec.added || []).forEach(function (a) {
      secFlags[a.id] = Object.assign(secFlags[a.id] || {}, { added: true });
    });
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
      el.classList.toggle("em-off", removed.indexOf(id) !== -1);
      el.style.display = "";
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
    secOrder = order.slice();
    if (pendingSelect) {
      var again = pendingSelect;
      pendingSelect = null;
      if (again.isConnected) { select(again); return; }
    }
    decorate();
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
      setTimeout(place, 0);   // a restyle can move what the handles sit on
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
    } else if (d.type === "em-deselect") {
      select(null);
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
