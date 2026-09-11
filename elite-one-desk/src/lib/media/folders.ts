/** Library folders. A fixed list keeps the picker navigable as it grows. */
export const MEDIA_FOLDERS = [
  "general",
  "categories",
  "services",
  "features",
  "packages",
  "people",
  "brand",
] as const;

export type MediaFolder = (typeof MEDIA_FOLDERS)[number];

export const isMediaFolder = (value: string): value is MediaFolder =>
  (MEDIA_FOLDERS as readonly string[]).includes(value);
