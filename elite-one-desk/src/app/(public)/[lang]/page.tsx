import { notFound } from "next/navigation";

import { JsonLd } from "@/components/site/json-ld";
import { SectionRenderer, buildBlockContext } from "@/components/site/section-renderer";
import { PreviewBanner } from "@/components/site/preview-banner";
import { isLocale } from "@/lib/i18n/config";
import { resolvePageForRender } from "@/lib/preview";
import { buildMetadata, organizationJsonLd } from "@/lib/seo";

type Params = {
  params: Promise<{ lang: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export async function generateMetadata({ params }: Pick<Params, "params">) {
  const { lang } = await params;
  if (!isLocale(lang)) return {};
  return buildMetadata({ locale: lang, path: "/", entityType: "page", entityKey: "home" });
}

export default async function HomePage({ params, searchParams }: Params) {
  const { lang } = await params;
  if (!isLocale(lang)) notFound();

  const [{ page, isPreview }, ctx, organization] = await Promise.all([
    resolvePageForRender("home", await searchParams),
    buildBlockContext(lang),
    organizationJsonLd(lang),
  ]);
  if (!page) notFound();

  return (
    <>
      {isPreview ? <PreviewBanner /> : null}
      <SectionRenderer sections={page.sections} locale={lang} ctx={ctx} />
      <JsonLd
        data={[
          organization,
          {
            "@context": "https://schema.org",
            "@type": "WebSite",
            name: ctx.settings.brand.siteNameEn,
            url: process.env.NEXT_PUBLIC_SITE_URL ?? "",
            potentialAction: {
              "@type": "SearchAction",
              target: `${process.env.NEXT_PUBLIC_SITE_URL ?? ""}/search?q={search_term_string}`,
              "query-input": "required name=search_term_string",
            },
          },
        ]}
      />
    </>
  );
}
