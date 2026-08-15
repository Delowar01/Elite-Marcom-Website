/* Elite Marcom — services page
   Three small behaviours for the service cards:
   the entrance (the photograph is uncovered, then the words arrive), the
   chapter rail that fills with reading progress, and keyboard parity with
   hover. Everything degrades to the finished page with no script at all. */
(function () {
  "use strict";
  var doc = document;
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  /* ---------- the entrance ---------- */
  (function () {
    var items = doc.querySelectorAll(".sc-anim");
    if (!items.length) return;
    if (reduceMotion.matches || !("IntersectionObserver" in window)) {
      items.forEach(function (el) { el.classList.add("is-in"); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-in");
        io.unobserve(entry.target);
      });
    }, { rootMargin: "0px 0px -10% 0px", threshold: 0.12 });
    items.forEach(function (el) { io.observe(el); });
    /* the same fail-safes the rest of the site uses: never leave a card
       unrevealed because an observer did not fire */
    setTimeout(function () {
      doc.querySelectorAll(".sc-anim:not(.is-in)").forEach(function (el) {
        var r = el.getBoundingClientRect();
        if (r.top < window.innerHeight && r.bottom > 0) el.classList.add("is-in");
      });
    }, 2200);
    setTimeout(function () {
      doc.querySelectorAll(".sc-anim:not(.is-in)").forEach(function (el) { el.classList.add("is-in"); });
    }, 6000);
  })();

  /* ---------- the chapter rail ---------- */
  (function () {
    var chapters = Array.prototype.slice.call(doc.querySelectorAll(".sc-chapter"));
    if (!chapters.length || reduceMotion.matches) return;
    var ticking = false;
    function paint() {
      var vh = window.innerHeight;
      chapters.forEach(function (chapter) {
        var bar = chapter.querySelector(".sc-rail i");
        if (!bar) return;
        var r = chapter.getBoundingClientRect();
        /* 0 when the chapter's top reaches 72% down the viewport, 1 at its end */
        var progress = (vh * 0.72 - r.top) / Math.max(1, r.height);
        bar.style.height = Math.max(0, Math.min(1, progress)) * 100 + "%";
      });
      ticking = false;
    }
    function onScroll() {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(paint);
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    paint();
  })();

  /* ---------- keyboard parity with hover ----------
     A mouse click focuses the link too, so only :focus-visible — the browser's
     own "this was the keyboard" signal — opens the panel, and it closes again
     the moment focus leaves. Without this a click would leave a card stuck. */
  doc.querySelectorAll(".sc-card").forEach(function (card) {
    card.addEventListener("focusin", function (e) {
      var keyed = true;
      try { keyed = e.target.matches(":focus-visible"); } catch (err) { /* older browser */ }
      if (keyed) card.classList.add("is-key");
    });
    card.addEventListener("focusout", function () { card.classList.remove("is-key"); });
  });
})();
