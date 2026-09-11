"use client";

import { useEffect, useRef } from "react";

/**
 * A small ring that trails the pointer and swells over anything clickable.
 *
 * Deliberately narrow in scope: it never replaces the system cursor, it is
 * `pointer-events: none` so it cannot intercept a click, and it is not rendered
 * at all on touch devices, on coarse pointers, or when the visitor has asked
 * for reduced motion. Position is written straight to a transform in a rAF
 * loop — no React state, so it costs nothing per frame in the tree.
 */
export function CursorCompanion() {
  const ringRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const fine = window.matchMedia("(pointer: fine) and (hover: hover)");
    const calm = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (!fine.matches || calm.matches) return;

    const ring = ringRef.current;
    if (!ring) return;

    let targetX = window.innerWidth / 2;
    let targetY = window.innerHeight / 2;
    let x = targetX;
    let y = targetY;
    let scale = 1;
    let targetScale = 1;
    let visible = false;
    let frame = 0;

    const onMove = (event: PointerEvent) => {
      targetX = event.clientX;
      targetY = event.clientY;
      if (!visible) {
        visible = true;
        x = targetX;
        y = targetY;
        ring.style.opacity = "1";
      }
      const interactive = (event.target as Element | null)?.closest(
        "a, button, input, select, textarea, [role='button'], summary",
      );
      targetScale = interactive ? 1.85 : 1;
      ring.dataset.active = interactive ? "true" : "false";
    };

    const onLeave = () => {
      visible = false;
      ring.style.opacity = "0";
    };

    const tick = () => {
      x += (targetX - x) * 0.18;
      y += (targetY - y) * 0.18;
      scale += (targetScale - scale) * 0.16;
      ring.style.transform = `translate3d(${x}px, ${y}px, 0) translate(-50%, -50%) scale(${scale})`;
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);

    window.addEventListener("pointermove", onMove, { passive: true });
    document.addEventListener("pointerleave", onLeave);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerleave", onLeave);
    };
  }, []);

  return (
    <div
      ref={ringRef}
      aria-hidden="true"
      className="pointer-events-none fixed left-0 top-0 z-[70] hidden size-8 rounded-full border opacity-0 transition-[opacity,border-color,background-color] duration-300 motion-safe:[@media(pointer:fine)]:block"
      style={{
        borderColor: "color-mix(in oklab, var(--color-peach) 60%, transparent)",
        backgroundColor: "color-mix(in oklab, var(--color-orange) 10%, transparent)",
        willChange: "transform",
      }}
    />
  );
}
