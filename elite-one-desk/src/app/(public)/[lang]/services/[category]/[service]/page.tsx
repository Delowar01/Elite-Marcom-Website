import Link from "next/link";
import { notFound } from "next/navigation";

import { Breadcrumbs } from "@/components/site/breadcrumbs";
import { EnquiryForm } from "@/components/site/enquiry-form";
import { FaqAccordion } from "@/components/site/faq-accordion";
import { JsonLd } from "@/components/site/json-ld";
import { MediaImage } from "@/components/site/media-image";
import { Reveal } from "@/components/site/reveal";
import { Icon } from "@/components/ui/icon";
import { toPlainText } from "@/lib/cms/sanitize";
import { isLocale, localeHref, pick } from "@/lib/i18n/config";
import { getDictionary } from "@/lib/i18n/dictionary";
import { getCatalog, getFaqs } from "@/lib/queries/catalog";
import { getMediaMap } from "@/lib/queries/site";
import { breadcrumbJsonLd, buildMetadata, faqJsonLd } from "@/lib/seo";
import { getSettings, whatsappLink } from "@/lib/settings";

type Params = { params: Promise<{ lang: string; category: string; service: string }> };

async function load(categorySlug: string, serviceSlug: string) {
  const catalog = await getCatalog();
  const category = catalog.categories.find((c) => c.slug === categorySlug);
  if (!category) return null;
  const service = (catalog.byCategory.get(category.id) ?? []).find((s) => s.slug === serviceSlug);
  if (!service) return null;
  return { catalog, category, service };
}

export async function generateMetadata({ params }: Params) {
  const { lang, category, service } = await params;
  if (!isLocale(lang)) return {};
  const found = await load(category, service);
  if (!found) return {};
  return buildMetadata({
    locale: lang,
    path: `/services/${category}/${service}`,
    entityType: "service",
    entityKey: `${category}/${service}`,
    title: pick(lang, found.service.titleEn, found.service.titleAr),
    description: toPlainText(pick(lang, found.service.introEn, found.service.introAr), 300),
    imageId: found.service.imageId,
    type: "article",
  });
}

export async function generateStaticParams() {
  const catalog = await getCatalog();
  const bySlug = new Map(catalog.categories.map((c) => [c.id, c.slug]));
  return catalog.services
    .map((s) => ({ category: bySlug.get(s.categoryId), service: s.slug }))
    .filter((p): p is { category: string; service: string } => Boolean(p.category));
}

/**
 * The service detail template (§12). Every block below disappears when its
 * field is empty, so a service with only an intro is a clean short page rather
 * than a page of empty headings — which is what lets one template carry
 * seventy very different services.
 */
