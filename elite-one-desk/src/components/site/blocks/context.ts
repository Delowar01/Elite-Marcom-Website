import type { MediaRef } from "@/lib/media/url";
import type {
  CategoryRow,
  FaqRow,
  PackageRow,
  ServiceRow,
  SubcategoryRow,
  TestimonialRow,
  VideoRow,
} from "@/lib/queries/catalog";
import type { Locale } from "@/lib/i18n/config";
import type { Dictionary } from "@/lib/i18n/dictionary";
import type { SiteSettings } from "@/lib/settings";

/**
 * Everything a section might need, fetched once per page render and handed
 * down. A block never opens its own connection: that is what turns a twelve
 * section homepage into forty queries.
 */
export type BlockContext = {
  locale: Locale;
  dict: Dictionary;
  settings: SiteSettings;
  media: Map<number, MediaRef>;
  catalog: {
    categories: CategoryRow[];
    services: ServiceRow[];
    subcategories: SubcategoryRow[];
    byCategory: Map<number, ServiceRow[]>;
  };
  packages: PackageRow[];
  videos: VideoRow[];
  testimonials: TestimonialRow[];
  faqs: FaqRow[];
  whatsappHref: string | null;
};

export type BlockProps = {
  values: Record<string, unknown>;
  ctx: BlockContext;
  /** Position on the page — used to give the first section hero treatment. */
  index: number;
};
