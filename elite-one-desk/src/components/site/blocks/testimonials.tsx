import { SectionHeading } from "@/components/site/section-heading";
import { TestimonialCarousel, type TestimonialEntry } from "@/components/site/testimonial-carousel";
import { num, text } from "@/lib/cms/values";
import { pick } from "@/lib/i18n/config";
import { mediaSrc, mediaSrcSet } from "@/lib/media/url";
import type { BlockProps } from "./context";

export function TestimonialsBlock({ values, ctx }: BlockProps) {
  const { locale, dict, settings } = ctx;
  if (!settings.features.showTestimonials) return null;

  const limit = num(values, "limit", 8);
  const rows = ctx.testimonials.slice(0, limit > 0 ? limit : undefined);
  if (!rows.length) return null;

  const entries: TestimonialEntry[] = rows.map((row) => {
    const image = row.imageId ? ctx.media.get(row.imageId) : null;
    return {
      id: row.id,
      name: row.name,
      company: row.company,
      country: row.country,
      quote: pick(locale, row.quoteEn, row.quoteAr),
      rating: row.rating,
      image: image
        ? { src: mediaSrc(image, image.derivatives?.[0] ?? undefined), srcSet: mediaSrcSet(image) }
        : null,
    };
  });

  return (
    <section className="section">
      <div className="shell shell-wide">
        <SectionHeading
          eyebrow={text(values, "eyebrow", locale) || dict.sections.testimonialsEyebrow}
          title={text(values, "title", locale)}
        />
        <div className="mt-9">
          <TestimonialCarousel
            entries={entries}
            labels={{
              previous: dict.a11y.previous,
              next: dict.a11y.next,
              slideOf: dict.a11y.slideOf,
            }}
          />
        </div>
      </div>
    </section>
  );
}
