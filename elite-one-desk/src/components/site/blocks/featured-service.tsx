import Link from "next/link";

import { MediaImage } from "@/components/site/media-image";
import { Reveal } from "@/components/site/reveal";
import { Icon } from "@/components/ui/icon";
import { getBlock } from "@/lib/cms/blocks";
import { items, mediaId, str, text } from "@/lib/cms/values";
import { localeHref } from "@/lib/i18n/config";
import type { BlockProps } from "./context";

/**
 * The Investor Licence feature. It is the one section allowed to look different
 * from the rest — an inset panel on its own ground, so it reads as a priority
 * rather than another row in the list.
 */
export function FeaturedServiceBlock({ values, ctx }: BlockProps) {
  const { locale } = ctx;
  const def = getBlock("featured-service")!;
  const pointFields = def.fields.find((f) => f.name === "points")!.itemFields ?? [];
  const points = items(values, "points", locale, pointFields);
  const image = ctx.media.get(mediaId(values, "image") ?? -1) ?? null;
  const ctaHref = str(values, "ctaHref", "/contact");
  const ctaLabel = text(values, "ctaLabel", locale);

  return (
    <section className="section-tight">
      <div className="shell shell-wide">
        <Reveal variant="scale-in">
          <div
            className="relative overflow-hidden rounded-[var(--radius-xl)] border"
            style={{
              borderColor: "color-mix(in oklab, var(--color-orange) 28%, transparent)",
              background:
                "linear-gradient(140deg, color-mix(in oklab, var(--color-ink-600) 92%, transparent) 0%, color-mix(in oklab, var(--color-ink-700) 96%, transparent) 58%, color-mix(in oklab, var(--color-ink-800) 98%, transparent) 100%)",
            }}
          >
            <div
              aria-hidden
              className="pointer-events-none absolute -top-40 size-[34rem] rounded-full opacity-55"
              style={{
                insetInlineEnd: "-8rem",
                background:
                  "radial-gradient(circle, color-mix(in oklab, var(--color-orange) 22%, transparent), transparent 68%)",
              }}
            />

            <div
              className={`relative grid gap-10 p-7 sm:p-10 lg:items-center lg:gap-14 lg:p-14 ${
                image ? "lg:grid-cols-[1.1fr_0.9fr]" : ""
              }`}
            >
              <div>
                <p className="eyebrow">{text(values, "eyebrow", locale)}</p>
                <h2 className="mt-4 text-[length:var(--text-h2)]">{text(values, "title", locale)}</h2>
                <p className="lede mt-5 max-w-xl">{text(values, "body", locale)}</p>

                {points.length ? (
                  <ul className={`mt-8 grid gap-x-8 gap-y-3 sm:grid-cols-2 ${image ? "" : "lg:grid-cols-3"}`}>
                    {points.map((point) => (
                      <li key={point.label} className="flex items-start gap-2.5 text-small text-body">
                        <Icon
                          name="check"
                          size={15}
                          className="mt-1 shrink-0"
                          style={{ color: "var(--color-orange)" }}
                        />
                        {point.label}
                      </li>
                    ))}
                  </ul>
                ) : null}

                {ctaLabel ? (
                  <div className="mt-9">
                    <Link href={localeHref(locale, ctaHref)} className="btn btn-primary">
                      {ctaLabel}
                      <Icon name="arrowRight" size={17} className="flip-rtl" />
                    </Link>
                  </div>
                ) : null}
              </div>

              {image ? (
                <div className="relative overflow-hidden rounded-[var(--radius-lg)] border border-line">
                  <MediaImage
                    media={image}
                    locale={locale}
                    sizes="(max-width: 1024px) 90vw, 38vw"
                    ratio="4 / 3"
                    className="w-full"
                  />
                </div>
              ) : null}
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
