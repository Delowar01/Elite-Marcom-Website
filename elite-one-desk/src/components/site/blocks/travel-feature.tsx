import Link from "next/link";

import { MediaImage } from "@/components/site/media-image";
import { Reveal } from "@/components/site/reveal";
import { SectionHeading } from "@/components/site/section-heading";
import { Icon } from "@/components/ui/icon";
import { getBlock } from "@/lib/cms/blocks";
import { items, mediaId, str, text } from "@/lib/cms/values";
import { localeHref } from "@/lib/i18n/config";
import type { BlockProps } from "./context";

/**
 * Travel, presented as a capability list beside one large image rather than a
 * wall of colourful destination cards — §49 rules out the ThemeForest travel
 * look, and the corporate ground has to survive the travel content.
 */
export function TravelFeatureBlock({ values, ctx }: BlockProps) {
  const { locale } = ctx;
  const def = getBlock("travel-feature")!;
  const fields = def.fields.find((f) => f.name === "capabilities")!.itemFields ?? [];
  const capabilities = items(values, "capabilities", locale, fields);
  const image = ctx.media.get(mediaId(values, "image") ?? -1) ?? null;
  const ctaHref = str(values, "ctaHref", "/services/travel-tourism");
  const ctaLabel = text(values, "ctaLabel", locale);

  return (
    <section className="section relative">
      <div
        className={`shell shell-wide grid gap-12 lg:items-center lg:gap-16 ${
          image ? "lg:grid-cols-[0.95fr_1.05fr]" : ""
        }`}
      >
        {image ? (
          <Reveal variant="slide-in" className="relative">
            <div className="relative overflow-hidden rounded-[var(--radius-xl)] border border-line">
              <MediaImage
                media={image}
                locale={locale}
                sizes="(max-width: 1024px) 92vw, 44vw"
                ratio="5 / 6"
                className="w-full"
              />
              <div
                aria-hidden
                className="absolute inset-0"
                style={{
                  background:
                    "linear-gradient(to top, color-mix(in oklab, var(--color-ink-900) 62%, transparent), transparent 55%)",
                }}
              />
            </div>
          </Reveal>
        ) : null}

        <div>
          <SectionHeading
            eyebrow={text(values, "eyebrow", locale)}
            title={text(values, "title", locale)}
            intro={text(values, "body", locale)}
          />

          {capabilities.length ? (
            <ul className="mt-9 flex flex-wrap gap-2">
              {capabilities.map((cap, index) => (
                <Reveal as="li" key={cap.label} delay={index * 35} variant="fade">
                  <span className="inline-flex items-center rounded-full border border-line px-3.5 py-2 text-[0.82rem] text-body transition-colors hover:border-[color-mix(in_oklab,var(--color-peach)_55%,transparent)] hover:text-strong">
                    {cap.label}
                  </span>
                </Reveal>
              ))}
            </ul>
          ) : null}

          {ctaLabel ? (
            <div className="mt-9">
              <Link href={localeHref(locale, ctaHref)} className="btn btn-ghost">
                {ctaLabel}
                <Icon name="arrowRight" size={16} className="flip-rtl" />
              </Link>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
