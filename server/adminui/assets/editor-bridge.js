/* Elite Marcom visual editor — bridge injected into the iframed preview.
   Highlights data-em regions, reports clicks to the admin shell, applies
   live text updates. Same-origin postMessage only. */
(function () {
  "use strict";
  if (window.top === window) return; // only meaningful inside the editor iframe

  var style = document.createElement("style");
  style.textContent =
    "[data-em]{outline:1px dashed rgba(237,108,38,.5);outline-offset:2px;cursor:pointer;}" +
    "[data-em]:hover{outline:2px solid #ed6c26;background:rgba(237,108,38,.08);}" +
    ".em-selected{outline:2px solid #ed6c26 !important;background:rgba(237,108,38,.14) !important;}" +
    "body.em-no-outline [data-em]{outline:none;background:none;}" +
    "body.em-no-outline [data-em]:hover{outline:2px solid #ed6c26;}";
  document.head.appendChild(style);

  var selected = null;
  function post(msg) {
    window.parent.postMessage(msg, location.origin);
  }
  function select(el) {
    if (selected) selected.classList.remove("em-selected");
    selected = el;
    if (el) el.classList.add("em-selected");
  }

  document.addEventListener("click", function (e) {
    var em = e.target.closest("[data-em]");
    if (em) {
      e.preventDefault();
      e.stopPropagation();
      select(em);
      post({ type: "em-select", key: em.getAttribute("data-em") });
      return;
    }
    var link = e.target.closest("a[href]");
    if (link) {
      e.preventDefault();
      post({ type: "em-nav-blocked" });
    }
  }, true);

  window.addEventListener("message", function (ev) {
    if (ev.origin !== location.origin || !ev.data || typeof ev.data !== "object") return;
    var d = ev.data;
    if (d.type === "em-update" && typeof d.key === "string") {
      document.querySelectorAll('[data-em="' + CSS.escape(d.key) + '"]').forEach(function (el) {
        el.innerHTML = d.html;
      });
    } else if (d.type === "em-outlines") {
      document.body.classList.toggle("em-no-outline", !d.on);
    } else if (d.type === "em-focus" && typeof d.key === "string") {
      var el = document.querySelector('[data-em="' + CSS.escape(d.key) + '"]');
      if (el) {
        select(el);
        el.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }
  });

  post({
    type: "em-ready",
    keys: Array.prototype.map.call(document.querySelectorAll("[data-em]"), function (el) {
      return el.getAttribute("data-em");
    })
  });
})();
