import "server-only";

import { unstable_cache } from "next/cache";
import { cache } from "react";
import { and, asc, eq } from "drizzle-orm";

import { TAGS } from "@/lib/cache";
import { db } from "@/lib/db";
import { media, navigationItems, socialLinks } from "@/lib/db/schema";
import type { MediaRef } from "@/lib/media/url";

export type NavItem = {
  id: number;
  labelEn: string;
  labelAr: string;
  href: string;
  isHighlighted: boolean;
  children: NavItem[];
};

const toTree = (
  rows: Array<{
    id: number;
    parentId: number | null;
    labelEn: string;
    labelAr: string;
    href: string;
    isHighlighted: boolean;
  }>,
): NavItem[] => {
  const byId = new Map<number, NavItem>();
  for (const row of rows) byId.set(row.id, { ...row, children: [] });
  const roots: NavItem[] = [];
  for (const row of rows) {
    const node = byId.get(row.id)!;
    const parent = row.parentId ? byId.get(row.parentId) : undefined;
    if (parent) parent.children.push(node);
    else roots.push(node);
  }
  return roots;
};

export const getMenu = unstable_cache(
  async (menu: "header" | "footer_services" | "footer_company" | "footer_legal") => {
    const rows = await db
      .select({
        id: navigationItems.id,
        parentId: navigationItems.parentId,
        labelEn: navigationItems.labelEn,
        labelAr: navigationItems.labelAr,
        href: navigationItems.href,
        isHighlighted: navigationItems.isHighlighted,
      })
      .from(navigationItems)
      .where(and(eq(navigationItems.isPublished, true), eq(navigationItems.menu, menu)))
      .orderBy(asc(navigationItems.sortOrder), asc(navigationItems.id));
    return toTree(rows);
  },
  ["navigation-menu"],
  { tags: [TAGS.navigation], revalidate: 3600 },
);

export const getSocialLinks = unstable_cache(
  async () =>
    db
      .select({ id: socialLinks.id, platform: socialLinks.platform, url: socialLinks.url })
      .from(socialLinks)
      .where(eq(socialLinks.isPublished, true))
      .orderBy(asc(socialLinks.sortOrder)),
  ["social-links"],
  { tags: [TAGS.social], revalidate: 3600 },
);

/**
 * The whole library in one request.
 *
 * A marketing site holds hundreds of images, not millions, and one lookup table
 * removes every N+1 join between a section and the picture it points at.
 * `unstable_cache` round-trips its result through JSON, so the cached half
 * returns the rows and the Map is rebuilt on this side of the boundary — a Map
 * stored in the cache comes back as a plain object.
 */
const getMediaRows = unstable_cache(
  async () =>
    db
      .select({
        id: media.id,
        filename: media.filename,
        width: media.width,
        height: media.height,
        altEn: media.altEn,
        altAr: media.altAr,
        title: media.title,
        derivatives: media.derivatives,
      })
      .from(media),
  ["media-rows"],
  { tags: [TAGS.media], revalidate: 3600 },
);

export const getMediaMap = cache(async (): Promise<Map<number, MediaRef>> => {
  const rows = await getMediaRows();
  return new Map(rows.map((r) => [r.id, { ...r, derivatives: r.derivatives ?? [] }]));
});
