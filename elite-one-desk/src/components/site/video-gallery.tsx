"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Icon } from "@/components/ui/icon";

export type VideoItem = {
  id: number;
  youtubeId: string;
  title: string;
  description: string;
  /** Uploaded still, or empty to fall back to YouTube's own poster. */
  posterSrc: string;
  posterSrcSet?: string;
  duration: string;
  featured: boolean;
};

type Labels = {
  play: string;
  close: string;
  openOnYoutube: string;
  loadNotice: string;
};

/**
 * Poster-first YouTube gallery.
 *
 * Nothing is requested from YouTube on page load — not the iframe, not the
 * player script. A card shows a still (an uploaded one where the editor
 * supplied it, otherwise YouTube's own thumbnail) and only when a visitor
 * presses play does an iframe appear, pointed at youtube-nocookie.com with
 * autoplay. That is the difference between a video section costing ~1 KB of
 * markup and costing most of a mobile performance budget.
 */
export function VideoGallery({ videos, labels }: { videos: VideoItem[]; labels: Labels }) {
  const [openId, setOpenId] = useState<string | null>(null);
  const reduce = useReducedMotion();
  const dialogRef = useRef<HTMLDivElement>(null);
  const lastFocused = useRef<HTMLElement | null>(null);

  const close = useCallback(() => {
    setOpenId(null);
    lastFocused.current?.focus();
  }, []);

  useEffect(() => {
    if (!openId) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
      if (event.key !== "Tab") return;
      // Keep tabbing inside the dialog while it is open.
      const focusable = dialogRef.current?.querySelectorAll<HTMLElement>(
        "a[href], button:not([disabled]), iframe, [tabindex]:not([tabindex='-1'])",
      );
      if (!focusable?.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    document.documentElement.style.overflow = "hidden";
    const timer = setTimeout(() => dialogRef.current?.focus(), 40);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.documentElement.style.overflow = "";
      clearTimeout(timer);
    };
  }, [openId, close]);

  if (!videos.length) return null;
  const active = videos.find((v) => v.youtubeId === openId) ?? null;

  return (
    <>
      <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {videos.map((video, index) => (
          <li
            key={video.id}
            className={video.featured && index === 0 ? "sm:col-span-2 lg:col-span-2" : undefined}
          >
            <button
              type="button"
              onClick={(event) => {
                lastFocused.current = event.currentTarget;
                setOpenId(video.youtubeId);
              }}
              aria-label={`${labels.play}: ${video.title}`}
              className="group relative block w-full overflow-hidden rounded-[var(--radius-lg)] border border-line bg-[var(--color-ink-700)] text-start"
            >
              <span className="block aspect-video w-full overflow-hidden">
                <img
                  src={video.posterSrc}
                  srcSet={video.posterSrcSet}
                  sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
                  alt=""
                  loading="lazy"
                  decoding="async"
                  className="size-full object-cover transition-transform duration-700 ease-[var(--ease-out-expo)] group-hover:scale-[1.04]"
                />
              </span>

              <span
                aria-hidden
                className="absolute inset-0"
                style={{
                  background:
                    "linear-gradient(to top, color-mix(in oklab, var(--color-ink-900) 88%, transparent) 4%, transparent 62%)",
                }}
              />

              {/* The play control: a ring that fills on hover, never a bouncing
                  badge. */}
              <span className="absolute left-1/2 top-1/2 flex size-15 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border backdrop-blur-sm transition-all duration-400 ease-[var(--ease-out-expo)] group-hover:scale-108"
                style={{
                  borderColor: "color-mix(in oklab, var(--color-warm) 45%, transparent)",
                  background: "color-mix(in oklab, var(--color-ink-900) 45%, transparent)",
                }}
              >
                <span
                  aria-hidden
                  className="absolute inset-0 scale-50 rounded-full opacity-0 transition-all duration-400 ease-[var(--ease-out-expo)] group-hover:scale-100 group-hover:opacity-100"
                  style={{ background: "var(--color-orange)" }}
                />
                <Icon name="play" size={19} className="relative ms-0.5 text-strong group-hover:text-white" />
              </span>

              {video.duration ? (
                <span className="absolute top-3 rounded-full border border-line bg-[color-mix(in_oklab,var(--color-ink-900)_72%,transparent)] px-2.5 py-1 text-[0.7rem] font-medium tabular-nums text-strong backdrop-blur-sm" style={{ insetInlineEnd: "0.75rem" }}>
                  {video.duration}
                </span>
              ) : null}

              <span className="absolute inset-x-0 bottom-0 block p-5">
                <span className="block font-display text-[0.98rem] font-semibold leading-snug text-strong">
                  {video.title}
                </span>
                {video.description ? (
                  <span className="mt-1 line-clamp-2 block text-[0.82rem] text-muted">
                    {video.description}
                  </span>
                ) : null}
              </span>
            </button>
          </li>
        ))}
      </ul>

      <p className="mt-5 text-[0.78rem] text-muted">{labels.loadNotice}</p>

      <AnimatePresence>
        {active ? (
          <motion.div
            className="fixed inset-0 z-70 flex items-center justify-center p-4 sm:p-8"
            initial={reduce ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={reduce ? undefined : { opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <button
              type="button"
              aria-label={labels.close}
              onClick={close}
              className="absolute inset-0 bg-[color-mix(in_oklab,var(--color-ink-900)_92%,transparent)] backdrop-blur-md"
            />
            <motion.div
              ref={dialogRef}
              role="dialog"
              aria-modal="true"
              aria-label={active.title}
              tabIndex={-1}
              initial={reduce ? false : { opacity: 0, scale: 0.97, y: 12 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={reduce ? undefined : { opacity: 0, scale: 0.985 }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
              className="relative z-10 w-full max-w-5xl outline-none"
            >
              <div className="overflow-hidden rounded-[var(--radius-lg)] border border-line bg-black shadow-[var(--shadow-lift)]">
                <div className="aspect-video w-full">
                  <iframe
                    // Privacy-enhanced host: no cookie is set unless the visitor
                    // actually plays the video.
                    src={`https://www.youtube-nocookie.com/embed/${active.youtubeId}?autoplay=1&rel=0&modestbranding=1&playsinline=1`}
                    title={active.title}
                    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                    allowFullScreen
                    referrerPolicy="strict-origin-when-cross-origin"
                    className="size-full border-0"
                  />
                </div>
              </div>

              <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-display text-[1rem] font-semibold text-strong">{active.title}</p>
                  {active.description ? (
                    <p className="mt-1 max-w-2xl text-small text-muted">{active.description}</p>
                  ) : null}
                </div>
                <div className="flex shrink-0 gap-2">
                  <a
                    href={`https://www.youtube.com/watch?v=${active.youtubeId}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn btn-ghost btn-sm"
                  >
                    {labels.openOnYoutube}
                    <Icon name="arrowUpRight" size={14} />
                  </a>
                  <button type="button" onClick={close} className="btn btn-ghost btn-sm">
                    {labels.close}
                  </button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </>
  );
}
