import Link from "next/link";

import { PackageCard } from "@/components/site/package-card";
import { Reveal } from "@/components/site/reveal";
import { SectionHeading } from "@/components/site/section-heading";
import { Icon } from "@/components/ui/icon";
import { num, str, text } from "@/lib/cms/values";
import { localeHref } from "@/lib/i18n/config";
import type { BlockProps } from "./context";

export function PackagesGridBlock({ values, ctx }: BlockProps) {
  const { locale, dict } = ctx;
  const region = str(values, "region");
  const limit = num(values, "limit", 6);

  const rows = ctx.packages
    .filter((p) => (region ? p.region === region : true))
    .slice(0, limit > 0 ? limit : undefined);
  if (!rows.length) return null;

  return (
    <section className="section">
      <div className="shell shell-wide">
        <SectionHeading
          eyebrow={text(values, "eyebrow", locale)}
          title={text(values, "title", locale)}
          intro={text(values, "intro", locale)}
        />

        <ul className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {rows.map((row, index) => (
            <Reveal as="li" key={row.id} delay={index * 60} className="h-full">
              <PackageCard
                row={row}
                locale={locale}
                image={row.imageId ? (ctx.media.get(row.imageId) ?? null) : null}
              />
            </Reveal>
          ))}
        </ul>

        <Reveal className="mt-9">
          <Link href={localeHref(locale, "/packages")} className="link-underline">
            {dict.common.viewAll}
            <Icon name="arrowRight" size={15} className="flip-rtl" />
          </Link>
        </Reveal>
      </div>
    </section>
  );
}
