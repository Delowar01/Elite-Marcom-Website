"use client";

import { motion, useMotionValue, useSpring, useTransform } from "motion/react";
import { useEffect, useId, useRef } from "react";

import { useCalmMotion } from "./use-calm-motion";

/**
 * The hero composition: a wire globe, a tilted orbit, an aircraft tracing it,
 * and the "1" of One Desk held in the centre.
 *
 * Three deliberate restraints, straight out of the brief:
 *  · the globe does not spin — the *orbit* moves, which reads as a flight path
 *    rather than clip-art;
 *  · the only colour is one orange arc and the aircraft;
 *  · parallax is a spring driving two transforms, so a pointer move costs a
 *    composited frame and nothing in React.
 *
 * The aircraft rides the orbit with SVG `animateMotion` rather than a CSS
 * motion path: both live in the same 500×470 viewBox, so the plane stays welded
 * to the route at every width instead of drifting off it as the box scales.
 * With reduced motion the whole thing settles into its finished state.
 */

const ORBIT =
  "M 250 92 C 366 92 448 156 448 235 C 448 314 366 378 250 378 C 134 378 52 314 52 235 C 52 156 134 92 250 92 Z";

export function OrbitComposition({ className = "" }: { className?: string }) {
  // Branches markup (the SMIL animation is present or not), so it has to wait
  // for mount rather than differ from what the server sent.
  const reduce = useCalmMotion();
  const hostRef = useRef<HTMLDivElement>(null);
  const uid = useId().replace(/:/g, "");

  const pointerX = useMotionValue(0);
  const pointerY = useMotionValue(0);
  const springX = useSpring(pointerX, { stiffness: 55, damping: 18, mass: 0.6 });
  const springY = useSpring(pointerY, { stiffness: 55, damping: 18, mass: 0.6 });

  const globeX = useTransform(springX, [-1, 1], [14, -14]);
  const globeY = useTransform(springY, [-1, 1], [10, -10]);
  const orbitX = useTransform(springX, [-1, 1], [-22, 22]);
  const orbitY = useTransform(springY, [-1, 1], [-15, 15]);

  useEffect(() => {
    if (reduce) return;
    if (!window.matchMedia("(pointer: fine)").matches) return;
    const onMove = (event: PointerEvent) => {
      const rect = hostRef.current?.getBoundingClientRect();
      if (!rect) return;
      pointerX.set(((event.clientX - rect.left) / rect.width) * 2 - 1);
      pointerY.set(((event.clientY - rect.top) / rect.height) * 2 - 1);
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => window.removeEventListener("pointermove", onMove);
  }, [pointerX, pointerY, reduce]);

  return (
    <div ref={hostRef} className={`relative isolate ${className}`} aria-hidden="true">
      {/* One soft wash of colour, kept far behind and away from every edge:
          the brief rules out glow used as decoration. */}
      <div
        className="pointer-events-none absolute left-1/2 top-1/2 -z-10 size-[118%] -translate-x-1/2 -translate-y-1/2 rounded-full opacity-70"
        style={{
          background:
            "radial-gradient(circle at 50% 45%, color-mix(in oklab, var(--color-orange) 15%, transparent) 0%, transparent 62%)",
        }}
      />

      <motion.svg
        viewBox="0 0 500 470"
        className="w-full"
        style={reduce ? undefined : { x: globeX, y: globeY }}
      >
        <defs>
          <linearGradient id={`${uid}-wire`} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="var(--color-warm)" stopOpacity="0.42" />
            <stop offset="55%" stopColor="var(--color-warm)" stopOpacity="0.16" />
            <stop offset="100%" stopColor="var(--color-warm)" stopOpacity="0.05" />
          </linearGradient>
          <radialGradient id={`${uid}-core`} cx="38%" cy="32%">
            <stop offset="0%" stopColor="var(--color-ink-400)" stopOpacity="0.55" />
            <stop offset="100%" stopColor="var(--color-ink-900)" stopOpacity="0.9" />
          </radialGradient>
        </defs>

        <g transform="translate(250 235)">
          <circle r="148" fill={`url(#${uid}-core)`} />
          <circle r="148" fill="none" stroke={`url(#${uid}-wire)`} strokeWidth="1" />

          {[-108, -74, -38, 0, 38, 74, 108].map((cy, i) => {
            const rx = Math.sqrt(Math.max(148 * 148 - cy * cy, 0));
            return (
              <ellipse
                key={cy}
                cy={cy}
                rx={rx}
                ry={Math.max(8, rx * 0.17)}
                fill="none"
                stroke="var(--color-warm)"
                strokeOpacity={i === 3 ? 0.2 : 0.1}
                strokeWidth="1"
              />
            );
          })}

          {[148, 108, 60, 18].map((rx, i) => (
            <ellipse
              key={rx}
              rx={rx}
              ry="148"
              fill="none"
              stroke="var(--color-warm)"
              strokeOpacity={i === 0 ? 0.18 : 0.09}
              strokeWidth="1"
            />
          ))}

          {/* The "1" of One Desk, held quietly: the idea, not a billboard. */}
          <text
            y="26"
            textAnchor="middle"
            fontFamily="var(--font-display)"
            fontSize="92"
            fontWeight="800"
            fill="var(--color-warm)"
            fillOpacity="0.07"
            letterSpacing="-0.04em"
          >
            1
          </text>
        </g>

        <g stroke="var(--color-warm)" strokeOpacity="0.2" strokeWidth="1">
          <path d="M24 60h26M37 47v26" />
          <path d="M450 410h26M463 397v26" />
        </g>
        <text x="24" y="96" fill="var(--color-warm)" fillOpacity="0.22" fontSize="10" letterSpacing="0.18em" fontFamily="var(--font-sans)">
          24.71° N
        </text>
        <text x="392" y="386" fill="var(--color-warm)" fillOpacity="0.22" fontSize="10" letterSpacing="0.18em" fontFamily="var(--font-sans)">
          46.67° E
        </text>
      </motion.svg>

      <motion.svg
        viewBox="0 0 500 470"
        className="absolute inset-0 w-full"
        style={reduce ? undefined : { x: orbitX, y: orbitY }}
      >
        <defs>
          <linearGradient id={`${uid}-arc`} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="var(--color-orange)" stopOpacity="0" />
            <stop offset="45%" stopColor="var(--color-orange)" stopOpacity="0.95" />
            <stop offset="100%" stopColor="var(--color-peach)" stopOpacity="0.2" />
          </linearGradient>
          <path id={`${uid}-orbit`} d={ORBIT} />
        </defs>

        <g transform="rotate(-14 250 235)">
          <use href={`#${uid}-orbit`} fill="none" stroke="var(--color-warm)" strokeOpacity="0.14" strokeWidth="1" strokeDasharray="3 7" />

          <path
            className={reduce ? undefined : "eod-arc"}
            d={ORBIT}
            fill="none"
            stroke={`url(#${uid}-arc)`}
            strokeWidth="2"
            strokeLinecap="round"
            pathLength={1}
            strokeDasharray="0.42 0.58"
            strokeDashoffset={-0.18}
          />

          {[
            [448, 235],
            [250, 92],
            [52, 235],
          ].map(([cx, cy]) => (
            <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r="3" fill="var(--color-peach)" fillOpacity="0.65" />
          ))}

          <g style={{ filter: "drop-shadow(0 0 9px color-mix(in oklab, var(--color-orange) 55%, transparent))" }}>
            {/* Drawn nose-first at the origin so `rotate="auto"` aims it along
                the direction of travel. Standing still it is parked on the
                right-hand node of the orbit rather than at SVG 0,0. */}
            <g transform={reduce ? "translate(448 235) rotate(90)" : undefined}>
              <path
                d="M-12 -1.2 L10.8 -11 L6 -1.2 L10.8 8.6 L4.8 6.2 L1 9.8 L0 4.8 L-5 3.6 L-1.7 0.9 Z"
                fill="var(--color-orange)"
              >
                {reduce ? null : (
                  <animateMotion dur="26s" repeatCount="indefinite" rotate="auto">
                    <mpath href={`#${uid}-orbit`} />
                  </animateMotion>
                )}
              </path>
            </g>
          </g>
        </g>
      </motion.svg>
    </div>
  );
}
