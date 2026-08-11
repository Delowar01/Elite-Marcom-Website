/* ============================================================
   ELITE MARCOM — homepage: services preview + lazy film gallery
   ============================================================ */
(function () {
  "use strict";
  var EM = window.EM || {};

  /* ---------- services row → preview image swap ---------- */
  var previewImg = document.getElementById("service-preview-img");
  if (previewImg) {
    document.querySelectorAll(".service-row[data-preview]").forEach(function (row) {
      function swap() {
        var src = row.getAttribute("data-preview");
        if (!src || previewImg.getAttribute("src") === src) return;
        previewImg.style.opacity = "0";
        var next = new Image();
        next.onload = function () {
          previewImg.src = src;
          previewImg.style.opacity = "1";
        };
        next.src = src;
      }
      row.addEventListener("pointerenter", swap);
      row.addEventListener("focus", swap);
    });
  }

  /* ---------- film gallery ---------- */
  var FILMS = [
    { id: "n6aja5N9DvM", title: "Elite Marcom — Event Highlight", label: "Exhibition", thumb: "/assets/portfolio/event-stage.webp", w: 622, h: 415 },
    { id: "yFE_IPhr4vw", title: "Brand Experience in Motion", label: "Live event", thumb: "/assets/portfolio/conference-main.webp", w: 444, h: 296 },
    { id: "Ln16qIE7BMg", title: "Exhibition Production Story", label: "Production", thumb: "/assets/portfolio/aces-pavilion-live.webp", w: 502, h: 335 },
    { id: "JsP5wRxM5Ow", title: "Space, Light and Audience", label: "Experience", thumb: "/assets/portfolio/conference-dinner.webp", w: 443, h: 295 },
    { id: "h_h35BI0_FU", title: "Behind the Build", label: "Behind scenes", thumb: "/assets/portfolio/aces-modern-live.webp", w: 496, h: 331 },
    { id: "HgPsbXFIQUM", title: "Selected Project Film", label: "Showreel", thumb: "/assets/portfolio/media-production.webp", w: 758, h: 467 }
  ];

  var grid = document.getElementById("film-grid");
  var statusEl = document.getElementById("film-status");
  if (!grid) return;

  var apiPromise = null;
  var activeCard = null;
  var activePlayer = null;

  function loadYouTubeApi() {
    if (apiPromise) return apiPromise;
    apiPromise = new Promise(function (resolve, reject) {
      if (window.YT && window.YT.Player) return resolve(window.YT);
      var prev = window.onYouTubeIframeAPIReady;
      window.onYouTubeIframeAPIReady = function () {
        if (typeof prev === "function") prev();
        resolve(window.YT);
      };
      var s = document.createElement("script");
      s.src = "https://www.youtube.com/iframe_api";
      s.onerror = function () { reject(new Error("yt-api")); };
      document.head.appendChild(s);
      setTimeout(function () { reject(new Error("yt-timeout")); }, 10000);
    });
    return apiPromise;
  }

  function watchUrl(film, seconds) {
    var url = "https://www.youtube.com/watch?v=" + film.id;
    if (seconds && seconds > 2) url += "&t=" + Math.floor(seconds) + "s";
    return url;
  }

  function stopActive() {
    if (activePlayer && activePlayer.destroy) {
      try { activePlayer.destroy(); } catch (e) { /* already gone */ }
    }
    activePlayer = null;
    if (activeCard) {
      var card = activeCard;
      activeCard = null;
      renderPoster(card, card.__film);
      var trigger = card.querySelector(".film-card__poster");
      if (trigger) trigger.focus();
    }
  }

  function renderPoster(card, film) {
    card.innerHTML =
      '<button type="button" class="film-card__poster" aria-label="Play film: ' + EM.escapeHtml(film.title) + '">' +
        '<img src="' + film.thumb + '" alt="" width="' + film.w + '" height="' + film.h + '" loading="lazy">' +
        '<span class="film-card__play" aria-hidden="true"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg></span>' +
        '<span class="film-card__label"><span class="chip">' + EM.escapeHtml(film.label) + '</span><strong>' + EM.escapeHtml(film.title) + "</strong></span>" +
      "</button>";
    card.querySelector(".film-card__poster").addEventListener("click", function () { activate(card, film); });
  }

  function renderPlayerShell(card, film) {
    card.innerHTML =
      '<div class="film-card__frame"><div class="film-card__mount"></div></div>' +
      '<div class="film-card__bar">' +
        '<a href="' + watchUrl(film, 0) + '" target="_blank" rel="noopener" data-continue>Continue on YouTube</a>' +
        '<button type="button" data-stop>Stop playback</button>' +
      "</div>";
    card.querySelector("[data-stop]").addEventListener("click", stopActive);
    var cont = card.querySelector("[data-continue]");
    cont.addEventListener("click", function () {
      if (activePlayer && activePlayer.getCurrentTime) {
        try { cont.href = watchUrl(film, activePlayer.getCurrentTime()); } catch (e) { /* keep base url */ }
      }
    });
  }

  function activate(card, film) {
    if (activeCard === card) return;
    stopActive();
    activeCard = card;
    if (statusEl) statusEl.textContent = "Loading film: " + film.title;
    renderPlayerShell(card, film);
    loadYouTubeApi().then(function (YT) {
      if (activeCard !== card) return;
      var mount = card.querySelector(".film-card__mount");
      if (!mount) return;
      activePlayer = new YT.Player(mount, {
        videoId: film.id,
        playerVars: { autoplay: 1, rel: 0, modestbranding: 1, playsinline: 1 },
        events: {
          onReady: function () { if (statusEl) statusEl.textContent = "Now playing: " + film.title; },
          onError: function () {
            /* inline playback failed — fall back to the normal watch page */
            stopActive();
            window.open(watchUrl(film, 0), "_blank", "noopener");
          }
        }
      });
    }).catch(function () {
      stopActive();
      window.open(watchUrl(film, 0), "_blank", "noopener");
    });
  }

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && activeCard) stopActive();
  });

  FILMS.forEach(function (film) {
    var card = document.createElement("article");
    card.className = "film-card reveal";
    card.setAttribute("data-reveal", "zoom-up");
    card.__film = film;
    renderPoster(card, film);
    grid.appendChild(card);
    if (EM.observeReveal) EM.observeReveal(card); else card.classList.add("is-visible");
  });
})();
