"use client";

import Link from "next/link";
import { useState } from "react";

import { Icon } from "@/components/ui/icon";

export type ServiceIndexEntry = {
  href: string;
  title: string;
  tagline: string;
  count: string;
  icon: string;
  image?: { src: string; srcSet?: string; alt: string; width: number; height: number } | null;
};

/**
 * The main services section, as an editorial index rather than a card grid —
 * §49 rules out "six identical cards sitting in a grid", and a numbered list of
 * rows carries a hierarchy that six equal boxes cannot.
 *
 * The preview is one stacked stage whose layers cross-fade, so hovering never
 * triggers a network request or a layout pass; the images are already there.
 */
export function ServiceIndex({ entries, showCounts }: { entries: ServiceIndexEntry[]; showCounts: boolean }) {
  // `hovered` is null at rest so no row is marked before the pointer arrives —
  // a row that starts underlined and nudged across reads as a layout fault.
  // The preview stage still needs something to show, hence the separate index.
  const [hovered, setHovered] = useState<number | null>(null);
  const shown = hovered ?? 0;
  const hasArtwork = entries.some((entry) => entry.image);

  return (
    <div
      className={`grid gap-10 lg:items-start lg:gap-14 ${hasArtwork ? "lg:grid-cols-[1fr_auto]" : ""}`}
    >
      <ul className="order-2 lg:order-1" onMouseLeave={() => setHovered(null)}>
        {entries.map((entry, index) => (
          <li key={entry.href}>
            <Link
              href={entry.href}
              onMouseEnter={() => setHovered(index)}
              onFocus={() => setHovered(index)}
              onBlur={() => setHovered(null)}
              data-active={hovered === index}
              className="group relative flex items-start gap-4 border-t border-line py-6 transition-colors last:border-b sm:gap-6 sm:py-7"
            >
              {/* The orange rule that follows the pointer down the list. */}
              <span
                aria-hidden
                className="pointer-events-none absolute inset-x-0 top-0 h-px origin-[inline-start] scale-x-0 transition-transform duration-500 ease-[var(--ease-out-expo)] group-data-[active=true]:scale-x-100"
                style={{ background: "var(--color-orange)" }}
              />
              <span className="mt-1 font-display text-[0.72rem] font-semibold tabular-nums text-muted transition-colors group-data-[active=true]:text-[var(--color-peach)]">
                {String(index + 1).padStart(2, "0")}
              </span>

              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <span className="font-display text-[length:var(--text-h3)] font-bold text-strong transition-transform duration-500 ease-[var(--ease-out-expo)] group-data-[active=true]:translate-x-[0.35rem] rtl:group-data-[active=true]:-translate-x-[0.35rem]">
                    {entry.title}
                  </span>
                  {showCounts && entry.count ? (
                    <span className="text-[0.75rem] text-muted">{entry.count}</span>
                  ) : null}
                </span>
                {entry.tagline ? (
                  <span className="mt-1.5 block max-w-lg text-small text-muted">{entry.tagline}</span>
                ) : null}
              </span>

              {/* Thumbnail for narrow screens, where there is no hover stage. */}
              {entry.image ? (
                <span className="hidden size-16 shrink-0 overflow-hidden rounded-[var(--radius-sm)] border border-line sm:block lg:hidden">
                  <img
                    src={entry.image.src}
                    srcSet={entry.image.srcSet}
                    sizes="64px"
                    alt=""
                    width={entry.image.width}
                    height={entry.image.height}
                    loading="lazy"
                    decoding="async"
                    className="size-full object-cover"
                  />
                </span>
              ) : null}

              <span className="mt-1 flex size-9 shrink-0 items-center justify-center rounded-full border border-line text-muted transition-all duration-300 group-data-[active=true]:border-[var(--color-orange)] group-data-[active=true]:text-[var(--color-orange)]">
                <Icon name="arrowUpRight" size={15} className="flip-rtl" />
              </span>
            </Link>
          </li>
        ))}
      </ul>

      <div className={`order-1 hidden lg:order-2 ${hasArtwork ? "lg:block" : ""}`}>
        <div className="relative aspect-[4/5] w-[min(26vw,22rem)] overflow-hidden rounded-[var(--radius-lg)] border border-line bg-[var(--color-ink-700)]">
          {entries.map((entry, index) =>
            entry.image ? (
              <img
                key={entry.href}
                src={entry.image.src}
                srcSet={entry.image.srcSet}
                sizes="(max-width: 1024px) 0px, 22rem"
                alt=""
                width={entry.image.width}
                height={entry.image.height}
                loading={index === 0 ? "eager" : "lazy"}
                decoding="async"
                data-active={shown === index}
                className="absolute inset-0 size-full scale-[1.03] object-cover opacity-0 transition-[opacity,transform] duration-700 ease-[var(--ease-out-expo)] data-[active=true]:scale-100 data-[active=true]:opacity-100"
              />
            ) : null,
          )}
          <div
            aria-hidden
            className="absolute inset-0"
            style={{
              background:
                "linear-gradient(to top, color-mix(in oklab, var(--color-ink-900) 78%, transparent), transparent 58%)",
            }}
          />
          <div className="absolute inset-x-0 bottom-0 flex items-center gap-2.5 p-5">
            <Icon name={entries[shown]?.icon ?? "desk"} size={18} style={{ color: "var(--color-peach)" }} />
            <span className="font-display text-[0.9rem] font-semibold text-strong">
              {entries[shown]?.title}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
