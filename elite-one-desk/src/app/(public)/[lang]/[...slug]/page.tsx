import { notFound } from "next/navigation";

import { SectionRenderer, buildBlockContext } from "@/components/site/section-renderer";
import { PreviewBanner } from "@/components/site/preview-banner";
import { isLocale } from "@/lib/i18n/config";
import { getPage, getPublishedPages } from "@/lib/queries/content";
import { resolvePageForRender } from "@/lib/preview";
import { buildMetadata } from "@/lib/seo";

type Params = {
  params: Promise<{ lang: string; slug: string[] }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

/**
 * Every page that is not the homepage, the catalogue or search: About, Contact,
 * the legal pages and anything an admin creates. They are all rows in `pages`
 * carrying a list of sections, so a new page needs no code.
 *
 * A multi-segment address never legitimately reaches here — `/services/x/y` is
 * matched by its own route first — so anything with a slash is a 404.
 */
export async function generateMetadata({ params }: Pick<Params, "params">) {
  const { lang, slug } = await params;
  if (!isLocale(lang) || slug.length !== 1) return {};
  const page = await getPage(slug[0]!);
  if (!page) return {};
  return buildMetadata({
    locale: lang,
    path: `/${slug[0]}`,
    entityType: "page",
    entityKey: slug[0]!,
    title: lang === "ar" && page.titleAr ? page.titleAr : page.titleEn,
  });
}

export default async function CmsPage({ params, searchParams }: Params) {
  const { lang, slug } = await params;
  if (!isLocale(lang) || slug.length !== 1) notFound();

  const { page, isPreview } = await resolvePageForRender(slug[0]!, await searchParams);
  // An unpublished page is still viewable in preview, which is the point of it.
  if (!page || (!page.isPublished && !isPreview)) notFound();

  const ctx = await buildBlockContext(lang);
  return (
    <>
      {isPreview ? <PreviewBanner /> : null}
      <SectionRenderer sections={page.sections} locale={lang} ctx={ctx} />
    </>
  );
}

export async function generateStaticParams() {
  const pages = await getPublishedPages();
  return pages.filter((p) => p.slug !== "home").map((p) => ({ slug: [p.slug] }));
}
