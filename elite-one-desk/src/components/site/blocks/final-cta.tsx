import Link from "next/link";

import { Reveal } from "@/components/site/reveal";
import { Icon } from "@/components/ui/icon";
import { bool, str, text } from "@/lib/cms/values";
import { localeHref } from "@/lib/i18n/config";
import type { BlockProps } from "./context";

export function FinalCtaBlock({ values, ctx }: BlockProps) {
  const { locale, dict, whatsappHref } = ctx;
  const title = text(values, "title", locale);
  const body = text(values, "body", locale);
  const ctaHref = str(values, "primaryCtaHref", "/contact");
  const ctaLabel = text(values, "primaryCtaLabel", locale) || dict.nav.primaryCta;
  const showWhatsapp = bool(values, "showWhatsapp", true) && Boolean(whatsappHref);

  return (
    <section className="section-tight">
      <div className="shell shell-wide">
        <Reveal variant="scale-in">
          <div className="relative overflow-hidden rounded-[var(--radius-xl)] border border-line px-6 py-14 text-center sm:px-12 sm:py-20">
            <div
              aria-hidden
              className="grid-texture pointer-events-none absolute inset-0 opacity-70"
            />
            <div
              aria-hidden
              className="pointer-events-none absolute left-1/2 top-full size-[38rem] -translate-x-1/2 -translate-y-1/2 rounded-full"
              style={{
                background:
                  "radial-gradient(circle, color-mix(in oklab, var(--color-orange) 18%, transparent), transparent 70%)",
              }}
            />

            <div className="relative mx-auto max-w-2xl">
              <h2 className="text-[length:var(--text-h1)]">{title}</h2>
              {body ? <p className="lede mx-auto mt-5 max-w-xl">{body}</p> : null}

              <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
                <Link href={localeHref(locale, ctaHref)} className="btn btn-primary">
                  {ctaLabel}
                  <Icon name="arrowRight" size={17} className="flip-rtl" />
                </Link>
                {showWhatsapp && whatsappHref ? (
                  <a
                    href={whatsappHref}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn btn-ghost"
                  >
                    <Icon name="whatsapp" size={17} strokeWidth={1.6} />
                    {dict.common.whatsappUs}
                  </a>
                ) : null}
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
