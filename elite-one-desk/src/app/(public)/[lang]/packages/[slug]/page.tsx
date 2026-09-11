import Link from "next/link";
import { notFound } from "next/navigation";

import { Breadcrumbs } from "@/components/site/breadcrumbs";
import { EnquiryForm } from "@/components/site/enquiry-form";
import { JsonLd } from "@/components/site/json-ld";
import { MediaImage } from "@/components/site/media-image";
import { Reveal } from "@/components/site/reveal";
import { Icon } from "@/components/ui/icon";
import { toPlainText } from "@/lib/cms/sanitize";
import { isLocale, localeHref, pick } from "@/lib/i18n/config";
import { getDictionary } from "@/lib/i18n/dictionary";
import { getCatalog, getPackageBySlug, getPackages } from "@/lib/queries/catalog";
import { getMediaMap } from "@/lib/queries/site";
import { breadcrumbJsonLd, buildMetadata } from "@/lib/seo";
import { getSettings, whatsappLink } from "@/lib/settings";

type Params = { params: Promise<{ lang: string; slug: string }> };

export async function generateMetadata({ params }: Params) {
  const { lang, slug } = await params;
  if (!isLocale(lang)) return {};
  const row = await getPackageBySlug(slug);
  if (!row) return {};
  return buildMetadata({
    locale: lang,
    path: `/packages/${slug}`,
    entityType: "package",
    entityKey: slug,
    title: pick(lang, row.titleEn, row.titleAr),
    description: toPlainText(pick(lang, row.summaryEn, row.summaryAr), 300),
    imageId: row.imageId,
    type: "article",
  });
}

export async function generateStaticParams() {
  return (await getPackages()).map((p) => ({ slug: p.slug }));
}

export default async function PackagePage({ params }: Params) {
  const { lang, slug } = await params;
  if (!isLocale(lang)) notFound();

  const row = await getPackageBySlug(slug);
  if (!row) notFound();

  const [media, catalog, settings] = await Promise.all([getMediaMap(), getCatalog(), getSettings()]);
  const dict = getDictionary(lang);
  const title = pick(lang, row.titleEn, row.titleAr);
  const image = row.imageId ? media.get(row.imageId) : null;
  const whatsapp = whatsappLink(settings, lang, title);
  const highlights = (row.highlights ?? []).map((h) => pick(lang, h.en, h.ar)).filter(Boolean);

  const trail = [
    { name: dict.nav.home, path: "/" },
    { name: dict.common.packages, path: "/packages" },
    { name: title, path: `/packages/${slug}` },
  ];

  return (
    <>
      <section className="relative overflow-clip pb-8 pt-[clamp(6.5rem,9vw,9rem)]">
        <div className="grid-texture pointer-events-none absolute inset-0 -z-10" />
        <div className="shell shell-wide grid gap-10 lg:grid-cols-[1.05fr_0.95fr] lg:items-center">
          <div>
            <Link href={localeHref(lang, "/packages")} className="eyebrow transition-opacity hover:opacity-75">
              {dict.common.packages}
            </Link>
            <h1 className="mt-5 text-[length:var(--text-h1)]">{title}</h1>

            <div className="mt-5 flex flex-wrap gap-x-5 gap-y-2 text-small text-muted">
              {pick(lang, row.destinationEn, row.destinationAr) ? (
                <span className="inline-flex items-center gap-1.5">
                  <Icon name="mapPin" size={15} />
                  {pick(lang, row.destinationEn, row.destinationAr)}
                </span>
              ) : null}
              {pick(lang, row.durationEn, row.durationAr) ? (
                <span className="inline-flex items-center gap-1.5">
                  <Icon name="clock" size={15} />
                  {pick(lang, row.durationEn, row.durationAr)}
                </span>
              ) : null}
            </div>

            {pick(lang, row.summaryEn, row.summaryAr) ? (
              <p className="lede mt-5 max-w-xl">{pick(lang, row.summaryEn, row.summaryAr)}</p>
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
          </div>

          {image ? (
            <div className="overflow-hidden rounded-[var(--radius-lg)] border border-line">
              <MediaImage media={image} locale={lang} sizes="(max-width: 1024px) 92vw, 45vw" ratio="4 / 3" priority className="w-full" />
            </div>
          ) : null}
        </div>
      </section>

      <Breadcrumbs locale={lang} label={dict.nav.breadcrumb} trail={trail} />

      <div className="shell shell-wide grid gap-12 py-12 lg:grid-cols-[1.15fr_0.85fr] lg:gap-16">
        <div className="min-w-0">
          {pick(lang, row.bodyEn, row.bodyAr) ? (
            <Reveal>
              <div className="prose-eod" dangerouslySetInnerHTML={{ __html: pick(lang, row.bodyEn, row.bodyAr) }} />
            </Reveal>
          ) : null}

          {highlights.length ? (
            <Reveal className="mt-10">
              <h2 className="mb-5 text-[length:var(--text-h3)]">
                {lang === "ar" ? "أبرز ما يشمله البرنامج" : "What the programme includes"}
              </h2>
              <ul className="grid gap-3 sm:grid-cols-2">
                {highlights.map((item) => (
                  <li key={item} className="flex items-start gap-2.5 text-small text-body">
                    <Icon name="check" size={15} className="mt-1 shrink-0" style={{ color: "var(--color-orange)" }} />
                    {item}
                  </li>
                ))}
              </ul>
            </Reveal>
          ) : null}
        </div>

        <aside className="min-w-0">
          <div id="request" className="scroll-mt-28 lg:sticky lg:top-28">
            <h2 className="mb-1.5 text-[length:var(--text-h3)]">{dict.form.heading}</h2>
            <p className="mb-5 text-small text-muted">{dict.form.subheading}</p>
            <EnquiryForm
              locale={lang}
              dict={dict}
              forcedPreset="travel"
              categories={catalog.categories.map((c) => ({ id: c.id, title: pick(lang, c.titleEn, c.titleAr) }))}
              services={catalog.services.map((s) => ({
                id: s.id,
                categoryId: s.categoryId,
                title: pick(lang, s.titleEn, s.titleAr),
                preset: s.formPreset,
              }))}
            />
          </div>
        </aside>
      </div>

      <JsonLd
        data={[
          breadcrumbJsonLd(lang, trail),
          {
            "@context": "https://schema.org",
            "@type": "TouristTrip",
            name: title,
            description: toPlainText(pick(lang, row.summaryEn, row.summaryAr), 300),
            touristType: pick(lang, row.destinationEn, row.destinationAr) || undefined,
          },
        ]}
      />
    </>
  );
}
