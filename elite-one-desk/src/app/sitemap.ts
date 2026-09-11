import type { MetadataRoute } from "next";

import { siteUrl } from "@/lib/env";
import { LOCALES, localeHref } from "@/lib/i18n/config";
import { getPackages, publishedSlugs } from "@/lib/queries/catalog";
import { getPublishedPages } from "@/lib/queries/content";
import { getSettings } from "@/lib/settings";

/** Search results and the admin never appear here; everything published does. */
const SKIP = new Set(["search"]);

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const [settings, pages, { categories, services }, packages] = await Promise.all([
    getSettings(),
    getPublishedPages(),
    publishedSlugs(),
    getPackages(),
  ]);

  const locales = settings.features.arabicEnabled ? LOCALES : ["en" as const];

  const entries: Array<{ path: string; lastModified: Date; priority: number; changeFrequency: MetadataRoute.Sitemap[number]["changeFrequency"] }> = [
    { path: "/", lastModified: new Date(), priority: 1, changeFrequency: "weekly" },
    { path: "/services", lastModified: new Date(), priority: 0.9, changeFrequency: "weekly" },
    { path: "/packages", lastModified: new Date(), priority: 0.7, changeFrequency: "weekly" },
  ];

  for (const page of pages) {
    if (page.slug === "home" || SKIP.has(page.slug)) continue;
    entries.push({
      path: `/${page.slug}`,
      lastModified: page.updatedAt,
      priority: 0.6,
      changeFrequency: "monthly",
    });
  }
  for (const category of categories) {
    entries.push({
      path: `/services/${category.slug}`,
      lastModified: category.updatedAt,
      priority: 0.8,
      changeFrequency: "weekly",
    });
  }
  for (const service of services) {
    entries.push({
      path: `/services/${service.category}/${service.slug}`,
      lastModified: service.updatedAt,
      priority: 0.7,
      changeFrequency: "monthly",
    });
  }
  for (const row of packages) {
    entries.push({
      path: `/packages/${row.slug}`,
      lastModified: row.updatedAt,
      priority: 0.6,
      changeFrequency: "monthly",
    });
  }

  // Each address is listed once per language with the alternates attached, so
  // Google is told about the Arabic edition rather than left to find it.
  return entries.flatMap((entry) =>
    locales.map((locale) => ({
      url: `${siteUrl}${localeHref(locale, entry.path)}`,
      lastModified: entry.lastModified,
      changeFrequency: entry.changeFrequency,
      priority: entry.priority,
      alternates: {
        languages: Object.fromEntries(
          locales.map((l) => [l, `${siteUrl}${localeHref(l, entry.path)}`]),
        ),
      },
    })),
  );
}
