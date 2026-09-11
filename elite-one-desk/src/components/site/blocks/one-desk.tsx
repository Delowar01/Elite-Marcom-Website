import Link from "next/link";

import { ConvergeDiagram } from "@/components/site/converge-diagram";
import { SectionHeading } from "@/components/site/section-heading";
import { Icon } from "@/components/ui/icon";
import { getBlock } from "@/lib/cms/blocks";
import { items, str, text } from "@/lib/cms/values";
import { localeHref } from "@/lib/i18n/config";
import type { BlockProps } from "./context";

export function OneDeskBlock({ values, ctx }: BlockProps) {
  const { locale } = ctx;
  const def = getBlock("one-desk")!;
  const fields = def.fields.find((f) => f.name === "paths")!.itemFields ?? [];
  const paths = items(values, "paths", locale, fields).map((p) => p.label);
  const ctaHref = str(values, "ctaHref");
  const ctaLabel = text(values, "ctaLabel", locale);

  return (
    <section className="section relative overflow-clip">
      <div className="shell shell-wide grid items-center gap-12 lg:grid-cols-[0.9fr_1.1fr] lg:gap-16">
        <div>
          <SectionHeading
            eyebrow={text(values, "eyebrow", locale)}
            title={text(values, "title", locale)}
            intro={text(values, "body", locale)}
          />
          {ctaHref && ctaLabel ? (
            <div className="mt-8">
              <Link href={localeHref(locale, ctaHref)} className="btn btn-ghost">
                {ctaLabel}
                <Icon name="arrowRight" size={16} className="flip-rtl" />
              </Link>
            </div>
          ) : null}
        </div>

        <ConvergeDiagram paths={paths} deskLabel={locale === "ar" ? "مكتب واحد" : "One Desk"} />
      </div>
    </section>
  );
}
