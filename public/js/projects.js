/* ============================================================
   ELITE MARCOM — projects wall, filters and detail viewer
   ============================================================ */
(function () {
  "use strict";
  var EM = window.EM;

  var PROJECTS = [
    { id: "aces-pavilion", name: "ACES Pavilion", cat: "exhibitions", catLabel: "Exhibitions",
      img: "/assets/portfolio/aces-pavilion.webp", w: 603, h: 339,
      images: ["/assets/portfolio/aces-pavilion.webp", "/assets/portfolio/aces-pavilion-live.webp", "/assets/portfolio/aces-modern-live.webp"],
      desc: "A technology-led pavilion with a circular LED halo, demo stations and hospitality seating — designed and produced as one connected environment.",
      scope: "3D design · Production · AV integration", focus: "Technology in service of the brand",
      delivery: "Concept to live operation by one team" },
    { id: "n-lube", name: "N-Lube", cat: "exhibitions", catLabel: "Exhibitions",
      img: "/assets/portfolio/n-lube.webp", w: 597, h: 336,
      images: ["/assets/portfolio/n-lube.webp"],
      desc: "A dramatic black-and-gold exhibition environment with a sculptural oil-drop centrepiece and premium product display.",
      scope: "Design · Fabrication · Installation", focus: "Premium material presence",
      delivery: "Turnkey stand delivery" },
    { id: "executive-interior", name: "Executive Interior", cat: "interiors", catLabel: "Interiors",
      img: "/assets/portfolio/executive-interior.webp", w: 1259, h: 1014,
      images: ["/assets/portfolio/executive-interior.webp", "/assets/portfolio/boardroom.webp"],
      desc: "A contemporary executive environment in warm wood and stone — planned, detailed and fitted out to a calm, confident standard.",
      scope: "Planning · Fit-out · Finishing", focus: "Quiet executive luxury",
      delivery: "Design through final handover" },
    { id: "giic", name: "GIIC", cat: "exhibitions", catLabel: "Exhibitions",
      img: "/assets/portfolio/giic.webp", w: 502, h: 353,
      images: ["/assets/portfolio/giic.webp"],
      desc: "A colour-forward exhibition stand with layered product walls and a suspended circular banner for long-distance visibility.",
      scope: "Design · Build · Graphics", focus: "Product architecture",
      delivery: "Design to show floor" },
    { id: "conference-experience", name: "Conference Experience", cat: "events", catLabel: "Events",
      img: "/assets/portfolio/conference-experience.webp", w: 444, h: 296,
      images: ["/assets/portfolio/conference-experience.webp", "/assets/portfolio/conference-main.webp"],
      desc: "A full-room corporate conference — staging, AV, lighting and attendee flow operated live by one production team.",
      scope: "Staging · AV · Operations", focus: "Audience attention",
      delivery: "Program to live delivery" },
    { id: "nabd-jobs", name: "Nabd Jobs", cat: "exhibitions", catLabel: "Exhibitions",
      img: "/assets/portfolio/nabd-jobs.webp", w: 601, h: 338,
      images: ["/assets/portfolio/nabd-jobs.webp"],
      desc: "A recruitment-platform stand with an approachable, open plan and clear conversation zones for high visitor turnover.",
      scope: "Design · Build · Support", focus: "Open visitor journey",
      delivery: "Complete stand package" },
    { id: "boardroom", name: "Boardroom", cat: "interiors", catLabel: "Interiors",
      img: "/assets/portfolio/boardroom.webp", w: 418, h: 414,
      images: ["/assets/portfolio/boardroom.webp", "/assets/portfolio/executive-interior.webp"],
      desc: "A boardroom fit-out balancing presence and practicality — acoustic comfort, integrated AV and a table built for long decisions.",
      scope: "Interior design · Fit-out", focus: "Function with presence",
      delivery: "Detailing to installation" },
    { id: "team-experience", name: "Team Experience", cat: "activations", catLabel: "Activations",
      img: "/assets/portfolio/team-experience.webp", w: 862, h: 616,
      images: ["/assets/portfolio/team-experience.webp"],
      desc: "A facilitated team-building activation — challenges, equipment and pacing engineered so every participant stays in the game.",
      scope: "Concept · Facilitation · Logistics", focus: "Genuine participation",
      delivery: "Full activation management" },
    { id: "securiton", name: "Securiton", cat: "exhibitions", catLabel: "Exhibitions",
      img: "/assets/portfolio/securiton-live.webp", w: 457, h: 343,
      images: ["/assets/portfolio/securiton-live.webp", "/assets/portfolio/securiton.webp"],
      desc: "A product-focused exhibition experience with dedicated demonstration zones for fire-detection technology.",
      scope: "Design · Build · Demonstration zones", focus: "Product understanding",
      delivery: "Turnkey with live support" },
    { id: "branded-collection", name: "Branded Collection", cat: "brand-media", catLabel: "Brand & Media",
      img: "/assets/portfolio/branded-collection.webp", w: 893, h: 893,
      images: ["/assets/portfolio/branded-collection.webp"],
      desc: "A coordinated merchandise collection — sourcing, branding, packaging and fulfilment managed as one program.",
      scope: "Sourcing · Branding · Fulfilment", focus: "Consistent brand touch",
      delivery: "Sample to delivery" },
    { id: "hospitality-space", name: "Hospitality Space", cat: "interiors", catLabel: "Interiors",
      img: "/assets/portfolio/hospitality-space.webp", w: 422, h: 317,
      images: ["/assets/portfolio/hospitality-space.webp"],
      desc: "A café environment where material warmth and service flow were designed together — fit-out executed to daily-use durability.",
      scope: "Interior design · Fit-out", focus: "Warmth and flow",
      delivery: "Concept to opening day" },
    { id: "gala-dinner", name: "Gala Dinner", cat: "events", catLabel: "Events",
      img: "/assets/portfolio/conference-dinner.webp", w: 443, h: 295,
      images: ["/assets/portfolio/conference-dinner.webp", "/assets/portfolio/live-experience.webp"],
      desc: "A gala evening staged in layered violet light — table styling, program and technical production under one direction.",
      scope: "Staging · Lighting · Guest experience", focus: "Atmosphere",
      delivery: "Full event production" },
    { id: "virgo-acp", name: "Virgo ACP", cat: "exhibitions", catLabel: "Exhibitions",
      img: "/assets/portfolio/virgo-acp.webp", w: 1400, h: 788,
      images: ["/assets/portfolio/virgo-acp.webp", "/assets/portfolio/virgo-live.webp", "/assets/portfolio/virgo-render.webp"],
      desc: "A bold geometric environment whose triangulated facade is built from the client's own aluminium composite panels — the product as architecture.",
      scope: "Design · Fabrication · Installation", focus: "Material-led architecture",
      delivery: "Concept to show floor" },
    { id: "event-film", name: "Event Film", cat: "brand-media", catLabel: "Brand & Media",
      img: "/assets/portfolio/media-production.webp", w: 758, h: 467,
      images: ["/assets/portfolio/media-production.webp"],
      desc: "Cinematic event coverage — planned shot lists, live capture and post-production delivered as highlight films and social edits.",
      scope: "Videography · Post-production", focus: "The story of the night",
      delivery: "Capture to final films" },
    { id: "desert-experience", name: "Desert Experience", cat: "activations", catLabel: "Activations",
      img: "/assets/portfolio/desert-experience.webp", w: 616, h: 411,
      images: ["/assets/portfolio/desert-experience.webp"],
      desc: "A desert brand experience — camel rides, camp hospitality and guest logistics coordinated for a safe, memorable evening.",
      scope: "Concept · Logistics · Hospitality", focus: "Place as experience",
      delivery: "Complete experience management" },
    { id: "modern-majlis", name: "Modern Majlis", cat: "interiors", catLabel: "Interiors",
      img: "/assets/portfolio/modern-majlis.webp", w: 585, h: 439,
      images: ["/assets/portfolio/modern-majlis.webp"],
      desc: "A contemporary majlis interior — traditional proportions expressed in modern materials, arches and soft light.",
      scope: "Interior design · Fit-out", focus: "Tradition, modern voice",
      delivery: "Design to installation" },
    { id: "event-identity", name: "Event Identity", cat: "brand-media", catLabel: "Brand & Media",
      img: "/assets/portfolio/event-identity.webp", w: 395, h: 417,
      images: ["/assets/portfolio/event-identity.webp"],
      desc: "An event identity system carried across banners, signage and collateral — one visual voice at every touchpoint.",
      scope: "Identity · Signage · Collateral", focus: "Coherence at scale",
      delivery: "System design to production" },
    { id: "guest-experience-team", name: "Guest Experience Team", cat: "events", catLabel: "Events",
      img: "/assets/portfolio/guest-experience-team.webp", w: 588, h: 384,
      images: ["/assets/portfolio/guest-experience-team.webp"],
      desc: "A briefed, supervised guest-experience team — registration, wayfinding and hospitality delivered with calm precision.",
      scope: "Staffing · Briefing · Supervision", focus: "Every guest met well",
      delivery: "Managed staffing service" },
    { id: "live-experience", name: "Live Experience", cat: "events", catLabel: "Events",
      img: "/assets/portfolio/live-experience.webp", w: 1053, h: 702,
      images: ["/assets/portfolio/live-experience.webp", "/assets/portfolio/event-stage.webp"],
      desc: "A large-format live production — stage, light and sound tuned to carry emotion to the back row.",
      scope: "Production · Lighting · Show calling", focus: "Collective moment",
      delivery: "Technical production and operation" },
    { id: "aces-technology", name: "ACES Technology", cat: "exhibitions", catLabel: "Exhibitions",
      img: "/assets/portfolio/aces-technology.webp", w: 589, h: 332,
      images: ["/assets/portfolio/aces-technology.webp", "/assets/portfolio/aces-render.webp"],
      desc: "A second-generation ACES environment focused on digital infrastructure — clean lines, integrated screens and demo-ready product walls.",
      scope: "3D design · Production", focus: "Clarity of message",
      delivery: "Design to build" }
  ];

  var wall = document.getElementById("project-wall");
  var countEl = document.getElementById("project-count");
  var emptyEl = document.getElementById("project-empty");
  var filterWrap = document.getElementById("project-filters");
  var dialogScrim = document.getElementById("project-dialog");
  if (!wall) return;

  var dlg = EM.dialog(dialogScrim);
  var dlgContent = document.getElementById("project-dialog-content");

  /* ---------- render wall ---------- */
  PROJECTS.forEach(function (p, i) {
    var card = document.createElement("button");
    card.type = "button";
    card.className = "project-card reveal";
    card.setAttribute("data-reveal", "zoom-up");
    card.setAttribute("data-reveal-delay", String((i % 6) * 60));
    card.setAttribute("data-cat", p.cat);
    card.setAttribute("aria-label", p.name + " — " + p.catLabel + ". View project details.");
    card.innerHTML =
      '<img src="' + p.img + '" alt="" width="' + p.w + '" height="' + p.h + '" loading="lazy">' +
      '<span class="project-card__meta"><span class="cat">' + EM.escapeHtml(p.catLabel) + "</span><strong>" + EM.escapeHtml(p.name) + "</strong></span>";
    card.addEventListener("click", function () { openProject(p.id); });
    wall.appendChild(card);
    if (EM.observeReveal) EM.observeReveal(card); else card.classList.add("is-visible");
  });

  /* ---------- filters ---------- */
  function applyFilter(key) {
    var shown = 0;
    wall.querySelectorAll(".project-card").forEach(function (card) {
      var match = key === "all" || card.getAttribute("data-cat") === key;
      card.classList.toggle("is-hidden", !match);
      if (match) shown++;
    });
    if (filterWrap) {
      filterWrap.querySelectorAll(".filter-chip").forEach(function (chip) {
        chip.setAttribute("aria-pressed", chip.getAttribute("data-filter") === key ? "true" : "false");
      });
    }
    if (countEl) countEl.textContent = shown + " project" + (shown === 1 ? "" : "s") + " shown";
    if (emptyEl) emptyEl.hidden = shown !== 0;
  }
  if (filterWrap) {
    filterWrap.addEventListener("click", function (e) {
      var chip = e.target.closest(".filter-chip");
      if (chip) applyFilter(chip.getAttribute("data-filter"));
    });
  }
  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-filter-reset]")) applyFilter("all");
  });
  applyFilter("all");

  /* ---------- detail viewer ---------- */
  function openProject(id) {
    var p = null;
    PROJECTS.forEach(function (x) { if (x.id === id) p = x; });
    if (!p) return;
    var media = p.images.map(function (src, i) {
      return '<figure class="media-frame"><img src="' + src + '" alt="' + EM.escapeHtml(p.name) + ' — view ' + (i + 1) + '" loading="lazy"></figure>';
    }).join("");
    dlgContent.innerHTML =
      '<div class="project-dialog__media' + (p.images.length === 1 ? " single" : "") + '">' + media + "</div>" +
      '<span class="chip chip--orange">' + EM.escapeHtml(p.catLabel) + "</span>" +
      '<h2 id="project-dialog-title" style="margin-top:14px;">' + EM.escapeHtml(p.name) + "</h2>" +
      "<p>" + EM.escapeHtml(p.desc) + "</p>" +
      '<dl class="case__facts">' +
        "<div><dt>Scope</dt><dd>" + EM.escapeHtml(p.scope) + "</dd></div>" +
        "<div><dt>Focus</dt><dd>" + EM.escapeHtml(p.focus) + "</dd></div>" +
        "<div><dt>Delivery</dt><dd>" + EM.escapeHtml(p.delivery) + "</dd></div>" +
      "</dl>" +
      '<a class="btn btn--primary" href="/contact">Discuss a similar project</a>';
    dlg.open();
  }
  document.querySelectorAll("[data-open-project]").forEach(function (btn) {
    btn.addEventListener("click", function () { openProject(btn.getAttribute("data-open-project")); });
  });
})();
