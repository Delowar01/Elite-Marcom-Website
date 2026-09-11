import { EnquiryForm } from "@/components/site/enquiry-form";
import { Reveal } from "@/components/site/reveal";
import { SectionHeading } from "@/components/site/section-heading";
import { Icon } from "@/components/ui/icon";
import { bool, text } from "@/lib/cms/values";
import { pick } from "@/lib/i18n/config";
import type { BlockProps } from "./context";

/**
 * Contact details come from Site Settings, not from this block's own fields:
 * an address typed into one section and again into the footer is an address
 * that will eventually disagree with itself.
 */
export function ContactDetailsBlock({ values, ctx }: BlockProps) {
  const { locale, dict, settings, catalog, whatsappHref } = ctx;
  const { contact } = settings;
  const showMap = bool(values, "showMap", true) && Boolean(contact.mapEmbedUrl);
  const showForm = bool(values, "showForm", true);

  const address = pick(locale, contact.addressEn, contact.addressAr);
  const city = pick(locale, contact.cityEn, contact.cityAr);
  const country = pick(locale, contact.countryEn, contact.countryAr);
  const hours = pick(locale, contact.hoursEn, contact.hoursAr);

  const rows = [
    address || city
      ? {
          icon: "mapPin",
          label: locale === "ar" ? "العنوان" : "Address",
          value: [address, [city, country].filter(Boolean).join(", ")].filter(Boolean).join("\n"),
          href: null,
        }
      : null,
    contact.phone
      ? {
          icon: "phone",
          label: dict.common.callUs,
          value: contact.phoneDisplay || contact.phone,
          href: `tel:${contact.phone}`,
        }
      : null,
    whatsappHref
      ? { icon: "whatsapp", label: dict.common.whatsappUs, value: dict.common.whatsappUs, href: whatsappHref }
      : null,
    contact.email
      ? { icon: "mail", label: dict.common.emailUs, value: contact.email, href: `mailto:${contact.email}` }
      : null,
    hours ? { icon: "clock", label: locale === "ar" ? "أوقات العمل" : "Opening hours", value: hours, href: null } : null,
  ].filter((row): row is NonNullable<typeof row> => Boolean(row));

  return (
    <section className="section-tight">
      <div className="shell shell-wide grid gap-12 lg:grid-cols-[0.85fr_1.15fr] lg:gap-16">
        <div>
          <SectionHeading title={text(values, "title", locale)} intro={text(values, "intro", locale)} />

          {rows.length ? (
            <ul className="mt-8 space-y-5">
              {rows.map((row) => (
                <Reveal as="li" key={row.label} className="flex gap-3.5">
                  <span
                    className="flex size-10 shrink-0 items-center justify-center rounded-full border border-line"
                    style={{ color: "var(--color-peach)" }}
                  >
                    <Icon name={row.icon} size={17} strokeWidth={row.icon === "whatsapp" ? 1.6 : 1.5} />
                  </span>
                  <span className="min-w-0">
                    <span className="block text-[0.75rem] uppercase tracking-[0.1em] text-muted rtl:tracking-normal">
                      {row.label}
                    </span>
                    {row.href ? (
                      <a
                        href={row.href}
                        target={row.href.startsWith("http") ? "_blank" : undefined}
                        rel={row.href.startsWith("http") ? "noopener noreferrer" : undefined}
                        dir={row.icon === "phone" ? "ltr" : undefined}
                        className="mt-0.5 block text-[0.95rem] text-strong transition-colors hover:text-[var(--color-peach)]"
                      >
                        {row.value}
                      </a>
                    ) : (
                      <span className="mt-0.5 block whitespace-pre-line text-[0.95rem] text-strong">
                        {row.value}
                      </span>
                    )}
                  </span>
                </Reveal>
              ))}
            </ul>
          ) : null}

          {showMap ? (
            <Reveal className="mt-9 overflow-hidden rounded-[var(--radius-lg)] border border-line">
              <iframe
                src={contact.mapEmbedUrl}
                title={locale === "ar" ? "الموقع على الخريطة" : "Office location on the map"}
                loading="lazy"
                referrerPolicy="no-referrer-when-downgrade"
                className="h-72 w-full border-0"
              />
            </Reveal>
          ) : null}
        </div>

        {showForm ? (
          <Reveal>
            <EnquiryForm
              locale={locale}
              dict={dict}
              categories={catalog.categories.map((c) => ({
                id: c.id,
                title: pick(locale, c.titleEn, c.titleAr),
              }))}
              services={catalog.services.map((s) => ({
                id: s.id,
                categoryId: s.categoryId,
                title: pick(locale, s.titleEn, s.titleAr),
                preset: s.formPreset,
              }))}
            />
          </Reveal>
        ) : null}
      </div>
    </section>
  );
}
