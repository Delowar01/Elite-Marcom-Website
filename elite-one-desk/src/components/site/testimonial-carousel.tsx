"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useCallback, useEffect, useState } from "react";

import { Icon } from "@/components/ui/icon";

export type TestimonialEntry = {
  id: number;
  name: string;
  company: string;
  country: string;
  quote: string;
  rating: number | null;
  image: { src: string; srcSet?: string } | null;
};

/**
 * One quote at a time, with the rest reachable by dots or arrow keys. It does
 * not auto-advance: a testimonial that moves while it is being read is a
 * carousel working against its own purpose.
 */
export function TestimonialCarousel({
  entries,
  labels,
}: {
  entries: TestimonialEntry[];
  labels: { previous: string; next: string; slideOf: string };
}) {
  const [index, setIndex] = useState(0);
  const [direction, setDirection] = useState(1);
  const reduce = useReducedMotion();

  const go = useCallback(
    (next: number) => {
      setDirection(next > index ? 1 : -1);
      setIndex((next + entries.length) % entries.length);
    },
    [entries.length, index],
  );

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "ArrowRight") go(index + 1);
      if (event.key === "ArrowLeft") go(index - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, index]);

  if (!entries.length) return null;
  const entry = entries[index]!;
  const offset = reduce ? 0 : 28 * direction;

  return (
    <div
      className="relative"
      role="group"
      aria-roledescription="carousel"
      aria-label={labels.slideOf.replace("{n}", String(index + 1)).replace("{total}", String(entries.length))}
    >
      <div className="panel relative overflow-hidden p-7 sm:p-10">
        <Icon
          name="quote"
          size={44}
          strokeWidth={0}
          fill="currentColor"
          className="absolute top-6 opacity-10"
          style={{ insetInlineEnd: "1.5rem", color: "var(--color-peach)" }}
        />

        <AnimatePresence mode="wait" initial={false}>
          <motion.figure
            key={entry.id}
            initial={reduce ? false : { opacity: 0, x: offset }}
            animate={{ opacity: 1, x: 0 }}
            exit={reduce ? undefined : { opacity: 0, x: -offset }}
            transition={{ duration: 0.36, ease: [0.16, 1, 0.3, 1] }}
          >
            {entry.rating ? (
              <div className="mb-5 flex gap-1" aria-label={`${entry.rating} / 5`}>
                {Array.from({ length: 5 }, (_, i) => (
                  <Icon
                    key={i}
                    name="star"
                    size={15}
                    strokeWidth={0}
                    fill="currentColor"
                    style={{
                      color: i < entry.rating! ? "var(--color-orange)" : "var(--border-color)",
                    }}
                  />
                ))}
              </div>
            ) : null}

            <blockquote className="max-w-3xl font-display text-[clamp(1.05rem,0.95rem+0.6vw,1.4rem)] leading-relaxed text-strong">
              {entry.quote}
            </blockquote>

            <figcaption className="mt-7 flex items-center gap-3.5">
              {entry.image ? (
                <img
                  src={entry.image.src}
                  srcSet={entry.image.srcSet}
                  sizes="48px"
                  alt=""
                  width={48}
                  height={48}
                  loading="lazy"
                  decoding="async"
                  className="size-12 rounded-full border border-line object-cover"
                />
              ) : (
                <span
                  aria-hidden
                  className="flex size-12 items-center justify-center rounded-full border border-line font-display text-[0.95rem] font-semibold text-muted"
                >
                  {entry.name.slice(0, 1)}
                </span>
              )}
              <span>
                <span className="block text-[0.92rem] font-semibold text-strong">{entry.name}</span>
                <span className="block text-[0.8rem] text-muted">
                  {[entry.company, entry.country].filter(Boolean).join(" · ")}
                </span>
              </span>
            </figcaption>
          </motion.figure>
        </AnimatePresence>
      </div>

      {entries.length > 1 ? (
        <div className="mt-5 flex items-center gap-3">
          <button
            type="button"
            onClick={() => go(index - 1)}
            aria-label={labels.previous}
            className="flex size-10 items-center justify-center rounded-full border border-line text-body transition-colors hover:border-[color-mix(in_oklab,var(--color-peach)_55%,transparent)] hover:text-strong"
          >
            <Icon name="chevronRight" size={16} className="rotate-180 rtl:rotate-0" />
          </button>
          <button
            type="button"
            onClick={() => go(index + 1)}
            aria-label={labels.next}
            className="flex size-10 items-center justify-center rounded-full border border-line text-body transition-colors hover:border-[color-mix(in_oklab,var(--color-peach)_55%,transparent)] hover:text-strong"
          >
            <Icon name="chevronRight" size={16} className="rtl:rotate-180" />
          </button>

          <ol className="ms-2 flex gap-1.5">
            {entries.map((item, i) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => go(i)}
                  aria-label={labels.slideOf
                    .replace("{n}", String(i + 1))
                    .replace("{total}", String(entries.length))}
                  aria-current={i === index}
                  className="h-1.5 rounded-full transition-all duration-300"
                  style={{
                    width: i === index ? "1.5rem" : "0.375rem",
                    background: i === index ? "var(--color-orange)" : "var(--border-color)",
                  }}
                />
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </div>
  );
}
