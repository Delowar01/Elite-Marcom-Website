import Link from "next/link";

import { Reveal } from "@/components/site/reveal";
import { SectionHeading } from "@/components/site/section-heading";
import { Icon } from "@/components/ui/icon";
import { getBlock } from "@/lib/cms/blocks";
import { items, text } from "@/lib/cms/values";
import { localeHref } from "@/lib/i18n/config";
import type { BlockProps } from "./context";

/**
 * The row of direct entry points under the hero. Deliberately terse: a visitor
 * who already knows they want an investor licence should reach it in one click
 * without reading the rest of the page.
 */
export function QuickLinksBlock({ values, ctx }: BlockProps) {
  const { locale } = ctx;
  const def = getBlock("quick-links")!;
  const fields = def.fields.find((f) => f.name === "links")!.itemFields ?? [];
  const links = items(values, "links", locale, fields);
  if (!links.length) return null;

  return (
    <section className="section-tight relative">
      <div className="shell shell-wide">
        <SectionHeading
          eyebrow={text(values, "title", locale) || ctx.dict.sections.quickAccess}
          intro={text(values, "intro", locale)}
        />

        <ul className="mt-9 grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-4">
          {links.map((link, index) => (
            <Reveal as="li" key={`${link.href}-${index}`} delay={index * 45} variant="fade-up">
              <Link
                href={localeHref(locale, link.href || "/services")}
                className="group flex h-full items-center gap-3 rounded-[var(--radius-md)] border border-line bg-[color-mix(in_oklab,var(--color-ink-700)_45%,transparent)] p-4 transition-all duration-300 hover:-translate-y-0.5 hover:border-[color-mix(in_oklab,var(--color-orange)_55%,transparent)] hover:bg-[color-mix(in_oklab,var(--color-ink-600)_60%,transparent)]"
              >
                <span
                  className="flex size-9 shrink-0 items-center justify-center rounded-full border border-line transition-colors group-hover:border-[color-mix(in_oklab,var(--color-orange)_60%,transparent)]"
                  style={{ color: "var(--color-peach)" }}
                >
                  <Icon name={link.icon || "sparkle"} size={17} />
                </span>
                <span className="min-w-0 text-[0.88rem] font-medium leading-snug text-strong">
                  {link.label}
                </span>
                <Icon
                  name="arrowRight"
                  size={15}
                  className="ms-auto shrink-0 flip-rtl opacity-0 transition-opacity duration-300 group-hover:opacity-70"
                />
              </Link>
            </Reveal>
          ))}
        </ul>
      </div>
    </section>
  );
}
