import { notFound } from "next/navigation";

import { Breadcrumbs } from "@/components/site/breadcrumbs";
import { PackageCard } from "@/components/site/package-card";
import { Reveal } from "@/components/site/reveal";
import { isLocale } from "@/lib/i18n/config";
import { getDictionary } from "@/lib/i18n/dictionary";
import { getPackages } from "@/lib/queries/catalog";
import { getMediaMap } from "@/lib/queries/site";
import { buildMetadata } from "@/lib/seo";

type Params = { params: Promise<{ lang: string }> };

const REGION_LABELS: Record<string, { en: string; ar: string }> = {
  egypt: { en: "Egypt", ar: "مصر" },
  international: { en: "International", ar: "دولي" },
  holiday: { en: "Holiday", ar: "عطلات" },
  corporate: { en: "Corporate", ar: "شركات" },
};

export async function generateMetadata({ params }: Params) {
  const { lang } = await params;
  if (!isLocale(lang)) return {};
  return buildMetadata({
    locale: lang,
    path: "/packages",
    entityType: "page",
    entityKey: "packages",
    title: lang === "ar" ? "البرامج السياحية" : "Travel packages",
    description:
      lang === "ar"
        ? "برامج سياحية إلى مصر ووجهات دولية، وباقات عائلية وشركات — جميعها قابلة للتخصيص."
        : "Egypt and international tour packages, family and corporate itineraries — every one of them adjustable.",
  });
}

export default async function PackagesPage({ params }: Params) {
  const { lang } = await params;
  if (!isLocale(lang)) notFound();

  const dict = getDictionary(lang);
  const [rows, media] = await Promise.all([getPackages(), getMediaMap()]);

  const regions = Array.from(new Set(rows.map((r) => r.region)));

  return (
    <>
      <section className="relative overflow-clip pb-8 pt-[clamp(6.5rem,9vw,9rem)]">
        <div className="grid-texture pointer-events-none absolute inset-0 -z-10" />
        <div className="shell shell-wide">
          <p className="eyebrow">{lang === "ar" ? "السفر والسياحة" : "Travel & tourism"}</p>
          <h1 className="mt-5 max-w-3xl text-[length:var(--text-h1)]">
            {lang === "ar" ? "برامج مُعدّة، وقابلة للتعديل" : "Prepared itineraries, built to be changed"}
          </h1>
          <p className="lede mt-5 max-w-2xl">
            {lang === "ar"
              ? "ابدأ من برنامج جاهز أو اطلب برنامجًا مخصصًا بالكامل — التذاكر والفنادق والتنقلات والمرشد."
              : "Start from a prepared programme or ask for one built around you — flights, hotels, transfers and a guide."}
          </p>
        </div>
      </section>

      <Breadcrumbs
        locale={lang}
        label={dict.nav.breadcrumb}
        trail={[
          { name: dict.nav.home, path: "/" },
          { name: dict.common.packages, path: "/packages" },
        ]}
      />

      <div className="shell shell-wide pb-[var(--spacing-section)] pt-10">
        {rows.length === 0 ? (
          <p className="text-body">{dict.common.noResults}</p>
        ) : (
          regions.map((region) => {
            const inRegion = rows.filter((r) => r.region === region);
            const label = REGION_LABELS[region];
            return (
              <section key={region} className="mb-14 last:mb-0">
                <h2 className="mb-6 text-[length:var(--text-h3)]">
                  {label ? (lang === "ar" ? label.ar : label.en) : region}
                </h2>
                <ul className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
                  {inRegion.map((row, index) => (
                    <Reveal as="li" key={row.id} delay={index * 55} className="h-full">
                      <PackageCard
                        row={row}
                        locale={lang}
                        image={row.imageId ? (media.get(row.imageId) ?? null) : null}
                      />
                    </Reveal>
                  ))}
                </ul>
              </section>
            );
          })
        )}
      </div>
    </>
  );
}
