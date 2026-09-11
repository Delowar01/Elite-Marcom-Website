import "server-only";

import { unstable_cache } from "next/cache";
import { and, asc, desc, eq, isNull, or } from "drizzle-orm";

import { TAGS } from "@/lib/cache";
import { db } from "@/lib/db";
import {
  faqs,
  serviceCategories,
  serviceSubcategories,
  services,
  testimonials,
  travelPackages,
  videos,
} from "@/lib/db/schema";

export type CategoryRow = typeof serviceCategories.$inferSelect;
export type ServiceRow = typeof services.$inferSelect;
export type SubcategoryRow = typeof serviceSubcategories.$inferSelect;
export type PackageRow = typeof travelPackages.$inferSelect;
export type VideoRow = typeof videos.$inferSelect;
export type TestimonialRow = typeof testimonials.$inferSelect;
export type FaqRow = typeof faqs.$inferSelect;

export const getCategories = unstable_cache(
  async (): Promise<CategoryRow[]> =>
    db
      .select()
      .from(serviceCategories)
      .where(eq(serviceCategories.isPublished, true))
      .orderBy(asc(serviceCategories.sortOrder), asc(serviceCategories.id)),
  ["categories"],
  { tags: [TAGS.catalog], revalidate: 3600 },
);

export const getServices = unstable_cache(
  async (): Promise<ServiceRow[]> =>
    db
      .select()
      .from(services)
      .where(eq(services.isPublished, true))
      .orderBy(asc(services.sortOrder), asc(services.id)),
  ["services"],
  { tags: [TAGS.catalog], revalidate: 3600 },
);

export const getSubcategories = unstable_cache(
  async (): Promise<SubcategoryRow[]> =>
    db
      .select()
      .from(serviceSubcategories)
      .where(eq(serviceSubcategories.isPublished, true))
      .orderBy(asc(serviceSubcategories.sortOrder), asc(serviceSubcategories.id)),
  ["subcategories"],
  { tags: [TAGS.catalog], revalidate: 3600 },
);

/**
 * The whole published catalogue in one shape. Every public page needs the same
 * three lists — a category page needs its services, a service page needs its
 * siblings for "related" — so they are fetched once and sliced in memory.
 */
export async function getCatalog() {
  const [categories, allServices, subcategories] = await Promise.all([
    getCategories(),
    getServices(),
    getSubcategories(),
  ]);
  const byCategory = new Map<number, ServiceRow[]>();
  for (const service of allServices) {
    const list = byCategory.get(service.categoryId) ?? [];
    list.push(service);
    byCategory.set(service.categoryId, list);
  }
  return { categories, services: allServices, subcategories, byCategory };
}

export const getPackages = unstable_cache(
  async (): Promise<PackageRow[]> =>
    db
      .select()
      .from(travelPackages)
      .where(eq(travelPackages.isPublished, true))
      .orderBy(desc(travelPackages.isFeatured), asc(travelPackages.sortOrder), asc(travelPackages.id)),
  ["packages"],
  { tags: [TAGS.packages], revalidate: 3600 },
);

export const getVideos = unstable_cache(
  async (): Promise<VideoRow[]> =>
    db
      .select()
      .from(videos)
      .where(eq(videos.isPublished, true))
      .orderBy(desc(videos.isFeatured), asc(videos.sortOrder), asc(videos.id)),
  ["videos"],
  { tags: [TAGS.videos], revalidate: 3600 },
);

export const getTestimonials = unstable_cache(
  async (): Promise<TestimonialRow[]> =>
    db
      .select()
      .from(testimonials)
      .where(eq(testimonials.isPublished, true))
      .orderBy(desc(testimonials.isFeatured), asc(testimonials.sortOrder), asc(testimonials.id)),
  ["testimonials"],
  { tags: [TAGS.testimonials], revalidate: 3600 },
);

export const getFaqs = unstable_cache(
  async (): Promise<FaqRow[]> =>
    db
      .select()
      .from(faqs)
      .where(eq(faqs.isPublished, true))
      .orderBy(asc(faqs.sortOrder), asc(faqs.id)),
  ["faqs"],
  { tags: [TAGS.faqs], revalidate: 3600 },
);

/** Global questions plus anything attached to this category or service. */
export async function getFaqsFor(opts: {
  scope: "global" | "all";
  categoryId?: number;
  serviceId?: number;
}): Promise<FaqRow[]> {
  const all = await getFaqs();
  if (opts.scope === "all") return all;
  return all.filter((faq) => {
    if (faq.scope === "global") return true;
    if (opts.categoryId && faq.categoryId === opts.categoryId) return true;
    if (opts.serviceId && faq.serviceId === opts.serviceId) return true;
    return false;
  });
}

/** Used by the service page: global + this service's + its category's. */
export const serviceFaqFilter = (
  rows: FaqRow[],
  categoryId: number,
  serviceId: number,
): FaqRow[] =>
  rows.filter(
    (faq) =>
      faq.serviceId === serviceId ||
      (faq.scope === "category" && faq.categoryId === categoryId),
  );

export const getCategoryBySlug = async (slug: string) =>
  (await getCategories()).find((c) => c.slug === slug) ?? null;

export const getPackageBySlug = async (slug: string) =>
  (await getPackages()).find((p) => p.slug === slug) ?? null;

/** Only used by the sitemap, which wants unpublished rows excluded anyway. */
export const publishedSlugs = async () => {
  const { categories, services: all } = await getCatalog();
  const byId = new Map(categories.map((c) => [c.id, c.slug]));
  return {
    categories: categories.map((c) => ({ slug: c.slug, updatedAt: c.updatedAt })),
    services: all
      .map((s) => ({
        category: byId.get(s.categoryId),
        slug: s.slug,
        updatedAt: s.updatedAt,
      }))
      .filter((s): s is { category: string; slug: string; updatedAt: Date } => Boolean(s.category)),
  };
};

/** Kept for the FAQ admin screen, which lists unattached questions first. */
export const orphanFaqFilter = () =>
  and(eq(faqs.scope, "global"), or(isNull(faqs.categoryId), isNull(faqs.serviceId)));
