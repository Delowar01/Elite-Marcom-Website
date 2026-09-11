import { revalidateTag } from "next/cache";

/**
 * Pages render per request (the CSP nonce makes them dynamic), so the caching
 * lives one level down: the data loaders are cached and tagged, and publishing
 * drops the tag. The result behaves like a static site that updates the instant
 * an editor presses Publish, with no build step in between.
 */
export const TAGS = {
  settings: "settings",
  navigation: "navigation",
  social: "social",
  catalog: "catalog",
  pages: "pages",
  media: "media",
  packages: "packages",
  videos: "videos",
  testimonials: "testimonials",
  faqs: "faqs",
  seo: "seo",
} as const;

export type CacheTag = (typeof TAGS)[keyof typeof TAGS];

export function revalidate(...tags: CacheTag[]): void {
  for (const tag of tags) revalidateTag(tag);
}

/** Anything that can change what a public page shows. */
export function revalidateEverything(): void {
  revalidate(...(Object.values(TAGS) as CacheTag[]));
}
