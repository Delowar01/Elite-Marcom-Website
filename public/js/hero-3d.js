/* ============================================================
   ELITE MARCOM — homepage interactive GLB hero
   Three.js 0.167.1 (vendored) · aces-exhibition.glb
   ============================================================ */
import * as THREE from "/vendor/three/three.module.min.js";
import { GLTFLoader } from "/vendor/three/GLTFLoader.js";
import { DRACOLoader } from "/vendor/three/DRACOLoader.js";

(function () {
  "use strict";

  var stage = document.getElementById("glb-stage");
  var stageWrap = stage ? stage.parentElement : null;
  var cue = document.getElementById("scroll-cue");
  if (!stage) return;

  if (location.protocol === "file:") {
    stage.innerHTML = '<p style="padding:24px;color:inherit;opacity:.7;max-width:34ch;">Please run the supplied local server (start-local.sh or START WEBSITE.bat) to view the interactive 3D model.</p>';
    return;
  }

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var finePointer = window.matchMedia("(hover: hover) and (pointer: fine)").matches;

  /* lower-resource device detection → cap resolution and frame rate */
  var lowPower = (navigator.hardwareConcurrency || 8) <= 4 ||
                 (navigator.deviceMemory && navigator.deviceMemory <= 4) ||
                 !finePointer;
  var PIXEL_CAP = lowPower ? 0.48 : 0.68;
  var FPS_CAP = lowPower ? 17 : 24;
  var FRAME_MS = 1000 / FPS_CAP;

  var GLB_URL = "/assets/aces-exhibition.glb";

  /* Preload the GLB bytes without blocking hero text. */
  var preload = fetch(GLB_URL).then(function (r) {
    if (!r.ok) throw new Error("glb http " + r.status);
    return r.arrayBuffer();
  });

  function fail(err) {
    /* Keep hero copy and atmosphere fully usable — no broken canvas, no debug text. */
    if (window.console && console.warn) console.warn("3D hero unavailable:", err && err.message ? err.message : err);
    if (stageWrap) stageWrap.classList.remove("is-loading");
    stage.innerHTML = "";
    stage.removeAttribute("role");
    stage.removeAttribute("aria-label");
  }

  function start() {
    var renderer;
    try {
      renderer = new THREE.WebGLRenderer({
        alpha: true,
        antialias: !lowPower,
        powerPreference: "high-performance",
        preserveDrawingBuffer: false
      });
    } catch (e) { return fail(e); }

    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;
    renderer.shadowMap.enabled = false;
    renderer.setClearColor(0x000000, 0);

    if (stageWrap) stageWrap.classList.add("is-loading");
    stage.appendChild(renderer.domElement);

    var scene = new THREE.Scene();
    var camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);

    /* balanced lighting: hemisphere + warm key + cool fill + warm point + violet rim */
    scene.add(new THREE.HemisphereLight(0xf2ecff, 0x2a2233, 1.05));
    var key = new THREE.DirectionalLight(0xffd9b0, 2.1);
    key.position.set(4, 6, 5);
    scene.add(key);
    var fill = new THREE.DirectionalLight(0xb9c4ff, 0.8);
    fill.position.set(-5, 3, -2);
    scene.add(fill);
    var warm = new THREE.PointLight(0xff9b68, 18, 30);
    warm.position.set(-2.5, 2.2, 3.5);
    scene.add(warm);
    var rim = new THREE.DirectionalLight(0x8f77d6, 1.4);
    rim.position.set(0, 4, -6);
    scene.add(rim);

    var pivot = new THREE.Group();
    scene.add(pivot);

    /* interaction state */
    var baseY = -0.5;              /* resting yaw */
    var targetY = baseY, targetX = 0;
    var curY = baseY, curX = 0;
    var hoverY = 0, hoverX = 0;
    var scrollRot = 0;
    var dragging = false;
    var settled = false;
    var visible = true;
    var rafId = null;
    var lastFrame = 0;

    function requestRender() {
      settled = false;
      if (rafId === null && visible && !document.hidden) rafId = requestAnimationFrame(tick);
    }

    function tick(ts) {
      rafId = null;
      if (!visible || document.hidden) return;
      if (ts - lastFrame < FRAME_MS) { rafId = requestAnimationFrame(tick); return; }
      lastFrame = ts;

      var goalY = targetY + hoverY + scrollRot;
      var goalX = THREE.MathUtils.clamp(targetX + hoverX, -0.35, 0.42);
      curY += (goalY - curY) * 0.07;
      curX += (goalX - curX) * 0.07;
      pivot.rotation.y = curY;
      pivot.rotation.x = curX;

      renderer.render(scene, camera);

      var still = Math.abs(goalY - curY) < 0.0005 && Math.abs(goalX - curX) < 0.0005;
      if (still && !dragging) { settled = true; return; } /* stop continuous rendering once easing settles */
      rafId = requestAnimationFrame(tick);
    }

    /* sizing */
    function resize() {
      var w = stage.clientWidth, h = stage.clientHeight;
      if (!w || !h) return;
      var dpr = Math.min(window.devicePixelRatio || 1, 2) * PIXEL_CAP;
      renderer.setPixelRatio(Math.max(0.4, dpr));
      renderer.setSize(w, h, true);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      requestRender();
    }
    if ("ResizeObserver" in window) new ResizeObserver(resize).observe(stage);
    else window.addEventListener("resize", resize);

    /* pause when offscreen */
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          visible = en.isIntersecting;
          if (visible) requestRender();
        });
      }, { threshold: 0.02 }).observe(stage);
    }
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) requestRender();
    });

    /* load model */
    preload.then(function (buffer) {
      var loader = new GLTFLoader();
      var draco = new DRACOLoader();
      draco.setDecoderPath("/vendor/three/draco/");
      loader.setDRACOLoader(draco);
      loader.parse(buffer, "/assets/", function (gltf) {
        var model = gltf.scene;

        /* frame: compute bounds, normalize scale, center */
        var box = new THREE.Box3().setFromObject(model);
        var size = box.getSize(new THREE.Vector3());
        var center = box.getCenter(new THREE.Vector3());
        var maxDim = Math.max(size.x, size.y, size.z) || 1;
        var scale = 3.4 / maxDim;
        model.scale.setScalar(scale);
        model.position.set(-center.x * scale, -center.y * scale, -center.z * scale);

        model.traverse(function (node) {
          if (node.isMesh && node.material) {
            node.castShadow = false;
            node.receiveShadow = false;
            var mats = Array.isArray(node.material) ? node.material : [node.material];
            mats.forEach(function (m) {
              if (m.map) m.map.anisotropy = lowPower ? 1 : 4;
              m.envMapIntensity = 0.9;
            });
          }
        });

        pivot.add(model);
        camera.position.set(0, 1.15, 5.6);
        camera.lookAt(0, 0.1, 0);

        if (stageWrap) stageWrap.classList.remove("is-loading");
        if (cue) cue.classList.add("is-ready");
        resize();

        if (reduceMotion) {
          /* static first frame only — no auto-rotation, no continuous pointer response */
          pivot.rotation.y = baseY;
          renderer.render(scene, camera);
          return;
        }
        requestRender();
        bindInteraction();
        bindScroll();
      }, function (err) { fail(err || new Error("glb parse")); });
    }).catch(fail);

    /* pointer hover: subtle rotation offset (fine pointers only) */
    function bindInteraction() {
      if (finePointer) {
        stage.addEventListener("pointermove", function (e) {
          if (dragging || e.pointerType !== "mouse") return;
          var r = stage.getBoundingClientRect();
          hoverY = ((e.clientX - r.left) / r.width - 0.5) * 0.22;
          hoverX = ((e.clientY - r.top) / r.height - 0.5) * 0.12;
          requestRender();
        }, { passive: true });
        stage.addEventListener("pointerleave", function () {
          hoverY = 0; hoverX = 0;
          requestRender();
        });
      }

      /* drag: horizontal rotation + small clamped vertical pitch, with pointer capture */
      var startX = 0, startY = 0, startRotY = 0, startRotX = 0;
      stage.addEventListener("pointerdown", function (e) {
        if (e.pointerType === "mouse" && e.button !== 0) return;
        dragging = true;
        startX = e.clientX; startY = e.clientY;
        startRotY = targetY; startRotX = targetX;
        try { stage.setPointerCapture(e.pointerId); } catch (err) { /* unsupported */ }
        requestRender();
      });
      stage.addEventListener("pointermove", function (e) {
        if (!dragging) return;
        var dx = e.clientX - startX;
        var dy = e.clientY - startY;
        /* touch: only treat as drag when clearly horizontal, so page scroll stays natural */
        if (e.pointerType === "touch" && Math.abs(dy) > Math.abs(dx) * 1.2) return;
        targetY = startRotY + dx * 0.006;
        targetX = THREE.MathUtils.clamp(startRotX + dy * 0.003, -0.3, 0.38);
        requestRender();
      });
      function endDrag(e) {
        if (!dragging) return;
        dragging = false;
        try { stage.releasePointerCapture(e.pointerId); } catch (err) { /* noop */ }
        requestRender();
      }
      stage.addEventListener("pointerup", endDrag);
      stage.addEventListener("pointercancel", endDrag);
    }

    /* scroll: ~1.5 radians of controlled rotation across the hero exit */
    function bindScroll() {
      var ticking = false;
      function onScroll() {
        if (ticking) return;
        ticking = true;
        requestAnimationFrame(function () {
          ticking = false;
          var heroH = stage.closest(".hero") ? stage.closest(".hero").offsetHeight : window.innerHeight;
          var p = Math.min(1, Math.max(0, window.scrollY / Math.max(1, heroH)));
          scrollRot = p * 1.5;
          requestRender();
        });
      }
      window.addEventListener("scroll", onScroll, { passive: true });
      onScroll();
    }
  }

  /* initialize during idle time shortly after first paint */
  if ("requestIdleCallback" in window) {
    requestIdleCallback(start, { timeout: 1200 });
  } else {
    setTimeout(start, 350);
  }
})();