export default async function ServicePage({ params }: Params) {
  const { lang, category: categorySlug, service: serviceSlug } = await params;
  if (!isLocale(lang)) notFound();

  const found = await load(categorySlug, serviceSlug);
  if (!found) notFound();
  const { catalog, category, service } = found;

  const [media, allFaqs, settings] = await Promise.all([getMediaMap(), getFaqs(), getSettings()]);
  const dict = getDictionary(lang);

  const title = pick(lang, service.titleEn, service.titleAr);
  const categoryTitle = pick(lang, category.titleEn, category.titleAr);
  const image = service.imageId ? media.get(service.imageId) : null;
  const whatsapp = whatsappLink(settings, lang, title);

  const local = (list: Array<{ en: string; ar: string }> | null | undefined) =>
    (list ?? []).map((item) => pick(lang, item.en, item.ar)).filter(Boolean);

  const benefits = local(service.benefits);
  const audience = local(service.audience);
  const requirements = local(service.requirements);
  const steps = (service.processSteps ?? [])
    .map((step) => ({
      label: pick(lang, step.en, step.ar),
      detail: pick(lang, step.detailEn, step.detailAr),
    }))
    .filter((step) => step.label);

  const faqs = allFaqs
    .filter(
      (faq) =>
        faq.serviceId === service.id ||
        (faq.scope === "category" && faq.categoryId === category.id),
    )
    .map((faq) => ({
      id: faq.id,
      question: pick(lang, faq.questionEn, faq.questionAr),
      answer: pick(lang, faq.answerEn, faq.answerAr),
    }));

  const related = (catalog.byCategory.get(category.id) ?? [])
    .filter((s) => s.id !== service.id)
    .slice(0, 4);

  const trail = [
    { name: dict.nav.home, path: "/" },
    { name: dict.common.services, path: "/services" },
    { name: categoryTitle, path: `/services/${categorySlug}` },
    { name: title, path: `/services/${categorySlug}/${serviceSlug}` },
  ];

  // Visa services get the embassy-decides notice on top of the standing
  // government one; both are editable in Site Settings.
  const isVisa = /visa/i.test(service.slug) || /visa/i.test(category.slug);
  const disclaimers = [
    settings.disclaimers.showOnServicePages
      ? pick(lang, settings.disclaimers.governmentEn, settings.disclaimers.governmentAr)
      : "",
    isVisa ? pick(lang, settings.disclaimers.visaEn, settings.disclaimers.visaAr) : "",
  ].filter(Boolean);

  return (
    <>
      <section className="relative overflow-clip pb-8 pt-[clamp(6.5rem,9vw,9rem)]">
        <div className="grid-texture pointer-events-none absolute inset-0 -z-10" />
        <div className="shell shell-wide grid gap-10 lg:grid-cols-[1.1fr_0.9fr] lg:items-center">
          <div>
            <Link
              href={localeHref(lang, `/services/${categorySlug}`)}
              className="eyebrow transition-opacity hover:opacity-75"
            >
              {categoryTitle}
            </Link>
            <h1 className="mt-5 max-w-2xl text-[length:var(--text-h1)]">{title}</h1>
            {pick(lang, service.introEn, service.introAr) ? (
              <p className="lede mt-5 max-w-xl">{pick(lang, service.introEn, service.introAr)}</p>
            ) : null}

            <div className="mt-8 flex flex-wrap gap-3">
              <a href="#request" className="btn btn-primary">
                {dict.common.requestService}
                <Icon name="arrowRight" size={16} className="flip-rtl" />
              </a>
              {whatsapp ? (
                <a href={whatsapp} target="_blank" rel="noopener noreferrer" className="btn btn-ghost">
                  <Icon name="whatsapp" size={16} strokeWidth={1.6} />
                  {dict.common.whatsappUs}
                </a>
              ) : null}
            </div>

            {pick(lang, service.timelineEn, service.timelineAr) ? (
              <p className="mt-6 inline-flex items-center gap-2 rounded-full border border-line px-3.5 py-2 text-[0.8rem] text-muted">
                <Icon name="clock" size={14} />
                <span className="font-medium text-body">{dict.service.timeline}:</span>
                {pick(lang, service.timelineEn, service.timelineAr)}
              </p>
            ) : null}
          </div>

          {image ? (
            <div className="overflow-hidden rounded-[var(--radius-lg)] border border-line">
              <MediaImage
                media={image}
                locale={lang}
                sizes="(max-width: 1024px) 92vw, 42vw"
                ratio="4 / 3"
                priority
                className="w-full"
              />
            </div>
          ) : null}
        </div>
      </section>

      <Breadcrumbs locale={lang} label={dict.nav.breadcrumb} trail={trail} />

      <div className="shell shell-wide grid gap-12 py-12 lg:grid-cols-[1.15fr_0.85fr] lg:gap-16">
        <div className="min-w-0">
          {pick(lang, service.bodyEn, service.bodyAr) ? (
            <Reveal>
              <h2 className="mb-5 text-[length:var(--text-h3)]">{dict.service.overview}</h2>
              <div
                className="prose-eod"
                dangerouslySetInnerHTML={{ __html: pick(lang, service.bodyEn, service.bodyAr) }}
              />
            </Reveal>
          ) : null}

          {benefits.length ? (
            <Reveal className="mt-12">
              <h2 className="mb-5 text-[length:var(--text-h3)]">{dict.service.benefits}</h2>
              <ul className="grid gap-3 sm:grid-cols-2">
                {benefits.map((item) => (
                  <li key={item} className="flex items-start gap-2.5 text-small text-body">
                    <Icon name="check" size={15} className="mt-1 shrink-0" style={{ color: "var(--color-orange)" }} />
                    {item}
                  </li>
                ))}
              </ul>
            </Reveal>
          ) : null}

          {audience.length ? (
            <Reveal className="mt-12">
              <h2 className="mb-5 text-[length:var(--text-h3)]">{dict.service.audience}</h2>
              <ul className="flex flex-wrap gap-2">
                {audience.map((item) => (
                  <li key={item} className="rounded-full border border-line px-3.5 py-2 text-[0.82rem] text-body">
                    {item}
                  </li>
                ))}
              </ul>
            </Reveal>
          ) : null}

          {requirements.length ? (
            <Reveal className="mt-12">
              <h2 className="mb-5 text-[length:var(--text-h3)]">{dict.service.requirements}</h2>
              <ul className="divide-y border-y" style={{ borderColor: "var(--border-color)" }}>
                {requirements.map((item) => (
                  <li key={item} className="flex items-start gap-3 py-3 text-small text-body">
                    <Icon name="fileText" size={15} className="mt-0.5 shrink-0 text-muted" />
                    {item}
                  </li>
                ))}
              </ul>
            </Reveal>
          ) : null}

          {steps.length ? (
            <Reveal className="mt-12">
              <h2 className="mb-6 text-[length:var(--text-h3)]">{dict.service.process}</h2>
              <ol className="relative">
                <span
                  aria-hidden
                  className="absolute inset-y-0 w-px"
                  style={{ insetInlineStart: "1.125rem", background: "var(--border-color)" }}
                />
                {steps.map((step, index) => (
                  <li key={step.label} className="relative ps-12 pb-7 last:pb-0">
                    <span
                      className="absolute top-0 flex size-9 items-center justify-center rounded-full border font-display text-[0.72rem] font-bold tabular-nums"
                      style={{
                        insetInlineStart: 0,
                        borderColor: "color-mix(in oklab, var(--color-orange) 45%, transparent)",
                        background: "var(--color-ink-800)",
                        color: "var(--color-peach)",
                      }}
                    >
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <h3 className="pt-1.5 text-[0.98rem]">{step.label}</h3>
                    {step.detail ? <p className="mt-1.5 text-small text-muted">{step.detail}</p> : null}
                  </li>
                ))}
              </ol>
            </Reveal>
          ) : null}

          {pick(lang, service.notesEn, service.notesAr) ? (
            <Reveal className="mt-12">
              <h2 className="mb-4 text-[length:var(--text-h3)]">{dict.service.notes}</h2>
              <div
                className="prose-eod rounded-[var(--radius-md)] border border-line p-5 text-small"
                dangerouslySetInnerHTML={{ __html: pick(lang, service.notesEn, service.notesAr) }}
              />
            </Reveal>
          ) : null}

          {faqs.length ? (
            <Reveal className="mt-12">
              <h2 className="mb-4 text-[length:var(--text-h3)]">{dict.service.faq}</h2>
              <FaqAccordion entries={faqs} />
            </Reveal>
          ) : null}

          {disclaimers.length ? (
            <div className="mt-12 space-y-3">
              {disclaimers.map((note) => (
                <p
                  key={note.slice(0, 40)}
                  className="rounded-[var(--radius-md)] border border-line bg-[color-mix(in_oklab,var(--color-warm)_3%,transparent)] p-4 text-[0.78rem] leading-relaxed text-muted"
                >
                  {note}
                </p>
              ))}
            </div>
          ) : null}
        </div>

        <aside className="min-w-0">
          <div id="request" className="lg:sticky lg:top-28 scroll-mt-28">
            <h2 className="mb-1.5 text-[length:var(--text-h3)]">{dict.form.heading}</h2>
            <p className="mb-5 text-small text-muted">{dict.form.subheading}</p>
            <EnquiryForm
              locale={lang}
              dict={dict}
              categories={catalog.categories.map((c) => ({
                id: c.id,
                title: pick(lang, c.titleEn, c.titleAr),
              }))}
              services={catalog.services.map((s) => ({
                id: s.id,
                categoryId: s.categoryId,
                title: pick(lang, s.titleEn, s.titleAr),
                preset: s.formPreset,
              }))}
              initialCategoryId={category.id}
              initialServiceId={service.id}
            />
          </div>
        </aside>
      </div>

      {related.length ? (
        <section className="section-tight border-t border-line">
          <div className="shell shell-wide">
            <h2 className="mb-6 text-[length:var(--text-h3)]">{dict.common.relatedServices}</h2>
            <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {related.map((item) => (
                <li key={item.id}>
                  <Link
                    href={localeHref(lang, `/services/${categorySlug}/${item.slug}`)}
                    className="group flex h-full flex-col rounded-[var(--radius-md)] border border-line p-4 transition-colors hover:border-[color-mix(in_oklab,var(--color-peach)_45%,transparent)]"
                  >
                    <span className="text-[0.9rem] font-semibold leading-snug text-strong">
                      {pick(lang, item.titleEn, item.titleAr)}
                    </span>
                    <Icon
                      name="arrowUpRight"
                      size={14}
                      className="mt-auto flip-rtl pt-3 text-muted transition-colors group-hover:text-[var(--color-peach)]"
                    />
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </section>
      ) : null}

      <JsonLd
        data={[
          breadcrumbJsonLd(lang, trail),
          ...(faqJsonLd(faqs) ? [faqJsonLd(faqs)!] : []),
          {
            "@context": "https://schema.org",
            "@type": "Service",
            name: title,
            serviceType: categoryTitle,
            description: toPlainText(pick(lang, service.introEn, service.introAr), 300),
            areaServed: { "@type": "Country", name: "Saudi Arabia" },
            provider: {
              "@type": "Organization",
              name: pick(lang, settings.brand.legalNameEn, settings.brand.legalNameAr),
              url: process.env.NEXT_PUBLIC_SITE_URL ?? "",
            },
          },
        ]}
      />
    </>
  );
}
