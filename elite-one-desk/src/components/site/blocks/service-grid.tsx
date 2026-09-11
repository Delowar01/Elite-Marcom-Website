import Link from "next/link";

import { Reveal } from "@/components/site/reveal";
import { SectionHeading } from "@/components/site/section-heading";
import { ServiceIndex, type ServiceIndexEntry } from "@/components/site/service-index";
import { Icon } from "@/components/ui/icon";
import { bool, num, text } from "@/lib/cms/values";
import { localeHref, pick, plural } from "@/lib/i18n/config";
import { mediaSrc, mediaSrcSet } from "@/lib/media/url";
import type { BlockProps } from "./context";

/** The six core categories, read live from the catalogue rather than retyped. */
export function ServiceGridBlock({ values, ctx }: BlockProps) {
  const { locale, dict, catalog, media } = ctx;
  const limit = num(values, "limit", 0);
  const showCounts = bool(values, "showCounts", true);

  const categories = limit > 0 ? catalog.categories.slice(0, limit) : catalog.categories;
  if (!categories.length) return null;

  const entries: ServiceIndexEntry[] = categories.map((category) => {
    const image = category.imageId ? media.get(category.imageId) : null;
    const count = catalog.byCategory.get(category.id)?.length ?? 0;
    return {
      href: localeHref(locale, `/services/${category.slug}`),
      title: pick(locale, category.titleEn, category.titleAr),
      tagline: pick(locale, category.taglineEn, category.taglineAr),
      count: count ? plural(locale, dict.service.servicesCount, count) : "",
      icon: category.icon,
      image: image
        ? {
            src: mediaSrc(image, image.derivatives?.[1] ?? undefined),
            srcSet: mediaSrcSet(image),
            alt: "",
            width: image.width,
            height: image.height,
          }
        : null,
    };
  });

  return (
    <section className="section relative">
      <div className="shell shell-wide">
        <SectionHeading
          eyebrow={text(values, "eyebrow", locale) || dict.sections.servicesEyebrow}
          title={text(values, "title", locale)}
          intro={text(values, "intro", locale)}
        />

        <div className="mt-12">
          <ServiceIndex entries={entries} showCounts={showCounts} />
        </div>

        <Reveal className="mt-10">
          <Link href={localeHref(locale, "/services")} className="link-underline">
            {dict.common.viewAllServices}
            <Icon name="arrowRight" size={15} className="flip-rtl" />
          </Link>
        </Reveal>
      </div>
    </section>
  );
}
