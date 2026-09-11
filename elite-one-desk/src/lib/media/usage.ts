import "server-only";

import { eq, or, sql } from "drizzle-orm";

import { db } from "@/lib/db";
import {
  pageSections,
  pages,
  serviceCategories,
  services,
  testimonials,
  travelPackages,
  videos,
} from "@/lib/db/schema";

export type MediaUse = { label: string; where: string; href: string };

/**
 * Where a picture is placed.
 *
 * Deleting a file that a page still points at leaves a broken image on the live
 * site, and the first you would hear of it is from a visitor. So the library
 * refuses, and shows the editor exactly which screens to clear first.
 *
 * Section values are jsonb, so they are searched by value rather than by a list
 * of known field names — a block type that gains an image field later is
 * covered without anyone coming back to this file.
 */
export async function mediaUsage(id: number): Promise<MediaUse[]> {
  const uses: MediaUse[] = [];

  const [sections, categories, serviceRows, packageRows, videoRows, testimonialRows] =
    await Promise.all([
      db
        .select({
          id: pageSections.id,
          blockType: pageSections.blockType,
          pageTitle: pages.titleEn,
          pageSlug: pages.slug,
        })
        .from(pageSections)
        .innerJoin(pages, eq(pages.id, pageSections.pageId))
        .where(
          sql`
            exists (select 1 from jsonb_each(${pageSections.published}) e
                    where e.value = to_jsonb(${id}::int))
            or exists (select 1 from jsonb_each(coalesce(${pageSections.draft}, '{}'::jsonb)) e
                       where e.value = to_jsonb(${id}::int))
          `,
        ),
      db
        .select({ id: serviceCategories.id, title: serviceCategories.titleEn })
        .from(serviceCategories)
        .where(eq(serviceCategories.imageId, id)),
      db.select({ id: services.id, title: services.titleEn }).from(services).where(eq(services.imageId, id)),
      db
        .select({ id: travelPackages.id, title: travelPackages.titleEn })
        .from(travelPackages)
        .where(eq(travelPackages.imageId, id)),
      db
        .select({ id: videos.id, title: videos.titleEn })
        .from(videos)
        .where(or(eq(videos.thumbnailId, id))),
      db
        .select({ id: testimonials.id, name: testimonials.name })
        .from(testimonials)
        .where(eq(testimonials.imageId, id)),
    ]);

  for (const row of sections) {
    uses.push({
      label: `${row.pageTitle} — ${row.blockType} section`,
      where: "Pages & sections",
      href: `/admin/pages/section/${row.id}`,
    });
  }
  for (const row of categories) {
    uses.push({ label: row.title, where: "Service categories", href: `/admin/categories/${row.id}` });
  }
  for (const row of serviceRows) {
    uses.push({ label: row.title, where: "Services", href: `/admin/services/${row.id}` });
  }
  for (const row of packageRows) {
    uses.push({ label: row.title, where: "Travel packages", href: `/admin/packages/${row.id}` });
  }
  for (const row of videoRows) {
    uses.push({ label: row.title, where: "Videos", href: `/admin/videos` });
  }
  for (const row of testimonialRows) {
    uses.push({ label: row.name, where: "Testimonials", href: `/admin/testimonials` });
  }

  return uses;
}
