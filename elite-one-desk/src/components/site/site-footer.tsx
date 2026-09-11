import Link from "next/link";

import { Icon } from "@/components/ui/icon";
import { Logo } from "@/components/ui/logo";
import type { Locale } from "@/lib/i18n/config";
import { localeHref, pick } from "@/lib/i18n/config";
import { getDictionary } from "@/lib/i18n/dictionary";
import { getMenu, getSocialLinks } from "@/lib/queries/site";
import { getSettings } from "@/lib/settings";

const SOCIAL_ICON: Record<string, string> = {
  linkedin: "users",
  instagram: "sparkle",
  facebook: "users",
  x: "close",
  twitter: "close",
  youtube: "play",
  tiktok: "play",
  snapchat: "sparkle",
  whatsapp: "whatsapp",
};

export async function SiteFooter({ locale }: { locale: Locale }) {
  const [services, company, legal, social, settings] = await Promise.all([
    getMenu("footer_services"),
    getMenu("footer_company"),
    getMenu("footer_legal"),
    getSocialLinks(),
    getSettings(),
  ]);
  const dict = getDictionary(locale);
  const { contact, brand, disclaimers } = settings;
  const year = new Date().getFullYear();

  const address = pick(locale, contact.addressEn, contact.addressAr);
  const city = pick(locale, contact.cityEn, contact.cityAr);
  const country = pick(locale, contact.countryEn, contact.countryAr);
  const hours = pick(locale, contact.hoursEn, contact.hoursAr);
  const disclaimer = pick(locale, disclaimers.governmentEn, disclaimers.governmentAr);

  const columns = [
    { title: dict.footer.services, items: services },
    { title: dict.footer.company, items: company },
  ].filter((c) => c.items.length > 0);

  return (
    <footer className="relative mt-auto border-t border-line bg-[var(--color-ink-900)]">
      <div className="shell shell-wide grid gap-12 pt-[clamp(3.5rem,5vw,5.5rem)] pb-10 lg:grid-cols-[1.35fr_repeat(3,minmax(0,1fr))] lg:gap-10">
        <div className="max-w-sm">
          <Logo height={46} />
          <p className="mt-5 text-small text-muted">{dict.footer.builtLine}</p>
          {social.length ? (
            <div className="mt-6">
              <p className="eyebrow mb-3">{dict.footer.followUs}</p>
              <ul className="flex flex-wrap gap-2">
                {social.map((item) => (
                  <li key={item.id}>
                    <a
                      href={item.url}
                      target="_blank"
                      rel="noopener noreferrer me"
                      aria-label={item.platform}
                      className="flex size-10 items-center justify-center rounded-full border border-line text-body transition-colors hover:border-[color-mix(in_oklab,var(--color-peach)_55%,transparent)] hover:text-strong"
                    >
                      <Icon name={SOCIAL_ICON[item.platform.toLowerCase()] ?? "arrowUpRight"} size={17} />
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>

        {columns.map((column) => (
          <nav key={column.title} aria-label={column.title}>
            <h2 className="eyebrow mb-4">{column.title}</h2>
            <ul className="space-y-2.5">
              {column.items.map((item) => (
                <li key={item.id}>
                  <Link
                    href={localeHref(locale, item.href)}
                    className="text-small text-body transition-colors hover:text-strong"
                  >
                    {pick(locale, item.labelEn, item.labelAr)}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        ))}

        <div>
          <h2 className="eyebrow mb-4">{dict.footer.contact}</h2>
          <ul className="space-y-3 text-small text-body">
            {address || city ? (
              <li className="flex gap-2.5">
                <Icon name="mapPin" size={16} className="mt-0.5 shrink-0 text-muted" />
                <span>
                  {address}
                  {address && city ? <br /> : null}
                  {[city, country].filter(Boolean).join(", ")}
                </span>
              </li>
            ) : null}
            {contact.phone ? (
              <li className="flex gap-2.5">
                <Icon name="phone" size={16} className="mt-0.5 shrink-0 text-muted" />
                <a href={`tel:${contact.phone}`} dir="ltr" className="transition-colors hover:text-strong">
                  {contact.phoneDisplay || contact.phone}
                </a>
              </li>
            ) : null}
            {contact.email ? (
              <li className="flex gap-2.5">
                <Icon name="mail" size={16} className="mt-0.5 shrink-0 text-muted" />
                <a href={`mailto:${contact.email}`} className="transition-colors hover:text-strong">
                  {contact.email}
                </a>
              </li>
            ) : null}
            {hours ? (
              <li className="flex gap-2.5">
                <Icon name="clock" size={16} className="mt-0.5 shrink-0 text-muted" />
                <span>{hours}</span>
              </li>
            ) : null}
          </ul>
        </div>
      </div>

      {disclaimer ? (
        <div className="shell shell-wide">
          <p className="rounded-[var(--radius-md)] border border-line bg-[color-mix(in_oklab,var(--color-warm)_3%,transparent)] p-4 text-[0.8rem] leading-relaxed text-muted">
            {disclaimer}
          </p>
        </div>
      ) : null}

      <div className="shell shell-wide mt-8 flex flex-col gap-3 border-t border-line py-6 text-[0.8rem] text-muted sm:flex-row sm:items-center sm:justify-between">
        <p>
          © {year} {pick(locale, brand.legalNameEn, brand.legalNameAr)}. {dict.footer.rights}
        </p>
        {legal.length ? (
          <ul className="flex flex-wrap gap-x-5 gap-y-2">
            {legal.map((item) => (
              <li key={item.id}>
                <Link href={localeHref(locale, item.href)} className="transition-colors hover:text-strong">
                  {pick(locale, item.labelEn, item.labelAr)}
                </Link>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </footer>
  );
}
