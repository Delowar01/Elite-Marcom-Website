import { getDictionary } from "@/lib/i18n/dictionary";
import type { Locale } from "@/lib/i18n/config";
import { getCatalog, getFaqs, getPackages, getTestimonials, getVideos } from "@/lib/queries/catalog";
import { getMediaMap } from "@/lib/queries/site";
import type { RenderedSection } from "@/lib/queries/content";
import { getSettings, whatsappLink } from "@/lib/settings";

import { ContactDetailsBlock } from "./blocks/contact-details";
import type { BlockContext, BlockProps } from "./blocks/context";
import { EgyptFeatureBlock } from "./blocks/egypt-feature";
import { FaqBlock } from "./blocks/faq";
import { FeaturedServiceBlock } from "./blocks/featured-service";
import { FinalCtaBlock } from "./blocks/final-cta";
import { HeroBlock } from "./blocks/hero";
import { ImageTextBlock } from "./blocks/image-text";
import { OneDeskBlock } from "./blocks/one-desk";
import { PackagesGridBlock } from "./blocks/packages-grid";
import { PageHeroBlock } from "./blocks/page-hero";
import { ProcessBlock } from "./blocks/process";
import { QuickLinksBlock } from "./blocks/quick-links";
import { RichTextBlock } from "./blocks/rich-text";
import { ServiceGridBlock } from "./blocks/service-grid";
import { StatsBlock } from "./blocks/stats";
import { TestimonialsBlock } from "./blocks/testimonials";
import { TravelFeatureBlock } from "./blocks/travel-feature";
import { VideoShowcaseBlock } from "./blocks/video-showcase";
import { WhyUsBlock } from "./blocks/why-us";

type BlockComponent = (props: BlockProps) => React.ReactNode | Promise<React.ReactNode>;

/** Block type → renderer. A type with no entry here is skipped, not crashed on. */
const RENDERERS: Record<string, BlockComponent> = {
  hero: HeroBlock,
  "quick-links": QuickLinksBlock,
  "one-desk": OneDeskBlock,
  "service-grid": ServiceGridBlock,
  "featured-service": FeaturedServiceBlock,
  "travel-feature": TravelFeatureBlock,
  "egypt-feature": EgyptFeatureBlock,
  "packages-grid": PackagesGridBlock,
  "video-showcase": VideoShowcaseBlock,
  process: ProcessBlock,
  "why-us": WhyUsBlock,
  stats: StatsBlock,
  testimonials: TestimonialsBlock,
  faq: FaqBlock,
  "final-cta": FinalCtaBlock,
  "page-hero": PageHeroBlock,
  "rich-text": RichTextBlock,
  "image-text": ImageTextBlock,
  "contact-details": ContactDetailsBlock,
};

/**
 * Builds the shared context once, then renders the sections in order. Each
 * loader is individually cached and tagged, so a page with twelve sections
 * still costs at most one round trip per dataset — and usually none.
 */
export async function buildBlockContext(locale: Locale): Promise<BlockContext> {
  const [settings, media, catalog, packages, videos, testimonials, faqs] = await Promise.all([
    getSettings(),
    getMediaMap(),
    getCatalog(),
    getPackages(),
    getVideos(),
    getTestimonials(),
    getFaqs(),
  ]);

  return {
    locale,
    dict: getDictionary(locale),
    settings,
    media,
    catalog,
    packages,
    videos,
    testimonials,
    faqs,
    whatsappHref: whatsappLink(settings, locale),
  };
}

export async function SectionRenderer({
  sections,
  locale,
  ctx,
}: {
  sections: RenderedSection[];
  locale: Locale;
  ctx?: BlockContext;
}) {
  const context = ctx ?? (await buildBlockContext(locale));

  return (
    <>
      {sections.map((section, index) => {
        const Renderer = RENDERERS[section.blockType];
        if (!Renderer) return null;
        return (
          <div key={section.id} data-section={section.blockType} data-draft={section.isDraft || undefined}>
            <Renderer values={section.values} ctx={context} index={index} />
          </div>
        );
      })}
    </>
  );
}
