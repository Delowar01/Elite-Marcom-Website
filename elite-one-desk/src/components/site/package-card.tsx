import Link from "next/link";

import { MediaImage } from "@/components/site/media-image";
import { Icon } from "@/components/ui/icon";
import type { Locale } from "@/lib/i18n/config";
import { localeHref, pick } from "@/lib/i18n/config";
import type { MediaRef } from "@/lib/media/url";
import type { PackageRow } from "@/lib/queries/catalog";

export function PackageCard({
  row,
  locale,
  image,
}: {
  row: PackageRow;
  locale: Locale;
  image: MediaRef | null;
}) {
  const title = pick(locale, row.titleEn, row.titleAr);
  const destination = pick(locale, row.destinationEn, row.destinationAr);
  const duration = pick(locale, row.durationEn, row.durationAr);
  const summary = pick(locale, row.summaryEn, row.summaryAr);

  return (
    <Link
      href={localeHref(locale, `/packages/${row.slug}`)}
      className="group flex h-full flex-col overflow-hidden rounded-[var(--radius-lg)] border border-line bg-[color-mix(in_oklab,var(--color-ink-700)_45%,transparent)] transition-all duration-400 ease-[var(--ease-out-expo)] hover:-translate-y-1 hover:border-[color-mix(in_oklab,var(--color-peach)_45%,transparent)]"
    >
      {image ? (
        <span className="block overflow-hidden">
          <MediaImage
            media={image}
            locale={locale}
            alt=""
            sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
            ratio="16 / 11"
            className="w-full transition-transform duration-700 ease-[var(--ease-out-expo)] group-hover:scale-[1.05]"
          />
        </span>
      ) : null}

      <span className="flex flex-1 flex-col p-5">
        {destination || duration ? (
          <span className="mb-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[0.74rem] text-muted">
            {destination ? (
              <span className="inline-flex items-center gap-1.5">
                <Icon name="mapPin" size={13} /> {destination}
              </span>
            ) : null}
            {duration ? (
              <span className="inline-flex items-center gap-1.5">
                <Icon name="clock" size={13} /> {duration}
              </span>
            ) : null}
          </span>
        ) : null}

        <span className="font-display text-[1.02rem] font-semibold leading-snug text-strong">{title}</span>
        {summary ? <span className="mt-2 line-clamp-3 text-small text-muted">{summary}</span> : null}

        <span className="mt-auto flex items-center gap-1.5 pt-5 text-[0.82rem] font-semibold text-strong">
          <span className="relative">
            {locale === "ar" ? "التفاصيل" : "View details"}
            <span
              aria-hidden
              className="absolute inset-x-0 -bottom-0.5 h-px origin-[inline-start] scale-x-0 transition-transform duration-400 ease-[var(--ease-out-expo)] group-hover:scale-x-100"
              style={{ background: "var(--color-orange)" }}
            />
          </span>
          <Icon name="arrowRight" size={14} className="flip-rtl" />
        </span>
      </span>
    </Link>
  );
}
