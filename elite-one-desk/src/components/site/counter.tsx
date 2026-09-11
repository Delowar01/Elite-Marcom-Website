"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Counts a figure up once, when it is first scrolled into view.
 *
 * Only the leading run of digits animates — "500+" counts to 500 and keeps the
 * plus, "24/7" is left exactly as typed. An editor should never have to think
 * about what the animation will do to their text.
 */
export function Counter({ value, className }: { value: string; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const match = /^(\D*)(\d[\d,]*)(.*)$/s.exec(value.trim());
  const target = match ? Number(match[2]!.replace(/,/g, "")) : null;
  const [display, setDisplay] = useState(target === null ? value : `${match![1]}0${match![3]}`);

  useEffect(() => {
    const node = ref.current;
    if (!node || target === null) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setDisplay(value);
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries.some((e) => e.isIntersecting)) return;
        observer.disconnect();
        const duration = 1400;
        const start = performance.now();
        const tick = (now: number) => {
          const t = Math.min((now - start) / duration, 1);
          // easeOutExpo — fast start, long settle.
          const eased = t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
          const current = Math.round(target * eased).toLocaleString();
          setDisplay(`${match![1]}${current}${match![3]}`);
          if (t < 1) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
      },
      { threshold: 0.4 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [match, target, value]);

  return (
    <span ref={ref} className={className} aria-label={value}>
      <span aria-hidden>{display}</span>
    </span>
  );
}
