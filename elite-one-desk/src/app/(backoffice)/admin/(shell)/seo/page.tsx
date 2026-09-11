import { asc, eq } from "drizzle-orm";

import { AdminPageHeader } from "@/components/admin/page-header";
import { requirePermission } from "@/lib/auth/guard";
import { toPlainText } from "@/lib/cms/sanitize";
import { db } from "@/lib/db";
import {
  media,
  pages,
  seoMetadata,
  serviceCategories,
  services,
  travelPackages,
} from "@/lib/db/schema";
import { SeoClient, type SeoEntity } from "./seo-client";

export const metadata = { title: "SEO" };
export const dynamic = "force-dynamic";

export default async function SeoPage() {
  const session = await requirePermission("seo.manage", "/admin/seo");

  const [pageRows, categoryRows, serviceRows, packageRows, overrides, library] = await Promise.all([
    db.select().from(pages).orderBy(asc(pages.sortOrder), asc(pages.id)),
    db.select().from(serviceCategories).orderBy(asc(serviceCategories.sortOrder)),
    db
      .select({ service: services, categorySlug: serviceCategories.slug })
      .from(services)
      .innerJoin(serviceCategories, eq(serviceCategories.id, services.categoryId))
      .orderBy(asc(serviceCategories.sortOrder), asc(services.sortOrder)),
    db.select().from(travelPackages).orderBy(asc(travelPackages.sortOrder)),
    db.select().from(seoMetadata),
    db
      .select({
        id: media.id,
        filename: media.filename,
        title: media.title,
        altEn: media.altEn,
        width: media.width,
        height: media.height,
        folder: media.folder,
      })
      .from(media)
      .orderBy(asc(media.folder), asc(media.title)),
  ]);

  const overrideMap = new Map(overrides.map((row) => [`${row.entityType}:${row.entityKey}`, row]));
  const withOverride = (type: SeoEntity["type"], key: string): SeoEntity["override"] => {
    const row = overrideMap.get(`${type}:${key}`);
    if (!row) return null;
    return {
      titleEn: row.titleEn,
      titleAr: row.titleAr,
      descriptionEn: row.descriptionEn,
      descriptionAr: row.descriptionAr,
      canonicalUrl: row.canonicalUrl,
      ogTitle: row.ogTitle,
      ogDescription: row.ogDescription,
      ogImageId: row.ogImageId,
      noindex: row.noindex,
    };
  };

  const entities: SeoEntity[] = [
    ...pageRows.map((row) => ({
      type: "page" as const,
      key: row.slug,
      label: row.titleEn,
      path: row.slug === "home" ? "/" : `/${row.slug}`,
      fallbackTitle: row.titleEn,
      fallbackDescription: "",
      override: withOverride("page", row.slug),
    })),
    ...categoryRows.map((row) => ({
      type: "category" as const,
      key: row.slug,
      label: row.titleEn,
      path: `/services/${row.slug}`,
      fallbackTitle: row.titleEn,
      fallbackDescription: toPlainText(row.summaryEn, 160),
      override: withOverride("category", row.slug),
    })),
    ...serviceRows.map(({ service, categorySlug }) => ({
      type: "service" as const,
      key: `${categorySlug}/${service.slug}`,
      label: service.titleEn,
      path: `/services/${categorySlug}/${service.slug}`,
      fallbackTitle: service.titleEn,
      fallbackDescription: toPlainText(service.introEn, 160),
      override: withOverride("service", `${categorySlug}/${service.slug}`),
    })),
    ...packageRows.map((row) => ({
      type: "package" as const,
      key: row.slug,
      label: row.titleEn,
      path: `/packages/${row.slug}`,
      fallbackTitle: row.titleEn,
      fallbackDescription: toPlainText(row.summaryEn, 160),
      override: withOverride("package", row.slug),
    })),
  ];

  return (
    <>
      <AdminPageHeader
        title="SEO"
        description="Every address on the site, with the title and description it will use. Leave a field empty and the page keeps following its own content — which is usually the right answer."
      />
      <SeoClient csrf={session.csrfToken} entities={entities} media={library} />
    </>
  );
}
